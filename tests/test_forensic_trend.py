"""
突變門檻與跨年度趨勢單元測試（Task 2.3）
==========================================
驗證 src.forensic.sudden_change_flag 與 cross_year_trend 依 R7.6/7.7 運作，
並確認既有四層方法（班佛 MAD+卡方、Beneish、Isolation Forest、IQR）仍存在（R7.10）。

對應設計：design.md「Components and Interfaces → 1. Forensic_Engine」。
"""
import pandas as pd

from src.forensic import (
    SUDDEN_CHANGE_THRESHOLD_MAX,
    SUDDEN_CHANGE_THRESHOLD_MIN,
    benford_chi_square,
    benford_mad,
    beneish_lite,
    cross_year_trend,
    flag_outliers,
    isolation_forest_scores,
    sudden_change_flag,
)


# --------------------------------------------------------------------------
# R7.6：突變門檻判定
# --------------------------------------------------------------------------
def test_sudden_change_flag_default_threshold():
    """預設門檻 0.30：|YoY| >= 0.30 → True，否則 False（R7.6）。"""
    assert sudden_change_flag(0.30) is True      # 邊界（>=）
    assert sudden_change_flag(0.31) is True
    assert sudden_change_flag(-0.50) is True     # 絕對值
    assert sudden_change_flag(0.29) is False
    assert sudden_change_flag(0.0) is False


def test_sudden_change_flag_custom_threshold():
    """可設定門檻：判定依提供之門檻（R7.6）。"""
    assert sudden_change_flag(0.15, threshold=0.10) is True
    assert sudden_change_flag(0.15, threshold=0.20) is False


def test_sudden_change_flag_threshold_clamped_to_range():
    """門檻超出 0.01–5.00 → 夾擠至合法邊界（R7.6）。"""
    # 門檻 0 < 0.01 → 夾為 0.01；0.01 的變動應被判為突變
    assert sudden_change_flag(0.01, threshold=0.0) is True
    assert sudden_change_flag(0.005, threshold=0.0) is False
    # 門檻 100 > 5.00 → 夾為 5.00；5.0 的變動應被判為突變
    assert sudden_change_flag(5.0, threshold=100.0) is True
    assert sudden_change_flag(4.99, threshold=100.0) is False


def test_sudden_change_flag_none_rate_is_false():
    """不可計算指標（YoY 為 None）→ 排除於突變判定之外（R7.6, R7.11）。"""
    assert sudden_change_flag(None) is False


def test_threshold_range_constants():
    """門檻範圍常數符合 R7.6 規格（0.01–5.00）。"""
    assert SUDDEN_CHANGE_THRESHOLD_MIN == 0.01
    assert SUDDEN_CHANGE_THRESHOLD_MAX == 5.00


# --------------------------------------------------------------------------
# R7.7：跨年度趨勢覆蓋
# --------------------------------------------------------------------------
def test_cross_year_trend_three_years_sorted():
    """三個年度：由舊到新排序、涵蓋達標（R7.7）。"""
    trend = cross_year_trend({114: 300, 112: 100, 113: 200})
    assert trend["years"] == [112, 113, 114]
    assert trend["values"] == [100.0, 200.0, 300.0]
    assert trend["covers_min_years"] is True
    assert trend["n_years"] == 3


def test_cross_year_trend_fewer_than_three_takes_all():
    """不足 3 年：取全部可得年度，covers_min_years=False（R7.7）。"""
    trend = cross_year_trend({113: 200, 112: 100})
    assert trend["years"] == [112, 113]
    assert trend["n_years"] == 2
    assert trend["covers_min_years"] is False


def test_cross_year_trend_yoy_rates():
    """相鄰年度 YoY 比率計算正確；長度 = 年度數 - 1。"""
    trend = cross_year_trend({112: 100, 113: 150, 114: 300})
    # (150-100)/100 = 0.5 ; (300-150)/150 = 1.0
    assert trend["yoy_rates"] == [0.5, 1.0]
    assert len(trend["yoy_rates"]) == len(trend["years"]) - 1


def test_cross_year_trend_skips_missing_values():
    """缺值年度被略過，不拋例外（R7.11 精神）。"""
    trend = cross_year_trend({112: 100, 113: None, 114: 300})
    assert trend["years"] == [112, 114]
    assert trend["values"] == [100.0, 300.0]


def test_cross_year_trend_zero_prev_yields_none_rate():
    """前一年度值為 0 → 該 YoY 比率為 None（除零保護），不拋例外。"""
    trend = cross_year_trend({112: 0, 113: 100})
    assert trend["yoy_rates"] == [None]


def test_cross_year_trend_accepts_tuple_sequence():
    """支援 (year, value) 序列輸入。"""
    trend = cross_year_trend([(114, 3), (112, 1), (113, 2)])
    assert trend["years"] == [112, 113, 114]


def test_cross_year_trend_empty():
    """無可得年度 → 空趨勢、covers_min_years=False。"""
    trend = cross_year_trend({})
    assert trend["years"] == []
    assert trend["values"] == []
    assert trend["yoy_rates"] == []
    assert trend["covers_min_years"] is False
    assert trend["n_years"] == 0


# --------------------------------------------------------------------------
# R7.10：保留既有四層方法（回歸性存在檢查）
# --------------------------------------------------------------------------
def test_existing_methods_preserved():
    """既有班佛（MAD+卡方）、Beneish、Isolation Forest、IQR 方法仍可呼叫（R7.10）。"""
    # 班佛 MAD
    nums = [i * 111 for i in range(1, 50)]
    mad, observed, n = benford_mad(nums, min_n=10)
    assert n == len(nums)
    # 班佛卡方
    chi2, pval, sig = benford_chi_square(nums, min_n=30)
    assert chi2 is not None
    # Beneish 改良版
    score, detail = beneish_lite({
        "income_actual": 120, "income_last_year": 100,
        "expense_actual": 130, "expense_last_year": 100, "surplus": 10,
    })
    assert score is not None
    # IQR 離群
    df = pd.DataFrame({"x": [1.0, 2.0, 3.0, 4.0, 100.0]})
    flags = flag_outliers(df, "x")
    assert flags.iloc[-1]  # 100 為離群
    # Isolation Forest
    df2 = pd.DataFrame({"a": [1.0, 2, 3, 4, 5, 100], "b": [1.0, 2, 3, 4, 5, 100]})
    scores, expl = isolation_forest_scores(df2, ["a", "b"])
    assert len(scores) == len(df2)
