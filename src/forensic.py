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


# ---------- 招式：基金餘額勾稽（Fund Balance Reconciliation）----------
# 「勾稽」為台灣會計/審計正統用語：把應相符的數字互相核對、確認一致。
# 政府基金會計恆等式：期末基金餘額 = 期初基金餘額 + 本期賸餘(短絀) − 解繳公庫 ± 其他調整。
# 在最單純（無解繳公庫等調整）情況下即：期末 = 期初 + 本期賸餘。
# 勾稽「對不起來」代表決算數字內部不一致（可能是登載錯誤、OCR 抽取誤差，
# 或真實的帳務異常），是強而有力、可解釋的鑑識訊號。
FUND_RECON_FORMULA = ("基金餘額勾稽：期末基金餘額 = 期初基金餘額 + 本期賸餘(短絀) "
                      "− 解繳公庫 ± 其他調整")


def fund_reconciliation(fund_begin, surplus, fund_end, adjustments=0.0,
                        tolerance_ratio=0.005):
    """同期基金餘額勾稽（R7 鑑識，台灣會計用語）。

    驗證會計恆等式：期末基金餘額 ≈ 期初基金餘額 + 本期賸餘(短絀) − 解繳公庫。

    參數
    ----
    fund_begin : 期初基金餘額。
    surplus    : 本期賸餘(短絀)（短絀為負）。
    fund_end   : 期末基金餘額。
    adjustments: 解繳公庫等其他調整（預設 0；正值代表減少期末餘額的流出）。
    tolerance_ratio : 容許誤差比例（相對期末餘額），預設 0.5%。政府決算多以整數元
                      呈現、極少有四捨五入誤差，故容差設得很小；設 >0 是為容忍
                      OCR/抽取的個位數雜訊，不放過真正的帳務不一致。

    回傳
    ----
    dict：
      computable   : 是否可勾稽（三個基金數字齊備才可）。
      expected_end : 依恆等式推算的期末餘額 = 期初 + 本期賸餘 − 調整。
      diff         : 實際期末 − 推算期末（不一致金額，正負皆可能）。
      abs_diff     : |diff|。
      consistent   : |diff| 是否落在容差內（勾稽一致）。
      score        : 0–100 不一致可疑分（一致=0；不一致依偏離比例線性放大）。
      formula      : 明確公式字串（R7.9）。

    設計說明
    --------
    - 缺任一基金數字 → computable=False、score=0（缺資料不放大風險，R10.5）。
    - score 以「不一致金額占期末餘額比例」線性映射：偏離達 10% 即滿分 100，
      使可疑度可解釋且與金額規模無關（大園小園同一把尺）。
    """
    b = _to_float(fund_begin)
    s = _to_float(surplus)
    e = _to_float(fund_end)
    adj = _to_float(adjustments) or 0.0
    if b is None or s is None or e is None:
        return {"computable": False, "expected_end": None, "diff": None,
                "abs_diff": None, "consistent": None, "score": 0.0,
                "formula": FUND_RECON_FORMULA}

    expected_end = b + s - adj
    diff = e - expected_end
    abs_diff = abs(diff)
    # 容差以期末餘額規模為基準；期末為 0 時退回以期初規模，皆為 0 則用絕對 1 元。
    base = abs(e) or abs(b) or 1.0
    tolerance = base * tolerance_ratio
    consistent = abs_diff <= tolerance
    # 不一致比例 → 0–100 分：偏離達期末餘額 10% 即滿分。
    score = 0.0 if consistent else round(min(abs_diff / base * 1000, 100), 1)
    return {
        "computable": True,
        "expected_end": round(expected_end, 2),
        "diff": round(diff, 2),
        "abs_diff": round(abs_diff, 2),
        "consistent": consistent,
        "score": score,
        "formula": FUND_RECON_FORMULA,
    }


