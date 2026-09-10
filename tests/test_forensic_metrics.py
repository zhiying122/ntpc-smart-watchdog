"""
鑑識會計明確公式指標單元測試（Task 2.1）
============================================
驗證 src.forensic.compute_metrics 依 R7.1/7.2/7.4/7.5/7.9 計算六項指標、
附非空公式字串、以 4 位小數輸出，並計算收入/招生一致性與同儕 z-score/百分位。

對應設計：design.md「Components and Interfaces → 1. Forensic_Engine」。
"""
import math

from src.forensic import (
    METRIC_FORMULAS,
    compute_expense_structure,
    compute_metrics,
)
from src.models import ForensicMetrics, Metric


def _base_row():
    return {
        "income_actual": 1_200_000.0,
        "expense_actual": 1_000_000.0,
        "income_last_year": 1_000_000.0,
        "expense_last_year": 800_000.0,
        "personnel_expense": 600_000.0,
        "operating_expense": 300_000.0,
        "enrollment": 100,
    }


def test_returns_forensic_metrics_with_six_metrics():
    """回傳 ForensicMetrics，六項指標皆為 Metric（R7.1）。"""
    fm = compute_metrics(_base_row())
    assert isinstance(fm, ForensicMetrics)
    for m in (fm.income_growth, fm.expense_growth, fm.personnel_ratio,
              fm.operating_ratio, fm.income_per_child, fm.expense_per_child):
        assert isinstance(m, Metric)


def test_metric_values_match_formula_and_precision():
    """六項指標值等於公式計算並以 4 位小數輸出（R7.1, R7.4）。"""
    row = _base_row()
    fm = compute_metrics(row)

    assert fm.income_growth.value == round((1_200_000 - 1_000_000) / 1_000_000, 4)
    assert fm.expense_growth.value == round((1_000_000 - 800_000) / 800_000, 4)
    assert fm.personnel_ratio.value == round(600_000 / 1_000_000, 4)
    assert fm.operating_ratio.value == round(300_000 / 1_000_000, 4)
    assert fm.income_per_child.value == round(1_200_000 / 100, 4)
    assert fm.expense_per_child.value == round(1_000_000 / 100, 4)


def test_precision_is_four_decimals():
    """輸出精度為小數點後 4 位（R7.1）。"""
    row = _base_row()
    row["income_actual"] = 1_000_000.0 / 3  # 產生無限小數
    row["enrollment"] = 7
    fm = compute_metrics(row)
    val = fm.income_per_child.value
    # 小數位數不超過 4 位
    assert round(val, 4) == val


def test_each_metric_has_nonempty_formula():
    """每一指標附非空明確公式字串（R7.9）。"""
    fm = compute_metrics(_base_row())
    for m in (fm.income_growth, fm.expense_growth, fm.personnel_ratio,
              fm.operating_ratio, fm.income_per_child, fm.expense_per_child):
        assert isinstance(m.formula, str)
        assert m.formula.strip() != ""


def test_all_metric_formula_keys_present():
    """METRIC_FORMULAS 涵蓋六項指標的公式定義。"""
    for name in ("income_growth", "expense_growth", "personnel_ratio",
                 "operating_ratio", "income_per_child", "expense_per_child"):
        assert name in METRIC_FORMULAS
        assert METRIC_FORMULAS[name].strip() != ""


def test_zero_denominator_marks_uncomputable():
    """分母為 0（招生人數 0、前年度 0、總支出 0）→ computable=False（R7.11）。"""
    row = _base_row()
    row["enrollment"] = 0
    row["income_last_year"] = 0
    row["expense_actual"] = 0
    fm = compute_metrics(row)

    assert fm.income_per_child.computable is False
    assert fm.income_per_child.value is None
    assert fm.expense_per_child.computable is False
    assert fm.income_growth.computable is False
    assert fm.personnel_ratio.computable is False  # 總支出為 0


def test_missing_values_marks_uncomputable_without_raising():
    """缺值（None）不拋例外並標記不可計算（R7.11）。"""
    row = {
        "income_actual": None,
        "expense_actual": None,
        "income_last_year": None,
        "expense_last_year": None,
        "personnel_expense": None,
        "operating_expense": None,
        "enrollment": None,
    }
    fm = compute_metrics(row)  # 不應拋例外
    for m in (fm.income_growth, fm.expense_growth, fm.personnel_ratio,
              fm.operating_ratio, fm.income_per_child, fm.expense_per_child):
        assert m.computable is False
        assert m.value is None


def test_income_enrollment_consistency():
    """收入/招生一致性 = 相對同儕中位數的偏離比例（R7.2）。"""
    row = _base_row()  # income_per_child = 12000
    peer = {"income_per_child_median": 10_000.0}
    fm = compute_metrics(row, peer)
    expected = round((12_000 - 10_000) / 10_000, 4)
    assert fm.expense_structure["income_enrollment_consistency"] == expected


