"""
政府指揮中心核心邏輯測試（Gov_Console, R2.1–R2.8）
======================================================================
驗證 app/lib/gov_console.py：
  - 風險等級分級門檻（R2.2, Property 5）：>=70 高、40–69 中、<40 低。
  - KPI 計數非負且分類完備（R2.3, Property 6）：high+mid+low == gradable。
  - 排名排序與截斷（R2.5, R2.6, Property 8）：非遞增排序、高風險排名 <= 20。
  - 近三年趨勢（R2.7）：取最近三年、由舊到新排序。
  - 風險熱點（R2.8）：依高風險數聚合排序。

對應 Task 19.1「實作風險等級分級、KPI 計數與排名」。
屬性測試（Property 5/6/8）以 Hypothesis 實作，見本檔末段。

本模組位於 app/lib/（非 src 套件），且 app/ 無 __init__.py，故以檔案路徑載入，
避免更動既有 app/ 套件結構（沿用 test_modes.py 的載入方式）。
"""
import importlib.util
import math
import os
import sys

import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GC_PATH = os.path.join(_ROOT, "app", "lib", "gov_console.py")

_spec = importlib.util.spec_from_file_location("app_lib_gov_console", _GC_PATH)
gc = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = gc
_spec.loader.exec_module(gc)


# ===========================================================================
# 單元測試：分級門檻（R2.2）
# ===========================================================================
def test_grade_boundaries():
    """邊界一致性：恰 70 為高、恰 40 為中、恰 39.99 為低。"""
    assert gc.grade(70) == "高"
    assert gc.grade(69) == "中"
    assert gc.grade(69.9) == "中"
    assert gc.grade(40) == "中"
    assert gc.grade(39.9) == "低"
    assert gc.grade(0) == "低"


def test_grade_typical_values():
    assert gc.grade(100) == "高"
    assert gc.grade(85) == "高"
    assert gc.grade(55) == "中"
    assert gc.grade(10) == "低"


# ===========================================================================
# 單元測試：KPI 計數（R2.3）
# ===========================================================================
def _sample_latest():
    return pd.DataFrame({
        "park_id": ["A", "B", "C", "D", "E"],
        "park_name": ["甲園", "乙園", "丙園", "丁園", "戊園"],
        "district": ["板橋區", "板橋區", "新莊區", "新莊區", "林口區"],
        "risk_total": [85.0, 55.0, 30.0, 72.0, 45.0],
        "risk_level": ["高", "中", "低", "高", "中"],
        "iforest_score": [90.0, 20.0, 10.0, 75.0, 30.0],
    })


def test_kpi_counts_partition():
    df = _sample_latest()
    kpi = gc.kpi_counts(df)
    assert kpi.high == 2      # 85, 72
    assert kpi.mid == 2       # 55, 45
    assert kpi.low == 1       # 30
    assert kpi.gradable == 5
    assert kpi.high + kpi.mid + kpi.low == kpi.gradable
    assert kpi.new_anomaly == 2   # iforest >=70: 90, 75


def test_kpi_counts_handles_missing_scores():
    df = pd.DataFrame({"risk_total": [80.0, None, float("nan"), 30.0]})
    kpi = gc.kpi_counts(df)
    assert kpi.high == 1
    assert kpi.low == 1
    assert kpi.gradable == 2
    assert kpi.ungradable == 2
    assert kpi.high >= 0 and kpi.mid >= 0 and kpi.low >= 0


# ===========================================================================
# 單元測試：排名（R2.5, R2.6）
# ===========================================================================
def test_district_ranking_sorted_desc():
    df = _sample_latest()
    ranks = gc.district_risk_ranking(df)
    avgs = [r.avg_risk for r in ranks]
    assert avgs == sorted(avgs, reverse=True)
    # 新莊區 (30,72)->51, 板橋區 (85,55)->70, 林口區 45
    top = ranks[0]
    assert top.district == "板橋區"


def test_high_risk_ranking_sorted_and_truncated():
    df = _sample_latest()
    ranks = gc.high_risk_ranking(df)
    scores = [r.risk_total for r in ranks]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] == 85.0
    assert len(ranks) <= gc.MAX_RANKING


def test_high_risk_ranking_truncates_to_20():
    df = pd.DataFrame({
        "park_id": [f"P{i:03d}" for i in range(50)],
        "park_name": [f"園{i}" for i in range(50)],
        "district": ["板橋區"] * 50,
        "risk_total": [float(i) for i in range(50)],
    })
    ranks = gc.high_risk_ranking(df)
    assert len(ranks) == 20
    # 最高分應為 49
    assert ranks[0].risk_total == 49.0


