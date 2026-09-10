"""
鑑識會計四層方法（風險引擎核心 / 隊長護城河）
================================================
第一層：班佛定律 (Benford's Law) —— 抓數字造假傾向
第二層：Beneish M-Score 改良版 —— 抓盈餘/收支操縱（費用與收入背離）
第三層：財務比率交叉勾稽 + IQR 離群 —— 抓統計離群異常
第四層：Isolation Forest + SHAP —— 抓多維異常並保持可解釋

所有方法都「可解釋」：每個指標都有清楚定義、門檻或可解釋輸出，能對評審講清楚。
文獻佐證見 docs/methodology.md。
"""
import math

import numpy as np
import pandas as pd

# 班佛定律理論分布：首位數 d 出現機率 = log10(1 + 1/d)
BENFORD_EXPECTED = {d: math.log10(1 + 1 / d) for d in range(1, 10)}


# ---------- 招式一：班佛定律 ----------
def first_digit(n):
    """取一個數的首位有效數字(1-9)。"""
    n = abs(n)
    if n == 0:
        return None
    while n < 1:
        n *= 10
    return int(str(int(n))[0])


def benford_mad(numbers, min_n=10):
    """
    計算一組數字的班佛 MAD（平均絕對偏差）。
    MAD 越大代表越偏離自然分布，越可疑。
    參考審計實務門檻：
      < 0.006 高度吻合、0.006-0.012 可接受、0.012-0.015 邊緣、>0.015 不吻合(可疑)
    回傳 (mad, 觀測分布, 樣本數)。
    """
    digits = [first_digit(x) for x in numbers if x is not None and abs(x) > 0]
    digits = [d for d in digits if d]
    n = len(digits)
    if n < min_n:
        return None, {}, n  # 樣本太少不可靠

    observed = {d: digits.count(d) / n for d in range(1, 10)}
    mad = sum(abs(observed[d] - BENFORD_EXPECTED[d]) for d in range(1, 10)) / 9
    return round(mad, 5), observed, n


def benford_conformity(mad):
    """把 MAD 轉成白話等級與 0-100 風險分（越可疑分越高）。"""
    if mad is None:
        return "樣本不足", 0
    if mad < 0.006:
        return "高度吻合", 5
    if mad < 0.012:
        return "可接受", 25
    if mad < 0.015:
        return "邊緣", 60
    return "不吻合(可疑)", 90


def benford_chi_square(numbers, min_n=30):
    """
    班佛定律卡方適合度檢定（統計顯著性）。
    補強 MAD 的不足：MAD 只給偏離程度，卡方給出「偏離是否統計顯著」。
    自由度 = 8（9個首位數 - 1）；卡方臨界值 α=0.05 為 15.507。
    回傳 (chi2, p_value, 是否顯著偏離)。
    文獻：政府支出班佛檢定常用 Z 檢定與卡方檢定 (Durtschi et al., 2004)。
    """
    from scipy import stats as _stats

    digits = [first_digit(x) for x in numbers if x is not None and abs(x) > 0]
    digits = [d for d in digits if d]
    n = len(digits)
    if n < min_n:
        return None, None, None

    observed_counts = [digits.count(d) for d in range(1, 10)]
    expected_counts = [BENFORD_EXPECTED[d] * n for d in range(1, 10)]
    chi2 = sum((o - e) ** 2 / e for o, e in zip(observed_counts, expected_counts))
    p_value = 1 - _stats.chi2.cdf(chi2, df=8)
    significant = chi2 > 15.507  # α=0.05, df=8
    return round(chi2, 3), round(p_value, 5), significant


# ---------- 招式二：財務比率交叉勾稽 ----------
def compute_ratios(row):
    """算三個關鍵財務比率。"""
    income = row.get("income_actual") or 0
    expense = row.get("expense_actual") or 0
    tuition = row.get("tuition_actual") or 0
    ratios = {}
    # 收支比：支出/收入，>1 代表入不敷出
    ratios["expense_income_ratio"] = round(expense / income, 4) if income else None
    # 學雜費占收入比：反映自籌財源結構
    ratios["tuition_income_ratio"] = round(tuition / income, 4) if income else None
    return ratios


