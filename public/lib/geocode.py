"""
地理編碼與距離計算（Geocoding & Distance）— 公眾查詢網專用純邏輯
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的「呈現無關」地理工具。

技術決策（project-vision）：
--------------------------------------------------------------------------
- 地址轉座標一律使用 **Nominatim（OpenStreetMap 免費服務）**，不使用 Google
  Maps API（免金鑰、避免金鑰誤傳 GitHub、開源專業度更高）。
- 距離計算採 **Haversine 公式**（大圓距離），純數學、無外部相依，離線可算。

本模組不 import streamlit，不含任何呈現副作用；Nominatim 查詢由呼叫端負責
以 st.cache_data 包裝快取，避免對公共服務造成過量請求（遵守其使用政策：
每秒至多一次請求、需帶可識別的 User-Agent）。

責任 AI / 合規：僅將家長輸入之地址轉為座標以計算鄰近機構，不儲存、不回傳
任何可識別個人身分之資料至第三方。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

import requests

try:  # 套件情境（public/lib 在 sys.path）
    from lib import ntpc_districts as _nd  # type: ignore
except Exception:  # pragma: no cover - 檔案路徑載入後備
    import ntpc_districts as _nd  # type: ignore

#: Nominatim 公共服務端點（OpenStreetMap）。
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

#: 依 Nominatim 使用政策需帶可識別的 User-Agent（含用途與聯絡方式）。
_USER_AGENT = "SmartWatchdog-ParentPortal/1.0 (kindergarten public info lookup)"

#: 台灣本島大致經緯度範圍，用於過濾明顯離譜的地理編碼結果。
_TW_LAT_RANGE = (21.5, 25.5)
_TW_LNG_RANGE = (119.5, 122.5)

#: 新北市大致中心（板橋一帶），供地址查無結果時的地圖預設中心。
DEFAULT_CENTER: tuple[float, float] = (25.0116, 121.4657)


@dataclass(frozen=True)
class GeocodeResult:
    """單次地理編碼結果（呈現無關）。

    - ok=True 時 lat/lng 為有效座標、display_name 為定位到的地址描述。
    - ok=False 時 lat/lng 為 None，message 說明失敗原因（供頁面顯示友善提示）。
    - precision：定位精度，供頁面提示家長「定位到哪一層」：
        'address'（門牌/完整地址）/ 'street'（路名）/ 'district'（行政區中心）/
        ''（失敗）。
    - notice：非致命的補充提示（如「已定位到最接近的道路/行政區」），ok=True 時
      仍可能有值，供頁面提醒家長定位精度。
    """
    ok: bool
    lat: float | None = None
    lng: float | None = None
    display_name: str = ""
    message: str = ""
    precision: str = ""
    notice: str = ""


def _in_taiwan(lat: float, lng: float) -> bool:
    """座標是否落在台灣本島合理範圍（過濾錯誤定位）。"""
    return (_TW_LAT_RANGE[0] <= lat <= _TW_LAT_RANGE[1]
            and _TW_LNG_RANGE[0] <= lng <= _TW_LNG_RANGE[1])


# 門牌/樓層等細節詞：退化查詢時逐步剝除，提高 Nominatim 命中率。
_HOUSE_NO_RE = re.compile(r"\d+\s*(號|樓|F|f).*$")
_LANE_RE = re.compile(r"\d+\s*(巷|弄).*$")


def _query_nominatim(q: str, *, timeout: float) -> tuple[float, float, str] | None:
    """對 Nominatim 發一次查詢，成功且落在台灣則回 (lat,lng,display)，否則 None。

    連線/解析錯誤一律回 None（由上層決定退化或改用離線後備），不拋例外。
    """
    params = {
        "q": q, "format": "json", "limit": 1, "countrycodes": "tw",
        "accept-language": "zh-TW", "addressdetails": 0,
    }
    try:
        resp = requests.get(
            NOMINATIM_URL, params=params,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-TW"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data: Any = resp.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None
    top = data[0]
    try:
        lat, lng = float(top["lat"]), float(top["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_taiwan(lat, lng):
        return None
    return lat, lng, str(top.get("display_name", q))


def _query_structured(params: dict, *, timeout: float) -> tuple[float, float, str] | None:
    """以 Nominatim 結構化查詢（street/city/county 分欄）發一次請求。

    台灣門牌在 OpenStreetMap 覆蓋稀疏，且自由文字 `q=` 常查無；改用結構化查詢
    並將門牌號置於路名前（`street='90 瓊林路'`），命中率明顯較高、可達門牌級。
    連線/解析錯誤或落在台灣範圍外皆回 None。
    """
    p = {"format": "json", "limit": 1, "countrycodes": "tw",
         "accept-language": "zh-TW", "addressdetails": 0}
    p.update(params)
    try:
        resp = requests.get(
            NOMINATIM_URL, params=p,
            headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-TW"},
            timeout=timeout,
        )
        resp.raise_for_status()
        data: Any = resp.json()
    except (requests.RequestException, ValueError):
        return None
    if not isinstance(data, list) or not data:
        return None
    top = data[0]
    try:
        lat, lng = float(top["lat"]), float(top["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not _in_taiwan(lat, lng):
        return None
    return lat, lng, str(top.get("display_name", ""))


@dataclass(frozen=True)
class _ParsedAddress:
    """由自由地址字串解析出的結構化欄位（皆可能為空字串）。"""
    county: str      # 縣市（如「新北市」）
    district: str    # 行政區（如「新莊區」）
    road: str        # 路/街/大道（含段，如「文化路一段」）
    house_no: str    # 門牌號（純數字，如「90」）


# 縣市（本平台聚焦新北，但解析保留一般性）。
_COUNTY_RE = re.compile(r"(台北市|臺北市|新北市|基隆市|桃園市|[\u4e00-\u9fff]{1,3}[縣市])")
# 路/街/大道 + 可選「N段」。擷取到「段」為止（不含巷弄門牌）。
_ROAD_RE = re.compile(r"([\u4e00-\u9fff0-9]{1,10}(?:路|街|大道|大街))(?:([一二三四五六七八九十\d]{1,3})段)?")
# 門牌號：路名之後、接「號」的數字（也接受「N-N號」取主號）。
_HOUSE_RE = re.compile(r"(\d+)(?:-\d+)?\s*號")


def parse_address(address: str) -> _ParsedAddress:
    """把自由地址字串解析為結構化欄位（縣市/行政區/路名/門牌）。

    盡力而為的規則式解析：抓縣市、以行政區資料表比對行政區、抓路名（含段）、
    抓門牌號。任一欄抓不到即為空字串，由查詢端決定如何退化。
    """
    t = (address or "").strip()

    county = ""
    mc = _COUNTY_RE.search(t)
    if mc:
        county = mc.group(1)

    district = _nd.find_district_in_text(t) or ""

    # 先把縣市與行政區（含去「區」短名）從字串移除，避免路名正則把前綴一起吞掉。
    rest = t
    if county:
        rest = rest.replace(county, "")
    if district:
        rest = rest.replace(district, "")
        short = district[:-1] if district.endswith("區") else district
        if short:
            rest = rest.replace(short, "")
    rest = rest.strip()

    road = ""
    mr = _ROAD_RE.search(rest)
    if mr:
        road = mr.group(1)
        if mr.group(2):
            road = f"{road}{mr.group(2)}段"

    house_no = ""
    mh = _HOUSE_RE.search(rest)
    if mh:
        house_no = mh.group(1)

    return _ParsedAddress(county=county, district=district, road=road, house_no=house_no)


def _degrade_variants(q: str) -> list[tuple[str, str]]:
    """由完整地址產生「由細到粗」的查詢變體清單：[(查詢字串, 精度標記), ...]。

    例：「新北市新莊區瓊林路90號」→
        [(原字串,'address'), ('新北市新莊區瓊林路','street'),
         ('新北市新莊區','district')]
    去重並保序，讓上層依序嘗試，命中即止。
    """
    variants: list[tuple[str, str]] = [(q, "address")]

    # 剝除門牌/樓層 → 路名層。
    street = _HOUSE_NO_RE.sub("", q).strip()
    street = _LANE_RE.sub("", street).strip()
    street = re.sub(r"[，,、\s]+$", "", street)
    if street and street != q:
        variants.append((street, "street"))

    # 行政區層（用行政區資料表找到區名，組成「新北市OO區」）。
    dist = _nd.find_district_in_text(q)
    if dist:
        variants.append((f"新北市{dist}", "district"))

    # 去重保序。
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for v, p in variants:
        if v and v not in seen:
            seen.add(v)
            out.append((v, p))
    return out


def geocode_address(address: str, *, timeout: float = 8.0) -> GeocodeResult:
    """將家長輸入的地址轉為經緯度（多段退化 + 離線行政區後備）。

    設計（確保新北市任何行政區都能定位）：
      1. 依「由細到粗」順序向 Nominatim 查詢：完整地址（含門牌）→ 路名 →
         行政區。任一段命中即回傳，並以 precision/notice 標明定位到哪一層，
         讓家長知道「門牌查不到，已定位到最接近的道路/行政區」。
      2. 線上全部查無、或服務無法連線時，若地址含新北市行政區名，改用內建的
         **離線行政區中心座標**定位（precision='district'），保證不因單一門牌
         查無而卡住。
      3. 完全無法辨識（非新北市、無有效地名）才回傳 ok=False 與友善提示。

    查詢限定台灣（countrycodes=tw）並附繁中語系，回傳座標再過濾台灣範圍，
    避免同名地點定位到海外。本函式可能發出多次網路請求；呼叫端應以快取包裝。

    參數
    ----
    address:
        家長輸入的地址字串（如「新北市新莊區瓊林路90號」）。
    timeout:
        單次請求逾時秒數。

    回傳
    ----
    GeocodeResult
    """
    q = (address or "").strip()
    if not q:
        return GeocodeResult(ok=False, message="請輸入地址後再查詢。")

    parsed = parse_address(q)

    # ---- 第 1 順位：結構化「門牌級」查詢（命中率最高，可達確切門牌）----
    # Nominatim 結構化查詢要求門牌號在路名之前（street='90 瓊林路'）。
    if parsed.road and parsed.house_no and parsed.district:
        hit = _query_structured(
            {"street": f"{parsed.house_no} {parsed.road}",
             "city": parsed.district,
             "county": parsed.county or "新北市"},
            timeout=timeout,
        )
        if hit:
            lat, lng, display = hit
            # 確認回傳確實含門牌（display 內有「號」）才標為 address 級。
            precise = "號" in display
            return GeocodeResult(
                ok=True, lat=lat, lng=lng,
                display_name=display or q,
                precision="address" if precise else "street",
                notice="" if precise else "找不到確切門牌，已定位到最接近的道路。",
            )

    # ---- 第 2 順位：結構化「路名級」查詢 ----
    if parsed.road and parsed.district:
        hit = _query_structured(
            {"street": parsed.road, "city": parsed.district,
             "county": parsed.county or "新北市"},
            timeout=timeout,
        )
        if hit:
            lat, lng, display = hit
            has_house = "號" in display
            return GeocodeResult(
                ok=True, lat=lat, lng=lng, display_name=display or q,
                precision="address" if has_house else "street",
                notice=("" if has_house or not parsed.house_no
                        else "找不到確切門牌，已定位到最接近的道路。"),
            )

    # ---- 第 3 順位：自由文字退化查詢（原地址 → 去門牌 → 行政區字串）----
    # 使用者是否真的輸入了門牌號——只有輸入了門牌卻無法精確定位時，才提示
    # 「找不到確切門牌」；若使用者本來就只給到路名或行政區，就不該顯示該提示。
    user_gave_house = bool(parsed.house_no)
    variants = _degrade_variants(q)
    online_reached = False
    for query, precision in variants:
        hit = _query_nominatim(query, timeout=timeout)
        if hit is None:
            continue
        online_reached = True
        lat, lng, display = hit
        has_house = "號" in display
        if has_house:
            out_prec, notice = "address", ""
        elif precision == "district":
            out_prec = "district"
            notice = ("找不到確切門牌與道路，已定位到該行政區中心。"
                      if user_gave_house else "")
        else:
            out_prec = "street"
            notice = ("找不到確切門牌，已定位到最接近的道路。"
                      if user_gave_house else "")
        return GeocodeResult(
            ok=True, lat=lat, lng=lng, display_name=display,
            precision=out_prec, notice=notice)

    # ---- 第 4 順位：離線行政區後備 ----
    dist = parsed.district or _nd.find_district_in_text(q)
    if dist:
        center = _nd.district_center(dist)
        if center:
            lat, lng = center
            note = ("目前無法取得精確定位，已改用「%s」行政區中心作為參考位置。"
                    % dist)
            return GeocodeResult(ok=True, lat=lat, lng=lng,
                                 display_name=f"新北市{dist}（行政區中心）",
                                 precision="district", notice=note)

    # 完全無法辨識。
    if online_reached:
        msg = "查無此地址，請試著輸入更完整的地址（含縣市與行政區），例如「新北市板橋區文化路」。"
    else:
        msg = ("地址定位服務暫時無法連線；若您的地址在新北市，"
               "請確認有含行政區名（如「新莊區」），我們會以行政區中心為您定位。")
    return GeocodeResult(ok=False, message=msg)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """以 Haversine 公式計算兩座標間的大圓距離（公里）。

    純數學運算、無外部相依。地球半徑取 6371 km。相同座標回傳 0.0。
    """
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def format_distance(km: float) -> str:
    """把距離（公里）格式化為家長易讀字串：<1km 顯示公尺，否則顯示公里。"""
    if km < 1.0:
        return f"{int(round(km * 1000))} 公尺"
    return f"{km:.1f} 公里"
