"""
稽查員調查工作台組裝邏輯單元測試（Inspector Workspace assembly, R5）
=====================================================================
驗證 app/lib/inspector.py 的呈現無關組裝邏輯：
  - R5.1/R5.2：總風險分與雷達圖四分項，前三分項加權貢獻加總 == 總分。
  - R5.3：風險時間軸涵蓋所有可取得年度且由舊到新排序，變化點附觸發說明。
  - R5.4：財務/收費/營運/法規/NLP 五類分析，含結論與佐證；無資料類別標示。
  - R5.5：同儕比較（相同機構類型）各分項統計量；樣本不足標示。
  - R5.6：異常偵測三類（點/情境/集體）旗標、分數與觸發來源指標。
  - R5.7：證據鏈完整可追溯（結論 → 特徵 → 原始值 → 官方來源）。
  - R5.8：前 5 特徵歸因含貢獻方向（提高/降低），至多 5 筆。
  - R5.10：AI Copilot 以資料為依據回答並附來源，資料不足不杜撰。

本模組位於 app/lib/（非 src 套件），且 app/ 無 __init__.py，故以檔案路徑載入，
與既有 tests/test_modes.py 的載入慣例一致。
"""
import importlib.util
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_INSPECTOR_PATH = os.path.join(_ROOT, "app", "lib", "inspector.py")

_spec = importlib.util.spec_from_file_location("app_lib_inspector", _INSPECTOR_PATH)
inspector = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = inspector
_spec.loader.exec_module(inspector)


# --------------------------------------------------------------------------
# 測試夾具：一間高風險機構與一組同儕母體
# --------------------------------------------------------------------------
def _entity(**overrides):
    base = {
        "park_id": "13616",
        "park_name": "測試幼兒園",
        "park_type": "公校",
        "district": "林口區",
        "year": 114,
        "income_actual": 21947493.0,
        "expense_actual": 23545162.0,
        "tuition_actual": 2509662.0,
        "surplus": -1597669.0,
        "expense_income_ratio": 1.0728,
        "benford_mad": 0.03286,
        "beneish_score": 28.1,
        "iforest_score": 26.1,
        "expense_yoy_pct": 1.07,
        "penalty_count": 2,
        "eval_grade": "乙",
        "score_financial": 38.0,
        "score_penalty": 80.0,
        "score_eval": 40.0,
        "risk_total": 52.6,
        "risk_level": "中",
    }
    base.update(overrides)
    return base


def _population(n=6):
    pop = []
    for i in range(n):
        pop.append(_entity(
            park_id=f"1360{i}",
            park_name=f"同儕園{i}",
            risk_total=30.0 + i * 5,
            score_financial=20.0 + i * 3,
            score_penalty=0.0 if i % 2 else 50.0,
            score_eval=30.0,
            penalty_count=i % 3,
        ))
    return pop


# --------------------------------------------------------------------------
# R5.1 / R5.2：雷達圖分項加權總和 == 總分
# --------------------------------------------------------------------------
def test_radar_breakdown_contributions_sum_equals_total():
    radar = inspector.radar_breakdown(_entity())
    # 四分項齊備（財務/裁罰/評鑑/輿情）。
    assert [d.key for d in radar.dimensions] == ["financial", "penalty", "eval", "sentiment"]
    # 前三分項（計分分項）貢獻加總四捨五入一位小數 == 總分（R5.2 不變式）。
    total_contrib = round(sum(d.contribution for d in radar.dimensions), 1)
    assert total_contrib == radar.total
    assert 0.0 <= radar.total <= 100.0
    assert radar.level in ("低", "中", "高", "極高")
    # 責任 AI 聲明非空（R10.4/R19.4）。
    assert radar.not_illegality_notice


def test_radar_sentiment_dimension_weighted():
    """輿情已接入真實公開新聞爬蟲 → 正式計入雷達圖（forensic 檔權重 0.10）。

    _entity() 未帶 score_sentiment/neg_ratio → 走缺值中性（score_sentiment=20），
    貢獻 = 0.10 × 20 = 2.0（缺值中性不放大風險，責任 AI）。"""
    radar = inspector.radar_breakdown(_entity())
    sentiment = [d for d in radar.dimensions if d.key == "sentiment"][0]
    assert sentiment.weight == pytest.approx(0.10)
    assert sentiment.contribution == pytest.approx(2.0)


