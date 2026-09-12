"""
家長版地圖標記與關注度分級（Parent Map & Attention Level）— 純邏輯
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的地圖標記「呈現無關」
核心邏輯。本模組**不 import streamlit / folium**，只把機構列轉為家長版的
標記描述（ParentMarker），由頁面薄包裝交給 folium 繪製。

刻意與公務後台區隔（責任 AI，最重要的設計原則）：
--------------------------------------------------------------------------
1. **不重用後台的「風險」詞彙**。後台 Fiscalint 的 risk_total / risk_level
   來自財務鑑識，家長版的分級來自「網路公開輿情」，兩者資料基礎完全不同。
   若沿用「高/中/低風險」會讓家長誤以為兩者可信度相同。故家長版一律使用
   **「近期關注度（Attention Level）」** 這組描述性、非判斷性的詞彙：
       - calm    平靜期      近期無明顯集中的公開討論
       - active  有討論      出現一些公開討論，屬常見範圍
       - watch   值得留意    近期某主題討論量或負面比例出現變化，建議向園所查證
2. **柔和色階**：不用刺眼的警報紅。最高等級（值得留意）用暖琥珀，其餘用
   沉穩藍與安靜綠。避免造成家長不必要的恐慌。
3. **分級必附依據**：每一等級都帶「幾則討論、時間區間、資料來源」，讓家長
   自行判斷可信度，而非只丟一個標籤。
4. **不作違法/舞弊指控**：本模組不輸出任何指控性語言。

本模組的關注度分級直接取用 sentiment_watch.AttentionSummary 的結果；若某機構
無輿情資料，則標記為「尚無公開輿情資料」的中性狀態（灰），不臆測、不留白。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 家長版關注度等級（刻意獨立於後台 risk_level）
# ---------------------------------------------------------------------------
LEVEL_CALM = "calm"       # 平靜期
LEVEL_ACTIVE = "active"   # 有討論
LEVEL_WATCH = "watch"     # 值得留意
LEVEL_NONE = "none"       # 尚無公開輿情資料（中性）

#: 家長友善的等級顯示名稱（描述性、非判斷性）。
LEVEL_LABEL: dict[str, str] = {
    LEVEL_CALM: "平靜期",
    LEVEL_ACTIVE: "有討論",
    LEVEL_WATCH: "值得留意",
    LEVEL_NONE: "尚無公開輿情資料",
}

#: 每一等級的家長友善說明（一句話講清楚「這代表什麼、不代表什麼」）。
LEVEL_DESC: dict[str, str] = {
    LEVEL_CALM: "近期網路上沒有明顯集中的公開討論。",
    LEVEL_ACTIVE: "近期出現一些公開討論，屬常見範圍，可作為了解園所的參考。",
    LEVEL_WATCH: "近期某個主題的討論量或負面比例出現變化，建議家長可進一步向園所查證。",
    LEVEL_NONE: "目前尚未蒐集到此機構的公開網路討論，並非機構有無問題之判斷。",
}

# ---------------------------------------------------------------------------
# 柔和色階（刻意避開後台高飽和警報紅）
# ---------------------------------------------------------------------------
#: 標記主色（十六進位）。watch 用暖琥珀而非警報紅，降低恐慌感。
COLOR_CALM = "#5B9E7A"     # 安靜綠（沉穩、不刺眼）
COLOR_ACTIVE = "#5B84B1"   # 沉穩藍
COLOR_WATCH = "#D99A4E"    # 暖琥珀（提醒，非警報）
COLOR_NONE = "#AEB4BC"     # 中性灰
COLOR_HOME = "#3A6EA5"     # 家的位置（穩重藍）

LEVEL_COLOR: dict[str, str] = {
    LEVEL_CALM: COLOR_CALM,
    LEVEL_ACTIVE: COLOR_ACTIVE,
    LEVEL_WATCH: COLOR_WATCH,
    LEVEL_NONE: COLOR_NONE,
}

#: folium 內建 marker 的 icon 顏色只支援有限色名，這裡對應到最接近的柔和色名。
#: （頁面若改用 CircleMarker 則直接用上面的十六進位色，不受此限制。）
LEVEL_FOLIUM_COLOR: dict[str, str] = {
    LEVEL_CALM: "green",
    LEVEL_ACTIVE: "blue",
    LEVEL_WATCH: "orange",
    LEVEL_NONE: "lightgray",
}


def level_label(level: str) -> str:
    """回傳等級的家長友善顯示名稱；未知等級退回中性。"""
    return LEVEL_LABEL.get(level, LEVEL_LABEL[LEVEL_NONE])


def level_desc(level: str) -> str:
    """回傳等級的家長友善說明；未知等級退回中性說明。"""
    return LEVEL_DESC.get(level, LEVEL_DESC[LEVEL_NONE])


def color_for_level(level: str) -> str:
    """回傳等級對應的柔和色（十六進位）；未知等級回中性灰。"""
    return LEVEL_COLOR.get(level, COLOR_NONE)


def folium_color_for_level(level: str) -> str:
    """回傳 folium marker 可用的色名；未知等級回 lightgray。"""
    return LEVEL_FOLIUM_COLOR.get(level, "lightgray")


def _is_missing(v: object) -> bool:
    if v is None:
        return True
    try:
        return bool(math.isnan(float(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _clean(v: object) -> str:
    if _is_missing(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


# ---------------------------------------------------------------------------
# 家長版地圖標記描述（呈現無關）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ParentMarker:
    """家長版單一機構的地圖標記描述。

    僅含公開、非判斷性欄位：
      - name / ownership（公私立別）/ district：公開基本資訊。
      - lat / lng：座標（資料檔已提供）。
      - distance_km：距家長輸入位置的距離（公里）；未提供家位置時為 None。
      - attention_level：家長版關注度等級（calm/active/watch/none），來自輿情。
      - attention_basis：該等級的「依據」文字（幾則討論、時間區間、來源），
        供地圖卡片與圖例直接顯示，落實「分級必附依據」。

    不變式（責任 AI）：本物件不含任何後台風險分數/等級欄位，亦不含指控性語言。
    """
    park_id: str
    name: str
    ownership: str
    district: str
    lat: float | None
    lng: float | None
    attention_level: str = LEVEL_NONE
    attention_basis: str = ""
    distance_km: float | None = None
    has_coords: bool = False

    @property
    def level_label(self) -> str:
        return level_label(self.attention_level)

    @property
    def color(self) -> str:
        return color_for_level(self.attention_level)

    @property
    def folium_color(self) -> str:
        return folium_color_for_level(self.attention_level)


def build_marker(
    row: dict,
    *,
    attention_level: str = LEVEL_NONE,
    attention_basis: str = "",
    distance_km: float | None = None,
) -> ParentMarker:
    """由機構列（去識別化後的公開欄位）建立家長版標記描述。

    座標缺失時 has_coords=False，頁面應略過繪製該點。attention_level 與
    attention_basis 由呼叫端依 sentiment_watch 結果帶入；無輿情資料時維持
    預設的中性 none 狀態。

    參數
    ----
    row:
        單筆機構公開資料（dict），至少含 park_name / park_type / district /
        lat / lng。此列應為 permissions.authorize_dataframe(ROLE_PARENT) 投影
        後的資料，不含任何風險欄位。
    """
    name = _clean(row.get("park_name")) or "（未命名機構）"
    ownership = _clean(row.get("park_type"))
    district = _clean(row.get("district"))
    park_id = _clean(row.get("park_id"))

    lat_raw, lng_raw = row.get("lat"), row.get("lng")
    has_coords = not _is_missing(lat_raw) and not _is_missing(lng_raw)
    try:
        lat = float(lat_raw) if has_coords else None
        lng = float(lng_raw) if has_coords else None
    except (TypeError, ValueError):
        lat = lng = None
        has_coords = False

    return ParentMarker(
        park_id=park_id,
        name=name,
        ownership=ownership,
        district=district,
        lat=lat,
        lng=lng,
        attention_level=attention_level if attention_level in LEVEL_LABEL else LEVEL_NONE,
        attention_basis=attention_basis,
        distance_km=distance_km,
        has_coords=has_coords,
    )


# ---------------------------------------------------------------------------
# 圖例（供頁面顯示，集中定義確保與標記色一致）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LegendItem:
    level: str
    label: str
    color: str
    desc: str


def legend_items(include_home: bool = True) -> list[LegendItem]:
    """回傳地圖圖例項目（依關注度由低到高，最後附「您的位置」）。

    圖例文字與標記色來自同一組常數，確保地圖與圖例語意一致。
    """
    items = [
        LegendItem(LEVEL_CALM, LEVEL_LABEL[LEVEL_CALM], COLOR_CALM, LEVEL_DESC[LEVEL_CALM]),
        LegendItem(LEVEL_ACTIVE, LEVEL_LABEL[LEVEL_ACTIVE], COLOR_ACTIVE, LEVEL_DESC[LEVEL_ACTIVE]),
        LegendItem(LEVEL_WATCH, LEVEL_LABEL[LEVEL_WATCH], COLOR_WATCH, LEVEL_DESC[LEVEL_WATCH]),
        LegendItem(LEVEL_NONE, LEVEL_LABEL[LEVEL_NONE], COLOR_NONE, LEVEL_DESC[LEVEL_NONE]),
    ]
    if include_home:
        items.append(LegendItem("home", "您輸入的位置", COLOR_HOME, "以此為中心搜尋附近機構。"))
    return items
