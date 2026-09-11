"""
基金餘額勾稽（Fund Balance Reconciliation）單元測試
====================================================
驗證 src.forensic.fund_reconciliation / fund_continuity 與其接入 analyze、
以及 risk_score.score_financial 的「不對稱加成」行為。

「勾稽」為台灣會計/審計正統用語：把應相符的數字互相核對、確認一致。
會計恆等式：期末基金餘額 = 期初基金餘額 + 本期賸餘(短絀) − 解繳公庫 ± 其他調整。
"""
import pandas as pd

from src.forensic import analyze, fund_continuity, fund_reconciliation
from src.risk_score import score_financial


# --------------------------------------------------------------------------
# 同期勾稽：期末 = 期初 + 本期賸餘
# --------------------------------------------------------------------------
def test_fund_reconciliation_consistent():
    """恆等式成立 → consistent=True、score=0（板橋 113 實例）。"""
    r = fund_reconciliation(2927106, 1330817, 4257923)
    assert r["computable"] is True
    assert r["consistent"] is True
    assert r["diff"] == 0.0
    assert r["score"] == 0.0
    assert r["formula"]  # 明確公式字串非空


def test_fund_reconciliation_inconsistent_scores_high():
    """期末少 50 萬 → 不一致、可疑分明顯 > 0。"""
    r = fund_reconciliation(2927106, 1330817, 4257923 - 500000)
    assert r["consistent"] is False
    assert r["diff"] == -500000.0
    assert r["score"] > 0


def test_fund_reconciliation_missing_data_not_computable():
    """缺任一基金數字 → computable=False、score=0（不放大風險）。"""
    r = fund_reconciliation(None, 1330817, 4257923)
    assert r["computable"] is False
    assert r["score"] == 0.0


def test_fund_reconciliation_deficit_case():
    """本期短絀（負賸餘）亦能正確勾稽。"""
    # 期初 1000、短絀 -300 → 期末應為 700
    r = fund_reconciliation(1000, -300, 700)
    assert r["consistent"] is True
    assert r["score"] == 0.0


def test_fund_reconciliation_with_adjustment():
    """解繳公庫調整納入恆等式：期末 = 期初 + 賸餘 − 解繳。"""
    # 期初 1000 + 賸餘 500 − 解繳 200 = 1300
    r = fund_reconciliation(1000, 500, 1300, adjustments=200)
    assert r["consistent"] is True


# --------------------------------------------------------------------------
# 跨年度連續性勾稽：本年期初 = 上年期末
# --------------------------------------------------------------------------
def test_fund_continuity_consistent():
    """本年期初 = 上年期末 → 一致、score=0。"""
    c = fund_continuity(4257923, 4257923)
    assert c["consistent"] is True
    assert c["score"] == 0.0


def test_fund_continuity_broken_scores_high():
    """銜接不上 → 不一致、可疑分 > 0。"""
    c = fund_continuity(4257923, 4000000)
    assert c["consistent"] is False
    assert c["score"] > 0


def test_fund_continuity_missing_not_computable():
    """缺數字 → computable=False、score=0。"""
    c = fund_continuity(None, 4000000)
    assert c["computable"] is False
    assert c["score"] == 0.0


# --------------------------------------------------------------------------
# analyze 接入：產出勾稽欄位，且相鄰年度才做連續性勾稽
# --------------------------------------------------------------------------
def test_analyze_produces_recon_columns():
    """analyze 輸出同期與跨年度勾稽欄位。"""
    df = pd.DataFrame([
        {"park_id": "A", "park_name": "甲園", "park_type": "公校", "year": 112,
         "income_actual": 1000, "expense_actual": 900, "surplus": 100,
         "fund_balance_begin": 500, "fund_balance_end": 600},
        {"park_id": "A", "park_name": "甲園", "park_type": "公校", "year": 113,
         "income_actual": 1100, "expense_actual": 1000, "surplus": 100,
         "fund_balance_begin": 600, "fund_balance_end": 700},
    ])
    out = analyze(df)
    for col in ["fund_recon_score", "fund_recon_consistent",
                "fund_continuity_score"]:
        assert col in out.columns
    # 兩列同期勾稽皆一致（期末 = 期初 + 賸餘）
    assert bool(out["fund_recon_consistent"].iloc[0]) is True
    assert bool(out["fund_recon_consistent"].iloc[1]) is True
    # 113 年期初 600 = 112 年期末 600 → 連續性一致（score 0）
    row113 = out[out["year"] == 113].iloc[0]
    assert row113["fund_continuity_score"] == 0.0


def test_analyze_continuity_skips_non_adjacent_years():
    """年度不相鄰（112→114，缺 113）不做連續性勾稽，避免假陽性。"""
    df = pd.DataFrame([
        {"park_id": "B", "park_name": "乙園", "park_type": "公校", "year": 112,
         "income_actual": 1000, "expense_actual": 900, "surplus": 100,
         "fund_balance_begin": 500, "fund_balance_end": 600},
        {"park_id": "B", "park_name": "乙園", "park_type": "公校", "year": 114,
         "income_actual": 1200, "expense_actual": 1100, "surplus": 100,
         "fund_balance_begin": 481910, "fund_balance_end": 582010},
    ])
    out = analyze(df)
    # 114 與 112 不相鄰 → 連續性分維持 0（不誤判斷裂）
    row114 = out[out["year"] == 114].iloc[0]
    assert row114["fund_continuity_score"] == 0.0


# --------------------------------------------------------------------------
# score_financial 不對稱加成：一致不動、不一致向上加成
# --------------------------------------------------------------------------
def _base_row(**over):
    r = {"benford_score": 50, "beneish_score": 20, "iforest_score": 30,
         "expense_income_ratio": 1.05, "expense_yoy_pct": 10,
         "surplus": 100, "income_actual": 1000,
         "fund_recon_score": 0.0, "fund_continuity_score": 0.0}
    r.update(over)
    return r


def test_score_financial_bonus_zero_when_consistent():
    """勾稽一致（分 0）→ 財務分不因勾稽而改變。"""
    base = _base_row()
    no_fund = {k: v for k, v in base.items()
               if k not in ("fund_recon_score", "fund_continuity_score")}
    assert score_financial(base) == score_financial(no_fund)


def test_score_financial_bonus_added_when_inconsistent():
    """同期勾稽不一致（100 分）→ 財務分 +15（封頂 100）。"""
    consistent = score_financial(_base_row())
    inconsistent = score_financial(_base_row(fund_recon_score=100.0))
    assert round(inconsistent - consistent, 1) == 15.0


def test_score_financial_bonus_uses_max_of_two_recons():
    """取同期與連續性勾稽分的較大者做加成。"""
    s = score_financial(_base_row(fund_recon_score=40.0,
                                  fund_continuity_score=100.0))
    base = score_financial(_base_row())
    assert round(s - base, 1) == 15.0  # max(40,100)=100 → +15


def test_score_financial_bonus_capped_at_100():
    """加成後仍封頂 100，不溢出。"""
    s = score_financial(_base_row(benford_score=100, beneish_score=100,
                                  iforest_score=100, fund_recon_score=100.0))
    assert s <= 100.0
