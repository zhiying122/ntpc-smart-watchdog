"""
公校幼兒園決算書財務抽取
================================
從新北市地方教育發展基金決算書（第5冊，有文字層）抽取各市立幼兒園的
「基金來源、用途及餘絀表」財務數字。一頁同時含本年度與上年度決算數，
因此單一 PDF 即可取得跨年度資料。

用法：
    python -m src.extract_public "路徑\\114年決算書第五冊.pdf" --year 114

輸出：data/processed/financials.csv
"""
import argparse
import os
import re
import csv

import pdfplumber

# 專案根目錄
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "processed")

# 幼兒園名稱樣式：新北市立OO幼兒園
PARK_NAME_RE = re.compile(r"新北市立([\u4e00-\u9fa5]{1,6})幼兒園")
# 園所編號樣式：13601-4 之類
PARK_ID_RE = re.compile(r"(136\d{2})-")


def _num(s):
    """把 '35,307,451' 轉成 int；抓不到回傳 None。"""
    if s is None:
        return None
    s = s.replace(",", "").strip()
    try:
        return int(round(float(s)))
    except (ValueError, TypeError):
        return None


def _first_amount_after(line, label):
    """
    在某一行找到 label 後的第一個金額數字。
    決算表格式：科目名稱 預算數 % 決算數 % ...
    我們取『本年度決算數』= label 後的第 2 個數字（第1個是預算數）。
    """
    if label not in line:
        return None
    tail = line.split(label, 1)[1]
    nums = re.findall(r"-?[\d,]+(?:\.\d+)?", tail)
    # nums[0]=預算數  nums[1]=預算%  nums[2]=決算數 ...
    # 但%值多為小數，金額多為整數含逗號，改用啟發式：取第一個「像金額」的整數
    ints = [n for n in nums if "," in n or (n.lstrip("-").isdigit() and len(n) >= 4)]
    return ints


def extract_one_page(text):
    """從一頁『基金來源、用途及餘絀表』文字抽出財務欄位。"""
    lines = text.splitlines()
    rec = {}

    for ln in lines:
        # 4 基金來源（收入）：本年度決算數 = 該行第2個大額整數
        if ln.strip().startswith("4 基金來源"):
            ints = _first_amount_after(ln, "基金來源")
            # 格式: 預算數 100.00 決算數 100.00 增減 % 上年度 %
            if len(ints) >= 1:
                rec["income_budget"] = _num(ints[0]) if len(ints) > 0 else None
                rec["income_actual"] = _num(ints[1]) if len(ints) > 1 else None
                rec["income_last_year"] = _num(ints[-1]) if len(ints) >= 3 else None
        # 5 基金用途（支出）
        elif ln.strip().startswith("5 基金用途"):
            ints = _first_amount_after(ln, "基金用途")
            if len(ints) >= 1:
                rec["expense_budget"] = _num(ints[0]) if len(ints) > 0 else None
                rec["expense_actual"] = _num(ints[1]) if len(ints) > 1 else None
                rec["expense_last_year"] = _num(ints[-1]) if len(ints) >= 3 else None
        # 4S 教學收入（學雜費，反映幼兒繳費規模）
        elif "教學收入" in ln:
            ints = _first_amount_after(ln, "教學收入")
            if ints:
                rec["tuition_actual"] = _num(ints[1]) if len(ints) > 1 else _num(ints[0])
        # 期末基金餘額：格式為「預算數 決算數 增減 % 上年度」，取第2個(決算數)
        elif ln.strip().startswith("期末基金餘額"):
            ints = _first_amount_after(ln, "期末基金餘額")
            if ints:
                # 這行無 % 欄位間隔：ints[0]=預算數, ints[1]=決算數
                rec["fund_balance_end"] = _num(ints[1]) if len(ints) > 1 else _num(ints[0])
        # 本期賸餘(短絀)：格式「預算數 決算數 增減 % 上年度」，取第2個(決算數)
        elif "本期賸餘" in ln:
            ints = _first_amount_after(ln, ")")
            if ints:
                rec["surplus"] = _num(ints[1]) if len(ints) > 1 else _num(ints[0])

    return rec


AMOUNT_RE = re.compile(r"[\d,]{4,}")


def collect_detail_amounts(text):
    """從明細頁蒐集逐筆金額（供班佛定律用）。取 >=4 位含逗號的正整數。"""
    out = []
    for m in AMOUNT_RE.findall(text):
        v = m.replace(",", "")
        if v.isdigit() and int(v) > 0:
            out.append(int(v))
    return out


def extract_pdf(pdf_path, year):
    """
    掃描整份決算書，抽出所有幼兒園的：
      1) 餘絀表彙總數字（收入/支出/學雜費/餘額）
      2) 明細逐筆金額清單（供班佛定律用，存成分號分隔字串）
    """
    records = []
    current = None
    detail_buffer = []

    def flush(rec, details):
        if rec is not None:
            rec["detail_amounts"] = ";".join(str(x) for x in details)
            records.append(rec)

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if "幼兒園" not in txt:
                continue

            name_m = PARK_NAME_RE.search(txt)

            # 遇到新園的餘絀表 → 收尾上一間，開新的一間
            if ("基金來源、用途及餘絀表" in txt and "本 年 度 決 算 數" in txt
                    and name_m):
                id_m = PARK_ID_RE.search(txt)
                flush(current, detail_buffer)
                detail_buffer = []
                current = {
                    "park_id": id_m.group(1) if id_m else "",
                    "park_name": f"新北市立{name_m.group(1)}幼兒園",
                    "park_type": "公校",
                    "year": year,
                }
                current.update(extract_one_page(txt))

            # 明細頁 → 累積逐筆金額
            if current is not None and ("明細表" in txt or "各項費用" in txt):
                detail_buffer.extend(collect_detail_amounts(txt))

        flush(current, detail_buffer)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=2, action="append", metavar=("YEAR", "PDF"),
                    required=True, help="可重複：--add 114 路徑 --add 113 路徑")
    ap.add_argument("--out", default=os.path.join(OUT_DIR, "financials.csv"))
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)

    all_records = []
    for year, path in args.add:
        recs = extract_pdf(path, year.strip())
        print(f"  年度 {year}: 抽出 {len(recs)} 間")
        all_records.extend(recs)

    if not all_records:
        print("[!] 沒有抽到任何幼兒園資料，請確認 PDF 路徑與內容。")
        return

    fields = ["park_id", "park_name", "park_type", "year",
              "income_actual", "income_last_year",
              "expense_actual", "expense_last_year",
              "tuition_actual", "surplus", "fund_balance_end",
              "detail_amounts"]

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in all_records:
            w.writerow(r)

    print(f"[OK] 共抽出 {len(all_records)} 筆（跨年度），已寫入 {args.out}")


if __name__ == "__main__":
    main()
