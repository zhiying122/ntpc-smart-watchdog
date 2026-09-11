"""
公校幼兒園決算書財務抽取（座標定位法，已對 34/34 跨年度交叉驗證）
================================================================
從新北市地方教育發展基金決算書（第5冊，有文字層）抽取各市立幼兒園的
「基金來源、用途及餘絀表」財務數字。用 PyMuPDF 文字座標鎖定「本年度決算數」欄，
依政府會計科目（4基金來源=收入、5基金用途=支出、4S1學雜費、本期賸餘=餘絀）取數。
同頁亦含「上年度決算數」欄 → 供跨年度交叉驗證與 income_last_year/expense_last_year。
另從各園明細頁蒐集逐筆金額（detail_amounts），供班佛定律真檢定。

用法（自動掃 data/raw 三年度第5冊）：
    python -m src.extract_public

輸出：data/processed/financials.csv
契約欄位對齊 src/risk_score.py → src/forensic.analyze 的輸入需求。
"""
import csv
import os
import re

import pymupdf

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "processed")

# 三年度第5冊（市立幼兒園決算，編號 13601 起）
YEAR_PDFS = {
    112: os.path.join(ROOT, "data/raw/資料集/資料集/公校/112年度決算書/第5冊/112年決算書第五冊.pdf"),
    113: os.path.join(ROOT, "data/raw/資料集/資料集/公校/113年度決算書/第5冊/113年決算書第五冊.pdf"),
    114: os.path.join(ROOT, "data/raw/資料集/資料集/公校/114年度決算書/第5冊/114年決算書第五冊.pdf"),
}

# 餘絀表欄位 x 座標窗（探測得出）：本年度決算數靠左整數；上年度決算數在右側
COL_CUR = (283, 355)
COL_PREV = (462, 515)

PARK_NAME_RE = re.compile(r"新北市立(\S+?幼兒園)")
CODE_RE = re.compile(r"(136\d\d)-(\d+)")
NUM_RE = re.compile(r"^-?[\d,]+$")
CJK = re.compile(r"[\u4e00-\u9fff]")
AMOUNT_RE = re.compile(r"[\d,]{4,}")


def _parse_num(s):
    s = s.replace(",", "")
    try:
        return int(s)
    except ValueError:
        return None


def _rows_by_y(words, tol=3):
    words = sorted(words, key=lambda w: (round(w[1] / tol), w[0]))
    out, cur, buf = [], None, []
    for w in words:
        yk = round(w[1] / tol)
        if cur is None:
            cur = yk
        if yk != cur:
            out.append(buf)
            buf, cur = [], yk
        buf.append(w)
    if buf:
        out.append(buf)
    return out


def _joined(lw):
    return "".join(w[4] for w in sorted(lw, key=lambda w: w[0]))


def _num_in_col(lw, col):
    """欄內取決算數：整數（% 有小數點會被排除），取最靠左者＝決算數欄。"""
    lo, hi = col
    cands = [(x0, _parse_num(t)) for x0, _, _, _, t, *_ in lw
             if lo <= x0 <= hi and NUM_RE.match(t) and _parse_num(t) is not None]
    if not cands:
        return None
    cands.sort(key=lambda c: c[0])
    return cands[0][1]


def _subject(joined):
    if joined.startswith("4基金來源"):
        return "income"
    if joined.startswith("5基金用途"):
        return "expense"
    if joined.startswith("4S1學雜費收入") or joined.startswith("4S1"):
        return "tuition"
    # 期初/期末基金餘額：供基金餘額勾稽（期末 = 期初 + 本期賸餘）。
    # 需在「本期賸餘」判斷之前，避免「期初基金餘額」被別的規則吃掉。
    if joined.startswith("期初基金餘額"):
        return "fund_begin"
    if joined.startswith("期末基金餘額"):
        return "fund_end"
    if joined.startswith("本期賸餘"):
        return "surplus"
    return None


def _is_pure_number_row(lw):
    return not any(CJK.search(w[4]) for w in lw)


def _income_actual_on_page(page):
    for lw in _rows_by_y(page.get_text("words")):
        if _joined(lw).startswith("4基金來源"):
            return _num_in_col(lw, COL_CUR)
    return None


