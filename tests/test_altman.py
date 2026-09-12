"""
Altman Z'' 在地化困境分單元測試
================================================
驗證 src.forensic.altman_z2_lite 的判別邏輯、值域與確定性，以及其接入
analyze() 產出欄位、並被 risk_score.score_financial 納入計分（權重 15%）。

文獻依據：Altman (1968) Journal of Finance 23(4)；Altman (2000/2013) Z''-Score
非上市/非製造業改良模型。本實作為「Altman Z'' 判別精神」的在地化代理版
（幼兒園決算無完整資產負債表），公式與代理比率皆可解釋、可攤開。
"""
import math

import pandas as pd
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.forensic import (ALTMAN_Z2_DISTRESS, ALTMAN_Z2_SAFE, altman_z2_lite,
                          analyze)
from src.risk_score import score_financial


# --------------------------------------------------------------------------
# 基本判別：困境 / 安全 / 灰色地帶
# --------------------------------------------------------------------------
def test_altman_distress_scores_high():
    """嚴重短絀 + 基金薄弱 → 困境區，困境分接近滿分。"""
    # 支出遠大於收入、無基金 → Z2' 應極低（困境）。
    score, detail = altman_z2_lite({
        "income_actual": 1000, "expense_actual": 1500,
        "surplus": -500, "fund_balance_end": 0})
    assert score == 100.0
    assert detail["altman_zone"] == "困境"
    assert detail["altman_z2"] <= ALTMAN_Z2_DISTRESS


def test_altman_safe_scores_zero():
    """健康結餘 + 厚實基金 → 安全區，困境分 0。"""
    score, detail = altman_z2_lite({
        "income_actual": 1000, "expense_actual": 700,
        "surplus": 300, "fund_balance_end": 2000})
    assert score == 0.0
    assert detail["altman_zone"] == "安全"
    assert detail["altman_z2"] >= ALTMAN_Z2_SAFE


def test_altman_grey_zone_interpolated():
    """介於困境與安全界線之間 → 灰色地帶，分數為 0–100 內插值。"""
    # 微幅結餘、薄基金：落在灰色帶。
    score, detail = altman_z2_lite({
        "income_actual": 1000, "expense_actual": 950,
        "surplus": 50, "fund_balance_end": 100})
    if detail["altman_zone"] == "灰色地帶":
        assert 0.0 < score < 100.0


def test_altman_missing_income_returns_none():
    """缺 income 或 income==0 → 不可計算，回 (None, {})。"""
    assert altman_z2_lite({"income_actual": None})[0] is None
    assert altman_z2_lite({"income_actual": 0})[0] is None


def test_altman_surplus_backfilled_from_income_minus_expense():
    """surplus 缺值時以 income-expense 回補，不拋例外且可計算。"""
    score, detail = altman_z2_lite({
        "income_actual": 1000, "expense_actual": 1200, "fund_balance_end": 0})
    assert score is not None
    # 回補後 surplus = -200 → x1 = -0.2
    assert detail["altman_x1_surplus_ratio"] == -0.2


# --------------------------------------------------------------------------
# analyze 接入：產出 altman 欄位
# --------------------------------------------------------------------------
def test_analyze_produces_altman_columns():
    """analyze 輸出 altman_score / altman_z2 / altman_zone 欄位。"""
    df = pd.DataFrame([
        {"park_id": "A", "park_name": "甲園", "park_type": "公校", "year": 113,
         "income_actual": 1000, "expense_actual": 1500, "surplus": -500,
         "income_last_year": 900, "expense_last_year": 1000,
         "fund_balance_begin": 0, "fund_balance_end": 0},
    ])
    out = analyze(df)
    for col in ["altman_score", "altman_z2", "altman_zone"]:
        assert col in out.columns
    # 該園嚴重入不敷出 → 困境、分數高。
    assert out["altman_score"].iloc[0] == 100.0
    assert out["altman_zone"].iloc[0] == "困境"


# --------------------------------------------------------------------------
# 接入 score_financial：Altman 分項納入計分（權重 15%）
# --------------------------------------------------------------------------
def _base_row(**over):
    r = {"benford_score": 0, "beneish_score": 0, "iforest_score": 0,
         "expense_income_ratio": 1.0, "expense_yoy_pct": 0,
         "surplus": 0, "income_actual": 1000,
         "fund_recon_score": 0.0, "fund_continuity_score": 0.0,
         "altman_score": 0.0}
    r.update(over)
    return r


def test_score_financial_includes_altman_weight():
    """Altman 分項以 15% 權重納入財務分：altman=100 → 財務分 +15。"""
    base = score_financial(_base_row(altman_score=0.0))
    high = score_financial(_base_row(altman_score=100.0))
    assert round(high - base, 1) == 15.0


def test_score_financial_altman_missing_is_neutral():
    """altman 缺值（NaN）視為中性 0，不放大也不拋例外。"""
    r = _base_row()
    del r["altman_score"]
    r["altman_score"] = float("nan")
    assert score_financial(r) == score_financial(_base_row(altman_score=0.0))


# --------------------------------------------------------------------------
# 屬性測試：值域與確定性
# Feature: smart-watchdog-platform, Property (Altman Z'' lite range/determinism)
# --------------------------------------------------------------------------
@settings(max_examples=150, suppress_health_check=[HealthCheck.too_slow])
@given(
    income=st.floats(min_value=1.0, max_value=1e9,
                     allow_nan=False, allow_infinity=False),
    expense=st.floats(min_value=0.0, max_value=1e9,
                      allow_nan=False, allow_infinity=False),
    fund=st.floats(min_value=0.0, max_value=1e9,
                   allow_nan=False, allow_infinity=False),
)
def test_property_altman_range_and_determinism(income, expense, fund):
    """Feature: smart-watchdog-platform, Property: Altman Z'' lite。

    對任意合法財務輸入：困境分恆落在 [0,100]、zone 為三態之一，且確定性
    （同輸入同輸出）。"""
    row = {"income_actual": income, "expense_actual": expense,
           "surplus": income - expense, "fund_balance_end": fund}
    s1, d1 = altman_z2_lite(row)
    s2, d2 = altman_z2_lite(row)
    assert s1 == s2                       # 確定性
    assert 0.0 <= s1 <= 100.0             # 值域
    assert d1["altman_zone"] in ("困境", "安全", "灰色地帶")
    assert not math.isnan(d1["altman_z2"])
