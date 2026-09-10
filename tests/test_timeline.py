"""
風險時間軸與變化點偵測單元測試（Timeline & Change-Point Unit Tests）
======================================================================
對應 Task 7.1（src/timeline.py），驗證 build_timeline / detect_change_points
的具體行為與邊界（R12.1, R12.2, R12.3, R12.4, R5.3）。

註：Property 18（時間軸排序與完整）與 Property 36（變化點標記與說明）之
屬性測試屬於獨立的選用任務 7.2 / 7.3，本檔僅涵蓋具體範例與邊界之單元測試。
"""
from src.timeline import (
    DEFAULT_YOY_THRESHOLD,
    DEFAULT_Z_THRESHOLD,
    MIN_SERIES_LENGTH,
    ChangePoint,
    RiskTimeline,
    TimelinePoint,
    build_timeline,
    detect_change_points,
)


# --------------------------------------------------------------------------
# build_timeline（R12.1, R5.3）
# --------------------------------------------------------------------------
def test_build_timeline_sorts_oldest_to_newest():
    """時間軸依年度由舊到新排序（R5.3, R12.1）。"""
    records = [
        {"park_id": "A", "year": 114, "risk_total": 60.0},
        {"park_id": "A", "year": 112, "risk_total": 20.0},
        {"park_id": "A", "year": 113, "risk_total": 40.0},
    ]
    tl = build_timeline(records)
    assert isinstance(tl, RiskTimeline)
    assert tl.years == [112, 113, 114]
    assert [p.value for p in tl.points] == [20.0, 40.0, 60.0]


def test_build_timeline_covers_all_available_years():
    """時間軸涵蓋所有可取得年度，不遺漏（R12.1）。"""
    records = [
        {"year": 110, "risk_total": 10.0},
        {"year": 111, "risk_total": 15.0},
        {"year": 112, "risk_total": 20.0},
        {"year": 113, "risk_total": 25.0},
    ]
    tl = build_timeline(records)
    assert tl.years == [110, 111, 112, 113]
    assert len(tl.points) == 4


def test_build_timeline_resolves_entity_id():
    """未指定 entity_id 時由紀錄推得。"""
    records = [{"park_id": "P123", "year": 112, "risk_total": 30.0}]
    tl = build_timeline(records)
    assert tl.entity_id == "P123"


def test_build_timeline_missing_metric_keeps_year_with_none():
    """指標缺值時仍保留該年度（value=None），確保覆蓋完整（R12.1）。"""
    records = [
        {"year": 112, "risk_total": 20.0},
        {"year": 113},  # 缺指標
        {"year": 114, "risk_total": 50.0},
    ]
    tl = build_timeline(records)
    assert tl.years == [112, 113, 114]
    assert tl.points[1].value is None


def test_build_timeline_skips_unparseable_year():
    """無法解析年度的紀錄被略過，不中斷其餘（穩健性）。"""
    records = [
        {"year": 112, "risk_total": 20.0},
        {"year": None, "risk_total": 99.0},  # 無效年度
        {"year": 113, "risk_total": 40.0},
    ]
    tl = build_timeline(records)
    assert tl.years == [112, 113]


def test_build_timeline_custom_metric_and_year_alias():
    """支援自訂指標欄位與年度別名（年度/fiscal_year）。"""
    records = [
        {"年度": 113, "personnel_ratio": 0.7},
        {"年度": 112, "personnel_ratio": 0.5},
    ]
    tl = build_timeline(records, metric="personnel_ratio")
    assert tl.metric == "personnel_ratio"
    assert tl.years == [112, 113]
    assert [p.value for p in tl.points] == [0.5, 0.7]


def test_build_timeline_empty_input():
    """空輸入回傳空時間軸，不拋例外。"""
    tl = build_timeline([])
    assert tl.points == []
    assert tl.years == []


# --------------------------------------------------------------------------
# detect_change_points — YoY 突變判準（R12.2, R12.3）
# --------------------------------------------------------------------------
def test_detect_change_points_yoy_spike():
    """明顯年度突變被標記為變化點（R12.2, R12.3）。"""
    # 100 → 105（+5%）→ 200（+90%）：第三點觸發 YoY 判準。
    series = [100.0, 105.0, 200.0]
    cps = detect_change_points(series)
    assert len(cps) >= 1
    cp = cps[-1]
    assert isinstance(cp, ChangePoint)
    assert cp.index == 2
    assert cp.direction == "上升"
    assert cp.yoy_rate is not None and cp.yoy_rate >= DEFAULT_YOY_THRESHOLD


