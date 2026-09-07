"""
前後端資料一致性檢查
======================
檢查三個層面：
  A. 欄位契約：CSV 實際欄位 vs 前端讀取欄位 vs 資料字典宣稱欄位
  B. 計算邏輯：假資料(make_mock_data) 的分數 vs 真引擎(risk_score) 重算的分數
  C. 資料完整性：NaN、型別、值域、去重

輸出：純文字報告到 stdout。
"""
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

PROC = os.path.join(ROOT, "data", "processed")
LATEST = os.path.join(PROC, "kindergartens_latest.csv")
FULL = os.path.join(PROC, "kindergartens.csv")

out = []
def log(s=""):
    out.append(str(s))

# ---------- A. 欄位契約 ----------
log("=" * 60)
log("A. 欄位契約檢查")
log("=" * 60)

latest = pd.read_csv(LATEST)
full = pd.read_csv(FULL)
csv_cols = set(latest.columns)

# 前端各頁實際引用的欄位（掃描 app/ 內 r['x'] / row['x'] / df['x'] / row.get('x')）
app_dir = os.path.join(ROOT, "app")
pat = re.compile(r"""(?:row|r|df|latest|geo|high|hist|view)(?:\.get\(|\[)['"]([a-z_]+)['"]""")
frontend_cols = set()
for dp, _, files in os.walk(app_dir):
    for fn in files:
        if fn.endswith(".py"):
            txt = open(os.path.join(dp, fn), encoding="utf-8").read()
            frontend_cols.update(pat.findall(txt))

# 只保留看起來像資料欄位的（排除 session_state 等）
known = {"park_id", "park_name", "park_type", "year", "district", "lat", "lng",
         "income_actual", "expense_actual", "tuition_actual", "surplus",
         "expense_income_ratio", "benford_mad", "benford_sample_n", "benford_score",
         "benford_chi2", "benford_pvalue", "benford_significant",
         "beneish_score", "beneish_egdi", "beneish_tata", "iforest_score",
         "iforest_explain", "expense_yoy_pct", "penalty_count", "eval_grade",
         "score_financial", "score_penalty", "score_eval", "score_sentiment",
         "neg_ratio", "risk_total", "risk_level", "risk_level_abs"}
frontend_data_cols = frontend_cols & known

missing_in_csv = frontend_data_cols - csv_cols
log(f"CSV 欄位數：{len(csv_cols)}")
log(f"前端引用的資料欄位數：{len(frontend_data_cols)}")
if missing_in_csv:
    log(f"[錯誤] 前端引用但 CSV 缺少的欄位：{sorted(missing_in_csv)}")
else:
    log("[OK] 前端引用的每個欄位都存在於 CSV")

# 資料字典宣稱的欄位（data-dictionary.md 表格內的 code）
dd = os.path.join(ROOT, "docs", "data-dictionary.md")
dd_cols = set()
if os.path.exists(dd):
    ddtxt = open(dd, encoding="utf-8").read()
    for m in re.findall(r"`([a-z_]+)`", ddtxt):
        if m in known:
            dd_cols.add(m)
    dd_missing = dd_cols - csv_cols
    log(f"資料字典提及欄位數：{len(dd_cols)}")
    if dd_missing:
        log(f"[警告] 資料字典提到但 CSV 沒有的欄位：{sorted(dd_missing)}")
    else:
        log("[OK] 資料字典提到的欄位 CSV 都有")

# 真引擎 risk_score 的輸出欄位契約
try:
    from src import risk_score
    engine_cols = set(risk_score.build.__doc__ or "")  # 佔位
    log("[OK] 成功匯入 src.risk_score（真引擎可用）")
except Exception as e:
    log(f"[警告] 無法匯入 src.risk_score：{type(e).__name__}: {e}")

# ---------- B. 計算邏輯一致性（假資料 vs 真引擎重算）----------
log("")
log("=" * 60)
log("B. 計算邏輯一致性（真引擎重算 vs 假CSV記錄）")
log("=" * 60)

# 真引擎需要 financials 欄位當輸入。假 CSV 已含這些欄位，抽出來組成 financials 樣式
fin_cols = ["park_id", "park_name", "park_type", "year",
            "income_actual", "expense_actual", "tuition_actual", "surplus"]
