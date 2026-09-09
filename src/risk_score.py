"""
可解釋風險評分模型（白盒子）
================================
把鑑識會計指標 + 裁罰 + 評鑑 + 輿情，組成 0-100 的總風險分。
核心原則：可解釋。每個分項規則寫死在設定裡，能對評審講清楚
「87 分 = 財務40 + 裁罰30 + 評鑑15 + 輿情15」怎麼來的。

輸出：data/processed/kindergartens.csv （交給組員做儀表板的契約檔）
"""
import os
import pandas as pd

from src.forensic import analyze

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

# ---------- 分項權重（可調，簡報時秀這張）----------
WEIGHTS = {
    # 只用「已接入的真實資料源」組成總分，避免佔位值稀釋真實性。
    # 輿情資料源尚未接入（無真實爬蟲/NLP），故不納入計分；原 10% 依比例
    # 分配給其餘三項（45:30:15 → 50:34:16，合計 100%）。
    "financial": 0.50,   # 財務異常（四層鑑識會計，資料最完整可靠）
    "penalty": 0.34,     # 裁罰紀錄
    "eval": 0.16,        # 評鑑結果
}


def score_financial(row):
    """
    財務異常分(0-100)：四層鑑識會計方法疊合，全部可解釋。
    可解釋組成：
      班佛定律 25% + Beneish改良版 20% + Isolation Forest 25%
      + 收支比離群 10% + 跨年度突變 10% + 賸餘短絀率 10%
    多層方法互相佐證：多個方法同時指向的園，風險最高。
    """
    # NaN 安全轉 0：非營利園無逐筆明細 → benford_score 為 NaN，該層視為中性(0)，
    # 不可用「NaN or 0」（NaN 為 truthy 會保留 NaN 並汙染總分）。
    def _z(v):
        return 0.0 if v is None or pd.isna(v) else float(v)

    benford = _z(row.get("benford_score"))
    beneish = _z(row.get("beneish_score"))
    iforest = _z(row.get("iforest_score"))
    outlier = 100 if row.get("outlier_expense_ratio") else 0
    # 收支比 >1 (入不敷出) 加權：超過越多分越高
    ratio = row.get("expense_income_ratio")
    ratio_pts = 0
    if pd.notna(ratio) and ratio > 1:
        ratio_pts = min((ratio - 1) * 500, 100)  # 超支20%即滿分
    yoy = row.get("expense_yoy_pct")
    yoy_pts = min(abs(yoy) * 2, 100) if pd.notna(yoy) else 0
    # 賸餘短絀率：本期短絀占收入比，短絀越大代表基金被侵蝕，是重要財務警訊
    deficit_pts = 0
    surplus = row.get("surplus")
    income = row.get("income_actual")
    if pd.notna(surplus) and pd.notna(income) and income and surplus < 0:
        deficit_ratio = abs(surplus) / income
        deficit_pts = min(deficit_ratio * 1000, 100)  # 短絀達收入10%即滿分

    score = (0.25 * benford + 0.20 * beneish + 0.25 * iforest
             + 0.10 * ratio_pts + 0.10 * yoy_pts + 0.10 * deficit_pts)
    return round(min(score, 100), 1)


def score_penalty(penalty_count):
    """裁罰分(0-100)：0次=0, 1次=50, 2次=80, 3次以上=100。"""
    if pd.isna(penalty_count):
        return 0
    c = int(penalty_count)
    return {0: 0, 1: 50, 2: 80}.get(c, 100)


def score_eval(grade):
    """評鑑分(0-100)：優=0 良=20 中=50 待改進=90。缺資料=中性30。"""
    mapping = {"優": 0, "甲": 10, "良": 20, "乙": 40, "中": 50,
               "丙": 70, "待改進": 90, "不通過": 100}
    if pd.isna(grade) or grade == "":
        return 30
    return mapping.get(str(grade).strip(), 30)


def score_sentiment(neg_ratio):
    """輿情分(0-100)：負面比例 * 100。缺資料=中性20。"""
    if pd.isna(neg_ratio):
        return 20
    return round(min(float(neg_ratio) * 100, 100), 1)


def risk_level_absolute(total):
    """絕對門檻分級（保留備用）：≥60高, ≥35中, 其餘低。"""
    if total >= 60:
        return "高"
    if total >= 35:
        return "中"
    return "低"


def risk_level_percentile(series):
    """
    百分位相對分級（主用）：以全體同儕分布做相對風險等級。
    前 15% = 高風險（最需優先稽查）、次 35% = 中風險、其餘 = 低風險。
    學理：同儕比較 (peer benchmarking) + 百分位分級，適合「排序稽查優先序」的目的，
    不宣稱絕對造假門檻。文獻見 docs/methodology.md 同儕比較段落。
    """
    ranks = series.rank(pct=True)  # 0~1，越大分數越高

    def level(r):
        if r >= 0.85:
            return "高"
        if r >= 0.50:
            return "中"
        return "低"
    return ranks.apply(level)


