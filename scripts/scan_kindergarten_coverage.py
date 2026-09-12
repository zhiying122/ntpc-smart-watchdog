"""
一次性掃描：確認公校決算書 PDF 內幼兒園（含國小附設幼兒園）涵蓋情況。
不修改任何資料，只印出事實供決策：
  - 每一冊裡「附設幼兒園 / 附幼」「XX幼兒園」出現次數
  - 「基金來源、用途及餘絀表」出現次數（代表有獨立財務餘絀表的單位數）
  - 抽樣列出偵測到的幼兒園名稱（獨立市立園 vs 國小附設園）
"""
import re
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "E_教育局-資料集" / "資料集" / "公校"

# 每年度五冊全掃，確認附幼是否只在第5冊或散在其他冊
YEARS = [112, 113, 114]
BOOKS = [1, 2, 3, 4, 5]

RE_INDEP = re.compile(r"新北市立(\S{1,8}?幼兒園)")           # 獨立市立幼兒園
RE_AFFIL = re.compile(r"(\S{2,12}?(?:國民小學|國小|國民中學|高級中學|高中)\S{0,6}?附設幼兒園)")
RE_ANY_KG = re.compile(r"(\S{0,12}?幼兒園)")
RE_YUXU = re.compile(r"基金來源[、,]?\s*用途及餘絀表")
RE_CODE = re.compile(r"(136\d\d)-\d")


def book_path(year: int, book: int) -> Path:
    d = BASE / f"{year}年度決算書" / f"第{book}冊"
    # 檔名格式：114年決算書第五冊.pdf（用中文冊號）
    cn = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五"}[book]
    return d / f"{year}年決算書第{cn}冊.pdf"


def scan_book(year: int, book: int):
    p = book_path(year, book)
    if not p.exists():
        return None
    doc = pymupdf.open(str(p))
    full = []
    for i in range(doc.page_count):
        full.append(doc.load_page(i).get_text())
    doc.close()
    text = "\n".join(full)

    indep = set(RE_INDEP.findall(text))
    affil = set(RE_AFFIL.findall(text))
    yuxu_count = len(RE_YUXU.findall(text))
    codes = set(RE_CODE.findall(text))
    affil_word_hits = text.count("附設幼兒園")

    return {
        "year": year, "book": book, "pages": len(full),
        "indep_parks": indep,
        "affil_parks": affil,
        "affil_word_hits": affil_word_hits,
        "yuxu_count": yuxu_count,
        "codes_136xx": codes,
    }


def main():
    print("=" * 70)
    print("公校決算書 幼兒園涵蓋掃描")
    print("=" * 70)
    for year in YEARS:
        for book in BOOKS:
            r = scan_book(year, book)
            if r is None:
                print(f"[{year} 第{book}冊] 缺檔，跳過")
                continue
            print(f"\n[{year} 第{book}冊] 共 {r['pages']} 頁")
            print(f"  獨立市立幼兒園 (新北市立XX幼兒園): {len(r['indep_parks'])} 種")
            print(f"  國小附設幼兒園 (XX附設幼兒園): {len(r['affil_parks'])} 種")
            print(f"  '附設幼兒園' 字樣出現次數: {r['affil_word_hits']}")
            print(f"  '基金來源、用途及餘絀表' 出現次數: {r['yuxu_count']}")
            print(f"  136xx 園編號 種類: {len(r['codes_136xx'])}")
            if r["indep_parks"]:
                print(f"  [獨立園樣本] {sorted(list(r['indep_parks']))[:8]}")
            if r["affil_parks"]:
                print(f"  [附設園樣本] {sorted(list(r['affil_parks']))[:8]}")


if __name__ == "__main__":
    main()
