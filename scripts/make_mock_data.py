"""
產生假資料 kindergartens_latest.csv（組員線介面開發用）
======================================================
用途：讓「介面與 AI 呈現」線在隊長真資料出爐前先全速開工。
欄位完全對齊 docs/data-dictionary.md 與 src/risk_score.py 的輸出契約，
真資料一來，直接用同名檔覆蓋即可，介面不需改動。

資料基礎：
  - 園名/行政區/地址：data/external/addresses.csv（真實 22 間新北市立幼兒園）
  - 裁罰次數/評鑑等第：data/external/penalties.csv（示範資料）
  - 財務數字與鑑識指標：以固定亂數種子合成的「看起來合理」的假值
  - lat/lng：新北市各行政區近似座標（供地圖標點測試）

用法：
    python scripts/make_mock_data.py
輸出：
    data/processed/kindergartens_latest.csv
    data/processed/kindergartens.csv（多年度，供趨勢圖，簡化為近3年）
"""
import os
import random

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(ROOT, "data", "external")
PROC = os.path.join(ROOT, "data", "processed")

random.seed(20260907)  # 固定種子，結果可重現

# ---------- 分項評分規則（與 src/risk_score.py 保持一致）----------
WEIGHTS = {"financial": 0.45, "penalty": 0.30, "eval": 0.15, "sentiment": 0.10}
EVAL_MAP = {"優": 0, "甲": 10, "良": 20, "乙": 40, "中": 50,
            "丙": 70, "待改進": 90, "不通過": 100}

# 新北市各行政區近似中心座標（供地圖標點；真資料會用 Nominatim geocode 精準座標）
DISTRICT_COORD = {
    "板橋區": (25.0095, 121.4626), "三重區": (25.0614, 121.4869),
    "中和區": (24.9998, 121.4990), "永和區": (25.0078, 121.5150),
    "新店區": (24.9678, 121.5420), "樹林區": (24.9906, 121.4207),
    "鶯歌區": (24.9538, 121.3540), "三峽區": (24.9340, 121.3690),
    "淡水區": (25.1677, 121.4406), "五股區": (25.0827, 121.4380),
    "泰山區": (25.0590, 121.4310), "林口區": (25.0776, 121.3915),
    "深坑區": (25.0022, 121.6156), "三芝區": (25.2580, 121.5008),
    "八里區": (25.1509, 121.3980), "萬里區": (25.1793, 121.6893),
    "烏來區": (24.8654, 121.5510), "瑞芳區": (25.1088, 121.8050),
    "金山區": (25.2216, 121.6362), "土城區": (24.9723, 121.4430),
    "蘆洲區": (25.0847, 121.4739), "新莊區": (25.0359, 121.4503),
}


def score_penalty(c):
    return {0: 0, 1: 50, 2: 80}.get(int(c), 100)


def score_eval(grade):
    if not isinstance(grade, str) or grade == "":
        return 30
    return EVAL_MAP.get(grade.strip(), 30)


def score_financial(benford, beneish, iforest, ratio, yoy, deficit_ratio):
    """複刻 risk_score.py 的 score_financial 組成，讓假分數與真管線同規則。"""
    outlier = 100 if (ratio is not None and (ratio > 1.3 or ratio < 0.6)) else 0
    ratio_pts = min((ratio - 1) * 500, 100) if (ratio and ratio > 1) else 0
    yoy_pts = min(abs(yoy) * 2, 100) if yoy is not None else 0
    deficit_pts = min(deficit_ratio * 1000, 100) if deficit_ratio > 0 else 0
    score = (0.25 * benford + 0.20 * beneish + 0.25 * iforest
             + 0.10 * ratio_pts + 0.10 * yoy_pts + 0.10 * deficit_pts)
    return round(min(score, 100), 1)


def risk_level_percentile(series):
    ranks = series.rank(pct=True)

    def lvl(r):
        return "高" if r >= 0.85 else ("中" if r >= 0.50 else "低")
    return ranks.apply(lvl)


