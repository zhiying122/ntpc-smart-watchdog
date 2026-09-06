"""
鑑識會計三招（風險引擎核心 / 隊長護城河）
================================================
招式一：班佛定律 (Benford's Law) —— 抓數字造假傾向
招式二：財務比率交叉勾稽 —— 抓離群異常
招式三：跨年度趨勢突變 —— 抓暴增暴減

所有方法都「可解釋」：每個指標都有清楚定義與門檻，能對評審講清楚。
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
