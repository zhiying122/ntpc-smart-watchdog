"""
風險地圖核心邏輯（Risk Map Core Logic）
============================================================
小小守護員 Smart Watchdog Platform — 政府指揮中心（Gov_Console）風險地圖的
「呈現無關」（presentation-independent）核心計算邏輯。

技術決策（project-vision）：地圖底圖採 **Leaflet + OpenStreetMap**（免費、
免金鑰、避免金鑰誤傳 GitHub），地址轉座標用免費 Nominatim geocoding。
本模組**不依賴** Streamlit / folium，只負責把契約檔的機構列轉為「可渲染的
標記描述」（MapMarker），Streamlit 地圖頁面（app/pages/2_map.py）應作為薄
包裝（thin wrapper），呼叫本模組取得標記後再交由 folium 繪製。

本模組負責：
- **確定性顏色映射**（R2.4, Property 7）：高→紅、中→黃、低→綠。
- **標記明細**（R2.9）：點選標記顯示機構名稱、風險分數與主要風險訊號。
- **缺資料處理**（R2.10）：標記缺風險分數或主要風險訊號時，顯示機構名稱並
  以「資料尚未提供」標示，而非空白或錯誤。

等級來源（重要）：地圖著色**優先採用契約檔既有的 `risk_level` 欄位**
（由 src/risk_score.py 的分機構類型百分位分級產生，高/中/低），確保與主頁、
排名、KPI 完全一致。僅當某列 `risk_level` 缺失時，才退回以 gov_console.grade()
的絕對門檻即時分級（fallback）。實務上契約檔每列皆有 `risk_level`，故此
fallback 幾乎不會觸發——地圖等級與全站一致，不會出現同園跨頁等級不同。

責任 AI（Responsible AI）：風險（risk）不等於違法（illegality）。本模組僅
呈現分數、等級與風險訊號，不作任何違法/舞弊認定。

對應 design.md「政府指揮中心（R2）」章節與 Property 7。
Validates: Requirements 2.4, 2.9, 2.10
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# 分級門檻與等級標籤沿用 gov_console（單一分級來源）。
# 兼容兩種載入方式：
#   1) 作為套件子模組 `from lib import risk_map`（Streamlit 頁面）→ 相對匯入。
#   2) 以檔案路徑載入（pytest，見 test_gov_console.py 的載入方式）→ 具名匯入。
try:  # 套件情境（app/lib/ 作為 lib 套件）
    from .gov_console import LEVEL_HIGH, LEVEL_LOW, LEVEL_MID, grade
except ImportError:  # 檔案路徑載入情境（測試 / 直接執行）
    from gov_console import (  # type: ignore  # noqa: E402
        LEVEL_HIGH,
        LEVEL_LOW,
        LEVEL_MID,
        grade,
    )

# ---------------------------------------------------------------------------
# 確定性顏色映射（R2.4, Property 7）
# ---------------------------------------------------------------------------
#: 地圖標記顏色：高→紅、中→黃、低→綠（十六進位色碼，供 Leaflet/folium 使用）。
COLOR_HIGH = "#D64545"   # 紅（高風險）
COLOR_MID = "#E0A93B"    # 黃（中風險）
COLOR_LOW = "#3F8F5B"    # 綠（低風險）
#: 等級無法辨識（缺資料/未知）時的中性色（灰），不著紅/黃/綠避免誤導。
COLOR_UNKNOWN = "#9AA0A6"

#: 風險等級 → 顏色的確定映射表（Property 7 的單一事實來源）。
LEVEL_COLOR: dict[str, str] = {
    LEVEL_HIGH: COLOR_HIGH,
    LEVEL_MID: COLOR_MID,
    LEVEL_LOW: COLOR_LOW,
}

#: 缺資料時對使用者顯示的標準提示（R2.10）。
DATA_UNAVAILABLE = "資料尚未提供"


def color_for_level(level: object) -> str:
    """依風險等級回傳確定的地圖標記顏色（R2.4, Property 7）。

    映射為確定（deterministic）：相同等級恆得相同顏色。
        - 「高」→ 紅（COLOR_HIGH）
        - 「中」→ 黃（COLOR_MID）
        - 「低」→ 綠（COLOR_LOW）
        - 其他/缺失 → 中性灰（COLOR_UNKNOWN），避免以紅/黃/綠誤導。

    參數
    ----
    level:
        風險等級標籤（通常為「高」/「中」/「低」字串）。

    回傳
    ----
    str: 十六進位色碼。

    Validates: Requirements 2.4
    """
    return LEVEL_COLOR.get(str(level), COLOR_UNKNOWN)


def _is_missing(v: object) -> bool:
    """判定值是否缺失（None 或 NaN）。"""
    if v is None:
        return True
    try:
        return bool(math.isnan(float(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _clean_str(v: object) -> str:
    """去除頭尾空白並轉為字串；缺失或空白視為空字串。"""
    if _is_missing(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


# ---------------------------------------------------------------------------
# 主要風險訊號抽取（R2.9）
# ---------------------------------------------------------------------------
def build_risk_signals(row: dict, level: str | None = None) -> list[str]:
    """由機構列抽取「主要風險訊號」清單（R2.9）。

    以可解釋、可 Demo 的規則從既有契約欄位導出人類可讀的風險訊號描述：
        - 收支比 > 1（入不敷出）
        - 有裁罰紀錄（penalty_count > 0）
        - 財務分項分數偏高（score_financial >= 40）
    找不到任何具體訊號但等級非「低」時，回傳「綜合風險分數偏高」作為概括訊號；
    等級為「低」時回傳「風險低」。缺欄位一律安全略過（不拋例外）。

    參數
    ----
    row:
        機構單列資料（dict 或可 .get 的 Mapping），欄位對齊契約檔。
    level:
        已解析的風險等級（可能由分數即時分級而來）。傳入時用於概括訊號的
        判定，優先於 row 內的 `risk_level`，確保與標記著色所用等級一致；
        為 None 時退回讀取 row 的 `risk_level`。

    回傳
    ----
    list[str]: 主要風險訊號描述清單（可能為空）。

    Validates: Requirements 2.9
    """
    signals: list[str] = []

    ratio = row.get("expense_income_ratio")
    if not _is_missing(ratio):
        try:
            if float(ratio) > 1:
                signals.append(f"入不敷出（收支比 {float(ratio):.2f}）")
        except (TypeError, ValueError):
            pass

    pen = row.get("penalty_count")
    if not _is_missing(pen):
        try:
            n = int(float(pen))
            if n > 0:
                signals.append(f"裁罰 {n} 次")
        except (TypeError, ValueError):
            pass

    fin = row.get("score_financial")
    if not _is_missing(fin):
        try:
            if float(fin) >= 40:
                signals.append("財務指標異常")
        except (TypeError, ValueError):
            pass

    if not signals:
        lvl = _clean_str(level) if level is not None else _clean_str(row.get("risk_level"))
        if lvl and lvl != LEVEL_LOW:
            signals.append("綜合風險分數偏高")
        elif lvl == LEVEL_LOW:
            signals.append("風險低")

    return signals


# ---------------------------------------------------------------------------
# 標記描述（R2.9, R2.10）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MapMarker:
    """單一地圖標記的呈現描述（presentation-independent）。

    - `has_coords` 為 False 時，該機構無座標，頁面應略過不繪製。
    - `has_data` 為 False 時，缺風險分數或主要風險訊號，頁面應顯示 `name`
      並以 `DATA_UNAVAILABLE`（「資料尚未提供」）標示（R2.10）。
    - `color` 依 `level` 確定映射（R2.4, Property 7）。

    Validates: Requirements 2.4, 2.9, 2.10
    """
    name: str
    lat: float | None
    lng: float | None
    score: float | None
    level: str
    color: str
    signals: list[str] = field(default_factory=list)
    has_coords: bool = False
    has_data: bool = True
    #: 缺資料時的使用者提示（R2.10）；有資料時為空字串。
    unavailable_note: str = ""

    def score_text(self) -> str:
        """風險分數的顯示字串；缺分數時回傳「資料尚未提供」（R2.10）。"""
        if self.score is None:
            return DATA_UNAVAILABLE
        return f"{self.score:.1f}"

    def signals_text(self) -> list[str]:
        """主要風險訊號顯示清單；缺訊號時回傳含「資料尚未提供」的單元素清單。"""
        return list(self.signals) if self.signals else [DATA_UNAVAILABLE]


def build_marker(row: dict,
                 name_col: str = "park_name",
                 score_col: str = "risk_total",
                 level_col: str = "risk_level",
                 lat_col: str = "lat",
                 lng_col: str = "lng") -> MapMarker:
    """由機構列建立地圖標記描述（R2.9, R2.10）。

    - **名稱**：一律取機構名稱；缺名稱時以「（未命名機構）」佔位（仍可上圖）。
    - **顏色**：依 `level_col`（若缺，退而以 `grade(score)` 即時分級）確定映射
      至紅/黃/綠（R2.4, Property 7）。
    - **缺資料（R2.10）**：缺風險分數，或無任何主要風險訊號時，`has_data`
      為 False 並填入 `unavailable_note`＝「資料尚未提供」；此時頁面應顯示名稱
      並標示該提示，而非空白或錯誤。
    - **座標**：缺 lat/lng 時 `has_coords` 為 False，頁面應略過繪製該點。

    參數
    ----
    row:
        機構單列資料（dict 或可 .get 的 Mapping）。
    name_col / score_col / level_col / lat_col / lng_col:
        對應契約檔欄位名。

    回傳
    ----
    MapMarker: 呈現無關的標記描述。

    Validates: Requirements 2.4, 2.9, 2.10
    """
    name = _clean_str(row.get(name_col)) or "（未命名機構）"

    # 座標
    lat_raw = row.get(lat_col)
    lng_raw = row.get(lng_col)
    has_coords = not _is_missing(lat_raw) and not _is_missing(lng_raw)
    try:
        lat = float(lat_raw) if has_coords else None
        lng = float(lng_raw) if has_coords else None
    except (TypeError, ValueError):
        lat = lng = None
        has_coords = False

    # 分數
    score_raw = row.get(score_col)
    if _is_missing(score_raw):
        score = None
    else:
        try:
            score = float(score_raw)
        except (TypeError, ValueError):
            score = None

    # 等級：優先取既有欄位 risk_level（百分位三級，與主頁/排名同源，確保跨頁一致）；
    # 僅在該欄位缺失時才以 grade() 絕對門檻即時分級（fallback）；仍無則空字串（→ 灰色）。
    level = _clean_str(row.get(level_col))
    if not level and score is not None:
        level = grade(score)

    color = color_for_level(level)

    # 主要風險訊號（傳入已解析等級，使概括訊號與著色等級一致）
    signals = build_risk_signals(row, level=level)

    # 缺資料判定（R2.10）：缺分數 或 無主要風險訊號。
    has_data = score is not None and len(signals) > 0
    note = "" if has_data else DATA_UNAVAILABLE

    return MapMarker(
        name=name,
        lat=lat,
        lng=lng,
        score=score,
        level=level,
        color=color,
        signals=signals,
        has_coords=has_coords,
        has_data=has_data,
        unavailable_note=note,
    )


def build_markers(rows, **col_kwargs) -> list[MapMarker]:
    """將多筆機構列轉為標記描述清單（薄包裝頁面一次取得所有標記）。

    參數
    ----
    rows:
        可疊代的機構列（每筆為 dict 或可 .get 的 Mapping）。
    col_kwargs:
        轉傳給 `build_marker` 的欄位名覆寫。

    回傳
    ----
    list[MapMarker]

    Validates: Requirements 2.4, 2.9, 2.10
    """
    return [build_marker(dict(r) if not isinstance(r, dict) else r, **col_kwargs)
            for r in rows]
