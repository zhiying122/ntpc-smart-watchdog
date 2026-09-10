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

from src.forensic import analyze, cross_metric_flags
from src.penalty_nlp import penalty_severity_score, classify_penalty_text

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

    base = (0.25 * benford + 0.20 * beneish + 0.25 * iforest
            + 0.10 * ratio_pts + 0.10 * yoy_pts + 0.10 * deficit_pts)

    # 交叉指標關係加成（鑑識會計核心，可解釋、有上限）：
    #   單位幼兒收入偏離同儕 +12；收入-支出成長背離 +10。
    #   這是「指標之間關係不合理」的訊號，比單一門檻更有說服力。
    cross_bonus = 0
    if row.get("cross_unit_income_outlier"):
        cross_bonus += 12
    if row.get("cross_rev_exp_divergence"):
        cross_bonus += 10
    if row.get("cross_unit_expense_outlier"):
        cross_bonus += 10  # 每生單位成本偏離同儕（成本面交叉勾稽）

    return round(min(base + cross_bonus, 100), 1)


def score_penalty(row):
    """
    裁罰分(0-100)：改用「裁罰性質分類 + 嚴重度」，而非純次數。
    2 次收費違規應遠重於 2 次行政缺失——看違規性質，不只看次數。
    詳見 src/penalty_nlp.py。相容舊呼叫：也接受單一 penalty_count 純量。
    """
    if isinstance(row, (int, float)):
        # 舊介面相容：只給次數時，無事由文字可分類
        return penalty_severity_score(row, "")
    return penalty_severity_score(row.get("penalty_count"), row.get("penalty_reason"))


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


def risk_level_by_group(df, score_col, group_col, min_group=7):
    """
    分組百分位相對分級（公平性版）：在每個「機構類型」內部各自做百分位分級，
    避免把資料可得性/財務結構不同的異質機構放同一把尺比較。

    學理：同儕比較 (peer benchmarking) 應在「可比同儕群體」內進行。公校與
    非營利園的收入來源、可抽取的財務細緻度不同（非營利園無逐筆明細 → 無班佛
    分項），屬不同同儕群體，分開排序才公平（PCAOB AS 2305 分析程序精神）。

    min_group：某類型樣本數 < min_group 時，該類型改用「全體」百分位，
    避免小樣本下百分位分級不穩定（例如某類型只有 3 間，前 15% 無意義）。
    回傳與 df 對齊的等級 Series（高/中/低）。
    """
    import pandas as pd

    if group_col not in df.columns:
        return risk_level_percentile(df[score_col])

    result = pd.Series(index=df.index, dtype="object")
    for _gval, idx in df.groupby(group_col).groups.items():
        sub = df.loc[idx, score_col]
        if len(sub) >= min_group:
            result.loc[idx] = risk_level_percentile(sub)
        else:
            # 小樣本：退回以全體分布計算的百分位，較穩健
            all_rank = df[score_col].rank(pct=True)
            result.loc[idx] = all_rank.loc[idx].apply(
                lambda r: "高" if r >= 0.85 else ("中" if r >= 0.50 else "低"))
    return result


EXTERNAL = os.path.join(ROOT, "data", "external")


