"""
同儕群組與統計量單元測試（Peer Group & Comparison Unit Tests）
================================================================
對應 Task 4.1（src/peer.py），驗證 build_peer_group / peer_stats 的
具體行為與邊界（R13.1, R13.2, R13.3, R13.4）。

註：Property 35（同儕統計量正確）之屬性測試屬於獨立的選用任務 4.3，
本檔僅涵蓋具體範例與邊界之單元測試。
"""
import statistics

from src.peer import (
    DEFAULT_PEER_KEYS,
    MIN_PEER_SAMPLE,
    PeerComparison,
    PeerGroup,
    build_peer_group,
    peer_stats,
)


# --------------------------------------------------------------------------
# build_peer_group（R13.1）
# --------------------------------------------------------------------------
def _pop():
    return [
        {"park_id": "A", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 10.0},
        {"park_id": "B", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 20.0},
        {"park_id": "C", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 30.0},
        {"park_id": "D", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 40.0},
        {"park_id": "E", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 50.0},
        {"park_id": "F", "park_type": "非營利", "size_band": "大", "district": "新莊", "risk_total": 99.0},
    ]


def test_build_peer_group_filters_by_dimensions():
    """同儕群組只納入同 (park_type, size_band, district) 的成員（R13.1）。"""
    pop = _pop()
    entity = pop[0]  # A：公立/中/板橋
    group = build_peer_group(entity, pop)
    assert isinstance(group, PeerGroup)
    assert group.by == DEFAULT_PEER_KEYS
    ids = {m["park_id"] for m in group.members}
    assert ids == {"A", "B", "C", "D", "E"}  # 不含非營利/大/新莊 的 F
    assert group.size == 5


def test_build_peer_group_includes_entity_when_absent():
    """受評機構不在 population 時仍納入群組自身（供含自身百分位）。"""
    pop = _pop()
    entity = {"park_id": "Z", "park_type": "公立", "size_band": "中",
              "district": "板橋", "risk_total": 25.0}
    group = build_peer_group(entity, pop)
    assert entity in group.members
    assert group.size == 6  # A–E + Z


def test_build_peer_group_custom_dimensions():
    """可自訂分群維度。"""
    pop = _pop()
    entity = pop[5]  # F：非營利
    group = build_peer_group(entity, pop, by=("park_type",))
    ids = {m["park_id"] for m in group.members}
    assert ids == {"F"}


# --------------------------------------------------------------------------
# peer_stats — 正常統計量（R13.2, R13.3）
# --------------------------------------------------------------------------
def test_peer_stats_median_percentile_zscore():
    """中位數/百分位/z-score 與參考實作一致（R13.2）。"""
    pop = _pop()[:5]  # 值 10,20,30,40,50
    entity = pop[2]   # C = 30
    group = build_peer_group(entity, pop)
    pc = peer_stats(entity, group, metric="risk_total")

    assert isinstance(pc, PeerComparison)
    assert pc.insufficient is False
    assert pc.sample_n == 5
    assert pc.median == 30.0

    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values)
    assert pc.z_score == round((30.0 - mean) / stdev, 4)

    # 百分位：≤30 的有 3 筆 / 5 = 60%
    assert pc.percentile == 60.0


def test_peer_stats_position_labels():
    """相對位置標籤依 z-score 判定（R13.3）。"""
    pop = _pop()[:5]
    group = build_peer_group(pop[0], pop)

    low = peer_stats({"risk_total": 10.0}, group)
    high = peer_stats({"risk_total": 50.0}, group)
    mid = peer_stats({"risk_total": 30.0}, group)

    assert low.position == "低於同儕"
    assert high.position == "高於同儕"
    assert mid.position == "接近同儕"


def test_peer_stats_percentile_within_range():
    """百分位恆落於 0–100（R13.2）。"""
    pop = _pop()[:5]
    group = build_peer_group(pop[0], pop)
    for v in (0.0, 10.0, 30.0, 50.0, 100.0):
        pc = peer_stats({"risk_total": v}, group)
        assert 0.0 <= pc.percentile <= 100.0


def test_peer_stats_robust_deviation_uses_mad():
    """穩健偏差以中位數與 MAD 為基礎（R13.2）。"""
    pop = _pop()[:5]  # 10,20,30,40,50 → median 30, abs dev [20,10,0,10,20], MAD=10
    group = build_peer_group(pop[0], pop)
    pc = peer_stats({"risk_total": 50.0}, group)
    expected = round((50.0 - 30.0) / (1.4826 * 10.0), 4)
    assert pc.robust_deviation == expected


# --------------------------------------------------------------------------
# peer_stats — 邊界與缺值（R13.4 及穩健性）
# --------------------------------------------------------------------------
def test_peer_stats_insufficient_sample():
    """群組樣本數低於門檻標記 insufficient（R13.4）。"""
    pop = [
        {"park_id": "A", "park_type": "公立", "size_band": "小", "district": "三重", "risk_total": 10.0},
        {"park_id": "B", "park_type": "公立", "size_band": "小", "district": "三重", "risk_total": 20.0},
    ]
    entity = pop[0]
    group = build_peer_group(entity, pop)
    assert group.size < MIN_PEER_SAMPLE
    pc = peer_stats(entity, group)
    assert pc.insufficient is True
    assert pc.position == "樣本不足"


def test_peer_stats_zero_stdev_gives_zero_zscore():
    """群組值全相同（stdev==0）時 z-score 與穩健偏差為 0，不拋例外。"""
    pop = [{"park_id": str(i), "park_type": "公立", "size_band": "中",
            "district": "板橋", "risk_total": 42.0} for i in range(6)]
    entity = pop[0]
    group = build_peer_group(entity, pop)
    pc = peer_stats(entity, group)
    assert pc.insufficient is False
    assert pc.z_score == 0.0
    assert pc.robust_deviation == 0.0


def test_peer_stats_entity_value_missing():
    """受評機構該指標缺值時仍回報群組中位數但個體統計量無法計算。"""
    pop = _pop()[:5]
    group = build_peer_group(pop[0], pop)
    pc = peer_stats({"risk_total": None}, group)
    assert pc.value is None
    assert pc.median == 30.0
    assert pc.percentile is None
    assert pc.position == "無法判定"


def test_peer_stats_ignores_non_numeric_and_bool():
    """非數值與布林值不計入群組統計。"""
    pop = [
        {"park_id": "A", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 10.0},
        {"park_id": "B", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 20.0},
        {"park_id": "C", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 30.0},
        {"park_id": "D", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 40.0},
        {"park_id": "E", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": 50.0},
        {"park_id": "F", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": "N/A"},
        {"park_id": "G", "park_type": "公立", "size_band": "中", "district": "板橋", "risk_total": True},
    ]
    entity = pop[0]
    group = build_peer_group(entity, pop)
    pc = peer_stats(entity, group)
    # 只計入 5 筆有效數值（排除 "N/A" 與 True）
    assert pc.sample_n == 5
    assert pc.median == 30.0