# --------------------------------------------------------------------------
# R5.3：時間軸涵蓋所有年度、由舊到新；變化點附觸發說明
# --------------------------------------------------------------------------
def test_timeline_sorted_old_to_new_and_covers_all_years():
    history = [
        _entity(year=114, risk_total=52.6),
        _entity(year=112, risk_total=20.0),
        _entity(year=113, risk_total=25.0),
    ]
    view = inspector.risk_timeline(history)
    assert view.years == [112, 113, 114]  # 由舊到新
    assert view.values == [20.0, 25.0, 52.6]


def test_timeline_change_points_have_nonempty_trigger():
    history = [
        _entity(year=110, risk_total=10.0),
        _entity(year=111, risk_total=11.0),
        _entity(year=112, risk_total=10.5),
        _entity(year=113, risk_total=90.0),  # 明顯突變
    ]
    view = inspector.risk_timeline(history)
    assert len(view.change_points) >= 1
    for cp in view.change_points:
        assert cp.trigger  # 非空觸發說明（R12.4）


# --------------------------------------------------------------------------
# R5.4：五類分析
# --------------------------------------------------------------------------
def test_five_category_analysis_covers_all_and_has_sources():
    cats = inspector.five_category_analysis(_entity())
    assert [c.category for c in cats] == ["財務", "收費", "營運", "法規", "NLP"]
    for c in cats:
        assert c.conclusion  # 每類皆有結論（無資料時為「無資料」）
        assert c.source is not None and c.source.authority  # R5.11 來源


def test_five_category_missing_data_flags_no_data():
    sparse = {"park_name": "空資料園", "park_type": "公校",
              "risk_total": 0.0, "risk_level": "低"}
    cats = inspector.five_category_analysis(sparse)
    finance = [c for c in cats if c.category == "財務"][0]
    assert finance.has_data is False
    assert finance.conclusion == "無資料"


# --------------------------------------------------------------------------
# R5.5：同儕比較
# --------------------------------------------------------------------------
def test_peer_comparison_returns_all_metrics():
    entity = _entity()
    pop = _population(6) + [entity]
    rows = inspector.peer_comparison(entity, pop)
    labels = [r.label for r in rows]
    assert "總風險分" in labels and "財務異常分" in labels
    for r in rows:
        assert r.position  # 相對位置標籤非空（R13.3）


def test_peer_comparison_insufficient_sample_flagged():
    entity = _entity()
    rows = inspector.peer_comparison(entity, [entity])  # 群組僅 1 → 樣本不足
    assert all(r.insufficient for r in rows)


# --------------------------------------------------------------------------
# R5.6：異常偵測
# --------------------------------------------------------------------------
def test_anomaly_summary_three_types_present():
    entity = _entity(risk_total=95.0)
    pop = _population(8) + [entity]
    summary = inspector.anomaly_summary(entity, pop)
    types = [it.anomaly_type for it in summary.items]
    assert types == ["點異常", "情境異常", "集體異常"]
    assert summary.confidence_label in ("high_confidence", "to_confirm", "none")
    assert summary.hit_count >= 0


def test_anomaly_summary_exposes_seven_method_details():
    """七方法明細應完整帶出（method/score/threshold/flag/applicable + 適用性）。"""
    entity = _entity(risk_total=95.0)
    pop = _population(8) + [entity]
    summary = inspector.anomaly_summary(entity, pop)
    # 七種方法都在
    assert len(summary.methods) == 7
    names = {m.method for m in summary.methods}
    assert names == {"isolation_forest", "lof", "zscore", "robust",
                     "timeseries", "changepoint", "clustering"}
    for m in summary.methods:
        assert m.label  # 中文顯示名非空
        assert m.anomaly_type in ("點異常", "情境異常", "集體異常")
        assert 0.0 <= m.score <= 100.0
        assert m.threshold >= 0.0
        assert isinstance(m.flag, bool)
        assert isinstance(m.applicable, bool)
        # 適用的方法應附非空假設/限制（method_applicability 說明）
        if m.applicable:
            assert m.assumption
            assert m.limitation
        # 不變式：適用時 flag == (score >= threshold)
        if m.applicable:
            assert m.flag == (m.score >= m.threshold)


