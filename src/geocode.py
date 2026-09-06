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


def geocode_one(address, cache):
    """單一地址轉座標，優先讀快取。回傳 (lat, lng) 或 None。"""
    if address in cache:
        return tuple(cache[address]) if cache[address] else None
    params = urllib.parse.urlencode({
        "q": address, "format": "json", "limit": 1, "countrycodes": "tw",
    })
    url = f"{NOMINATIM}?{params}"
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        if data:
            lat, lng = float(data[0]["lat"]), float(data[0]["lon"])
            cache[address] = [lat, lng]
            return lat, lng
    except Exception as e:
        print(f"    [!] 查詢失敗 {address}: {e}")
    cache[address] = None
    return None


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
            coord = geocode_one(addr, cache)
            time.sleep(1.1)  # 遵守 Nominatim 每秒 1 次規範
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
