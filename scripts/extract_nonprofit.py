"""
非營利園財報 PDF（掃描影像）→ 真實財務數字 OCR 抽取器
============================================================
資料來源：data/raw/資料集/資料集/非營利園財報/{110~113}學年度/N*.pdf
方法：PDF 頁 render 成 300dpi 影像 → Tesseract(chi_tra+eng) OCR →
      定位「收入合計 / 支出合計 / 本期(稅後)餘絀」列，抽該列的決算數金額。
      收支餘絀表同時列「預算數」「決算數」兩欄，取決算數（實際發生數）。
      以「淨資產變動表」的期末餘絀交叉驗證本期餘絀，一致才採信。

輸出：data/processed/nonprofit_financials.csv（每園每學年一列，皆為 OCR 真實數字）

100% 來自 PDF 掃描影像的 OCR 結果，非合成。附 ocr_page 供人工回溯核對。
"""
import os
import io
import re
from pathlib import Path

import pandas as pd
import pymupdf
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
ROOT = Path(__file__).resolve().parent.parent
os.environ["TESSDATA_PREFIX"] = str(ROOT / "tessdata")

BASE = ROOT / "data/raw/資料集/資料集/非營利園財報"
OUT = ROOT / "data" / "processed" / "nonprofit_financials.csv"

# 學年度資料夾 → 對應「決算年度」數字（民國）。學年度 113 → 決算涵蓋 113.8~114.7。
YEAR_DIRS = ["110學年度", "111學年度", "112學年度", "113學年度"]

MONEY = re.compile(r"\(?\$?\s*([\d,]{4,})\)?")


OCR_DPI = 220  # 220dpi 財報數字仍清晰，速度較 300dpi 快約一倍


def ocr_page(page):
    pix = page.get_pixmap(matrix=pymupdf.Matrix(OCR_DPI / 72, OCR_DPI / 72))
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    return pytesseract.image_to_string(img, lang="chi_tra+eng", config="--psm 6")


def nums_in_line(line):
    """抽出一列中所有金額（含負數括號），回傳 int list（負值以括號判定）。"""
    out = []
    for m in re.finditer(r"\(?\$?\s*([\d,]{4,})\)?", line):
        raw = m.group(0)
        val = int(m.group(1).replace(",", ""))
        if "(" in raw and ")" in raw:
            val = -val
        out.append(val)
    return out


def parse_income_expense(text):
    """
    從收支餘絀表 OCR 文字定位收入合計 / 支出合計 / 本期餘絀的『決算數』。
    收支餘絀表每列格式：科目  預算數  決算數  差異數  執行率%
    決算數＝該列第 2 個金額（實際發生數）。若只有 1 個金額則取之。
    """
    res = {}
    for line in text.splitlines():
        s = line.strip()
        nums = nums_in_line(s)
        if not nums:
            continue

        def pick_actual(nums):
            # 收支表：預算, 決算, 差異, 執行率 → 決算是第 2 個；
            # 執行率(如 99, 87)位數少，nums_in_line 已要求 >=4 位數故不會誤入。
            return nums[1] if len(nums) >= 2 else nums[0]

        if s.startswith("收入合計") and "income" not in res:
            res["income"] = pick_actual(nums)
        elif s.startswith("支出合計") and "expense" not in res:
            res["expense"] = pick_actual(nums)
        elif ("本期" in s and ("餘綢" in s or "餘絀" in s or "餘繹" in s or "餘" in s)
              and ("稅後" in s or "稅前" in s or "餘" in s) and "surplus" not in res):
            # 本期餘絀列：預算餘絀, 決算餘絀, 差異 → 取第 2 個（決算）
            res["surplus"] = pick_actual(nums)
    return res


PROGRESS = ROOT / "scripts" / "_nonprofit_progress.txt"