def extract_page(page):
    """抽收入/支出/學雜費/餘絀的本年度+上年度決算數（座標法）。"""
    lines = _rows_by_y(page.get_text("words"))
    data = {}
    n = len(lines)
    for idx, lw in enumerate(lines):
        subj = _subject(_joined(lw))
        if not subj or f"{subj}_cur" in data:
            continue
        cur = _num_in_col(lw, COL_CUR)
        prev = _num_in_col(lw, COL_PREV)
        if cur is None and idx + 1 < n and _is_pure_number_row(lines[idx + 1]):
            nxt = lines[idx + 1]
            cur = _num_in_col(nxt, COL_CUR)
            if prev is None:
                prev = _num_in_col(nxt, COL_PREV)
        data[f"{subj}_cur"] = cur
        data[f"{subj}_prev"] = prev
    return data


def _collect_detail_amounts(text):
    """明細頁逐筆金額（供班佛）。取 >=4 位含逗號/長整數的正數。"""
    out = []
    for m in AMOUNT_RE.findall(text):
        v = m.replace(",", "")
        if v.isdigit() and int(v) > 0:
            out.append(int(v))
    return out


def extract_pdf(pdf_path, year):
    """回傳該年度所有幼兒園的財務 record（含 detail_amounts）。"""
    doc = pymupdf.open(pdf_path)
    # 先定位每園餘絀表本表頁
    park_pages = {}  # code -> (name, page_index)
    for i in range(doc.page_count):
        page = doc.load_page(i)
        t = page.get_text()
        if "基金來源、用途及餘絀表" not in t:
            continue
        if _income_actual_on_page(page) is None:
            continue
        m = PARK_NAME_RE.search(t)
        if not m and i > 0:
            m = PARK_NAME_RE.search(doc.load_page(i - 1).get_text())
        if not m:
            continue
        name = m.group(1)
        cm = CODE_RE.search(t)
        code = cm.group(1) if cm else None
        if code is None:
            for j in (i - 1, i + 1):
                if 0 <= j < doc.page_count:
                    cm2 = CODE_RE.search(doc.load_page(j).get_text())
                    if cm2:
                        code = cm2.group(1)
                        break
        key = code or name
        if key not in park_pages:
            park_pages[key] = (name, i, code)

    records = []
    for key, (name, pidx, code) in park_pages.items():
        d = extract_page(doc.load_page(pidx))
        # 明細頁逐筆金額：餘絀表頁之後、下一園之前的明細/用途頁
        details = []
        for j in range(pidx, min(pidx + 8, doc.page_count)):
            tj = doc.load_page(j).get_text()
            if j > pidx and "基金來源、用途及餘絀表" in tj:
                break  # 到下一園
            if "明細表" in tj:
                details.extend(_collect_detail_amounts(tj))
        records.append({
            "park_id": code or "",
            "park_name": f"新北市立{name}",
            "park_type": "公校",
            "year": year,
            "income_actual": d.get("income_cur"),
            "income_last_year": d.get("income_prev"),
            "expense_actual": d.get("expense_cur"),
            "expense_last_year": d.get("expense_prev"),
            "tuition_actual": d.get("tuition_cur"),
            "surplus": d.get("surplus_cur"),
            # 基金餘額勾稽用（本年度決算數欄）：期末 = 期初 + 本期賸餘（− 解繳公庫等調整）。
            "fund_balance_begin": d.get("fund_begin_cur"),
            "fund_balance_end": d.get("fund_end_cur"),
            "detail_amounts": ";".join(str(x) for x in details),
        })
    doc.close()
    return records


FIELDS = ["park_id", "park_name", "park_type", "year",
          "income_actual", "income_last_year",
          "expense_actual", "expense_last_year",
          "tuition_actual", "surplus",
          "fund_balance_begin", "fund_balance_end",
          "detail_amounts"]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    all_records = []
    for year, path in YEAR_PDFS.items():
        if not os.path.exists(path):
            print(f"  年度 {year}: 缺檔 {path}")
            continue
        recs = extract_pdf(path, year)
        print(f"  年度 {year}: 抽出 {len(recs)} 間")
        all_records.extend(recs)

    out = os.path.join(OUT_DIR, "financials.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in all_records:
            w.writerow(r)
    print(f"[OK] 公校共 {len(all_records)} 筆 → {out}")


if __name__ == "__main__":
    main()