def fund_continuity(prev_fund_end, curr_fund_begin, tolerance_ratio=0.005):
    """跨年度基金連續性勾稽：本年度期初基金餘額 ≈ 上年度期末基金餘額。

    這是比同期勾稽更難造假的一致性檢核——同一機構相鄰兩年的基金餘額必須銜接。
    銜接不上代表某一年度數字被調整過或登載錯誤，是重要鑑識訊號。

    回傳與 fund_reconciliation 同構的 dict（computable/diff/abs_diff/consistent/score）。
    缺任一數字 → computable=False、score=0。
    """
    prev_e = _to_float(prev_fund_end)
    curr_b = _to_float(curr_fund_begin)
    if prev_e is None or curr_b is None:
        return {"computable": False, "diff": None, "abs_diff": None,
                "consistent": None, "score": 0.0,
                "formula": "跨年度連續性：本年度期初基金餘額 = 上年度期末基金餘額"}
    diff = curr_b - prev_e
    abs_diff = abs(diff)
    base = abs(prev_e) or abs(curr_b) or 1.0
    consistent = abs_diff <= base * tolerance_ratio
    score = 0.0 if consistent else round(min(abs_diff / base * 1000, 100), 1)
    return {
        "computable": True,
        "diff": round(diff, 2),
        "abs_diff": round(abs_diff, 2),
        "consistent": consistent,
        "score": score,
        "formula": "跨年度連續性：本年度期初基金餘額 = 上年度期末基金餘額",
    }


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

    # 先將特徵欄位一律強制轉為數值（非數值→NaN），再以中位數補值、最後補 0。
    # 先轉數值可根除 object dtype 在 .fillna 時的隱式降型 FutureWarning，
    # 且確保 IsolationForest 收到純數值矩陣（行為不變、更穩健）。
    feats = df[feature_cols].apply(pd.to_numeric, errors="coerce")
    X = feats.fillna(feats.median(numeric_only=True)).fillna(0)
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

    # 招式：基金餘額勾稽（期末 = 期初 + 本期賸餘）。缺基金欄位者 computable=False、
    # score=0（多為非營利園，OCR 未抽基金餘額，不放大其風險）。
    if "fund_balance_begin" in df.columns and "fund_balance_end" in df.columns:
        recon = df.apply(
            lambda r: fund_reconciliation(
                r.get("fund_balance_begin"), r.get("surplus"),
                r.get("fund_balance_end")), axis=1)
        df["fund_recon_score"] = [x["score"] for x in recon]
        df["fund_recon_diff"] = [x["diff"] for x in recon]
        df["fund_recon_consistent"] = [x["consistent"] for x in recon]
    else:
        df["fund_recon_score"] = 0.0
        df["fund_recon_diff"] = None
        df["fund_recon_consistent"] = None

    # 跨年度連續性勾稽：同園相鄰兩年「本年度期初 = 上年度期末」。
    if ("fund_balance_begin" in df.columns and "fund_balance_end" in df.columns
            and "park_name" in df.columns and "year" in df.columns):
        cont_score = pd.Series(0.0, index=df.index)
        cont_diff = pd.Series([None] * len(df), index=df.index, dtype="object")
        for _pname, idx in df.groupby("park_name").groups.items():
            g = df.loc[idx].sort_values("year")
            prev_end = None
            prev_year = None
            for i in g.index:
                curr_year = g.at[i, "year"]
                curr_begin = g.at[i, "fund_balance_begin"]
                # 僅在年度「真正相鄰」（相差 1）時才做連續性勾稽，避免因中間
                # 年度資料缺漏（例如只有 112、114）而誤判為斷裂（假陽性）。
                if (prev_end is not None and prev_year is not None
                        and pd.notna(curr_year)
                        and int(curr_year) - int(prev_year) == 1):
                    c = fund_continuity(prev_end, curr_begin)
                    if c["computable"]:
                        cont_score.at[i] = c["score"]
                        cont_diff.at[i] = c["diff"]
                prev_end = g.at[i, "fund_balance_end"]
                prev_year = curr_year
        df["fund_continuity_score"] = cont_score
        df["fund_continuity_diff"] = cont_diff
    else:
        df["fund_continuity_score"] = 0.0
        df["fund_continuity_diff"] = None

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
    #
    # 【指標獨立性 / 避免重複計分】score_financial 已「單獨」計分下列面向：
    #   收支比(expense_income_ratio)、支出年增率(expense_yoy_pct)、
    #   班佛(benford_mad→benford_score)、Beneish(beneish_score)。
    # 若再把它們餵進 iForest，等於同一異常訊號在總分裡被算兩次（隱性加權），
    # 破壞白盒子「權重=該面向重要性」的可解釋前提，且統計上造成共線性。
    #
    # 正解：iForest 只吃「其他分項未單獨計分、且代表不同財務面向」的維度，
    # 讓六層職責不重疊、權重名副其實：
    #   - tuition_income_ratio：學雜費占收入比（自籌財源結構），無其他層計分。
    #   - income_yoy_pct      ：收入年增率（收入面趨勢突變）；支出面已由
    #                           expense_yoy_pct 單獨計分，收入面未計 → 由此層補足。
    # 註：賸餘/短絀率已由 score_financial 的 deficit_pts 單獨計分，故不納入本層，
    #     以維持獨立性。
    iso_features = ["tuition_income_ratio", "income_yoy_pct"]
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


