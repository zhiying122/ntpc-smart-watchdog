"""
舞弊三角理論框架單元測試（Fraud Triangle, Cressey 1953）
================================================
驗證 src.fraud_triangle.assess 的三構面對映、成形程度判定、敘事與確定性，
以及其為「白盒對映層」的性質（僅讀既有分項、缺值中性、值域 0–100）。

三構面：壓力(Pressure)、機會(Opportunity)、合理化(Rationalization)。
"""
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.fraud_triangle import VERTEX_THRESHOLD, assess
from src.models import FraudTriangleFactor, FraudTriangleResult


# --------------------------------------------------------------------------
# 三構面對映：各構面由對應分項驅動
# --------------------------------------------------------------------------
def test_pressure_driven_by_altman_distress():
    """Altman 困境分高 → 壓力構面達門檻。"""
    res = assess({"altman_score": 100.0})
    assert res.pressure.score >= VERTEX_THRESHOLD
    assert res.pressure.present is True
    assert res.pressure.construct == "pressure"


def test_opportunity_driven_by_eval_and_account_anomaly():
    """評鑑缺失 + 帳務異常（班佛/勾稽）→ 機會構面達門檻。"""
    res = assess({"score_eval": 90.0, "benford_score": 90.0,
                  "fund_recon_score": 100.0})
    assert res.opportunity.score >= VERTEX_THRESHOLD
    assert res.opportunity.present is True


def test_rationalization_driven_by_penalty():
    """裁罰分高（重複違規/破窗）→ 合理化構面達門檻。"""
    res = assess({"score_penalty": 90.0, "score_sentiment": 60.0})
    assert res.rationalization.score >= VERTEX_THRESHOLD
    assert res.rationalization.present is True


# --------------------------------------------------------------------------
# 成形程度：0–3 頂點 → none/weak/partial/complete
# --------------------------------------------------------------------------
def test_triangle_complete_when_all_three_present():
    """三構面皆達門檻 → complete，敘事建議優先深度查核。"""
    res = assess({
        "altman_score": 100.0,                          # 壓力
        "score_eval": 90.0, "benford_score": 90.0,      # 機會
        "score_penalty": 90.0,                          # 合理化
    })
    assert res.vertices_present == 3
    assert res.completeness == "complete"
    assert "優先" in res.narrative


def test_triangle_none_when_all_neutral():
    """全缺值（中性 0）→ none，不判高風險（責任 AI）。"""
    res = assess({})
    assert res.vertices_present == 0
    assert res.completeness == "none"
    for f in (res.pressure, res.opportunity, res.rationalization):
        assert f.present is False
        assert f.signals  # 仍提供「訊號不明顯」說明，非空


def test_triangle_partial_two_vertices():
    """兩構面達門檻 → partial。"""
    res = assess({"score_eval": 90.0, "benford_score": 90.0,   # 機會
                  "score_penalty": 90.0})                       # 合理化
    assert res.vertices_present == 2
    assert res.completeness == "partial"


# --------------------------------------------------------------------------
# 白盒對映層性質：型別、缺值容忍、值域
# --------------------------------------------------------------------------
def test_returns_structured_result():
    """回傳 FraudTriangleResult，三構面皆為 FraudTriangleFactor。"""
    res = assess({"altman_score": 50.0})
    assert isinstance(res, FraudTriangleResult)
    for f in (res.pressure, res.opportunity, res.rationalization):
        assert isinstance(f, FraudTriangleFactor)


def test_tolerates_missing_and_nan_values():
    """缺值與 NaN 一律中性處理，不拋例外。"""
    res = assess({"altman_score": float("nan"), "score_penalty": None,
                  "expense_income_ratio": "—"})
    assert 0.0 <= res.pressure.score <= 100.0
    assert res.completeness in ("none", "weak", "partial", "complete")


def test_accepts_pandas_series():
    """支援 pandas.Series 輸入（與契約 CSV 列一致）。"""
    import pandas as pd
    row = pd.Series({"altman_score": 100.0, "score_penalty": 90.0,
                     "score_eval": 90.0, "benford_score": 90.0})
    res = assess(row)
    assert res.vertices_present == 3


# --------------------------------------------------------------------------
# 屬性測試：值域與確定性
# Feature: smart-watchdog-platform, Property (Fraud Triangle mapping range/determinism)
# --------------------------------------------------------------------------
_pct = st.floats(min_value=0.0, max_value=100.0,
                 allow_nan=False, allow_infinity=False)


@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(altman=_pct, eval_s=_pct, benford=_pct, beneish=_pct,
       recon=_pct, penalty=_pct, sentiment=_pct)
def test_property_triangle_range_and_determinism(
        altman, eval_s, benford, beneish, recon, penalty, sentiment):
    """Feature: smart-watchdog-platform, Property: Fraud Triangle mapping。

    對任意合法分項輸入：三構面分數恆落在 [0,100]、vertices 為 0–3、
    completeness 對應 vertices，且確定性（同輸入同輸出）。"""
    entity = {
        "altman_score": altman, "score_eval": eval_s,
        "benford_score": benford, "beneish_score": beneish,
        "fund_recon_score": recon, "score_penalty": penalty,
        "score_sentiment": sentiment,
    }
    r1 = assess(entity)
    r2 = assess(entity)
    for f in (r1.pressure, r1.opportunity, r1.rationalization):
        assert 0.0 <= f.score <= 100.0
    assert 0 <= r1.vertices_present <= 3
    expected = {3: "complete", 2: "partial", 1: "weak", 0: "none"}[r1.vertices_present]
    assert r1.completeness == expected
    # 確定性
    assert (r2.pressure.score, r2.opportunity.score, r2.rationalization.score) == \
           (r1.pressure.score, r1.opportunity.score, r1.rationalization.score)
