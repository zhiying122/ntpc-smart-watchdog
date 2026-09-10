"""
風險地圖核心邏輯測試（Risk Map, R2.4 / R2.9 / R2.10）
======================================================================
驗證 app/lib/risk_map.py：
  - 確定性顏色映射（R2.4）：高→紅、中→黃、低→綠；未知/缺失→中性灰。
  - 標記明細（R2.9）：名稱 + 分數 + 主要風險訊號。
  - 缺資料處理（R2.10）：缺分數或缺訊號 → 顯示名稱並標示「資料尚未提供」。

對應 Task 19.2「實作 Leaflet 風險地圖與標記點選」。
Property 7（地圖顏色映射確定）之屬性測試為 Task 19.3（另行實作），
本檔以單元測試涵蓋顏色映射的確定性與具體案例，及 R2.9/R2.10 行為。

本模組位於 app/lib/（非 src 套件），且 app/ 無 __init__.py，故以檔案路徑
載入（沿用 test_gov_console.py 的載入方式），並先載入其相依的 gov_console。
"""
import importlib.util
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_LIB = os.path.join(_ROOT, "app", "lib")


def _load(mod_name, filename):
    path = os.path.join(_LIB, filename)
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# risk_map 以 try/except 匯入 gov_console；先以「gov_console」名稱載入，
# 使其 except 分支的 `from gov_console import ...` 可解析。
sys.path.insert(0, _LIB)
_load("gov_console", "gov_console.py")
rm = _load("app_lib_risk_map", "risk_map.py")


# ===========================================================================
# 單元測試：確定性顏色映射（R2.4）
# ===========================================================================
def test_color_mapping_high_red():
    assert rm.color_for_level("高") == rm.COLOR_HIGH


def test_color_mapping_mid_yellow():
    assert rm.color_for_level("中") == rm.COLOR_MID


def test_color_mapping_low_green():
    assert rm.color_for_level("低") == rm.COLOR_LOW


def test_color_mapping_unknown_is_neutral():
    """未知/缺失等級 → 中性灰，不誤用紅/黃/綠。"""
    assert rm.color_for_level("未知") == rm.COLOR_UNKNOWN
    assert rm.color_for_level("") == rm.COLOR_UNKNOWN
    assert rm.color_for_level(None) == rm.COLOR_UNKNOWN


def test_color_mapping_deterministic():
    """同一等級多次呼叫恆得相同顏色（確定性）。"""
    for lvl in ("高", "中", "低", "未知"):
        assert rm.color_for_level(lvl) == rm.color_for_level(lvl)
    # 三色互異，避免混淆。
    assert len({rm.COLOR_HIGH, rm.COLOR_MID, rm.COLOR_LOW}) == 3


# ===========================================================================
# 單元測試：標記明細（R2.9）— 名稱 + 分數 + 主要風險訊號
# ===========================================================================
def test_build_marker_full_data():
    row = {
        "park_name": "甲幼兒園",
        "risk_total": 85.0,
        "risk_level": "高",
        "lat": 25.01,
        "lng": 121.46,
        "expense_income_ratio": 1.20,
        "penalty_count": 2,
        "score_financial": 45.0,
    }
    mk = rm.build_marker(row)
    assert mk.name == "甲幼兒園"
    assert mk.score == 85.0
    assert mk.level == "高"
    assert mk.color == rm.COLOR_HIGH
    assert mk.has_coords is True
    assert mk.has_data is True
    assert mk.unavailable_note == ""
    # 主要風險訊號：收支比>1、裁罰、財務異常皆命中。
    assert any("入不敷出" in s for s in mk.signals)
    assert any("裁罰 2 次" == s for s in mk.signals)
    assert "財務指標異常" in mk.signals
    assert mk.score_text() == "85.0"


def test_build_marker_level_from_score_when_missing_level():
    """缺 risk_level 時以 grade(score) 即時分級並著色。"""
    row = {"park_name": "乙園", "risk_total": 30.0, "lat": 25.0, "lng": 121.5}
    mk = rm.build_marker(row)
    assert mk.level == "低"
    assert mk.color == rm.COLOR_LOW
    # 低風險且無其他訊號 → 訊號為「風險低」，仍屬有資料。
    assert mk.signals == ["風險低"]
    assert mk.has_data is True