# ==========================================================================
# 明確公式鑑識指標（Explicit-Formula Forensic Metrics, R7.1/7.2/7.4/7.5/7.9）
# --------------------------------------------------------------------------
# 對齊 design.md「Components and Interfaces → 1. Forensic_Engine」：
#   compute_metrics(row, peer_stats) -> ForensicMetrics
# 每一 Metric 皆附「非空明確公式字串」(R7.9)，並以小數點後 4 位輸出 (R7.1)。
# 分母為 0 或缺值時，該指標標記 computable=False 而不拋例外 (R7.11，於此僅做
# 安全保護；完整的突變/同儕排除語意由 Task 2.2 補齊)。
# ==========================================================================
from src.models import ForensicMetrics, Metric  # noqa: E402

# 每一指標的明確公式定義字串（R7.9）。集中定義便於介面與文件引用。
METRIC_FORMULAS = {
    "income_growth": "收入成長率 = (本年度收入 − 前年度收入) / 前年度收入",
    "expense_growth": "支出成長率 = (本年度支出 − 前年度支出) / 前年度支出",
    "personnel_ratio": "人事費占比 = 人事費 / 總支出",
    "operating_ratio": "業務費占比 = 業務費 / 總支出",
    "income_per_child": "每名幼兒收入 = 收入 / 招生人數",
    "expense_per_child": "每名幼兒支出 = 支出 / 招生人數",
    "income_enrollment_consistency": (
        "收入招生一致性 = (每名幼兒收入 − 同儕每名幼兒收入中位數) "
        "/ 同儕每名幼兒收入中位數"
    ),
    "income_per_child_zscore": "每名幼兒收入 z-score = (x − 同儕平均) / 同儕標準差",
    "income_per_child_percentile": "每名幼兒收入百分位 = 同儕群組中 ≤ x 之比例 × 100",
    # 支出結構占比（R7.3）：人事/業務/其他三類占總支出比例，合計介於 0.99–1.01。
    "personnel_share": "人事費占比（結構） = 人事費 / 總支出",
    "operating_share": "業務費占比（結構） = 業務費 / 總支出",
    "other_share": "其他占比（結構） = (總支出 − 人事費 − 業務費) / 總支出",
}

# 精度：小數點後 4 位（R7.1）。
_METRIC_PRECISION = 4


def _to_float(value):
    """安全轉 float；None／NaN／無法轉換一律回傳 None（缺值保護 R7.11）。"""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _safe_ratio(numerator, denominator):
    """安全比值。

    回傳 (value, computable)：
      - 分子或分母缺值、或分母為 0 → (None, False)（R7.11）。
      - 否則 → (四捨五入至 4 位小數之比值, True)（R7.1）。
    """
    num = _to_float(numerator)
    den = _to_float(denominator)
    if num is None or den is None or den == 0:
        return None, False
    return round(num / den, _METRIC_PRECISION), True


def _make_metric(name, numerator, denominator):
    """依安全比值建立帶公式字串的 Metric（R7.9）。"""
    value, computable = _safe_ratio(numerator, denominator)
    return Metric(
        name=name,
        value=value,
        formula=METRIC_FORMULAS[name],
        computable=computable,
    )