# 真引擎還會用到 income_last_year / expense_last_year / detail_amounts / fund_balance_end
# 假資料沒有這些逐筆明細，因此真引擎的 benford/beneish 會走「資料不足」路徑。
# 這裡改為驗證「可用相同規則重算的分項」：score_penalty / score_eval / risk_total 加權公式。
try:
    from src.risk_score import (score_penalty, score_eval, WEIGHTS,
                                 risk_level_absolute)

    # 1) 裁罰分規則一致性
    ok_pen = all(
        score_penalty(r["penalty_count"]) == r["score_penalty"]
        for _, r in latest.iterrows()
    )
    log(f"[{'OK' if ok_pen else '錯誤'}] 裁罰分規則：真引擎 score_penalty 與 CSV 記錄"
        f"{'一致' if ok_pen else '不一致'}")

    # 2) 評鑑分規則一致性
    def _eval_cmp(r):
        g = r["eval_grade"]
        g = "" if pd.isna(g) else g
        return score_eval(g) == r["score_eval"]
    ok_eval = all(_eval_cmp(r) for _, r in latest.iterrows())
    log(f"[{'OK' if ok_eval else '錯誤'}] 評鑑分規則：真引擎 score_eval 與 CSV 記錄"
        f"{'一致' if ok_eval else '不一致'}")

    # 3) 總分加權公式一致性（用 CSV 的四個分項重算，比對 risk_total）
    recomputed = (WEIGHTS["financial"] * latest["score_financial"]
                  + WEIGHTS["penalty"] * latest["score_penalty"]
                  + WEIGHTS["eval"] * latest["score_eval"]
                  + WEIGHTS["sentiment"] * latest["score_sentiment"]).round(1)
    diff = (recomputed - latest["risk_total"]).abs()
    ok_total = (diff <= 0.11).all()  # 容許四捨五入 0.1 誤差
    log(f"[{'OK' if ok_total else '錯誤'}] 總分加權公式：用真引擎權重{WEIGHTS} 重算，"
        f"最大誤差 {diff.max():.2f}（{'一致' if ok_total else '不一致'}）")

    # 4) 絕對分級一致性
    ok_abs = all(risk_level_absolute(r["risk_total"]) == r["risk_level_abs"]
                 for _, r in latest.iterrows())
    log(f"[{'OK' if ok_abs else '錯誤'}] 絕對分級規則：真引擎 risk_level_absolute 與 CSV"
        f"{'一致' if ok_abs else '不一致'}")

except Exception as e:
    log(f"[警告] 無法比對真引擎計算規則：{type(e).__name__}: {e}")

# ---------- C. 資料完整性 ----------
log("")
log("=" * 60)
log("C. 資料完整性")
log("=" * 60)

log(f"最新快照列數：{len(latest)}；多年度列數：{len(full)}；"
    f"年度：{sorted(full['year'].unique().tolist())}")

# 每園在最新檔應唯一
dup = latest["park_name"].duplicated().sum()
log(f"[{'OK' if dup == 0 else '錯誤'}] 最新快照園名唯一性：重複 {dup} 筆")

# 關鍵欄位不應為空
for c in ["risk_total", "risk_level", "score_financial", "score_penalty",
          "score_eval", "score_sentiment"]:
    n = latest[c].isna().sum()
    log(f"[{'OK' if n == 0 else '警告'}] {c} 空值：{n}")

# 值域檢查
for c in ["risk_total", "score_financial", "score_penalty", "score_eval",
          "score_sentiment"]:
    lo, hi = latest[c].min(), latest[c].max()
    ok = lo >= 0 and hi <= 100
    log(f"[{'OK' if ok else '警告'}] {c} 值域 [{lo:.1f}, {hi:.1f}]（應在 0-100）")

# 座標範圍（新北市約 lat 24.6-25.3, lng 121.2-122.0）
geo_ok = (latest["lat"].between(24.5, 25.4).all()
          and latest["lng"].between(121.0, 122.1).all())
log(f"[{'OK' if geo_ok else '警告'}] 座標落在新北市範圍："
    f"lat[{latest['lat'].min():.3f},{latest['lat'].max():.3f}] "
    f"lng[{latest['lng'].min():.3f},{latest['lng'].max():.3f}]")

# 風險等級值域
lv_ok = set(latest["risk_level"].unique()) <= {"高", "中", "低"}
log(f"[{'OK' if lv_ok else '錯誤'}] 風險等級值：{latest['risk_level'].unique().tolist()}")

report = "\n".join(out)
open(os.path.join(ROOT, "consistency_report.txt"), "w", encoding="utf-8").write(report)
print(report)