def test_build_risk_signals_fallback_for_high_without_specifics():
    row = {"risk_level": "高"}
    signals = rm.build_risk_signals(row)
    assert signals == ["綜合風險分數偏高"]


# ===========================================================================
# 單元測試：缺資料處理（R2.10）— 顯示名稱 + 「資料尚未提供」
# ===========================================================================
def test_build_marker_missing_score_marks_unavailable():
    """缺風險分數 → has_data False、note 為「資料尚未提供」，名稱仍在。"""
    row = {"park_name": "丙園", "risk_level": "中", "lat": 25.0, "lng": 121.5}
    mk = rm.build_marker(row)
    assert mk.name == "丙園"
    assert mk.score is None
    assert mk.has_data is False
    assert mk.unavailable_note == rm.DATA_UNAVAILABLE
    assert mk.score_text() == rm.DATA_UNAVAILABLE


def test_build_marker_no_signals_when_no_score_and_no_level():
    """既無分數亦無等級/具體訊號 → 無主要風險訊號 → 標示資料尚未提供（R2.10）。"""
    row = {"park_name": "丁園", "lat": 25.0, "lng": 121.5}
    mk = rm.build_marker(row)
    assert mk.score is None
    assert mk.signals == []          # 無分數→無等級→無概括訊號，且無具體欄位
    assert mk.has_data is False
    assert mk.unavailable_note == rm.DATA_UNAVAILABLE
    # signals_text 缺訊號時回傳含「資料尚未提供」的清單。
    assert mk.signals_text() == [rm.DATA_UNAVAILABLE]


def test_build_marker_signals_use_resolved_level():
    """缺 risk_level 但有分數：概括訊號依即時分級的等級產生（與著色一致）。"""
    # 分數 55 → 中風險（無其他具體訊號）→ 概括訊號「綜合風險分數偏高」。
    mk = rm.build_marker({"park_name": "戊園", "risk_total": 55.0, "lat": 25.0, "lng": 121.5})
    assert mk.level == "中"
    assert mk.color == rm.COLOR_MID
    assert mk.signals == ["綜合風險分數偏高"]
    assert mk.has_data is True


def test_build_marker_name_always_present():
    """完全缺名稱仍有佔位名稱（可上圖、不空白）。"""
    mk = rm.build_marker({"risk_total": 80.0, "risk_level": "高"})
    assert mk.name == "（未命名機構）"


def test_build_marker_missing_coords():
    """缺 lat/lng → has_coords False，頁面應略過繪製。"""
    mk = rm.build_marker({"park_name": "戊園", "risk_total": 80.0, "risk_level": "高"})
    assert mk.has_coords is False
    assert mk.lat is None and mk.lng is None


def test_build_marker_nan_values_safe():
    """NaN 座標/分數不拋例外並正確判為缺失。"""
    nan = float("nan")
    mk = rm.build_marker({"park_name": "己園", "risk_total": nan,
                          "lat": nan, "lng": nan, "risk_level": "高"})
    assert mk.score is None
    assert mk.has_coords is False
    assert mk.has_data is False


# ===========================================================================
# 單元測試：批次建立
# ===========================================================================
def test_build_markers_batch():
    rows = [
        {"park_name": "A", "risk_total": 80.0, "risk_level": "高", "lat": 25.0, "lng": 121.5,
         "penalty_count": 1},
        {"park_name": "B", "risk_total": 30.0, "risk_level": "低", "lat": 25.1, "lng": 121.6},
        {"park_name": "C", "risk_level": "中", "lat": 25.2, "lng": 121.7},  # 缺分數
    ]
    markers = rm.build_markers(rows)
    assert len(markers) == 3
    assert markers[0].color == rm.COLOR_HIGH
    assert markers[1].color == rm.COLOR_LOW
    assert markers[2].has_data is False
    assert markers[2].unavailable_note == rm.DATA_UNAVAILABLE