def _growth_metric(name, current, last):
    """成長率指標 = (current − last) / |last|；last 為 0/缺值 → 不可計算。"""
    cur = _to_float(current)
    lst = _to_float(last)
    if cur is None or lst is None or lst == 0:
        return Metric(name=name, value=None, formula=METRIC_FORMULAS[name],
                      computable=False)
    value = round((cur - lst) / abs(lst), _METRIC_PRECISION)
    return Metric(name=name, value=value, formula=METRIC_FORMULAS[name],
                  computable=True)


def _peer_percentile(x, peer_values):
    """x 在同儕值序列中的百分位（≤ x 之比例 × 100），四捨五入至 4 位。"""
    vals = [v for v in (_to_float(p) for p in peer_values) if v is not None]
    if not vals:
        return None
    le_count = sum(1 for v in vals if v <= x)
    return round(le_count / len(vals) * 100, _METRIC_PRECISION)


def _peer_zscore(x, peer_values):
    """x 相對同儕的 z-score = (x − 平均) / 標準差；標準差為 0/樣本不足 → None。"""
    vals = [v for v in (_to_float(p) for p in peer_values) if v is not None]
    if len(vals) < 2:
        return None
    mean = sum(vals) / len(vals)
    var = sum((v - mean) ** 2 for v in vals) / len(vals)
    std = math.sqrt(var)
    if std == 0:
        return None
    return round((x - mean) / std, _METRIC_PRECISION)


def compute_expense_structure(expense, personnel, operating):
    """計算支出結構三類占比：人事／業務／其他（R7.3）。

    定義（皆以總支出為分母）：
      - personnel_share = 人事費 / 總支出
      - operating_share = 業務費 / 總支出
      - other_share     = (總支出 − 人事費 − 業務費) / 總支出

    設計不變式：三類占比合計恆為 1（在浮點四捨五入下介於 0.99–1.01，R7.3），
    因為 other_share 以「餘額」定義（總支出 − 人事 − 業務），故
    personnel + operating + other 在代數上等於 總支出 / 總支出 = 1。

    缺值保護（R7.11）：
      - 總支出為 0 或缺值 → 回傳空 dict，該指標被視為不可計算並排除，
        不拋例外，也不影響其餘指標。
      - 人事費／業務費缺值時以 0 代入（未提報視為 0），確保仍可輸出結構，
        餘額歸入「其他」。

    參數
    ----
    expense : 總支出（分母）。
    personnel : 人事費。
    operating : 業務費。

    回傳
    ----
    dict[str, float]
        含 personnel_share／operating_share／other_share（4 位小數）；
        總支出為 0／缺值時回傳空 dict。
    """
    total = _to_float(expense)
    if total is None or total == 0:
        return {}

    personnel_amt = _to_float(personnel) or 0.0
    operating_amt = _to_float(operating) or 0.0
    other_amt = total - personnel_amt - operating_amt

    return {
        "personnel_share": round(personnel_amt / total, _METRIC_PRECISION),
        "operating_share": round(operating_amt / total, _METRIC_PRECISION),
        "other_share": round(other_amt / total, _METRIC_PRECISION),
    }


