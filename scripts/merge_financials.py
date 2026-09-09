"""
合併公校 + 非營利園真實財務 → data/processed/financials.csv
============================================================
- 公校：來自 src/extract_public.py（決算書文字層，含 detail_amounts 供真班佛）
- 非營利園：來自 scripts/extract_nonprofit.py（掃描檔 OCR，收入/支出）
  併 data/external/nonprofit.csv 取園名/行政區；
  surplus 若 OCR 未抽到，用 income-expense 補算（會計恆等式，可靠）；
  income_last_year/expense_last_year 用同園前一學年度值（供年增率/跨年度）。

所有數字 100% 來自 PDF（公校文字層 + 非營利園 OCR），無合成值。
輸出覆蓋 financials.csv，供 src/risk_score.py 產生介面 CSV。
"""
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
EXT = ROOT / "data" / "external"
FIN = PROC / "financials.csv"

FIELDS = ["park_id", "park_name", "park_type", "year",
          "income_actual", "income_last_year",
          "expense_actual", "expense_last_year",
          "tuition_actual", "surplus", "fund_balance_end",
          "detail_amounts"]


def build_nonprofit_rows():
    npf = pd.read_csv(PROC / "nonprofit_financials.csv")
    meta = pd.read_csv(EXT / "nonprofit.csv")  # code, short_name, park_name, district
    meta_by_code = meta.set_index("code").to_dict("index")

    # ---- OCR 修正表（經淨資產變動表交叉驗證後的真值）----
    # key: (code, 學年度) -> {income, expense, surplus}
    # N34 佳和 113：收支表 OCR 把支出決算誤抄成收入決算(15,622,560)且餘絀誤判 -926,600；
    #   經 p6 本期稅後餘絀決算 145,750 與 p7 淨資產變動表相互佐證，修正如下：
    #   收入 15,622,560（原即正確）、餘絀 +145,750、支出 = 收入 - 餘絀 = 15,476,810。
    OCR_FIX = {
        ("N34", 113): {"income": 15622560, "expense": 15476810, "surplus": 145750},
    }

    # code 對齊：nonprofit_financials 的 code 是 'N01安溪' → 取 'N01'
    npf["code_norm"] = npf["code"].str.extract(r"^(N\d+)")
    npf = npf[npf["income_actual"].notna() & npf["expense_actual"].notna()].copy()

    rows = []
    # 依園分組，算前一學年度值
    for code_norm, g in npf.groupby("code_norm"):
        g = g.sort_values("acad_year").reset_index(drop=True)
        m = meta_by_code.get(code_norm, {})
        park_name = m.get("park_name", f"{code_norm}非營利幼兒園")
        prev_income = prev_expense = None
        for _, r in g.iterrows():
            yr = int(r["acad_year"])
            fix = OCR_FIX.get((code_norm, yr))
            if fix:
                income = fix["income"]
                expense = fix["expense"]
                surplus = fix["surplus"]
            else:
                income = int(r["income_actual"])
                expense = int(r["expense_actual"])
                # surplus：OCR 有就用，否則用會計恆等式補算
                if pd.notna(r.get("surplus")):
                    surplus = int(r["surplus"])
                else:
                    surplus = income - expense
            rows.append({
                "park_id": code_norm,
                "park_name": park_name,
                "park_type": "非營利",
                "year": int(r["acad_year"]),
                "income_actual": income,
                "income_last_year": prev_income,
                "expense_actual": expense,
                "expense_last_year": prev_expense,
                "tuition_actual": None,   # 非營利收支表未單列學雜費，誠實留空
                "surplus": surplus,
                "fund_balance_end": None,
                # 非營利園無逐筆明細（OCR 只取彙總），班佛改用群體檢定，個別留空
                "detail_amounts": "",
            })
            prev_income, prev_expense = income, expense
    return pd.DataFrame(rows)


def main():
    pub = pd.read_csv(FIN)  # 現有公校 financials
    pub = pub[pub["park_type"] == "公校"] if "park_type" in pub.columns else pub
    npdf = build_nonprofit_rows()

    merged = pd.concat([pub[FIELDS], npdf[FIELDS]], ignore_index=True)
    merged.to_csv(FIN, index=False, encoding="utf-8-sig")

    n_pub = (merged["park_type"] == "公校").sum()
    n_np = (merged["park_type"] == "非營利").sum()
    print(f"[OK] financials.csv 共 {len(merged)} 列（公校 {n_pub} + 非營利 {n_np}）")


if __name__ == "__main__":
    main()
