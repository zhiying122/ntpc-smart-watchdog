"""
新北市非營利幼兒園財務報告自動下載（延長單園時間軸的資料來源）
======================================================================
從「新北市幼兒教育資源網 - 非營利幼兒園財務資訊公告」頁面，自動下載全市
非營利幼兒園各學年度之財務報告 PDF。檔名帶園所編號（N01~N38），與系統
park_id 命名一致，便於後續抽取/OCR 併入多年度資料集（kindergartens.csv），
補齊單園跨年度時間軸。

此腳本只負責「下載存檔」；抽取數字仍走既有 pipeline（src/ocr_nonprofit.py
等）。下載檔案存至 data/external/nonprofit_reports/<學年度>/。

已知財報頁（各學年一頁，可續增）：
  113 學年度：/p/406-1000-14552,r122.php
用法：
    python scripts/fetch_nonprofit_reports.py
    python scripts/fetch_nonprofit_reports.py --year 113
"""
from __future__ import annotations

import os
import re
import ssl
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://kidedu.ntpc.edu.tw"
OUT_DIR = os.path.join(ROOT, "data", "external", "nonprofit_reports")

# 學年度 → 財報公告頁路徑（可續補其他學年頁面）。
YEAR_PAGES = {
    "113": "/p/406-1000-14552,r122.php",
}

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    data = urllib.request.urlopen(req, timeout=60, context=_ctx).read()
    return data if binary else data.decode("utf-8", "replace")


def _safe_name(label: str) -> str:
    """由連結顯示名清出安全檔名；無則回空。"""
    label = re.sub(r"<[^>]+>", "", label)
    label = re.sub(r"\s+", " ", label).strip()
    # 只留合法檔名字元
    return re.sub(r'[\\/:*?"<>|]', "_", label)


def download_year(year: str) -> int:
    page = YEAR_PAGES.get(year)
    if not page:
        print(f"[!] 未登錄 {year} 學年度的財報頁，略過。")
        return 0
    html = _get(BASE + page)
    links = re.findall(
        r'href="(/app/index\.php\?Action=downloadfile[^"]+)"[^>]*>(.*?)</a>',
        html, re.S)
    out_dir = os.path.join(OUT_DIR, year)
    os.makedirs(out_dir, exist_ok=True)
    n_ok = 0
    seen = set()
    for href, label in links:
        fname = _safe_name(label)
        if not fname.lower().endswith(".pdf") or fname in seen:
            continue
        seen.add(fname)
        url = BASE + href.replace("&amp;", "&")
        dest = os.path.join(out_dir, fname)
        try:
            data = _get(url, binary=True)
            if data[:4] != b"%PDF":
                print(f"  [!] 非 PDF，略過：{fname}")
                continue
            with open(dest, "wb") as fh:
                fh.write(data)
            n_ok += 1
            print(f"  [OK] {fname}（{len(data)//1024} KB）")
            time.sleep(0.5)  # 禮貌延遲
        except Exception as e:  # noqa: BLE001
            print(f"  [FAIL] {fname}: {e}")
    print(f"[OK] {year} 學年度：下載 {n_ok} 份財報 → {out_dir}")
    return n_ok


def main():
    years = []
    if "--year" in sys.argv:
        years = [sys.argv[sys.argv.index("--year") + 1]]
    else:
        years = list(YEAR_PAGES.keys())
    total = 0
    for y in years:
        print(f"[i] 抓取 {y} 學年度非營利幼兒園財報…")
        total += download_year(y)
    print(f"[完成] 共下載 {total} 份財報 PDF。")


if __name__ == "__main__":
    main()
