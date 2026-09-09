"""
產生 geocoded.csv（park_name, lat, lng, source）涵蓋公校 + 非營利園。
- 公校：用 src.geocode 的 Nominatim 真實地址地理編碼（失敗回退行政區中心）。
- 非營利：用 data/external/nonprofit.csv 的行政區中心（誠實標為概略位置；
  真實精確座標需逐園 geocode 地址，屬後續工作）。
"""
import csv
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import geocode as G  # noqa: E402

OUT = ROOT / "data" / "processed" / "geocoded.csv"


def _jitter(name):
    """依園名決定性微偏移（±0.008度，約±800m），使同區的園在地圖上不完全重疊。
    這只是視覺分散，座標本質為『行政區概略位置』，已於 source 誠實標示。"""
    h = hashlib.md5(name.encode("utf-8")).hexdigest()
    dlat = (int(h[:4], 16) / 0xFFFF - 0.5) * 0.016
    dlng = (int(h[4:8], 16) / 0xFFFF - 0.5) * 0.016
    return dlat, dlng


def main(online=True):
    rows = []
    cache = G._load_cache()

    # 公校：真實地址 geocode
    with open(ROOT / "data/external/addresses.csv", encoding="utf-8-sig") as f:
        pub = list(csv.DictReader(f))
    for i, r in enumerate(pub):
        name, addr, dist = r["park_name"], r["address"], r.get("district", "")
        coord = G.geocode_one(addr, cache, name=name, district=dist) if online else None
        src = "Nominatim"
        if coord is None:
            base = G.DISTRICT_CENTER.get(dist)
            if base:
                dlat, dlng = _jitter(name)
                coord = (base[0] + dlat, base[1] + dlng)
            src = "行政區概略"
        if coord:
            rows.append({"park_name": name, "district": dist, "lat": round(coord[0], 6),
                         "lng": round(coord[1], 6), "source": src})
    G._save_cache(cache)

    # 非營利：優先用 OCR 抽出的真實地址 geocode（精確座標），失敗回退行政區中心。
    with open(ROOT / "data/external/nonprofit.csv", encoding="utf-8-sig") as f:
        npf = list(csv.DictReader(f))
    for r in npf:
        name, dist = r["park_name"], r.get("district", "")
        addr = r.get("address", "")
        coord = None
        src = "行政區概略"
        if online and addr:
            coord = G.geocode_one(addr, cache, name="", district=dist)
            if coord:
                src = "Nominatim(真實地址)"
        if coord is None:
            base = G.DISTRICT_CENTER.get(dist)
            if base:
                dlat, dlng = _jitter(name)
                coord = (base[0] + dlat, base[1] + dlng)
        if coord:
            rows.append({"park_name": name, "district": dist,
                         "lat": round(coord[0], 6), "lng": round(coord[1], 6),
                         "source": src})
    G._save_cache(cache)

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["park_name", "district", "lat", "lng", "source"])
        w.writeheader()
        w.writerows(rows)
    print(f"[OK] geocoded.csv 共 {len(rows)} 筆")


if __name__ == "__main__":
    main(online="--offline" not in sys.argv)
