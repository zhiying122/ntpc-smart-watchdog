"""
分派最佳化單元測試（Allocation Optimizer Unit Tests）
======================================================
對應 Task 11.1（src/allocation.py），驗證 optimize 的核心行為：
風險覆蓋最大化（R3.2）與確定性 tie-break（R3.3），以及 R3.1 的
輸入/輸出契約。

註：Property 9/10/11/12/13（分派最佳化）之屬性測試屬於獨立的選用任務
11.3–11.5；本檔僅涵蓋具體範例與邊界之單元測試。限制過濾、N 驗證與
邊界訊息（fewer_than_n / 無合格說明 / N 無效）之完整語意屬 Task 11.2。
"""
from itertools import combinations

from src.allocation import (
    MAX_INSPECTORS,
    MIN_INSPECTORS,
    Institution,
    Policy,
    RegionFilter,
    deterministic_order,
    is_valid_n,
    optimize,
)
from src.models import AllocationItem, AllocationResult


def _insts(*pairs):
    """便利建構：pairs 為 (park_id, risk_score[, district]) tuple。"""
    out = []
    for p in pairs:
        if len(p) == 3:
            out.append(Institution(park_id=p[0], risk_score=p[1], district=p[2]))
        else:
            out.append(Institution(park_id=p[0], risk_score=p[1]))
    return out


# --------------------------------------------------------------------------
# R3.1：輸入/輸出契約
# --------------------------------------------------------------------------
def test_optimize_returns_allocation_result():
    """optimize 回傳 AllocationResult，selected 為 AllocationItem 清單（R3.1）。"""
    insts = _insts(("A", 80.0), ("B", 60.0), ("C", 40.0))
    result = optimize(insts, n=2)
    assert isinstance(result, AllocationResult)
    assert all(isinstance(item, AllocationItem) for item in result.selected)
    assert len(result.selected) == 2


def test_optimize_output_count_capped_by_n():
    """輸出數量不超過 N（R3.6 核心，供 R3.1 契約）。"""
    insts = _insts(("A", 80.0), ("B", 60.0), ("C", 40.0), ("D", 20.0))
    assert len(optimize(insts, n=1).selected) == 1
    assert len(optimize(insts, n=3).selected) == 3
    # N 大於候選數 → 全部輸出
    assert len(optimize(insts, n=10).selected) == 4


# --------------------------------------------------------------------------
# R3.2：風險覆蓋最大化
# --------------------------------------------------------------------------
def test_optimize_maximizes_risk_coverage():
    """所選機構風險分數總和為可行解中的最大值（R3.2）。"""
    insts = _insts(("A", 30.0), ("B", 90.0), ("C", 50.0), ("D", 70.0))
    n = 2
    result = optimize(insts, n=n)
    chosen_sum = sum(item.risk_score for item in result.selected)

    # 暴力法參考：所有基數為 min(n, len) 的子集，取最大風險總和
    k = min(n, len(insts))
    best = max(
        sum(inst.risk_score for inst in combo)
        for combo in combinations(insts, k)
    )
    assert chosen_sum == best
    # 具體：B(90) + D(70) = 160
    assert chosen_sum == 160.0
    assert {item.park_id for item in result.selected} == {"B", "D"}


def test_optimize_picks_highest_scores():
    """貪婪選取最高風險分數機構（R3.2）。"""
    insts = _insts(("low", 10.0), ("mid", 55.0), ("high", 99.0))
    result = optimize(insts, n=1)
    assert result.selected[0].park_id == "high"
    assert result.selected[0].risk_score == 99.0


# --------------------------------------------------------------------------
# R3.3：確定性與 tie-break
# --------------------------------------------------------------------------
def test_optimize_deterministic_same_input_same_output():
    """相同輸入永遠產生相同輸出（R3.3）。"""
    insts = _insts(("C", 50.0), ("A", 50.0), ("B", 80.0), ("D", 50.0))
    r1 = optimize(insts, n=2)
    r2 = optimize(insts, n=2)
    assert [i.park_id for i in r1.selected] == [i.park_id for i in r2.selected]


def test_optimize_tie_break_by_park_id_ascending():
    """風險分數相同時，依 park_id 由小至大選取（R3.3）。"""
    # 三間同分 50，選 2 → 應選 park_id 最小的 "A", "B"
    insts = _insts(("C", 50.0), ("A", 50.0), ("B", 50.0))
    result = optimize(insts, n=2)
    assert [i.park_id for i in result.selected] == ["A", "B"]


