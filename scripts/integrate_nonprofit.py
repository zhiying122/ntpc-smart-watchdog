# -*- coding: utf-8 -*-
"""
將非營利園 OCR 抽取結果併入財務資料集並重建風險評分。
====================================================================
安全原則：
  - 只納入 high / medium 信心的抽取（勾稽通過或可算收支比）；low 信心不納入
    計分（避免以錯誤數字污染風險分，責任 AI）。
  - 以「附加」方式加入非營利園列，不動既有公校 58 列。
  - 產出新的 financials_combined.csv 供 risk_score.build 使用；不覆寫原始
    financials.csv（可回溯、可還原）。
  - 每筆非營利園列標記 data_source 與 needs_review。

用法：python scripts/integrate_nonprofit.py [--min-confidence medium]
"""
import argparse
import glob
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

OCR_DIR = os.path.join(ROOT, "data", "derived", "nonprofit_ocr")
FINANCIALS = os.path.join(ROOT, "data", "processed", "financials.csv")
COMBINED = os.path.join(ROOT, "data", "processed", "financials_combined.csv")

_CONF_RANK = {"low": 0, "medium": 1, "high": 2}


def load_nonprofit_records(min_confidence: str) -> pd.DataFrame:
    """讀取 OCR JSON，篩出達信心門檻者，轉為 financials 格式的列。"""
    min_rank = _CONF_RANK.get(min_confidence, 1)
    rows = []
    for f in sorted(glob.glob(os.path.join(OCR_DIR, "*.json"))):
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        if _CONF_RANK.get(d.get("extraction_confidence"), 0) < min_rank:
            continue
        inc = d.get("income_total")
        exp = d.get("expense_total")
        # 需至少有收入與支出才能算財務指標。
        if inc is None or exp is None:
            continue
        rows.append({
            "park_id": f"{d['code']}",
            "park_name": f"新北市{d['name']}非營利幼兒園",
            "park_type": "非營利",
            "year": d["year"],
            "income_actual": inc,
            "income_last_year": None,   # OCR 未穩定抽取去年欄，留空（引擎容忍）
            "expense_actual": exp,
            "expense_last_year": None,
            "tuition_actual": None,
            "surplus": d.get("surplus"),
            "fund_balance_end": None,
            "detail_amounts": "",       # 無逐筆明細 → 無班佛（引擎以中性處理）
            "data_source": "非營利園財務報告（OCR 抽取）",
            "needs_review": d.get("needs_review", True),
            "extraction_confidence": d.get("extraction_confidence"),
        })
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-confidence", default="medium",
                    choices=["low", "medium", "high"],
                    help="納入計分的最低信心（預設 medium）")
    args = ap.parse_args()

    base = pd.read_csv(FINANCIALS)
    print(f"既有財務列（公校）：{len(base)}")

    np_df = load_nonprofit_records(args.min_confidence)
    print(f"納入的非營利園列（≥{args.min_confidence} 信心）：{len(np_df)}")
    if len(np_df):
        print("  各學年度：",
              np_df["year"].value_counts().sort_index().to_dict())

    # 對齊欄位（base 沒有的補上）。
    for col in np_df.columns:
        if col not in base.columns:
            base[col] = None
    combined = pd.concat([base, np_df], ignore_index=True)
    combined.to_csv(COMBINED, index=False, encoding="utf-8-sig")
    print(f"已輸出合併檔：{os.path.relpath(COMBINED, ROOT)}（{len(combined)} 列）")


if __name__ == "__main__":
    main()
