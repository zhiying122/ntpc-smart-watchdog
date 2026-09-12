"""
白盒混合風險評分單元測試（Risk_Scorer, R10.1–R10.3, R10.6, R5.2）
===================================================================
驗證 src/risk_score.py 的 `score(entity, weights, confidence) -> RiskBreakdown`：
  - 回傳共用型別 RiskBreakdown，total 落於 0–100。
  - 各分項加權貢獻明細 contributions；可加性不變式
    round(sum(contributions.values()), 1) == total（R5.2, R10.3）。
  - 四級分級 低／中／高／極高（R10.2）。
  - 保留既有加權 financial 0.50 + penalty 0.34 + eval 0.16（R10.6）。

對應 Task 6.1「實作分項貢獻明細與可加性」。
屬性測試（Property 17）另見 Task 6.3。
"""
import pytest

from src.models import RiskBreakdown
from src.risk_score import (
    WEIGHTS,
    risk_level_four,
    score,
    score_eval,
    score_financial,
    score_penalty,
)


def _entity(**overrides):
    """建立一個帶已算好分項分的評分輸入 dict。"""
    base = {
        "score_financial": 80.0,
        "score_penalty": 50.0,
        "score_eval": 20.0,
    }
    base.update(overrides)
    return base


def test_returns_risk_breakdown_type():
    """回傳型別為共用型別 RiskBreakdown。"""
    rb = score(_entity())
    assert isinstance(rb, RiskBreakdown)


def test_default_weights_preserved():
    """預設沿用既有加權 financial 0.50 + penalty 0.34 + eval 0.16（R10.6）。"""
    assert WEIGHTS == {"financial": 0.50, "penalty": 0.34, "eval": 0.16}
    rb = score(_entity())
    assert rb.weights == {"financial": 0.50, "penalty": 0.34, "eval": 0.16}


def test_contributions_are_weighted_scores():
    """各分項貢獻 = 權重 × 分項分數（R10.3）。"""
    rb = score(_entity(score_financial=80.0, score_penalty=50.0, score_eval=20.0))
    assert rb.contributions["financial"] == pytest.approx(0.50 * 80.0)
    assert rb.contributions["penalty"] == pytest.approx(0.34 * 50.0)
    assert rb.contributions["eval"] == pytest.approx(0.16 * 20.0)


def test_additivity_invariant():
    """可加性不變式：round(sum(contributions.values()), 1) == total（R5.2, R10.3）。"""
    rb = score(_entity(score_financial=73.3, score_penalty=50.0, score_eval=30.0))
    assert round(sum(rb.contributions.values()), 1) == rb.total


def test_total_within_range():
    """total 落於 0–100（含端點）。"""
    low = score(_entity(score_financial=0.0, score_penalty=0.0, score_eval=0.0))
    high = score(_entity(score_financial=100.0, score_penalty=100.0, score_eval=100.0))
    assert low.total == 0.0
    assert high.total == 100.0
    assert 0.0 <= low.total <= 100.0
    assert 0.0 <= high.total <= 100.0


def test_all_max_scores_total_100():
    """全滿分 → 總分 100（權重合計為 1）。"""
    rb = score(_entity(score_financial=100.0, score_penalty=100.0, score_eval=100.0))
    assert rb.total == 100.0


def test_level_four_levels():
    """四級絕對分級門檻（R10.2）：<40 低、40–69 中、70–89 高、>=90 極高。"""
    assert risk_level_four(0) == "低"
    assert risk_level_four(39.9) == "低"
    assert risk_level_four(40) == "中"
    assert risk_level_four(69.9) == "中"
    assert risk_level_four(70) == "高"
    assert risk_level_four(89.9) == "高"
    assert risk_level_four(90) == "極高"
    assert risk_level_four(100) == "極高"


def test_level_reported_matches_total():
    """回傳的 level 與 total 的四級門檻一致。"""
    rb = score(_entity(score_financial=100.0, score_penalty=100.0, score_eval=100.0))
    assert rb.level == "極高"
    rb_low = score(_entity(score_financial=0.0, score_penalty=0.0, score_eval=0.0))
    assert rb_low.level == "低"


def test_custom_weights_used():
    """自訂權重（純財務）僅計入定義的分項，且維持可加性。"""
    rb = score(_entity(score_financial=80.0), weights={"financial": 1.0})
    assert set(rb.contributions.keys()) == {"financial"}
    assert rb.total == 80.0
    assert round(sum(rb.contributions.values()), 1) == rb.total


def test_confidence_recorded():
    """confidence 寫入 data_confidence（R18.3）；None → 100 滿分。"""
    assert score(_entity(), confidence=42.5).data_confidence == 42.5
    assert score(_entity(), confidence=None).data_confidence == 100.0


def test_confidence_from_dataconfidence_object():
    """支援帶 .score 的 DataConfidence 物件。"""
    from src.models import DataConfidence
    dc = DataConfidence(entity_id="p", score=67.0)
    assert score(_entity(), confidence=dc).data_confidence == 67.0