def compute_metrics(row, peer_stats=None):
    """計算明確公式鑑識指標並回傳 ForensicMetrics（R7.1, 7.2, 7.4, 7.5, 7.9）。

    參數
    ----
    row : Mapping
        單一機構單一年度的財務欄位，支援鍵：
        income_actual, expense_actual, income_last_year, expense_last_year,
        personnel_expense（人事費）, operating_expense（業務費）,
        enrollment（招生人數）。
    peer_stats : Mapping | None
        同儕統計資訊，用於收入/招生一致性與同儕 z-score／百分位（R7.2, R7.5）。
        支援鍵：
          - "income_per_child_median"：同儕每名幼兒收入中位數（供一致性指標）。
          - "income_per_child_values"：同儕每名幼兒收入序列（供 z-score／百分位）。

    回傳
    ----
    ForensicMetrics
        六項明確公式指標（每項為帶公式字串的 Metric，值為 4 位小數或 None），
        並於 expense_structure 附上收入/招生一致性與同儕 z-score／百分位。
        分母為 0／缺值時該指標 computable=False（R7.11 安全保護）。
    """
    if hasattr(row, "get"):
        get = row.get
    else:  # 支援 dataclass / 具屬性物件
        get = lambda k, default=None: getattr(row, k, default)  # noqa: E731

    income = get("income_actual")
    expense = get("expense_actual")
    income_last = get("income_last_year")
    expense_last = get("expense_last_year")
    personnel = get("personnel_expense")
    operating = get("operating_expense")
    enrollment = get("enrollment")

    # 六項明確公式指標（R7.1）。
    income_growth = _growth_metric("income_growth", income, income_last)
    expense_growth = _growth_metric("expense_growth", expense, expense_last)
    personnel_ratio = _make_metric("personnel_ratio", personnel, expense)
    operating_ratio = _make_metric("operating_ratio", operating, expense)
    income_per_child = _make_metric("income_per_child", income, enrollment)
    expense_per_child = _make_metric("expense_per_child", expense, enrollment)

    # 支出結構三類占比：人事／業務／其他，合計介於 0.99–1.01（R7.3）。
    # 總支出為 0／缺值時回傳空 dict（該指標不可計算、被排除，不中斷其餘指標，R7.11）。
    extra: dict[str, float] = compute_expense_structure(expense, personnel, operating)

    # 收入/招生一致性與同儕 z-score／百分位（R7.2, R7.5）。
    peer_stats = peer_stats or {}
    ipc = income_per_child.value
    if income_per_child.computable and ipc is not None:
        median = _to_float(peer_stats.get("income_per_child_median")
                           if hasattr(peer_stats, "get") else None)
        if median is not None and median != 0:
            # 一致性指標：相對同儕中位數的偏離比例（R7.2）。
            extra["income_enrollment_consistency"] = round(
                (ipc - median) / abs(median), _METRIC_PRECISION
            )
        peer_values = (peer_stats.get("income_per_child_values")
                       if hasattr(peer_stats, "get") else None) or []
        z = _peer_zscore(ipc, peer_values)
        if z is not None:
            extra["income_per_child_zscore"] = z
        pct = _peer_percentile(ipc, peer_values)
        if pct is not None:
            extra["income_per_child_percentile"] = pct

    return ForensicMetrics(
        income_growth=income_growth,
        expense_growth=expense_growth,
        personnel_ratio=personnel_ratio,
        operating_ratio=operating_ratio,
        income_per_child=income_per_child,
        expense_per_child=expense_per_child,
        expense_structure=extra,
    )


# ==========================================================================
# 突變門檻與跨年度趨勢（Sudden Change & Cross-Year Trend, Task 2.3）
# --------------------------------------------------------------------------
# 對齊 design.md「Components and Interfaces → 1. Forensic_Engine」：
#   sudden_change_flag(yoy_rate, threshold=0.30) -> bool
# 需求：
#   R7.6：YoY 變動率絕對值達到門檻（預設 0.30，可設定範圍 0.01–5.00）→ 標記突變。
#   R7.7：提供涵蓋至少 3 個年度的跨年度趨勢；不足 3 年取全部可得年度。
#   R7.10：保留既有班佛（MAD+卡方）、Beneish 改良版、Isolation Forest、IQR 方法
#          （皆於本檔上方定義，未被本區塊改動）。
# ==========================================================================

# 突變門檻可設定範圍（R7.6）。
SUDDEN_CHANGE_THRESHOLD_MIN = 0.01
SUDDEN_CHANGE_THRESHOLD_MAX = 5.00
# 跨年度趨勢的最小涵蓋年度數（R7.7）。
TREND_MIN_YEARS = 3


