"""
模型驗證：證明「高風險分數的園，確實較常被裁罰」
================================================
這是評審問答「你怎麼證明模型準」的標準答案。
產出：
  1) 統計關聯（有裁罰組 vs 無裁罰組的平均風險分）
  2) 一張證明圖 reports/validation.png
用英文標籤避免 matplotlib 中文亂碼；報告文字用中文於 stdout。
"""
import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CSV = os.path.join(ROOT, "data", "processed", "kindergartens.csv")
REPORT_DIR = os.path.join(ROOT, "reports")


def main():
    df = pd.read_csv(CSV)
    # 同園多年度取最新年度為代表，避免重複計數
    df = df.sort_values("year", ascending=False).drop_duplicates("park_name", keep="first")

    df["has_penalty"] = df["penalty_count"].fillna(0) > 0
    grp = df.groupby("has_penalty")["risk_total"].agg(["mean", "count"])

    with_pen = grp.loc[True, "mean"] if True in grp.index else float("nan")
    without_pen = grp.loc[False, "mean"] if False in grp.index else float("nan")

    print("=" * 50)
    print("模型驗證結果")
    print("=" * 50)
    print(f"有裁罰紀錄的園：平均風險分 = {with_pen:.1f}（{int(grp.loc[True,'count']) if True in grp.index else 0} 間）")
    print(f"無裁罰紀錄的園：平均風險分 = {without_pen:.1f}（{int(grp.loc[False,'count']) if False in grp.index else 0} 間）")
    if with_pen == with_pen and without_pen == without_pen:
        diff = with_pen - without_pen
        print(f"差距：有裁罰組高出 {diff:.1f} 分")
        if diff > 0:
            print("結論：模型有效——被裁罰的園風險分數確實較高，驗證了評分方向正確。")

    # 相關係數（風險分 vs 裁罰次數）
    corr = df["risk_total"].corr(df["penalty_count"].fillna(0))
    print(f"風險分數與裁罰次數的相關係數 = {corr:.3f}")

    # ---------- 繪圖 ----------
    os.makedirs(REPORT_DIR, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))

    # 左：散佈圖 風險分 vs 裁罰次數
    axes[0].scatter(df["penalty_count"].fillna(0), df["risk_total"],
                    c=df["risk_total"], cmap="Reds", s=90, edgecolor="k")
    axes[0].set_xlabel("Penalty Count")
    axes[0].set_ylabel("Risk Score")
    axes[0].set_title(f"Risk Score vs Penalty Count (corr={corr:.2f})")
    axes[0].grid(alpha=0.3)

    # 右：長條圖 有/無裁罰的平均風險分
    labels = ["No Penalty", "Has Penalty"]
    means = [without_pen, with_pen]
    axes[1].bar(labels, means, color=["#4C9F70", "#D1495B"])
    axes[1].set_ylabel("Average Risk Score")
    axes[1].set_title("Avg Risk: Penalized vs Non-penalized")
    for i, v in enumerate(means):
        if v == v:
            axes[1].text(i, v + 0.5, f"{v:.1f}", ha="center", fontweight="bold")
    axes[1].grid(alpha=0.3, axis="y")

    plt.tight_layout()
    out = os.path.join(REPORT_DIR, "validation.png")
    plt.savefig(out, dpi=130)
    print(f"[OK] 驗證圖已存至 {out}")


if __name__ == "__main__":
    main()