def test_not_illegality_notice_present():
    """帶非空「風險不等於違法」聲明（R10.4 預設）。"""
    rb = score(_entity())
    assert rb.not_illegality_notice.strip() != ""


def test_computes_from_source_columns_when_scores_absent():
    """未提供 score_* 時，由來源欄位即時計算分項（與既有函式一致）。"""
    entity = {"penalty_count": 2, "eval_grade": "待改進"}
    rb = score(entity)
    assert rb.contributions["penalty"] == pytest.approx(WEIGHTS["penalty"] * score_penalty(2))
    assert rb.contributions["eval"] == pytest.approx(WEIGHTS["eval"] * score_eval("待改進"))
    # financial 缺來源 → score_financial 對缺值給中性 0
    assert rb.contributions["financial"] == pytest.approx(WEIGHTS["financial"] * score_financial(entity))


# ---------------------------------------------------------------------------
# Task 6.2：缺資料中性處理與責任 AI 標示（R10.4, R10.5, R18.2, R18.3, R19.4）
# ---------------------------------------------------------------------------
from src.risk_score import NEUTRAL_SUBSCORES


def test_missing_subscore_uses_neutral_value():
    """缺乏真實資料的分項以中性值代入（R10.5）。

    完全無 score_* 亦無來源欄位 → 各分項落在中性值：
      financial=0、penalty=0、eval=30。
    """
    rb = score({})  # 無任何來源
    assert rb.contributions["financial"] == pytest.approx(
        WEIGHTS["financial"] * NEUTRAL_SUBSCORES["financial"])
    assert rb.contributions["penalty"] == pytest.approx(
        WEIGHTS["penalty"] * NEUTRAL_SUBSCORES["penalty"])
    assert rb.contributions["eval"] == pytest.approx(
        WEIGHTS["eval"] * NEUTRAL_SUBSCORES["eval"])


def test_neutral_does_not_amplify_vs_max_risk():
    """中性值不放大風險：缺資料 total ≤ 該分項採最大風險值之 total（Property 30 上界）。"""
    for subkey in ("financial", "penalty", "eval"):
        entity_missing = _entity()
        entity_missing[f"score_{subkey}"] = float("nan")  # 該分項缺資料
        entity_max = _entity()
        entity_max[f"score_{subkey}"] = 100.0             # 該分項採最大風險
        rb_missing = score(entity_missing)
        rb_max = score(entity_max)
        assert rb_missing.total <= rb_max.total


def test_low_confidence_does_not_raise_total_or_level():
    """低可信度不得單獨推高風險：total 與 level 不隨 confidence 改變（R18.2）。"""
    entity = _entity()
    rb_high_conf = score(entity, confidence=100.0)
    rb_low_conf = score(entity, confidence=1.0)
    assert rb_low_conf.total == rb_high_conf.total
    assert rb_low_conf.level == rb_high_conf.level


def test_low_confidence_recorded_but_isolated():
    """低可信度僅記錄於 data_confidence（R18.3），不汙染分項貢獻。"""
    entity = _entity()
    rb = score(entity, confidence=5.0)
    assert rb.data_confidence == 5.0
    # 貢獻仍等於權重×分項分，與 confidence 無關
    assert rb.contributions["financial"] == pytest.approx(WEIGHTS["financial"] * 80.0)


def test_not_illegality_notice_non_empty_always():
    """每個 RiskBreakdown 皆附非空『風險不等於違法』聲明（R10.4, R19.4）。"""
    for entity in ({}, _entity(), _entity(score_financial=100.0)):
        rb = score(entity)
        assert rb.not_illegality_notice.strip() != ""
        assert "違法" in rb.not_illegality_notice


def test_data_confidence_carried_on_breakdown():
    """每個 RiskBreakdown 帶 data_confidence（R18.3）；未提供 → 100。"""
    assert score(_entity()).data_confidence == 100.0
    assert score(_entity(), confidence=73.0).data_confidence == 73.0


# ==========================================================================
# 雙評分檔（R26：財務鑑識園 vs 行為監測園）
# ==========================================================================
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

from src.risk_score import (  # noqa: E402
    PROFILE_BEHAVIORAL,
    PROFILE_FORENSIC,
    PROFILE_WEIGHTS,
    resolve_scoring_profile,
)


def test_resolve_profile_forensic_when_financials_present():
    """具獨立財務決算 → forensic（R26.1）。"""
    assert resolve_scoring_profile({"income_actual": 1000, "expense_actual": 900}) == PROFILE_FORENSIC
    assert resolve_scoring_profile({"score_financial": 44.8}) == PROFILE_FORENSIC


def test_resolve_profile_behavioral_when_no_financials():
    """無獨立財報（如國小附幼）→ behavioral（R26.1）。"""
    assert resolve_scoring_profile({"penalty_count": 2, "eval_grade": "乙"}) == PROFILE_BEHAVIORAL
    assert resolve_scoring_profile({}) == PROFILE_BEHAVIORAL