def test_peer_comparison_exposes_zscore_and_robust_deviation():
    """同儕比較應帶出 z-score 與穩健偏差（peer_stats 已算、過去未帶出）。"""
    entity = _entity(risk_total=95.0)
    pop = _population(8) + [entity]
    rows = inspector.peer_comparison(entity, pop)
    assert rows
    for r in rows:
        # 樣本足夠時 z-score/穩健偏差應為數值（非 None）
        if not r.insufficient and r.value is not None:
            assert isinstance(r.z_score, float)
            assert isinstance(r.robust_deviation, float)


# --------------------------------------------------------------------------
# R5.7：證據鏈可追溯
# --------------------------------------------------------------------------
def test_evidence_chain_fully_traceable():
    chain = inspector.evidence_chain(_entity())
    assert chain.conclusion
    assert chain.links  # 至少一條環
    assert chain.is_fully_traceable()  # 完整可追溯（R11.1–R11.4）
    for lk in chain.links:
        assert lk.feature and lk.raw_value is not None
        assert lk.source is not None and lk.source.authority


# --------------------------------------------------------------------------
# R5.8：前 5 特徵歸因含方向
# --------------------------------------------------------------------------
def test_top_feature_attributions_at_most_5_with_direction():
    attrs = inspector.top_feature_attributions(_entity(), n=5)
    assert 0 < len(attrs) <= 5
    # 依 |貢獻| 由大到小排序。
    mags = [abs(a.contribution) for a in attrs]
    assert mags == sorted(mags, reverse=True)
    for a in attrs:
        assert a.direction in ("提高", "降低")


def test_attribution_direction_matches_sign():
    # 收支比 > 中性基準 1.0 → 提高風險；評鑑分 < 中性基準 30 → 降低風險。
    entity = _entity(expense_income_ratio=1.5, score_eval=10.0,
                     score_financial=0.0, score_penalty=0.0,
                     benford_mad=0.006, beneish_score=0.0,
                     iforest_score=0.0, expense_yoy_pct=0.0)
    attrs = {a.feature: a for a in inspector.top_feature_attributions(entity, n=8)}
    assert attrs["expense_income_ratio"].direction == "提高"
    assert attrs["score_eval"].direction == "降低"


# --------------------------------------------------------------------------
# R5.10：Copilot 入口
# --------------------------------------------------------------------------
def test_copilot_answer_grounded_with_sources():
    ans = inspector.copilot_answer("這間機構的財務風險如何？", _entity())
    assert ans.text
    assert ans.grounded is True
    assert ans.sources  # 關鍵陳述附來源（R15.2）
    assert ans.not_illegality_notice


def test_copilot_answer_insufficient_data_not_fabricated():
    sparse = {"park_name": "空資料園"}
    ans = inspector.copilot_answer("這間機構的財務風險如何？", sparse)
    assert ans.grounded is False
    assert ans.data_sufficient is False
    assert ans.text  # 明確告知資料不足而非空白（R15.4）


# ==========================================================================
# R5.9：調查檢核清單（可勾選、可標記已完成/未完成）
# ==========================================================================
def test_default_checklist_all_unchecked_and_unique_keys():
    items = inspector.default_checklist()
    assert len(items) >= 3
    assert all(it.done is False for it in items)  # 預設全未完成
    keys = [it.key for it in items]
    assert len(keys) == len(set(keys))  # key 唯一
    assert all(it.label for it in items)  # 每項有顯示文字（R5.9）


def test_default_checklist_returns_fresh_objects():
    a = inspector.default_checklist()
    a[0].done = True
    b = inspector.default_checklist()
    assert b[0].done is False  # 不共享狀態，避免污染


def test_apply_checklist_state_toggles_and_is_pure():
    items = inspector.default_checklist()
    first = items[0].key
    updated = inspector.apply_checklist_state(items, {first: True})
    assert updated[0].done is True          # 依外部狀態勾選
    assert items[0].done is False           # 不就地修改輸入（純函式）
    # 未在 state 中的項目維持原值。
    assert updated[1].done == items[1].done


def test_checklist_progress_counts():
    items = inspector.default_checklist()
    done0, total = inspector.checklist_progress(items)
    assert done0 == 0 and total == len(items)
    items[0].done = True
    items[1].done = True
    done2, total2 = inspector.checklist_progress(items)
    assert done2 == 2 and total2 == total


