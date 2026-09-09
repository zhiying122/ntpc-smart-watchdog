"""
非營利園真實地址/行政區抽取（OCR 附註頁「履約地點」）
============================================================
非營利園財報附註頁載有「(五) 履約地點：新北市XX區...路..號」，
這是機構的真實立案地址。OCR 抽出後校正 nonprofit.csv 的行政區（原為推測值），
並提供可精確 geocode 的完整地址。

輸出：data/external/nonprofit_addresses.csv（code, park_name, district, address）
用 113 學年度（最新、最完整 38 間）。附註頁通常在 p8~p12。

100% 來自 PDF OCR，非推測。
"""
import io
import os
import re
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROOT = Path(__file__).resolve().parent.parent
os.environ["TESSDATA_PREFIX"] = str(ROOT / "tessdata")
BASE = ROOT / "data/raw/資料集/資料集/非營利園財報/113學年度"
META = ROOT / "data/external/nonprofit.csv"
OUT = ROOT / "data/external/nonprofit_addresses.csv"
PROGRESS = ROOT / "scripts" / "_addr_progress.txt"

DISTRICTS = ["板橋區", "三重區", "中和區", "永和區", "新莊區", "新店區", "樹林區", "鶯歌區",
             "三峽區", "淡水區", "汐止區", "瑞芳區", "土城區", "蘆洲區", "五股區", "泰山區",
             "林口區", "深坑區", "石碇區", "坪林區", "三芝區", "石門區", "八里區", "平溪區",
             "雙溪區", "貢寮區", "金山區", "萬里區", "烏來區"]

# 履約地點行：擷取「新北市XX區...」到樓層/句尾前的地址
ADDR_CLEAN = re.compile(r"(新北市\S{2,3}區[^\n，,。;；(（]*?\d+\s*號)")


def ocr(page):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(220 / 72, 220 / 72))
    return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png"))),
                                       lang="chi_tra+eng", config="--psm 6")


def extract_addr(pdf):
    doc = pymupdf.open(str(pdf))
    result = None
    for i in range(8, min(doc.page_count, 14)):
        txt = ocr(doc.load_page(i))
        for ln in txt.splitlines():
            if "履約地點" in ln and "新北市" in ln:
                dist = next((d for d in DISTRICTS if d in ln), None)
                # 清理地址（去空白）
                raw = ln.split("履約地點", 1)[1].lstrip(" :：").replace(" ", "")
                m = ADDR_CLEAN.search(raw)
                addr = m.group(1) if m else raw[:40]
                if dist:
                    result = (dist, addr)
                    break
        if result:
            break
    doc.close()
    return result


def main():
    import csv
    meta = {}
    with open(META, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            meta[r["code"]] = r
    PROGRESS.write_text("", encoding="utf-8")

    pdfs = sorted(BASE.glob("N*.pdf"))
    rows = []
    for n, pdf in enumerate(pdfs, 1):
        code = re.match(r"(N\d+)", pdf.name).group(1)
        m = meta.get(code, {})
        res = extract_addr(pdf)
        if res:
            dist, addr = res
        else:
            dist, addr = m.get("district", ""), ""
        rows.append({"code": code, "park_name": m.get("park_name", ""),
                     "district": dist, "address": addr})
        orig = m.get("district", "")
        flag = "" if dist == orig else f"  <<< 原推測 {orig} 校正為 {dist}"
        with PROGRESS.open("a", encoding="utf-8") as pf:
            pf.write(f"[{n}/{len(pdfs)}] {code} {dist} {addr}{flag}\n")

    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["code", "park_name", "district", "address"])
        w.writeheader()
        w.writerows(rows)
    with PROGRESS.open("a", encoding="utf-8") as pf:
        pf.write(f"[DONE] {len(rows)} 筆 → {OUT}\n")


if __name__ == "__main__":
    main()
