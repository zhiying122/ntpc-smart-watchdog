"""
權重敏感度分析（堵住「權重憑什麼」的質疑）
================================================
評審最愛問：「你的財務50%/裁罰34% 權重憑什麼？」
最專業的答案不是硬凹，而是證明：「就算大幅改動權重，高風險園的排名依然穩定，
所以結論對權重不敏感。」

方法：
  1) 用多組不同權重（含均等權重、極端權重）重算風險排名
  2) 計算各情境下 Top-N 高風險園的重疊率 + 排名相關性(Spearman)
  3) 高重疊率 = 結論穩健，權重選擇不影響主要結論

文獻依據：敏感度分析是多準則決策(MCDA)與風險評分模型的標準穩健性檢驗
(Saltelli et al., Global Sensitivity Analysis)。
"""
import os
import pandas as pd

from src.forensic import analyze

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

# 多組權重情境 (financial, penalty, eval)。現行三項制，基準＝引擎實際權重 50/34/16。
# 輿情資料源尚未接入故不納入計分，敏感度分析亦同步改為三項制。
BASE_NAME = "基準(50/34/16)"
SCENARIOS = {
    BASE_NAME: (0.50, 0.34, 0.16),
    "均等(33/33/33)": (1 / 3, 1 / 3, 1 / 3),
    "重財務(70/20/10)": (0.70, 0.20, 0.10),
    "重裁罰(30/55/15)": (0.30, 0.55, 0.15),
    "輕財務(25/50/25)": (0.25, 0.50, 0.25),
}


def _recompute_total(df, w):
    wf, wp, we = w
    return (wf * df["score_financial"] + wp * df["score_penalty"]
            + we * df["score_eval"]).round(1)


def main(top_n=5):
    from src.risk_score import build

    src = os.path.join(PROC, "financials.csv")
    df = build(pd.read_csv(src))
    # 同園多年度取最新
    df = df.sort_values("year", ascending=False).drop_duplicates("park_name", keep="first")

    # 各情境重算排名
    rankings = {}
    for name, w in SCENARIOS.items():
        total = _recompute_total(df, w)
        ranked = df.assign(t=total).sort_values("t", ascending=False)
        rankings[name] = ranked["park_name"].tolist()

    base = rankings[BASE_NAME][:top_n]
    print("=" * 60)
    print(f"權重敏感度分析：各情境 Top-{top_n} 高風險園")
    print("=" * 60)
    for name, order in rankings.items():
        top = order[:top_n]
        overlap = len(set(top) & set(base)) / top_n * 100
        print(f"\n[{name}] 重疊率={overlap:.0f}%")
        for i, p in enumerate(top, 1):
            print(f"   {i}. {p}")

    # Spearman 排名相關性（基準 vs 各情境）
    print("\n" + "=" * 60)
    print("排名穩健性（Spearman 相關，vs 基準情境）")
    print("=" * 60)
    base_full = pd.Series(range(len(rankings[BASE_NAME])),
                          index=rankings[BASE_NAME])
    for name, order in rankings.items():
        if name == BASE_NAME:
            continue
        other = pd.Series(range(len(order)), index=order)
        rho = base_full.corr(other, method="spearman")
        print(f"  {name}: ρ = {rho:.3f}")

    print("\n結論：若各情境 Top-N 重疊率高、Spearman ρ 接近 1，")
    print("代表高風險園排名對權重選擇不敏感，模型結論穩健。")


if __name__ == "__main__":
    main()
