"""
加入示範用「國小附設幼兒園」（無獨立財報 → 行為監測園 behavioral）
==================================================================
目的：證明雙評分檔（R26）能對「無財報附幼」自動切換為 behavioral 評分檔。
這些園在決算書層級無獨立財務餘絀表（財務併入母校國小），故 income/expense/surplus
留空 → resolve_scoring_profile 會自動判為 behavioral，套用「裁罰/評鑑/輿情」權重。

附幼的裁罰/評鑑資料來源為全國教保資訊網（題目允許之自蒐公開資料），此處以少量
示範資料佐證架構；正式資料待主辦方確認範圍後接入。標示為抽樣示範（R26.10）。

安全：僅「附加」附幼列到 financials_combined.csv，不覆寫既有 157 列真實財務資料。
可重複執行（先移除既有同 park_id 的示範列再加，冪等）。
"""
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMBINED = ROOT / "data" / "processed" / "financials_combined.csv"
PENALTIES = ROOT / "data" / "external" / "penalties.csv"

# 示範附幼（無財報）。park_id 以 A 開頭標示 affiliated，避免與公校 136xx/非營利 N 衝突。
import json

# 示範附幼（無財報）。park_id 以 A 開頭標示 affiliated，避免與公校 136xx/非營利 N 衝突。
# A01 板橋附幼帶「逐筆裁罰明細」（含日期）→ 破窗效應生效，可攤開累積軌跡（R25.7）。
# 軌跡刻意設計為「頻率遞增、時間越來越近」的破窗惡化樣態：
#   2024-02 行政(輕微) → 2024-11 收費(中度) → 2025-06 人力(中度) → 2026-05 安全(重大)
AFFILIATED = [
    {"park_id": "A01", "park_name": "新北市板橋區板橋國民小學附設幼兒園",
     "park_type": "公立附幼", "year": 114, "scoring_profile": "behavioral",
     "penalty_count": 4, "penalty_reason": "照顧安全疑慮與多次收費違規", "eval_grade": "乙",
     "penalty_records": json.dumps([
         {"date": "2024-02-15", "reason": "資料未依規公開"},
         {"date": "2024-11-03", "reason": "超收幼生與收費違規"},
         {"date": "2025-06-20", "reason": "進用未具資格人員"},
         {"date": "2026-05-08", "reason": "照顧安全疑慮與設施缺失"},
     ], ensure_ascii=False)},
    {"park_id": "A02", "park_name": "新北市三重區三重國民小學附設幼兒園",
     "park_type": "公立附幼", "year": 114, "scoring_profile": "behavioral",
     "penalty_count": 1, "penalty_reason": "設施安全缺失", "eval_grade": "良",
     "penalty_records": ""},
    {"park_id": "A03", "park_name": "新北市新莊區新莊國民小學附設幼兒園",
     "park_type": "公立附幼", "year": 114, "scoring_profile": "behavioral",
     "penalty_count": 0, "penalty_reason": "", "eval_grade": "優",
     "penalty_records": ""},
]


def main():
    df = pd.read_csv(COMBINED)
    # 冪等：移除既有示範附幼列
    ids = {a["park_id"] for a in AFFILIATED}
    df = df[~df["park_id"].isin(ids)].copy()

    # 確保欄位存在（scoring_profile / penalty_records）。
    if "scoring_profile" not in df.columns:
        df["scoring_profile"] = "forensic"
    if "penalty_records" not in df.columns:
        df["penalty_records"] = ""

    # 附幼列：財務欄位全留空（無獨立財報）→ 自動 behavioral。
    fin_rows = []
    for a in AFFILIATED:
        row = {c: None for c in df.columns}
        row["park_id"] = a["park_id"]
        row["park_name"] = a["park_name"]
        row["park_type"] = a["park_type"]
        row["year"] = a["year"]
        row["scoring_profile"] = a["scoring_profile"]
        row["detail_amounts"] = ""
        # 逐筆裁罰明細（含日期）→ 破窗效應生效（R25.7）。
        row["penalty_records"] = a.get("penalty_records", "")
        fin_rows.append(row)
    out = pd.concat([df, pd.DataFrame(fin_rows)], ignore_index=True)
    out.to_csv(COMBINED, index=False, encoding="utf-8-sig")
    print(f"[OK] 已加入 {len(AFFILIATED)} 間示範附幼（behavioral）→ {COMBINED} 共 {len(out)} 列")

    # 併入附幼的裁罰/評鑑到 penalties.csv（供 _merge_external 帶入裁罰分）。
    pen = pd.read_csv(PENALTIES)
    pen = pen[~pen["park_name"].isin([a["park_name"] for a in AFFILIATED])].copy()
    if "penalty_records" not in pen.columns:
        pen["penalty_records"] = ""
    pen_rows = [{"park_name": a["park_name"], "penalty_count": a["penalty_count"],
                 "penalty_reason": a["penalty_reason"], "eval_grade": a["eval_grade"],
                 "penalty_records": a.get("penalty_records", "")}
                for a in AFFILIATED]
    pen_out = pd.concat([pen, pd.DataFrame(pen_rows)], ignore_index=True)
    pen_out.to_csv(PENALTIES, index=False, encoding="utf-8-sig")
    print(f"[OK] 已加入附幼裁罰/評鑑 → {PENALTIES} 共 {len(pen_out)} 列")


if __name__ == "__main__":
    main()