def risk_level_abs(total):
    return "高" if total >= 60 else ("中" if total >= 35 else "低")


def build_year(addresses, penalties, year, drift=0.0):
    """為某年度合成一批園資料。drift 讓不同年度數字有差異，供趨勢/年增率。"""
    rows = []
    pen_map = penalties.set_index("park_name").to_dict("index")
    for i, a in addresses.iterrows():
        name = a["park_name"]
        district = a["district"]
        pen = pen_map.get(name, {})
        penalty_count = int(pen.get("penalty_count", 0) or 0)
        eval_grade = pen.get("eval_grade", "") or ""

        # ---- 合成財務數字（規模隨機，含少數異常園）----
        base_income = random.randint(18_000_000, 42_000_000)
        income = int(base_income * (1 + drift + random.uniform(-0.04, 0.04)))
        # 大多數園收支接近平衡，少數刻意做成入不敷出（財務異常示範）
        ratio = round(random.gauss(0.97, 0.10), 4)
        ratio = max(0.6, min(ratio, 1.8))
        expense = int(income * ratio)
        tuition = int(income * random.uniform(0.15, 0.35))
        surplus = income - expense

        # ---- 鑑識會計指標（假值，分布合理）----
        benford_mad = round(abs(random.gauss(0.010, 0.006)), 5)
        benford_sample_n = random.randint(35, 120)
        benford_chi2 = round(random.uniform(3.0, 22.0), 3)
        benford_significant = benford_chi2 > 15.507
        benford_pvalue = round(random.uniform(0.001, 0.9), 5)

        beneish_egdi = round(random.gauss(0.02, 0.08), 4)
        beneish_tata = round(surplus / income, 4) if income else 0.0
        beneish_score = round(min(max(beneish_egdi, 0) * 300
                                  + abs(beneish_tata) * 100, 100), 1)

        iforest_score = round(random.uniform(0, 100), 1)
        # 挑幾個明顯特徵當異常主因（做 AI 輸入與詳情頁展示）
        feat = random.choice([
            "{'expense_income_ratio': 2.1, 'surplus': -1.8, 'benford_mad': 1.2}",
            "{'benford_mad': 2.4, 'expense_yoy_pct': 1.5, 'beneish_score': 0.9}",
            "{'expense_yoy_pct': 2.7, 'expense_income_ratio': 1.1, 'tuition_income_ratio': -0.8}",
        ])

        yoy = round(random.gauss(4.0, 18.0), 2)  # 支出年增率(%)

        # 注意：score_financial 需要「班佛組內相對分」，那是全體層級才算得出來，
        # 因此財務分統一在 finalize() 重算，這裡先不算。
        rows.append({
            "park_id": f"136{i+1:02d}",
            "park_name": name, "park_type": "公校", "year": year,
            "district": district,
            "lat": None, "lng": None,  # 稍後填
            "income_actual": income, "expense_actual": expense,
            "tuition_actual": tuition, "surplus": surplus,
            "expense_income_ratio": ratio,
            "benford_mad": benford_mad, "benford_sample_n": benford_sample_n,
            "benford_chi2": benford_chi2, "benford_pvalue": benford_pvalue,
            "benford_significant": benford_significant,
            "beneish_score": beneish_score, "beneish_egdi": beneish_egdi,
            "beneish_tata": beneish_tata,
            "iforest_score": iforest_score, "iforest_explain": feat,
            "expense_yoy_pct": yoy,
            "penalty_count": penalty_count, "eval_grade": eval_grade,
            "score_penalty": score_penalty(penalty_count),
            "score_eval": score_eval(eval_grade),
        })
    return pd.DataFrame(rows)