def flag_outliers(df, col, k=1.5):
    """用 IQR 法標記離群值（可解釋的統計方法）。回傳布林 Series。"""
    s = df[col].dropna()
    if len(s) < 4:
        return pd.Series([False] * len(df), index=df.index)
    q1, q3 = s.quantile(0.25), s.quantile(0.75)
    iqr = q3 - q1
    low, high = q1 - k * iqr, q3 + k * iqr
    return (df[col] < low) | (df[col] > high)


# ---------- 招式三：跨年度趨勢突變 ----------
def yoy_change(current, last):
    """年度變動幅度(%)。"""
    if not last or last == 0:
        return None
    return round((current - last) / abs(last) * 100, 2)


def yoy_flag(change_pct, threshold=30):
    """變動超過門檻(預設±30%)標記為突變。"""
    if change_pct is None:
        return False
    return abs(change_pct) >= threshold


# ---------- 第二層：Beneish M-Score 改良版（非營利園適用）----------
# 原始 Beneish 為營利公司設計(含銷貨/應收)，幼兒園非營利無此概念。
# 我們借鑒其核心邏輯：「費用與收入成長背離」「應計項目異常」即操縱訊號。
# 改良指標（皆可從決算資料算出，需本年度與上年度數字）：
def beneish_lite(row):
    """
    Beneish 改良版分數(0-100)。越高越可疑。
    組成三個可解釋指數：
      1) EGDI 收支成長背離指數：支出成長遠高於收入成長 → 可疑
      2) SGI  收入成長指數：異常高成長(可能灌收入)
      3) TATA 應計項目比：本期賸餘與現金基礎背離(用賸餘/收入近似)
    """
    inc = row.get("income_actual")
    inc_last = row.get("income_last_year")
    exp = row.get("expense_actual")
    exp_last = row.get("expense_last_year")
    surplus = row.get("surplus")

    if not all(pd.notna(x) and x not in (0, None)
               for x in [inc, inc_last, exp, exp_last]):
        return None, {}

    # 成長率
    inc_growth = (inc - inc_last) / abs(inc_last)
    exp_growth = (exp - exp_last) / abs(exp_last)

    # 1) 收支成長背離：支出成長 - 收入成長，正值越大越可疑
    egdi = exp_growth - inc_growth
    # 2) 收入成長指數：SGI，異常高成長可疑（|.| 越大越可疑）
    sgi = inc_growth
    # 3) 應計比：賸餘占收入比，偏離 0 越大代表現金與帳面背離
    tata = (surplus / inc) if (pd.notna(surplus) and inc) else 0.0

    # 換算成 0-100 可疑分（可解釋線性映射，門檻參考鑑識實務經驗）
    egdi_pts = min(max(egdi, 0) * 300, 100)      # 支出比收入多成長 33% 即滿分
    sgi_pts = min(abs(sgi) * 200, 100)           # 收入劇烈變動
    tata_pts = min(abs(tata) * 400, 100)         # 應計偏離

    score = round(0.5 * egdi_pts + 0.25 * sgi_pts + 0.25 * tata_pts, 1)
    detail = {
        "beneish_egdi": round(egdi, 4),
        "beneish_sgi": round(sgi, 4),
        "beneish_tata": round(tata, 4),
    }
    return score, detail


