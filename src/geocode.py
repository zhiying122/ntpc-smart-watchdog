"""
地址轉經緯度座標 (Geocoding)
================================
用免費的 OpenStreetMap Nominatim 服務把幼兒園地址轉成經緯度，
供組員的 Leaflet 地圖標點使用。不需 API 金鑰、不用綁信用卡。

Nominatim 使用規範：每秒最多 1 次請求，需帶 User-Agent。
本模組已內建 1 秒延遲與快取，避免重複查詢。

用法：
    python -m src.geocode
輸入：data/external/addresses.csv
輸出：data/processed/geocoded.csv （park_name, lat, lng）
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDR_CSV = os.path.join(ROOT, "data", "external", "addresses.csv")
OUT_CSV = os.path.join(ROOT, "data", "processed", "geocoded.csv")
CACHE = os.path.join(ROOT, "data", "processed", "geocode_cache.json")

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "ntpc-smart-watchdog/1.0 (hackathon project)"}

# 新北市各行政區中心座標（fallback：地理編碼失敗時用行政區中心點）
DISTRICT_CENTER = {
    "板橋區": (25.0117, 121.4593), "三重區": (25.0614, 121.4870),
    "中和區": (24.9987, 121.4980), "永和區": (25.0077, 121.5150),
    "新店區": (24.9678, 121.5420), "樹林區": (24.9906, 121.4207),
    "鶯歌區": (24.9542, 121.3540), "三峽區": (24.9340, 121.3690),
    "淡水區": (25.1677, 121.4406), "五股區": (25.0827, 121.4380),
    "泰山區": (25.0590, 121.4310), "林口區": (25.0776, 121.3910),
    "深坑區": (25.0022, 121.6160), "三芝區": (25.2580, 121.5010),
    "八里區": (25.1510, 121.3980), "萬里區": (25.1790, 121.6890),
    "烏來區": (24.8650, 121.5510),
    "瑞芳區": (25.1090, 121.8060), "金山區": (25.2220, 121.6360),
    "土城區": (24.9720, 121.4430), "蘆洲區": (25.0850, 121.4740),
    "新莊區": (25.0360, 121.4320),
}


def _load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


# 新北市地理邊界：緯度 24.6~25.35，經度 121.28~122.0
# 東界放寬至 122.0 以涵蓋東北角(瑞芳/金山/萬里/貢寮)，仍可濾掉多數誤匹配
NTPC_BOUNDS = (24.6, 25.35, 121.28, 122.0)


def _in_ntpc(lat, lng):
    la0, la1, lo0, lo1 = NTPC_BOUNDS
    return la0 <= lat <= la1 and lo0 <= lng <= lo1


def _query(q):
    """對 Nominatim 送一次查詢，回傳 (lat,lng) 或 None。"""
    params = urllib.parse.urlencode({
        "q": q, "format": "json", "limit": 1, "countrycodes": "tw",
    })
    url = f"{NOMINATIM}?{params}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if data:
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            # 邊界檢查：超出新北市範圍視為誤匹配，捨棄
            if _in_ntpc(lat, lng):
                return lat, lng
    except Exception as e:
        print(f"    [!] 查詢失敗 {q}: {e}")
    return None


def geocode_one(address, cache, name="", district=""):
    """
    多層查詢策略（由精確到粗略）：
      1) 園所名稱（OSM 常收錄學校/幼兒園 POI）
      2) 完整地址
      3) 行政區 + 幼兒園關鍵字
    優先讀快取。回傳 (lat, lng) 或 None。
    """
    key = f"{name}|{address}"
    if key in cache:
        return tuple(cache[key]) if cache[key] else None

    coord = None
    if name:
        coord = _query(name)
        time.sleep(1.1)
    if coord is None and address:
        coord = _query(address)
        time.sleep(1.1)
    if coord is None and district:
        coord = _query(f"新北市{district} 幼兒園")
        time.sleep(1.1)

    cache[key] = list(coord) if coord else None
    return coord


def run(online=True):
    cache = _load_cache()
    rows = []
    with open(ADDR_CSV, "r", encoding="utf-8-sig") as f:
        reader = list(csv.DictReader(f))

    for i, r in enumerate(reader):
        name = r["park_name"]
        addr = r["address"]
        district = r.get("district", "")
        coord = None
        if online:
            coord = geocode_one(addr, cache, name=name, district=district)
        if coord is None:
            # fallback：用行政區中心
            coord = DISTRICT_CENTER.get(district)
            src = "行政區中心(fallback)"
        else:
            src = "Nominatim"
        if coord:
            rows.append({"park_name": name, "lat": coord[0], "lng": coord[1], "source": src})
            print(f"  [{i+1}/{len(reader)}] {name}: {coord[0]:.4f},{coord[1]:.4f} ({src})")

    _save_cache(cache)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["park_name", "lat", "lng", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] 已寫入 {OUT_CSV}（{len(rows)} 筆）")


if __name__ == "__main__":
    import sys
    # 加 --offline 可跳過網路查詢，直接用行政區中心（Demo 保底）
    run(online="--offline" not in sys.argv)