def finalize(df):
    """全體層級計算：班佛相對分、財務分、輿情分、座標、總分、等級。"""
    # 班佛分數用組內 MAD 百分位（複刻 forensic.analyze 的相對排名做法）
    df["benford_score"] = (df["benford_mad"].rank(pct=True) * 100).round(0)

    # 重算財務分（現在有正確的 benford_score）
    def sf(r):
        return score_financial(
            benford=r["benford_score"], beneish=r["beneish_score"],
            iforest=r["iforest_score"], ratio=r["expense_income_ratio"],
            yoy=r["expense_yoy_pct"],
            deficit_ratio=(abs(r["surplus"]) / r["income_actual"]
                           if r["surplus"] < 0 and r["income_actual"] else 0.0),
        )
    df["score_financial"] = df.apply(sf, axis=1)

    # 輿情分：假的負面比例（少數園偏高當亮點），對齊 score_sentiment 規則
    df["neg_ratio"] = [round(abs(random.gauss(0.18, 0.12)), 3) for _ in range(len(df))]
    df["score_sentiment"] = df["neg_ratio"].apply(lambda x: round(min(x * 100, 100), 1))

    # 座標：行政區中心 + 小抖動（避免完全重疊）
    lats, lngs = [], []
    for d in df["district"]:
        base = DISTRICT_COORD.get(d, (25.02, 121.46))
        lats.append(round(base[0] + random.uniform(-0.01, 0.01), 6))
        lngs.append(round(base[1] + random.uniform(-0.01, 0.01), 6))
    df["lat"], df["lng"] = lats, lngs

    # 總分（白盒子加權）
    df["risk_total"] = (
        WEIGHTS["financial"] * df["score_financial"]
        + WEIGHTS["penalty"] * df["score_penalty"]
        + WEIGHTS["eval"] * df["score_eval"]
        + WEIGHTS["sentiment"] * df["score_sentiment"]
    ).round(1)
    df["risk_level"] = risk_level_percentile(df["risk_total"])
    df["risk_level_abs"] = df["risk_total"].apply(risk_level_abs)
    return df.sort_values("risk_total", ascending=False)


OUT_COLS = ["park_id", "park_name", "park_type", "year", "district", "lat", "lng",
            "income_actual", "expense_actual", "tuition_actual", "surplus",
            "expense_income_ratio", "benford_mad", "benford_sample_n", "benford_score",
            "benford_chi2", "benford_pvalue", "benford_significant",
            "beneish_score", "beneish_egdi", "beneish_tata",
            "iforest_score", "iforest_explain", "expense_yoy_pct",
            "penalty_count", "eval_grade",
            "score_financial", "score_penalty", "score_eval", "score_sentiment",
            "neg_ratio", "risk_total", "risk_level", "risk_level_abs"]


def main():
    os.makedirs(PROC, exist_ok=True)
    addresses = pd.read_csv(os.path.join(EXT, "addresses.csv"))
    penalties = pd.read_csv(os.path.join(EXT, "penalties.csv")) \
        .drop_duplicates("park_name", keep="first")

    # 多年度（112/113/114）供趨勢圖
    frames = []
    for yr, drift in [(112, -0.06), (113, 0.0), (114, 0.05)]:
        frames.append(build_year(addresses, penalties, yr, drift))
    full = pd.concat(frames, ignore_index=True)
    full = finalize(full)
    full[OUT_COLS].to_csv(os.path.join(PROC, "kindergartens.csv"),
                          index=False, encoding="utf-8-sig")

    # 最新年度快照（每園一列）
    latest = (full.sort_values("year", ascending=False)
                  .drop_duplicates("park_name", keep="first")
                  .sort_values("risk_total", ascending=False))
    latest[OUT_COLS].to_csv(os.path.join(PROC, "kindergartens_latest.csv"),
                            index=False, encoding="utf-8-sig")

    print(f"[OK] 已產假資料：{len(latest)} 間園（最新年度快照）")
    print(f"     data/processed/kindergartens_latest.csv")
    print(f"     data/processed/kindergartens.csv（{len(full)} 列，多年度）")
    print()
    print(latest[["park_name", "risk_total", "risk_level",
                  "score_financial", "score_penalty"]].head(8).to_string(index=False))


if __name__ == "__main__":
    main()