# ---------- 第四層：Isolation Forest + SHAP（多維異常，可解釋）----------
def isolation_forest_scores(df, feature_cols):
    """
    對多維財務特徵跑 Isolation Forest，回傳每園 0-100 異常分（越高越異常）
    以及每園的 SHAP 特徵歸因（解釋為什麼異常）。
    非監督式，不需標籤，適合裁罰標籤有限的情境。
    """
    from sklearn.ensemble import IsolationForest

    X = df[feature_cols].fillna(df[feature_cols].median(numeric_only=True)).fillna(0)
    if len(X) < 4:
        return [None] * len(df), [{}] * len(df)

    model = IsolationForest(n_estimators=200, contamination="auto", random_state=42)
    model.fit(X)
    # decision_function 越小越異常 → 轉成 0-100 越大越異常
    raw = -model.decision_function(X)
    score = (raw - raw.min()) / (raw.max() - raw.min() + 1e-9) * 100

    # SHAP 解釋（可解釋白盒子）；shap 失敗時退化為特徵 z-score 貢獻
    explanations = []
    try:
        import shap
        explainer = shap.TreeExplainer(model)
        shap_vals = explainer.shap_values(X, check_additivity=False)
        for i in range(len(X)):
            contrib = {feature_cols[j]: round(float(shap_vals[i][j]), 3)
                       for j in range(len(feature_cols))}
            top = sorted(contrib.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
            explanations.append(dict(top))
    except Exception:
        med = X.median()
        std = X.std().replace(0, 1)
        for i in range(len(X)):
            z = ((X.iloc[i] - med) / std).abs()
            top = z.sort_values(ascending=False).head(3)
            explanations.append({k: round(float(v), 2) for k, v in top.items()})

    return [round(float(s), 1) for s in score], explanations


# ---------- 整合：對整份資料算所有鑑識指標 ----------
def analyze(df):
    """
    輸入 financials.csv 的 DataFrame，回傳含所有鑑識會計指標的 DataFrame。
    """
    df = df.copy()

    # 招式二：比率
    ratios = df.apply(compute_ratios, axis=1, result_type="expand")
    df = pd.concat([df, ratios], axis=1)
    df["outlier_expense_ratio"] = flag_outliers(df, "expense_income_ratio")

    # 招式三：跨年度（用本年度 vs 上年度支出）
    df["expense_yoy_pct"] = df.apply(
        lambda r: yoy_change(r.get("expense_actual"), r.get("expense_last_year")), axis=1
    )
    df["expense_yoy_flag"] = df["expense_yoy_pct"].apply(yoy_flag)
    df["income_yoy_pct"] = df.apply(
        lambda r: yoy_change(r.get("income_actual"), r.get("income_last_year")), axis=1
    )

    # 招式一：班佛定律（正確做法：用逐筆明細金額，跨數量級才有效）
    # 補強：同時算 MAD(偏離程度) 與卡方檢定(統計顯著性)
    mads, levels, benford_scores, ns = [], [], [], []
    chi2s, pvals, sigs = [], [], []
    for _, r in df.iterrows():
        raw = r.get("detail_amounts")
        nums = []
        if isinstance(raw, str) and raw.strip():
            nums = [int(x) for x in raw.split(";") if x.strip().isdigit()]
        mad, _, n = benford_mad(nums, min_n=30)
        level, score = benford_conformity(mad)
        chi2, pval, sig = benford_chi_square(nums, min_n=30)
        mads.append(mad)
        levels.append(level)
        benford_scores.append(score)
        ns.append(n)
        chi2s.append(chi2)
        pvals.append(pval)
        sigs.append(sig)
    df["benford_mad"] = mads
    df["benford_level"] = levels
    df["benford_sample_n"] = ns
    df["benford_chi2"] = chi2s
    df["benford_pvalue"] = pvals
    df["benford_significant"] = sigs

    # 班佛分數改用「組內相對排名」百分位（更公允、可解釋）：
    # MAD 越高在組內越可疑，換算成 0-100 的相對風險分。
    mad_series = pd.Series(mads, index=df.index)
    if mad_series.notna().sum() >= 2:
        df["benford_score"] = (mad_series.rank(pct=True) * 100).round(0)
    else:
        df["benford_score"] = benford_scores

    # 第二層：Beneish 改良版
    beneish_scores, beneish_details = [], []
    for _, r in df.iterrows():
        s, d = beneish_lite(r)
        beneish_scores.append(s if s is not None else 0)
        beneish_details.append(d)
    df["beneish_score"] = beneish_scores
    df["beneish_egdi"] = [d.get("beneish_egdi") for d in beneish_details]
    df["beneish_sgi"] = [d.get("beneish_sgi") for d in beneish_details]
    df["beneish_tata"] = [d.get("beneish_tata") for d in beneish_details]

    # 第四層：Isolation Forest + SHAP（多維異常）
    iso_features = ["expense_income_ratio", "tuition_income_ratio",
                    "expense_yoy_pct", "income_yoy_pct", "benford_mad",
                    "beneish_score"]
    iso_features = [c for c in iso_features if c in df.columns]
    iso_scores, iso_expl = isolation_forest_scores(df, iso_features)
    df["iforest_score"] = iso_scores
    df["iforest_explain"] = [str(e) for e in iso_expl]

    return df


# ---------- 交叉指標關係規則（鑑識會計核心：看指標之間的關係，不看單一門檻）----------
def cross_metric_flags(df):
    """
    計算「交叉指標關係」欄位與紅旗。回傳新增欄位後的 df。
    鑑識會計的精神：單一數字高不代表異常，指標之間的「關係」不合理才是訊號。

    需要欄位：income_actual, expense_actual, tuition_actual, enrollment,
              income_yoy_pct, expense_yoy_pct。缺 enrollment 的園（如查無現況者）
              人數相關指標為 NaN，對應紅旗自動不觸發（誠實：不硬編）。

    產出欄位：
      income_per_child            每生單位收入 = 收入 / 核定人數
      income_per_child_z          每生單位收入在「同類型同儕」中的 z 分數
      cross_unit_income_outlier   [規則X1] 單位幼兒收入顯著偏離同儕（|z|>=1.5 且偏高）
      cross_rev_exp_divergence    [規則X2] 收入-支出成長背離（收入年增遠低/高於支出年增）
      rev_exp_growth_gap          收入年增率 - 支出年增率（百分點）
      cross_tuition_share_z       學雜費占收入比在同儕中的 z（結構異常輔助）
    """
    df = df.copy()

    # --- 每生單位收入 / 每生單位成本（命題要求：財報 × 幼兒人數交叉分析）---
    if "enrollment" in df.columns:
        enr = pd.to_numeric(df["enrollment"], errors="coerce")
        inc = pd.to_numeric(df["income_actual"], errors="coerce")
        exp = pd.to_numeric(df["expense_actual"], errors="coerce")
        df["income_per_child"] = (inc / enr).where(enr > 0)
        # 每生單位成本 = 年度支出 / 核定招生人數。反映「養一個孩子的成本」，
        # 是幼兒園財務效率與資源投放的核心指標。偏離同儕過高 → 成本結構待查
        # （可能人事/採購浮編）；過低 → 恐排擠教保品質。缺人數者為 NaN（誠實不硬編）。
        df["expense_per_child"] = (exp / enr).where(enr > 0)
    else:
        df["income_per_child"] = pd.NA
        df["expense_per_child"] = pd.NA

    # --- 規則X1：單位幼兒收入 vs 同儕（同 park_type 分群，中位數 + 標準差）---
    df["income_per_child_z"] = pd.NA
    df["cross_unit_income_outlier"] = False
    if "park_type" in df.columns:
        for ptype, idx in df.groupby("park_type").groups.items():
            grp = df.loc[idx]
            s = pd.to_numeric(grp["income_per_child"], errors="coerce").dropna()
            if len(s) < 3:
                continue
            med = s.median()
            std = s.std(ddof=0) or 1e-9
            z = (pd.to_numeric(grp["income_per_child"], errors="coerce") - med) / std
            df.loc[idx, "income_per_child_z"] = z.round(2)
            # 偏「高」端 1.5σ 以上：收到的錢相對每個孩子異常多，值得查金流結構
            df.loc[idx, "cross_unit_income_outlier"] = (z >= 1.5).fillna(False)

    # --- 規則X3：每生單位成本 vs 同儕（成本面，與 X1 對稱）---
    # 每生成本偏離同儕過大（雙尾 |z|>=1.5）即成本結構異常：偏高恐浮編，
    # 偏低恐排擠品質。與收入面 X1 並列，構成「收入-成本」雙面交叉勾稽。
    df["expense_per_child_z"] = pd.NA
    df["cross_unit_expense_outlier"] = False
    if "park_type" in df.columns:
        for ptype, idx in df.groupby("park_type").groups.items():
            grp = df.loc[idx]
            s = pd.to_numeric(grp["expense_per_child"], errors="coerce").dropna()
            if len(s) < 3:
                continue
            med = s.median()
            std = s.std(ddof=0) or 1e-9
            z = (pd.to_numeric(grp["expense_per_child"], errors="coerce") - med) / std
            df.loc[idx, "expense_per_child_z"] = z.round(2)
            df.loc[idx, "cross_unit_expense_outlier"] = (z.abs() >= 1.5).fillna(False)

    # --- 規則X2：收入-支出成長背離 ---
    # 收入大幅成長但支出沒跟上（或相反），是收支結構突變的訊號。
    inc_yoy = pd.to_numeric(df.get("income_yoy_pct"), errors="coerce")
    exp_yoy = pd.to_numeric(df.get("expense_yoy_pct"), errors="coerce")
    df["rev_exp_growth_gap"] = (inc_yoy - exp_yoy).round(2)
    # 背離超過 25 個百分點視為關係異常（暫定門檻，收支應大致同步成長）
    df["cross_rev_exp_divergence"] = df["rev_exp_growth_gap"].abs() >= 25

    # --- 輔助：學雜費占收入比的同儕 z（結構異常）---
    df["cross_tuition_share_z"] = pd.NA
    if "tuition_income_ratio" in df.columns and "park_type" in df.columns:
        for ptype, idx in df.groupby("park_type").groups.items():
            grp = df.loc[idx]
            s = pd.to_numeric(grp["tuition_income_ratio"], errors="coerce").dropna()
            if len(s) < 3:
                continue
            med = s.median()
            std = s.std(ddof=0) or 1e-9
            z = (pd.to_numeric(grp["tuition_income_ratio"], errors="coerce") - med) / std
            df.loc[idx, "cross_tuition_share_z"] = z.round(2)

    return df


def benford_population(df):
    """
    全體宏觀班佛檢定（簡報主圖）：把所有幼兒園的所有財務數字合起來，
    檢定整體資料是否符合自然分布。這是樣本量最充足、最有說服力的一張圖。
    回傳 (mad, level, 觀測分布, 理論分布, 樣本數)。
    """
    num_cols = ["income_actual", "income_last_year", "expense_actual",
                "expense_last_year", "tuition_actual", "surplus", "fund_balance_end"]
    all_nums = []
    for c in num_cols:
        if c in df.columns:
            all_nums.extend([v for v in df[c].tolist() if pd.notna(v)])
    mad, observed, n = benford_mad(all_nums, min_n=10)
    level, _ = benford_conformity(mad)
    return mad, level, observed, dict(BENFORD_EXPECTED), n


if __name__ == "__main__":
    import os
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = os.path.join(ROOT, "data", "processed", "financials.csv")
    df = pd.read_csv(src)
    out = analyze(df)
    cols = ["park_name", "expense_income_ratio", "outlier_expense_ratio",
            "expense_yoy_pct", "expense_yoy_flag", "benford_mad", "benford_level"]
    print(out[cols].to_string(index=False))