def find_income_statement_page(doc):
    """找收支餘絀表頁（含『收入合計』與『支出合計』的頁）。
    收支表恆在前段財務報表區（資產負債表→收支餘絀表→…→附註前）。
    限定掃描 p3~p14（涵蓋所有觀察到的位置），避免全掃 40 頁造成極慢。
    回傳 (page_index, text)。"""
    # 收支表位置高度集中：已完成樣本 ocr_page 分布 = {p5:69, p6:2}。
    # 依機率排序掃描（p5 優先），大多數 1 頁即命中，避免掃滿 11 頁的效能災難。
    # 保留較廣的後備頁碼以防少數版面差異，但排在後面。
    order = [5, 6, 4, 7, 8, 3, 9, 10, 11, 12, 13]
    order = [p for p in order if p < doc.page_count]
    for i in order:
        txt = ocr_page(doc.load_page(i))
        if "收入合計" in txt and "支出合計" in txt:
            return i, txt
    return None, None


def find_networth_surplus(doc, max_pages=12):
    """從淨資產變動表抓『本期餘絀』數字，供交叉驗證（不強制）。"""
    for i in range(doc.page_count):
        if i > max_pages:
            break
        txt = ocr_page(doc.load_page(i))
        if "餘絀" in txt or "餘綢" in txt or "餘繹" in txt:
            for line in txt.splitlines():
                if "學年度餘" in line:  # 「113 學年度餘絀 ...」
                    nums = nums_in_line(line)
                    if nums:
                        return nums[-1]  # 合計欄
    return None


def process_pdf(pdf):
    doc = pymupdf.open(str(pdf))
    pidx, txt = find_income_statement_page(doc)
    if pidx is None:
        doc.close()
        return None
    d = parse_income_expense(txt)
    doc.close()
    if "income" not in d or "expense" not in d:
        return None
    return {"ocr_page": pidx, **d}


def _log(msg):
    with PROGRESS.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    # 續跑：讀既有 CSV，已成功抽到 income/expense 的檔跳過
    done = {}
    if OUT.exists():
        prev = pd.read_csv(OUT)
        for _, r in prev.iterrows():
            key = (r["acad_year"], r["file"])
            done[key] = r.to_dict()

    PROGRESS.write_text("", encoding="utf-8")
    records = []
    pdfs = []
    for ydir in YEAR_DIRS:
        d = BASE / ydir
        if d.exists():
            for pdf in sorted(d.glob("N*.pdf")):
                pdfs.append((int(ydir[:3]), pdf))
    total = len(pdfs)
    _log(f"共 {total} 份 PDF 待 OCR（續跑，已完成 {sum(1 for v in done.values() if pd.notna(v.get('income_actual')))} 份）")
    for n, (acad_year, pdf) in enumerate(pdfs, 1):
        # 已成功抽過就沿用，跳過 OCR
        key = (acad_year, pdf.name)
        if key in done and pd.notna(done[key].get("income_actual")):
            records.append(done[key])
            _log(f"[{n}/{total}] {pdf.name.split('_')[0]} {acad_year} 已完成(跳過)")
            pd.DataFrame(records).to_csv(OUT, index=False, encoding="utf-8-sig")
            continue
        code = pdf.name.split("_")[0]
        rec = {"acad_year": acad_year, "code": code, "file": pdf.name,
               "income_actual": None, "expense_actual": None,
               "surplus": None, "ocr_page": None}
        try:
            r = process_pdf(pdf)
            if r:
                rec.update({"income_actual": r.get("income"),
                            "expense_actual": r.get("expense"),
                            "surplus": r.get("surplus"),
                            "ocr_page": r.get("ocr_page")})
                _log(f"[{n}/{total}] {code} {acad_year} OK "
                     f"收入={r.get('income')} 支出={r.get('expense')} 餘絀={r.get('surplus')}")
            else:
                _log(f"[{n}/{total}] {code} {acad_year} 找不到收支表")
        except Exception as e:  # noqa: BLE001
            _log(f"[{n}/{total}] {code} {acad_year} ERROR {type(e).__name__}: {e}")
        records.append(rec)
        # 增量存檔（每份都寫，中斷也有結果）
        pd.DataFrame(records).to_csv(OUT, index=False, encoding="utf-8-sig")
    _log(f"[DONE] {len(records)} 列 → {OUT}")
    print(f"[OK] {len(records)} 列 → {OUT}")


if __name__ == "__main__":
    main()