# ===========================================================================
# 單元測試：近三年趨勢（R2.7）
# ===========================================================================
def test_risk_trend_recent_three_years_ascending():
    full = pd.DataFrame({
        "park_id": ["A", "A", "A", "A", "B", "B", "B", "B"],
        "year": [111, 112, 113, 114, 111, 112, 113, 114],
        "risk_total": [50, 60, 70, 80, 40, 45, 50, 55],
    })
    trend = gc.risk_trend(full, years=3)
    assert [p.year for p in trend] == [112, 113, 114]  # 舊到新，最近三年
    assert trend[0].year < trend[-1].year


def test_risk_trend_fewer_than_three_years():
    full = pd.DataFrame({
        "year": [113, 114],
        "risk_total": [50, 70],
    })
    trend = gc.risk_trend(full, years=3)
    assert [p.year for p in trend] == [113, 114]


# ===========================================================================
# 單元測試：風險熱點（R2.8）
# ===========================================================================
def test_risk_hotspots_by_high_count():
    df = pd.DataFrame({
        "district": ["板橋區", "板橋區", "板橋區", "新莊區", "林口區"],
        "risk_total": [80, 90, 30, 75, 20],
    })
    hs = gc.risk_hotspots(df)
    assert hs[0].district == "板橋區"
    assert hs[0].high_count == 2
    # 林口區無高風險，不列入
    assert all(h.district != "林口區" for h in hs)


def test_build_overview_end_to_end():
    latest = _sample_latest()
    full = pd.DataFrame({
        "park_id": ["A", "A", "B", "B"],
        "year": [113, 114, 113, 114],
        "risk_total": [50, 85, 40, 55],
    })
    ov = gc.build_overview(latest, full)
    assert ov.kpi.gradable == 5
    assert len(ov.high_risk_ranking) <= gc.MAX_RANKING
    assert len(ov.trend) == 2
    assert isinstance(ov.district_ranking, list)


# ===========================================================================
# 屬性測試（Property-Based Tests, Hypothesis）
# ===========================================================================

# --- Feature: smart-watchdog-platform, Property 5: 風險等級分級門檻 ---
# For any 介於 0 至 100 的風險分數，分級為：>=70 高、40<=分數<=69 中、<40 低。
@settings(max_examples=200)
@given(score=st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False))
def test_property_5_grade_thresholds(score):
    """Validates: Requirements 2.2"""
    level = gc.grade(score)
    if score >= 70:
        assert level == "高"
    elif score >= 40:
        assert level == "中"
    else:
        assert level == "低"
    # 邊界一致性：恰 70 為高、恰 40 為中。
    assert gc.grade(70.0) == "高"
    assert gc.grade(40.0) == "中"


# --- Feature: smart-watchdog-platform, Property 6: KPI 計數非負且分類完備 ---
# For any 機構集合，high/mid/low 皆為非負整數，且三者之和等於可分級機構總數。
@settings(max_examples=200)
@given(scores=st.lists(
    st.one_of(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        st.none(),
    ),
    max_size=60,
))
def test_property_6_kpi_counts_partition(scores):
    """Validates: Requirements 2.3"""
    df = pd.DataFrame({"risk_total": scores})
    kpi = gc.kpi_counts(df)
    # 非負整數
    for c in (kpi.high, kpi.mid, kpi.low, kpi.new_anomaly, kpi.gradable, kpi.ungradable):
        assert isinstance(c, int)
        assert c >= 0
    # 分類完備：high+mid+low == gradable
    assert kpi.high + kpi.mid + kpi.low == kpi.gradable
    # 可分級 + 不可分級 == 總數
    assert kpi.gradable + kpi.ungradable == len(scores)


# --- Feature: smart-watchdog-platform, Property 8: 排名排序與截斷 ---
# For any 機構或行政區集合，排名依風險分數非遞增排序，且高風險機構排名長度不超過 20。
@settings(max_examples=200)
@given(
    scores=st.lists(
        st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False),
        min_size=0, max_size=60,
    ),
    districts=st.lists(
        st.sampled_from(["板橋區", "新莊區", "林口區", "三重區", "中和區"]),
        min_size=0, max_size=60,
    ),
)
def test_property_8_ranking_sorted_and_truncated(scores, districts):
    """Validates: Requirements 2.5, 2.6"""
    n = min(len(scores), len(districts))
    scores = scores[:n]
    districts = districts[:n]
    df = pd.DataFrame({
        "park_id": [f"P{i:04d}" for i in range(n)],
        "park_name": [f"園{i}" for i in range(n)],
        "district": districts,
        "risk_total": scores,
    })

    # 高風險機構排名：非遞增排序 + 長度 <= 20
    inst = gc.high_risk_ranking(df)
    inst_scores = [r.risk_total for r in inst]
    assert inst_scores == sorted(inst_scores, reverse=True)
    assert len(inst) <= gc.MAX_RANKING
    assert len(inst) <= n

    # 行政區排名：依平均風險分非遞增排序
    dranks = gc.district_risk_ranking(df)
    davgs = [r.avg_risk for r in dranks]
    assert davgs == sorted(davgs, reverse=True)