def test_peer_zscore_and_percentile():
    """同儕 z-score 與百分位計算正確（R7.5）。"""
    row = _base_row()  # income_per_child = 12000
    peer_values = [8_000.0, 10_000.0, 12_000.0, 14_000.0]
    fm = compute_metrics(row, {"income_per_child_values": peer_values})

    z = fm.expense_structure["income_per_child_zscore"]
    pct = fm.expense_structure["income_per_child_percentile"]

    mean = sum(peer_values) / len(peer_values)
    var = sum((v - mean) ** 2 for v in peer_values) / len(peer_values)
    std = math.sqrt(var)
    assert z == round((12_000 - mean) / std, 4)
    # 12000 <= {12000, 14000 沒有, 8000,10000,12000} → 3/4 = 75%
    assert pct == round(3 / 4 * 100, 4)


def test_accepts_object_with_attributes():
    """支援以屬性存取的物件（如 dataclass）而非僅 dict。"""
    class Row:
        income_actual = 1_000_000.0
        expense_actual = 900_000.0
        income_last_year = 800_000.0
        expense_last_year = 800_000.0
        personnel_expense = 500_000.0
        operating_expense = 300_000.0
        enrollment = 50

    fm = compute_metrics(Row())
    assert fm.income_per_child.value == round(1_000_000 / 50, 4)
    assert fm.income_growth.computable is True


# ==========================================================================
# 支出結構占比與缺值保護單元測試（Task 2.2, R7.3/7.11）
# ==========================================================================
def _shares_sum(structure):
    return (structure["personnel_share"]
            + structure["operating_share"]
            + structure["other_share"])


def test_expense_structure_three_shares_present():
    """支出結構輸出人事/業務/其他三類占比（R7.3）。"""
    fm = compute_metrics(_base_row())
    es = fm.expense_structure
    for key in ("personnel_share", "operating_share", "other_share"):
        assert key in es


def test_expense_structure_values_match_formula():
    """三類占比等於各自公式（4 位小數）（R7.3）。"""
    row = _base_row()  # expense=1_000_000, personnel=600_000, operating=300_000
    es = compute_metrics(row).expense_structure
    assert es["personnel_share"] == round(600_000 / 1_000_000, 4)
    assert es["operating_share"] == round(300_000 / 1_000_000, 4)
    # 其他 = (1_000_000 - 600_000 - 300_000) / 1_000_000 = 0.1
    assert es["other_share"] == round(100_000 / 1_000_000, 4)


def test_expense_structure_shares_sum_within_tolerance():
    """三類占比合計介於 0.99–1.01（R7.3）。"""
    total = _shares_sum(compute_metrics(_base_row()).expense_structure)
    assert 0.99 <= total <= 1.01


def test_expense_structure_sum_when_personnel_operating_missing():
    """人事/業務缺值時以 0 代入，餘額歸其他，合計仍介於 0.99–1.01（R7.3, R7.11）。"""
    row = _base_row()
    row["personnel_expense"] = None
    row["operating_expense"] = None
    es = compute_metrics(row).expense_structure
    assert es["personnel_share"] == 0.0
    assert es["operating_share"] == 0.0
    assert es["other_share"] == 1.0
    assert 0.99 <= _shares_sum(es) <= 1.01


def test_expense_structure_excluded_when_total_expense_zero():
    """總支出為 0 → 支出結構被排除（空 dict），且不中斷其餘指標（R7.11）。"""
    row = _base_row()
    row["expense_actual"] = 0
    fm = compute_metrics(row)
    # 支出結構被排除
    assert "personnel_share" not in fm.expense_structure
    assert "operating_share" not in fm.expense_structure
    assert "other_share" not in fm.expense_structure
    # 其餘指標不受影響：分母為收入/前年度者仍可計算
    assert fm.income_per_child.computable is True
    assert fm.income_growth.computable is True


def test_expense_structure_excluded_when_total_expense_missing():
    """總支出缺值（None）→ 支出結構被排除，不拋例外（R7.11）。"""
    row = _base_row()
    row["expense_actual"] = None
    fm = compute_metrics(row)  # 不應拋例外
    assert fm.expense_structure.get("personnel_share") is None
    assert fm.expense_structure == {}


def test_compute_expense_structure_helper_zero_denominator():
    """compute_expense_structure：分母 0/缺值 → 空 dict（R7.11）。"""
    assert compute_expense_structure(0, 100, 200) == {}
    assert compute_expense_structure(None, 100, 200) == {}


def test_compute_expense_structure_helper_sum_is_one():
    """compute_expense_structure：任意合法輸入三類合計介於 0.99–1.01（R7.3）。"""
    es = compute_expense_structure(1_234_567, 700_000, 234_567)
    assert 0.99 <= _shares_sum(es) <= 1.01