def _merge_external(df):
    """併入裁罰/評鑑、地址座標等外部資料（若檔案存在）。"""
    # 裁罰與評鑑
    pen_path = os.path.join(EXTERNAL, "penalties.csv")
    if os.path.exists(pen_path):
        pen = pd.read_csv(pen_path).drop_duplicates("park_name", keep="first")
        pen_cols = ["park_name", "penalty_count", "eval_grade"]
        if "penalty_reason" in pen.columns:
            pen_cols.append("penalty_reason")
        df = df.merge(pen[pen_cols], on="park_name", how="left")
    # 幼兒人數（核定招生數，來源：全國教保資訊網，逐間人工查證併分班合計）
    enr_path = os.path.join(EXTERNAL, "enrollment.csv")
    if os.path.exists(enr_path):
        enr = pd.read_csv(enr_path, dtype={"park_id": str})
        enr = enr.drop_duplicates("park_id", keep="first")
        enr["enrollment"] = pd.to_numeric(enr["approved_capacity"], errors="coerce")
        df["park_id"] = df["park_id"].astype(str)
        df = df.merge(enr[["park_id", "enrollment"]], on="park_id", how="left")

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
    # 裁罰事由文字（供分類/嚴重度用）；非營利園或無裁罰者為空字串
    if "penalty_reason" not in df.columns:
        df["penalty_reason"] = ""
    df["penalty_reason"] = df["penalty_reason"].fillna("")
    # 裁罰主類別（收費/人力/安全/教保/行政），供前端與派工重點使用
    df["penalty_category"] = df.apply(
        lambda r: classify_penalty_text(r.get("penalty_reason"))["primary"] or "", axis=1)
    # 班佛樣本數：非營利園無逐筆明細 → 0（介面 int 顯示用）
    if "benford_sample_n" in df.columns:
        df["benford_sample_n"] = df["benford_sample_n"].fillna(0).astype(int)

    # 交叉指標關係規則（需 enrollment 併入後才能算每生單位收入）
    df = cross_metric_flags(df)

    df["score_financial"] = df.apply(score_financial, axis=1)
    df["score_penalty"] = df.apply(score_penalty, axis=1)
    df["score_eval"] = df["eval_grade"].apply(score_eval)

    df["risk_total"] = (
        WEIGHTS["financial"] * df["score_financial"]
        + WEIGHTS["penalty"] * df["score_penalty"]
        + WEIGHTS["eval"] * df["score_eval"]
    ).round(1)
    # 主用百分位相對分級（確保有高風險園、符合「稽查優先序」目的）。
    # 【公平性】分「機構類型」各自做百分位：公校與非營利園的財務結構、
    # 可得資料層不同（非營利園無逐筆明細 → 無班佛分項，財務分會被系統性
    # 低估），若混在同一把尺做百分位，非營利園會被不公平地壓在後段。
    # 故改為同類型內部比較（peer benchmarking），與交叉指標 z 分數的分群一致。
    # 每組樣本過少（<7）時退回全體百分位，避免小樣本分級不穩。
    df["risk_level"] = risk_level_by_group(df, "risk_total", "park_type", min_group=7)
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
            "expense_yoy_pct", "income_yoy_pct",
            "enrollment", "income_per_child", "income_per_child_z",
            "expense_per_child", "expense_per_child_z",
            "cross_unit_income_outlier", "cross_unit_expense_outlier",
            "rev_exp_growth_gap",
            "cross_rev_exp_divergence", "cross_tuition_share_z",
            "penalty_count", "penalty_reason",
            "penalty_category", "eval_grade",
            "score_financial", "score_penalty", "score_eval",
            "risk_total", "risk_level", "risk_level_abs"]
    cols = [c for c in cols if c in out.columns]
    out_path = os.path.join(PROC, "kindergartens.csv")
    out[cols].to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 風險評分完成（完整多年度）已寫入 {out_path}")

    # ---------- 給組員的「最新年度快照」：每園一列，供排名表與地圖直接用 ----------
    latest = (out.sort_values("year", ascending=False)
                 .drop_duplicates("park_name", keep="first")
                 .sort_values("risk_total", ascending=False)).copy()
    # 分級改在「快照本身」重算：稽查看的是每園最新狀態，相對排名應以「每園一列」
    # 的最新快照分布為基準（否則多年度重複列會扭曲百分位、使高風險占比偏離設計值）。
    # 一樣分機構類型各自百分位，維持公平性。
    latest["risk_level"] = risk_level_by_group(latest, "risk_total", "park_type", min_group=7)
    snap_path = os.path.join(PROC, "kindergartens_latest.csv")
    latest[cols].to_csv(snap_path, index=False, encoding="utf-8-sig")
    n_geo = latest["lat"].notna().sum() if "lat" in latest.columns else 0
    print(f"[OK] 最新年度快照（每園一列，{len(latest)}間，{n_geo}間有座標）已寫入 {snap_path}")
    print()
    print(out[["park_name", "risk_total", "risk_level", "score_financial",
               "benford_mad", "expense_income_ratio"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
