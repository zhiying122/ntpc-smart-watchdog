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
    mads, levels, benford_scores, ns = [], [], [], []
    for _, r in df.iterrows():
        raw = r.get("detail_amounts")
        nums = []
        if isinstance(raw, str) and raw.strip():
            nums = [int(x) for x in raw.split(";") if x.strip().isdigit()]
        mad, _, n = benford_mad(nums, min_n=30)
        level, score = benford_conformity(mad)
        mads.append(mad)
        levels.append(level)
        benford_scores.append(score)
        ns.append(n)
    df["benford_mad"] = mads
    df["benford_level"] = levels
    df["benford_sample_n"] = ns

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