def test_optimize_tie_break_score_precedes_id():
    """風險分數優先於 park_id：先按分數降冪，同分才比 id（R3.3）。"""
    insts = _insts(("Z", 90.0), ("A", 50.0), ("B", 90.0))
    result = optimize(insts, n=2)
    # 90 分的 B、Z（B<Z）優先於 50 分的 A
    assert [i.park_id for i in result.selected] == ["B", "Z"]


def test_deterministic_order_full_ordering():
    """deterministic_order 依 (分數 desc, park_id asc) 排序（R3.3）。"""
    insts = _insts(("C", 50.0), ("A", 50.0), ("B", 80.0), ("D", 20.0))
    ordered = deterministic_order(insts)
    assert [i.park_id for i in ordered] == ["B", "A", "C", "D"]


# --------------------------------------------------------------------------
# R3.10 核心：分派理由包含風險分數
# --------------------------------------------------------------------------
def test_each_selected_has_reason_with_risk_score():
    """每一入選機構附非空理由，且理由包含風險分數（R3.10 核心）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    result = optimize(insts, n=2)
    for item in result.selected:
        assert item.reason
        assert f"{item.risk_score:g}" in item.reason


# --------------------------------------------------------------------------
# 核心過濾（供 R3.4 / R3.5，完整邊界屬 Task 11.2）
# --------------------------------------------------------------------------
def test_optimize_excludes_inspected():
    """已稽查機構被排除於輸出之外（R3.4 核心）。"""
    insts = _insts(("A", 99.0), ("B", 80.0), ("C", 70.0))
    result = optimize(insts, n=2, inspected={"A"})
    assert "A" not in {i.park_id for i in result.selected}
    assert [i.park_id for i in result.selected] == ["B", "C"]


def test_optimize_region_filter():
    """區域限制下僅選取滿足限制的機構（R3.5 核心）。"""
    insts = _insts(
        ("A", 99.0, "板橋"),
        ("B", 80.0, "新莊"),
        ("C", 70.0, "板橋"),
    )
    rf = RegionFilter(allowed_districts={"板橋"})
    result = optimize(insts, n=3, region_filter=rf)
    assert {i.park_id for i in result.selected} == {"A", "C"}


def test_optimize_custom_policy_score_key():
    """policy 可自訂用於最大化的分數來源（R3.1 擴充點）。"""
    insts = [
        Institution(park_id="A", risk_score=10.0, attributes={"w": 100.0}),
        Institution(park_id="B", risk_score=90.0, attributes={"w": 5.0}),
    ]
    pol = Policy(name="weighted", score_key=lambda i: i.attributes["w"])
    result = optimize(insts, n=1, policy=pol)
    assert result.selected[0].park_id == "A"


# --------------------------------------------------------------------------
# Task 11.2：N 驗證（R3.9）
# --------------------------------------------------------------------------
def test_optimize_rejects_n_below_range():
    """N < 1（如 0、負數）→ 拒絕、空集合、附錯誤訊息（R3.9）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    for bad in (0, -1, -100):
        result = optimize(insts, n=bad)
        assert result.selected == []
        assert result.fewer_than_n is False
        assert result.message is not None
        assert "無效" in result.message


def test_optimize_rejects_n_above_range():
    """N > 1000 → 拒絕、空集合、附錯誤訊息（R3.9）。"""
    insts = _insts(("A", 80.0))
    result = optimize(insts, n=1001)
    assert result.selected == []
    assert result.message is not None
    assert "無效" in result.message


def test_optimize_rejects_non_integer_n():
    """N 非整數（float / None / str）→ 拒絕（R3.9）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    for bad in (2.5, 2.0, None, "2"):
        result = optimize(insts, n=bad)  # type: ignore[arg-type]
        assert result.selected == []
        assert result.message is not None
        assert "無效" in result.message


def test_optimize_rejects_bool_n():
    """N 為 bool（True/False）→ 拒絕，不因 bool 為 int 子類而誤收（R3.9）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    for bad in (True, False):
        result = optimize(insts, n=bad)  # type: ignore[arg-type]
        assert result.selected == []
        assert result.message is not None
        assert "無效" in result.message