# ==========================================================================
# R20.1：HITL 回饋（四種標籤，關聯機構與判定）
# ==========================================================================
def test_feedback_labels_are_the_four_allowed():
    labels = inspector.feedback_labels()
    assert labels == ["確為異常", "誤報", "資料問題", "需進一步稽查"]


def test_submit_hitl_feedback_valid_label_records():
    from src.audit import AuditLog, FeedbackStore
    store = FeedbackStore(audit_log=AuditLog())
    res = inspector.submit_hitl_feedback("13616", "verdict-1", "確為異常", store=store)
    assert res.ok is True
    assert res.feedback is not None
    assert res.feedback.entity_id == "13616"
    assert res.feedback.label == "確為異常"
    assert len(store) == 1
    assert res.message


def test_submit_hitl_feedback_invalid_label_rejected():
    from src.audit import AuditLog, FeedbackStore
    store = FeedbackStore(audit_log=AuditLog())
    res = inspector.submit_hitl_feedback("13616", "verdict-1", "亂填", store=store)
    assert res.ok is False
    assert res.feedback is None
    assert len(store) == 0          # 不寫入無效回饋
    assert res.message              # 有錯誤訊息


def test_submit_hitl_feedback_requires_entity_and_verdict():
    from src.audit import AuditLog, FeedbackStore
    store = FeedbackStore(audit_log=AuditLog())
    r1 = inspector.submit_hitl_feedback("", "verdict-1", "誤報", store=store)
    r2 = inspector.submit_hitl_feedback("13616", "", "誤報", store=store)
    assert r1.ok is False and r2.ok is False
    assert len(store) == 0


# ==========================================================================
# R5.13：載入失敗顯示訊息 + 重新載入不覆寫既有
# ==========================================================================
def test_load_workspace_success():
    row = _entity()
    res = inspector.load_workspace_data(lambda: row)
    assert res.ok is True
    assert res.stale is False
    assert res.row["park_name"] == row["park_name"]


def test_load_failure_preserves_existing_without_overwrite():
    existing = _entity(park_name="既有園")

    def boom():
        raise RuntimeError("讀檔錯誤")

    res = inspector.load_workspace_data(boom, existing=existing)
    assert res.ok is False
    assert res.stale is True                       # 沿用既有
    assert res.row["park_name"] == "既有園"        # 未覆寫既有
    assert "載入失敗" in res.message               # 顯示載入失敗訊息


def test_load_failure_without_existing_returns_none():
    def boom():
        raise RuntimeError("x")

    res = inspector.load_workspace_data(boom, existing=None)
    assert res.ok is False
    assert res.row is None
    assert res.stale is False
    assert res.message


def test_load_empty_result_treated_as_failure():
    res = inspector.load_workspace_data(lambda: None, existing=_entity())
    assert res.ok is False
    assert res.stale is True


# ==========================================================================
# R5.14：來源連結無法開啟顯示提示，其餘可操作
# ==========================================================================
def test_source_link_openable_when_valid_http():
    from src.models import SourceRef
    src = SourceRef(dataset="收退費", authority="教育部", url="https://example.gov.tw/x")
    link = inspector.source_link(src)
    assert link.accessible is True
    assert link.url == "https://example.gov.tw/x"
    assert link.notice == ""


def test_source_link_missing_url_flags_inaccessible():
    from src.models import SourceRef
    src = SourceRef(dataset="收退費", authority="教育部", url=None)
    link = inspector.source_link(src)
    assert link.accessible is False
    assert link.notice  # 顯示無法存取提示


def test_source_link_unreachable_override_flags_inaccessible():
    from src.models import SourceRef
    src = SourceRef(dataset="收退費", authority="教育部", url="https://example.gov.tw/x")
    link = inspector.source_link(src, reachable=False)
    assert link.accessible is False
    assert link.notice


def test_category_source_links_one_broken_does_not_break_others():
    cats = inspector.five_category_analysis(_entity())
    # 指定「財務」類來源無法連通，其餘不受影響。
    reach = {"財務": False}
    links = inspector.category_source_links(cats, reachability=reach)
    assert len(links) == len(cats)
    finance = links[0]
    assert finance.accessible is False and finance.notice
    # 其餘類別仍各自回傳連結狀態（維持可操作，不整批失效）。
    assert all(isinstance(lk.label, str) and lk.label for lk in links)
