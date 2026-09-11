"""稽查派工決策台橋接層 app/lib/dispatch.py 的單元測試。

只驗證「DataFrame → 引擎輸入 → 結果整理」的橋接正確性；最佳化/重排序
本身的正確性由 tests/test_allocation.py 與 tests/test_simulation.py 涵蓋。
"""
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
for _p in (ROOT, APP):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import dispatch  # noqa: E402


def _df():
    return pd.DataFrame({
        "park_id": [1, 2, 3, 4, 5],
        "park_name": ["甲園", "乙園", "丙園", "丁園", "戊園"],
        "district": ["板橋區", "板橋區", "三芝區", "金山區", "板橋區"],
        "risk_total": [90.0, 80.0, 70.0, 60.0, 50.0],
        "score_financial": [80, 60, 50, 40, 30],
        "score_penalty": [80, 0, 50, 0, 50],
        "score_eval": [40, 20, 0, 20, 0],
    })


# ---------------------------------------------------------------------------
# 分派最佳化橋接
# ---------------------------------------------------------------------------
def test_allocation_selects_top_n_by_risk():
    result, lookup = dispatch.run_allocation(_df(), n=3)
    out = dispatch.allocation_to_dataframe(result, lookup)
    assert len(out) == 3
    # 應選出風險最高的三間（甲/乙/丙），且依風險由高至低。
    assert out["機構名稱"].tolist() == ["甲園", "乙園", "丙園"]
    assert out["風險分"].tolist() == [90.0, 80.0, 70.0]


def test_allocation_region_filter():
    result, lookup = dispatch.run_allocation(
        _df(), n=5, allowed_districts={"板橋區"})
    out = dispatch.allocation_to_dataframe(result, lookup)
    # 僅板橋區三間（甲/乙/戊）。
    assert set(out["行政區"]) == {"板橋區"}
    assert len(out) == 3


def test_allocation_exclude_inspected():
    result, lookup = dispatch.run_allocation(_df(), n=3, inspected={"1"})
    out = dispatch.allocation_to_dataframe(result, lookup)
    assert "甲園" not in out["機構名稱"].tolist()  # 已稽查排除


def test_allocation_each_row_has_reason():
    result, _ = dispatch.run_allocation(_df(), n=3)
    for item in result.selected:
        assert item.reason  # 非空入選理由


def test_allocation_invalid_n_rejected():
    result, _ = dispatch.run_allocation(_df(), n=0)  # N 無效
    assert result.selected == []
    assert result.message  # 有錯誤說明


# ---------------------------------------------------------------------------
# What-if 模擬橋接
# ---------------------------------------------------------------------------
def test_simulation_reorders_by_scheme():
    result, lookup = dispatch.run_simulation(_df(), quota=5,
                                             weight_scheme="penalty_priority")
    assert not result.rejected
    out = dispatch.simulation_to_dataframe(result, lookup)
    assert len(out) == 5
    # 名次連續遞增。
    assert out["模擬名次"].tolist() == [1, 2, 3, 4, 5]


def test_simulation_quota_limits_output():
    result, lookup = dispatch.run_simulation(_df(), quota=2,
                                             weight_scheme="balanced")
    out = dispatch.simulation_to_dataframe(result, lookup)
    assert len(out) == 2


def test_simulation_invalid_quota_rejected():
    result, _ = dispatch.run_simulation(_df(), quota=0, weight_scheme="balanced")
    assert result.rejected
    assert result.ranked == []


def test_simulation_invalid_scheme_rejected():
    result, _ = dispatch.run_simulation(_df(), quota=5, weight_scheme="nonexistent")
    assert result.rejected


def test_weight_schemes_match_engine():
    from src import simulation as sim
    assert set(dispatch.WEIGHT_SCHEMES) == set(sim.ALLOWED_WEIGHT_SCHEMES)