def test_optimize_accepts_boundary_n():
    """N 邊界值 1 與 1000 為有效（R3.9）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    r_min = optimize(insts, n=MIN_INSPECTORS)
    assert r_min.message is None
    assert len(r_min.selected) == 1

    r_max = optimize(insts, n=MAX_INSPECTORS)
    # N 遠大於候選數 → 全部輸出並標示 fewer_than_n（R3.7）
    assert len(r_max.selected) == 2
    assert r_max.fewer_than_n is True


# --------------------------------------------------------------------------
# Task 11.2：合格 < N → fewer_than_n（R3.7）
# --------------------------------------------------------------------------
def test_optimize_fewer_than_n_flag_and_message():
    """合格機構數少於 N → 全輸出並標示 fewer_than_n，附說明（R3.7）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    result = optimize(insts, n=5)
    assert len(result.selected) == 2
    assert result.fewer_than_n is True
    assert result.message is not None
    assert "少於" in result.message


def test_optimize_exact_n_not_fewer_than_n():
    """合格機構數等於 N → 不標示 fewer_than_n（R3.6/R3.7 邊界）。"""
    insts = _insts(("A", 80.0), ("B", 60.0), ("C", 40.0))
    result = optimize(insts, n=3)
    assert len(result.selected) == 3
    assert result.fewer_than_n is False
    assert result.message is None


def test_optimize_more_than_n_not_fewer_than_n():
    """合格機構數多於 N → 取前 N，不標示 fewer_than_n（R3.6）。"""
    insts = _insts(("A", 80.0), ("B", 60.0), ("C", 40.0))
    result = optimize(insts, n=2)
    assert len(result.selected) == 2
    assert result.fewer_than_n is False


def test_optimize_fewer_than_n_after_filtering():
    """過濾（已稽查/區域）後合格數少於 N → fewer_than_n（R3.4, R3.5, R3.7）。"""
    insts = _insts(
        ("A", 99.0, "板橋"),
        ("B", 80.0, "新莊"),
        ("C", 70.0, "板橋"),
    )
    rf = RegionFilter(allowed_districts={"板橋"})
    result = optimize(insts, n=3, region_filter=rf, inspected={"A"})
    # 僅 C 合格（A 已稽查、B 非板橋）
    assert [i.park_id for i in result.selected] == ["C"]
    assert result.fewer_than_n is True


# --------------------------------------------------------------------------
# Task 11.2：無合格機構 → 空集合 + 說明（R3.8）
# --------------------------------------------------------------------------
def test_optimize_empty_candidate_list():
    """候選為空 → 空集合 + 說明（R3.8）。"""
    result = optimize([], n=3)
    assert result.selected == []
    assert result.fewer_than_n is False
    assert result.message is not None
    assert "候選機構清單為空" in result.message


def test_optimize_all_inspected_no_eligible():
    """所有候選皆已稽查 → 空集合 + 說明含已稽查成因（R3.4, R3.8）。"""
    insts = _insts(("A", 80.0), ("B", 60.0))
    result = optimize(insts, n=2, inspected={"A", "B"})
    assert result.selected == []
    assert result.message is not None
    assert "已稽查" in result.message


def test_optimize_region_excludes_all_no_eligible():
    """區域限制過濾殆盡 → 空集合 + 說明含區域成因（R3.5, R3.8）。"""
    insts = _insts(("A", 80.0, "新莊"), ("B", 60.0, "三重"))
    rf = RegionFilter(allowed_districts={"板橋"})
    result = optimize(insts, n=2, region_filter=rf)
    assert result.selected == []
    assert result.message is not None
    assert "區域限制" in result.message


# --------------------------------------------------------------------------
# Task 11.2：is_valid_n 直接驗證
# --------------------------------------------------------------------------
def test_is_valid_n():
    """is_valid_n 嚴格判定整數且落於 1..1000（R3.9）。"""
    assert is_valid_n(1) is True
    assert is_valid_n(1000) is True
    assert is_valid_n(500) is True
    assert is_valid_n(0) is False
    assert is_valid_n(1001) is False
    assert is_valid_n(-1) is False
    assert is_valid_n(2.5) is False
    assert is_valid_n(2.0) is False
    assert is_valid_n(True) is False
    assert is_valid_n(False) is False
    assert is_valid_n(None) is False
    assert is_valid_n("5") is False
