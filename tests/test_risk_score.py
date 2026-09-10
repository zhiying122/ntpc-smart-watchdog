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