EXTERNAL = os.path.join(ROOT, "data", "external")


def _merge_external(df):
    """併入裁罰/評鑑、地址座標等外部資料（若檔案存在）。"""
    # 裁罰與評鑑
    pen_path = os.path.join(EXTERNAL, "penalties.csv")
    if os.path.exists(pen_path):
        pen = pd.read_csv(pen_path).drop_duplicates("park_name", keep="first")
        df = df.merge(pen[["park_name", "penalty_count", "eval_grade"]],
                      on="park_name", how="left")
    # 座標
    geo_path = os.path.join(ROOT, "data", "processed", "geocoded.csv")
    if os.path.exists(geo_path):
        geo = pd.read_csv(geo_path).drop_duplicates("park_name", keep="first")
        geo_cols = ["park_name", "lat", "lng"]
        if "district" in geo.columns:
            geo_cols.append("district")
        df = df.merge(geo[geo_cols], on="park_name", how="left")
    return df


def build(df):
    """輸入 financials.csv，輸出完整風險評分 DataFrame。"""
    df = analyze(df)  # 先算鑑識會計指標
    df = _merge_external(df)  # 併入裁罰/評鑑/座標

    # 若沒有裁罰/評鑑/輿情欄位，先給預設
    if "penalty_count" not in df.columns:
        df["penalty_count"] = 0
    if "eval_grade" not in df.columns:
        df["eval_grade"] = ""

    # 併外部資料後，非營利園（無裁罰紀錄）penalty_count 會是 NaN。
    # 介面以 int() 顯示裁罰次數，NaN 會導致 "cannot convert float NaN to integer"。
    # 誠實預設：非營利園無裁罰資料 → 0 次；評鑑無資料 → 空字串（介面顯示 —）。
    df["penalty_count"] = df["penalty_count"].fillna(0).astype(int)
    df["eval_grade"] = df["eval_grade"].fillna("")
    # 班佛樣本數：非營利園無逐筆明細 → 0（介面 int 顯示用）
    if "benford_sample_n" in df.columns:
        df["benford_sample_n"] = df["benford_sample_n"].fillna(0).astype(int)

    df["score_financial"] = df.apply(score_financial, axis=1)
    df["score_penalty"] = df["penalty_count"].apply(score_penalty)
    df["score_eval"] = df["eval_grade"].apply(score_eval)

    df["risk_total"] = (
        WEIGHTS["financial"] * df["score_financial"]
        + WEIGHTS["penalty"] * df["score_penalty"]
        + WEIGHTS["eval"] * df["score_eval"]
    ).round(1)
    # 主用百分位相對分級（確保有高風險園、符合「稽查優先序」目的）
    df["risk_level"] = risk_level_percentile(df["risk_total"])
    # 同時保留絕對門檻分級供對照
    df["risk_level_abs"] = df["risk_total"].apply(risk_level_absolute)

    return df.sort_values("risk_total", ascending=False)


def main():
    src = os.path.join(PROC, "financials.csv")
    df = pd.read_csv(src)
    out = build(df)

    # 輸出契約檔（給組員）
    cols = ["park_id", "park_name", "park_type", "year",
            "district", "lat", "lng",
            "income_actual", "expense_actual", "tuition_actual", "surplus",
            "expense_income_ratio", "benford_mad", "benford_sample_n", "benford_score",
            "benford_chi2", "benford_pvalue", "benford_significant",
            "beneish_score", "beneish_egdi", "beneish_tata",
            "iforest_score", "iforest_explain",
            "expense_yoy_pct", "penalty_count", "eval_grade",
            "score_financial", "score_penalty", "score_eval",
            "risk_total", "risk_level", "risk_level_abs"]
    cols = [c for c in cols if c in out.columns]
    out_path = os.path.join(PROC, "kindergartens.csv")
    out[cols].to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 風險評分完成（完整多年度）已寫入 {out_path}")

    # ---------- 給組員的「最新年度快照」：每園一列，供排名表與地圖直接用 ----------
    latest = (out.sort_values("year", ascending=False)
                 .drop_duplicates("park_name", keep="first")
                 .sort_values("risk_total", ascending=False))
    snap_path = os.path.join(PROC, "kindergartens_latest.csv")
    latest[cols].to_csv(snap_path, index=False, encoding="utf-8-sig")
    n_geo = latest["lat"].notna().sum() if "lat" in latest.columns else 0
    print(f"[OK] 最新年度快照（每園一列，{len(latest)}間，{n_geo}間有座標）已寫入 {snap_path}")
    print()
    print(out[["park_name", "risk_total", "risk_level", "score_financial",
               "benford_mad", "expense_income_ratio"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