def test_detect_change_points_downward():
    """向下突變被標記且方向為下降。"""
    series = [100.0, 100.0, 40.0]  # -60%
    cps = detect_change_points(series)
    assert len(cps) >= 1
    assert cps[-1].direction == "下降"


def test_detect_change_points_trigger_is_non_empty():
    """每個變化點皆附非空觸發指標說明（R12.4）。"""
    series = [50.0, 50.0, 120.0]
    cps = detect_change_points(series, metric="income_growth")
    assert len(cps) >= 1
    for cp in cps:
        assert cp.trigger
        assert cp.trigger.strip() != ""
        assert "income_growth" in cp.trigger


def test_detect_change_points_stable_series_no_change():
    """平穩序列（小幅波動）不產生變化點。"""
    series = [100.0, 101.0, 100.5, 99.5, 100.0]
    cps = detect_change_points(series)
    assert cps == []


def test_detect_change_points_robust_zscore_outlier():
    """穩健 z-score 判準捕捉相對歷史的顯著離群點（R12.2）。"""
    # 穩定歷史後出現極端跳動，觸發穩健 z-score 判準。
    series = [10.0, 10.0, 10.0, 10.0, 100.0]
    cps = detect_change_points(series)
    assert len(cps) >= 1
    last = cps[-1]
    assert last.index == 4
    # z-score 或 yoy 至少一項達標；此案例 yoy 也達標，確認被標記即可。
    assert last.trigger


# --------------------------------------------------------------------------
# detect_change_points — 邊界與穩健性（R12.3）
# --------------------------------------------------------------------------
def test_detect_change_points_too_short_returns_empty():
    """序列過短（有效點 < MIN_SERIES_LENGTH）回傳空清單。"""
    assert detect_change_points([100.0, 200.0]) == []
    assert detect_change_points([100.0]) == []
    assert detect_change_points([]) == []
    assert MIN_SERIES_LENGTH == 3


def test_detect_change_points_skips_none_values():
    """None 值被略過但既有歷史仍作為基準，不拋例外。"""
    series = [100.0, None, 105.0, 300.0]
    cps = detect_change_points(series)
    # 有效點為 [100, 105, 300]，最後一點觸發突變，index 指向原始序列位置 3。
    assert len(cps) >= 1
    assert cps[-1].index == 3


def test_detect_change_points_previous_zero_no_yoy():
    """前值為 0 時 YoY 不可計算（None），改由穩健 z-score 判定，不拋例外。"""
    series = [0.0, 0.0, 0.0, 50.0]
    cps = detect_change_points(series)
    # 不應因除以零而拋例外；是否標記取決於穩健 z-score。
    for cp in cps:
        # 前值為 0 者其 yoy_rate 應為 None。
        if cp.previous_value == 0.0:
            assert cp.yoy_rate is None


def test_detect_change_points_sorted_by_index():
    """回傳的變化點依 index（時間先後）由小到大排序。"""
    series = [100.0, 100.0, 300.0, 300.0, 900.0]
    cps = detect_change_points(series)
    indices = [cp.index for cp in cps]
    assert indices == sorted(indices)


def test_detect_change_points_custom_thresholds():
    """可自訂門檻：提高 YoY 門檻使小幅變化不再被標記。"""
    series = [100.0, 100.0, 140.0]  # +40%
    # 預設門檻 0.30 → 標記
    assert len(detect_change_points(series)) >= 1
    # 門檻拉高到 0.50 且 z 門檻拉高 → 不標記
    cps = detect_change_points(series, z_threshold=100.0, yoy_threshold=0.50)
    assert cps == []


def test_build_and_detect_integration():
    """build_timeline 產出後接 detect_change_points 的整合路徑。"""
    records = [
        {"park_id": "X", "year": 114, "risk_total": 90.0},
        {"park_id": "X", "year": 112, "risk_total": 30.0},
        {"park_id": "X", "year": 113, "risk_total": 30.0},
    ]
    tl = build_timeline(records)
    series = [p.value for p in tl.points]
    assert series == [30.0, 30.0, 90.0]
    cps = detect_change_points(series, metric=tl.metric)
    assert len(cps) >= 1
    assert cps[-1].index == 2
    assert cps[-1].direction == "上升"
    assert DEFAULT_Z_THRESHOLD > 0
    assert isinstance(TimelinePoint(year=112, value=1.0), TimelinePoint)