def sudden_change_flag(yoy_rate, threshold=0.30):
    """判定某指標的年度對年度（YoY）變動是否構成「突變」（R7.6）。

    定義（對齊 design.md）：
        flag 為真 若且唯若 |yoy_rate| >= threshold。

    參數
    ----
    yoy_rate : float | None
        YoY 變動率（小數形式，例如 0.30 代表 +30%）。
        注意：本函式以「小數比率」為單位，與既有 ``yoy_flag`` 以百分比（30）
        為單位不同；兩者並存，各自服務不同呼叫端（``yoy_flag`` 供既有
        ``analyze`` 管線，本函式對齊 R7.6 的比率門檻語意）。
        yoy_rate 為 None（該指標不可計算，R7.11）→ 一律回傳 False，
        使不可計算指標被排除於突變判定之外。
    threshold : float, 預設 0.30
        突變門檻，可設定範圍 0.01–5.00（R7.6）。超出範圍將夾擠（clamp）
        至最近的合法邊界，確保門檻恆落在有效區間而不拋例外。

    回傳
    ----
    bool
        |yoy_rate| >= 有效門檻 時為 True，否則 False。
    """
    rate = _to_float(yoy_rate)
    if rate is None:
        return False
    # 將門檻夾擠至合法範圍 [0.01, 5.00]（R7.6）。
    thr = _to_float(threshold)
    if thr is None:
        thr = 0.30
    thr = max(SUDDEN_CHANGE_THRESHOLD_MIN, min(thr, SUDDEN_CHANGE_THRESHOLD_MAX))
    return abs(rate) >= thr


def cross_year_trend(year_values, min_years=TREND_MIN_YEARS):
    """建立涵蓋至少 3 個年度的跨年度趨勢；不足 3 年取全部可得年度（R7.7）。

    參數
    ----
    year_values : Mapping[int, float] | Iterable[tuple[int, float]]
        年度 → 指標值的對應。可為 dict（{112: v1, 113: v2, ...}）或
        (year, value) 的可迭代序列。缺值（None／NaN）之年度會被略過。
    min_years : int, 預設 3
        期望涵蓋的最小年度數（R7.7 = 3）。

    回傳
    ----
    dict
        {
          "years":  [由舊到新排序的年度],
          "values": [對應年度值（4 位小數）],
          "yoy_rates": [相鄰年度 YoY 比率；長度 = len(years) - 1，首年無前值故從缺],
          "covers_min_years": bool,  # 是否涵蓋 >= min_years 個年度
          "n_years": int,            # 實際涵蓋年度數（= 全部可得年度數，不足時取全部）
        }
        無任何可得年度時 years/values/yoy_rates 皆為空、covers_min_years=False。

    設計說明
    --------
    - 年度由舊到新排序，確保趨勢方向一致（與 R5.3/R12.1 時間軸語意一致）。
    - 涵蓋「全部可得年度」：不足 min_years 時不補值、不截斷，直接取全部
      可得年度（R7.7）。因此 n_years == 可得年度總數。
    - yoy_rates 以相鄰兩年計算 (cur - prev) / |prev|；prev 為 0 時該點以 None
      表示（不可計算，呼應 R7.11 的除零保護），不拋例外。
    """
    # 正規化為 (year, value) 序列。
    if hasattr(year_values, "items"):
        pairs = list(year_values.items())
    else:
        pairs = list(year_values)

    # 過濾缺值年度，並將年度轉為可排序數值。
    cleaned = []
    for year, value in pairs:
        v = _to_float(value)
        if v is None:
            continue
        try:
            y = int(year)
        except (TypeError, ValueError):
            continue
        cleaned.append((y, round(v, _METRIC_PRECISION)))

    # 由舊到新排序，全部可得年度皆納入（不足 min_years 取全部，R7.7）。
    cleaned.sort(key=lambda pair: pair[0])
    years = [y for y, _ in cleaned]
    values = [v for _, v in cleaned]

    # 相鄰年度 YoY 比率（除零 → None，R7.11）。
    yoy_rates = []
    for i in range(1, len(values)):
        prev, cur = values[i - 1], values[i]
        if prev == 0:
            yoy_rates.append(None)
        else:
            yoy_rates.append(round((cur - prev) / abs(prev), _METRIC_PRECISION))

    return {
        "years": years,
        "values": values,
        "yoy_rates": yoy_rates,
        "covers_min_years": len(years) >= min_years,
        "n_years": len(years),
    }
