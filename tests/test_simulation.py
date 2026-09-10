"""
What-if 情境模擬單元測試（Simulation Engine Unit Tests）
========================================================
對應 Task 12.1（src/simulation.py），驗證 simulate 的核心行為：
依配額/權重方案/排除近12月已稽查重排序（R4.1–R4.3）、不覆寫基準分數
（R4.4）、無效參數被拒絕且不變更既有顯示（R4.6）。

註：Property 14/15/16（模擬）之屬性測試屬於獨立的選用任務 12.2/12.3；
本檔僅涵蓋具體範例與邊界之單元測試。
"""
import copy
from datetime import date

from src.models import SimParams
from src.simulation import (
    ALLOWED_WEIGHT_SCHEMES,
    MAX_QUOTA,
    MIN_QUOTA,
    BaselineInstitution,
    SimulationResult,
    is_valid_quota,
    is_valid_weight_scheme,
    simulate,
)


def _inst(pid, total, financial=0.0, penalty=0.0, ev=0.0, last=None):
    return BaselineInstitution(
        park_id=pid,
        risk_total=total,
        components={"financial": financial, "penalty": penalty, "eval": ev},
        last_inspected=last,
    )


# --------------------------------------------------------------------------
# R4.1：配額改變輸出筆數
# --------------------------------------------------------------------------
def test_quota_limits_output_count():
    base = [_inst(f"P{i}", 50, financial=float(90 - i)) for i in range(10)]
    res5 = simulate(base, SimParams(quota=5, weight_scheme="balanced"))
    res3 = simulate(base, SimParams(quota=3, weight_scheme="balanced"))
    assert not res5.rejected and not res3.rejected
    assert len(res5.ranked) == 5
    assert len(res3.ranked) == 3


def test_quota_exceeding_population_returns_all():
    base = [_inst("A", 10, financial=10.0), _inst("B", 20, financial=20.0)]
    res = simulate(base, SimParams(quota=100, weight_scheme="balanced"))
    assert len(res.ranked) == 2


# --------------------------------------------------------------------------
# R4.2：權重方案影響排序
# --------------------------------------------------------------------------
def test_weight_scheme_reorders():
    # A 財務高、裁罰低；B 財務低、裁罰高。
    base = [
        _inst("A", 50, financial=90.0, penalty=0.0),
        _inst("B", 50, financial=0.0, penalty=90.0),
    ]
    fin = simulate(base, SimParams(quota=2, weight_scheme="financial_only"))
    pen = simulate(base, SimParams(quota=2, weight_scheme="penalty_priority"))
    assert fin.ranked[0].park_id == "A"
    assert pen.ranked[0].park_id == "B"


def test_deterministic_tie_break_by_park_id():
    # 相同模擬分數 → 依 park_id 由小至大。
    base = [_inst("Z", 50, financial=50.0), _inst("A", 50, financial=50.0)]
    res = simulate(base, SimParams(quota=2, weight_scheme="financial_only"))
    assert [r.park_id for r in res.ranked] == ["A", "Z"]
    assert res.ranked[0].rank == 1 and res.ranked[1].rank == 2


# --------------------------------------------------------------------------
# R4.3：排除近 12 個月已稽查
# --------------------------------------------------------------------------
def test_exclude_recent_inspected():
    now = date(2026, 9, 12)
    base = [
        _inst("recent", 90, financial=90.0, last=date(2026, 6, 1)),   # 近 12 月內
        _inst("old", 80, financial=80.0, last=date(2024, 1, 1)),       # 超過 12 月
        _inst("never", 70, financial=70.0, last=None),                 # 從未稽查
    ]
    res = simulate(
        base,
        SimParams(quota=10, weight_scheme="balanced", exclude_recent_inspected=True),
        now=now,
    )
    ids = {r.park_id for r in res.ranked}
    assert "recent" not in ids
    assert {"old", "never"} <= ids
    assert res.excluded_recent_count == 1


def test_no_exclusion_when_flag_off():
    now = date(2026, 9, 12)
    base = [_inst("recent", 90, financial=90.0, last=date(2026, 6, 1))]
    res = simulate(
        base,
        SimParams(quota=10, weight_scheme="balanced", exclude_recent_inspected=False),
        now=now,
    )
    assert {r.park_id for r in res.ranked} == {"recent"}
    assert res.excluded_recent_count == 0


# --------------------------------------------------------------------------
# R4.4：不覆寫基準風險分數
# --------------------------------------------------------------------------
def test_does_not_mutate_baseline():
    base = [
        _inst("A", 87.0, financial=90.0, penalty=10.0),
        _inst("B", 42.0, financial=20.0, penalty=80.0),
    ]
    snapshot = copy.deepcopy(base)
    simulate(base, SimParams(quota=1, weight_scheme="financial_only"))
    for before, after in zip(snapshot, base):
        assert before.risk_total == after.risk_total
        assert before.components == after.components
        assert before.last_inspected == after.last_inspected


# --------------------------------------------------------------------------
# R4.6：無效參數被拒絕且不變更顯示
# --------------------------------------------------------------------------
def test_invalid_quota_rejected():
    base = [_inst("A", 50, financial=50.0)]
    snapshot = copy.deepcopy(base)
    for bad in (0, 1000, -1, 5.0, True, "5", None):
        res = simulate(base, SimParams(quota=bad, weight_scheme="balanced"))
        assert res.rejected is True
        assert res.ranked == []
        assert res.message and "無效" in res.message
    # base 未被更動（不變更既有顯示）。
    assert base == snapshot


def test_invalid_weight_scheme_rejected():
    base = [_inst("A", 50, financial=50.0)]
    res = simulate(base, SimParams(quota=5, weight_scheme="not_a_scheme"))
    assert res.rejected is True
    assert res.ranked == []
    assert res.message and "無效" in res.message


def test_valid_params_not_rejected():
    base = [_inst("A", 50, financial=50.0)]
    res = simulate(base, SimParams(quota=5, weight_scheme="balanced"))
    assert isinstance(res, SimulationResult)
    assert res.rejected is False
    assert res.weight_scheme == "balanced"


# --------------------------------------------------------------------------
# 驗證輔助函式
# --------------------------------------------------------------------------
def test_is_valid_quota_boundaries():
    assert is_valid_quota(MIN_QUOTA) and is_valid_quota(MAX_QUOTA)
    assert not is_valid_quota(MIN_QUOTA - 1)
    assert not is_valid_quota(MAX_QUOTA + 1)
    assert not is_valid_quota(5.0) and not is_valid_quota(True)


def test_is_valid_weight_scheme():
    for name in ALLOWED_WEIGHT_SCHEMES:
        assert is_valid_weight_scheme(name)
    assert not is_valid_weight_scheme("bogus")
    assert not is_valid_weight_scheme(None)