def test_explicit_profile_override_respected():
    """entity 顯式 scoring_profile 覆寫自動判定（R26.1）。"""
    assert resolve_scoring_profile({"income_actual": 1000, "scoring_profile": "behavioral"}) == PROFILE_BEHAVIORAL


def test_behavioral_excludes_financial_subscore():
    """behavioral 檔財務分項不計入貢獻（R26.3）。"""
    rb = score({"score_penalty": 60.0, "score_eval": 40.0}, profile=PROFILE_BEHAVIORAL)
    assert rb.scoring_profile == PROFILE_BEHAVIORAL
    assert "financial" not in rb.contributions
    assert rb.profile_notice  # 揭露訊息非空（R26.6）


def test_behavioral_all_missing_flags_insufficient():
    """behavioral 三分項皆無真實資料 → 資料不足揭露（R26.8）。"""
    rb = score({}, profile=PROFILE_BEHAVIORAL)
    assert "不足" in rb.profile_notice


def test_forensic_profile_weights_sum_to_one():
    """forensic 四分項權重合計 1.0（R26.2）。"""
    w = PROFILE_WEIGHTS[PROFILE_FORENSIC]
    assert round(sum(v for v in w.values() if v is not None), 4) == 1.0


def test_behavioral_profile_weights_sum_to_one():
    """behavioral 三分項權重合計 1.0（R26.3）。"""
    w = {k: v for k, v in PROFILE_WEIGHTS[PROFILE_BEHAVIORAL].items() if v is not None}
    assert round(sum(w.values()), 4) == 1.0
    assert PROFILE_WEIGHTS[PROFILE_BEHAVIORAL]["financial"] is None


# Feature: smart-watchdog-platform, Property 49: 雙評分檔權重、範圍與確定性
@settings(max_examples=100)
@given(
    fin=st.floats(min_value=0, max_value=100),
    pen=st.floats(min_value=0, max_value=100),
    ev=st.floats(min_value=0, max_value=100),
    sen=st.floats(min_value=0, max_value=100),
    prof=st.sampled_from([PROFILE_FORENSIC, PROFILE_BEHAVIORAL]),
)
def test_property_49_dual_profile_weights_range_determinism(fin, pen, ev, sen, prof):
    """Property 49：評分檔為 forensic/behavioral 二者之一且確定性；
    權重合計 1.0；總分 0–100；輿情貢獻 ≤ 15。"""
    entity = {
        "score_financial": fin, "score_penalty": pen,
        "score_eval": ev, "score_sentiment": sen,
    }
    rb1 = score(entity, profile=prof)
    rb2 = score(entity, profile=prof)

    # 評分檔二選一且確定性
    assert rb1.scoring_profile in (PROFILE_FORENSIC, PROFILE_BEHAVIORAL)
    assert rb1.scoring_profile == rb2.scoring_profile == prof
    assert rb1.total == rb2.total

    # 權重合計 1.0
    assert round(sum(rb1.weights.values()), 4) == 1.0

    # behavioral 檔不含財務分項
    if prof == PROFILE_BEHAVIORAL:
        assert "financial" not in rb1.contributions

    # 總分 0–100
    assert 0.0 <= rb1.total <= 100.0

    # 輿情分項貢獻 ≤ 15（R10.8, R26.7）
    assert rb1.contributions.get("sentiment", 0.0) <= 15.0 + 1e-9


# ==========================================================================
# 破窗效應接入裁罰分項（R25.7）
# ==========================================================================
import json as _json  # noqa: E402

from src.risk_score import broken_window_penalty_score, score_penalty  # noqa: E402


def test_penalty_falls_back_when_no_records():
    """無逐筆明細 → score_penalty 退回既有嚴重度計分（向後相容，R25.7）。"""
    row = {"penalty_count": 2, "penalty_reason": "超收幼生與收費違規"}
    # 未帶 penalty_records → 走 penalty_severity_score
    assert score_penalty(row) == score_penalty(
        {"penalty_count": 2, "penalty_reason": "超收幼生與收費違規", "penalty_records": ""})


def test_penalty_uses_broken_window_when_records_present():
    """有逐筆明細（含日期）→ score_penalty 走破窗效應（R25.7）。"""
    recs = _json.dumps([
        {"date": "2024-02-15", "reason": "資料未依規公開"},
        {"date": "2026-05-08", "reason": "照顧安全疑慮與設施缺失"},
    ], ensure_ascii=False)
    row = {"penalty_count": 2, "penalty_reason": "多筆", "penalty_records": recs}
    bw = broken_window_penalty_score(recs)
    assert bw is not None
    assert score_penalty(row) == bw


def test_broken_window_penalty_none_when_empty():
    """無明細 → broken_window_penalty_score 回 None（讓呼叫端退回）。"""
    assert broken_window_penalty_score("") is None
    assert broken_window_penalty_score(None) is None
