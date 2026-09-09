"""
Fiscalint — 儀表板主頁（風險排名表）
====================================================
稽查工具主頁：頂部 KPI 數字帶 + 篩選橫列 + 自訂排名表（掃異常用）。
啟動：streamlit run app/主頁.py
"""
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import common  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜風險總覽",
    header_title="風險總覽",
    subtitle="全體受監理機構的風險評估總覽，依總風險分排序協助稽查資源投放。",
    module="風險總覽",
)

df = common.require_data()
full = common.load_full()

# ---------- 第一層：Risk Overview（企業級 KPI stat 帶）----------
n_high = int((df["risk_level"] == "高").sum())
n_mid = int((df["risk_level"] == "中").sum())
n_flags = int(sum(common.red_flag_count(r) for _, r in df.iterrows()))
n_penalized = int((pd.to_numeric(df["penalty_count"], errors="coerce").fillna(0) > 0).sum())
common.kpi_band([
    ("納管機構數", f"{len(df)}", False, "全體受監理教保機構"),
    ("高風險機構", f"{n_high}", True, "建議優先稽查"),
    ("鑑識紅旗總數", f"{n_flags}", n_flags > 0, "觸發鑑識會計異常規則"),
    ("已有裁罰紀錄", f"{n_penalized}", False, "作為模型驗證標籤"),
    ("平均風險分", f"{df['risk_total'].mean():.1f}", False, "全體平均"),
])

# ---------- 第二層：風險分布 + 優先案件 ----------
col_dist, col_prio = st.columns([1, 1.35], gap="large")
with col_dist:
    common.section("風險分布", "shield")
    counts = df["risk_level"].value_counts().to_dict()
    common.risk_distribution(counts, len(df))
with col_prio:
    common.section("優先稽查案件", "alert")
    common.priority_cases(df, n=5)

# ---------- 第三層：完整機構風險排名表 ----------
common.section("機構風險排名（完整）", "dashboard")

# ---------- 篩選橫列（資料表正上方）----------
f1, f2, f3, f4, f5 = st.columns([1.1, 1.4, 1.6, 1.3, 1.1])
with f1:
    types = sorted(df["park_type"].dropna().unique().tolist())
    # 少選項用 pills 多選（膠囊按鈕），全選也不會出現 multiselect 的 "No results"
    sel_types = st.pills("機構類型", types, selection_mode="multi", default=types)
with f2:
    levels_all = ["高", "中", "低"]
    sel_levels = st.pills("風險等級", levels_all, selection_mode="multi", default=levels_all)
with f3:
    # 行政區選項多，維持 multiselect（有下拉搜尋），預設不全選故無 "No results"
    districts = sorted(df["district"].dropna().unique().tolist())
    sel_districts = st.multiselect("行政區", districts, default=[])
with f4:
    sort_field = st.selectbox(
        "排序欄位",
        ["總風險分", "財務分", "裁罰分", "評鑑分", "收支比"],
        index=0,
    )
with f5:
    sort_dir = st.selectbox("排序", ["由高至低", "由低至高"], index=0)

SORT_MAP = {
    "總風險分": "risk_total", "財務分": "score_financial", "裁罰分": "score_penalty",
    "評鑑分": "score_eval", "收支比": "expense_income_ratio",
}

mask = (
    df["park_type"].isin(sel_types)
    & df["risk_level"].isin(sel_levels)
)
if sel_districts:
    mask &= df["district"].isin(sel_districts)

view = (df[mask]
        .sort_values(SORT_MAP[sort_field], ascending=(sort_dir == "由低至高"))
        .reset_index(drop=True))

st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:2px 0 10px;'>"
    f"共 {len(view)} 間，依「{sort_field}」{sort_dir}排序。</div>",
    unsafe_allow_html=True,
)

if len(view) == 0:
    st.warning("目前篩選條件下沒有符合的機構，請放寬條件。")
    st.stop()

common.render_ranking_table(view)

# 圖例
st.markdown(
    "<div style='margin:12px 0 4px;color:%s;font-size:.82rem;'>風險等級："
    "%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s"
    "&nbsp;&nbsp;·&nbsp;&nbsp;分數條長度＝風險分相對高低，越長越需優先稽查。</div>"
    % (common.MUTED,
       common.dot(common.LEVEL_COLOR["高"], "高風險"),
       common.dot(common.LEVEL_COLOR["中"], "中風險"),
       common.dot(common.LEVEL_COLOR["低"], "低風險")),
    unsafe_allow_html=True,
)

st.download_button(
    "下載目前篩選結果（CSV）",
    data=view.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
    file_name="risk_ranking_filtered.csv",
    mime="text/csv",
)

with st.expander("風險分數如何計算（白盒子說明）"):
    st.markdown(
        """
        總風險分是可解釋的加權組合，非黑盒子：

        ```
        總風險分 = 財務異常 ×50% + 裁罰紀錄 ×34% + 評鑑結果 ×16%
        ```

        - 財務異常：鑑識會計四層方法（班佛定律、Beneish 改良、Isolation Forest、收支比離群）
        - 裁罰紀錄：0 次 = 0、1 次 = 50、2 次 = 80、3 次以上 = 100
        - 評鑑結果：優 = 0、良 = 20、乙 = 40、待改進 = 90

        資料來源皆為真實 PDF 抽取：
        - 公校（22 間）：新北市地方教育發展基金決算書第 5 冊（文字層抽取，含逐筆明細供班佛檢定）
        - 非營利園（38 間）：非營利幼兒園財務報告掃描檔（Tesseract 中文 OCR）

        註：輿情負面度因尚未接入真實網路輿情資料源，暫不納入計分（避免以佔位值稀釋
        真實風險分）。接入真實輿情後可再加回並重新分配權重。
        """
    )

# ---------- 第四層：本期惡化榜（事前主動示警）----------
common.section("本期風險惡化榜（優先關注）", "alert")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "風險分較前一年度上升最多的機構。變化量比絕對分更具預警意義，"
    "呼應命題「從事後被動稽查提前為事前主動示警」。</div>",
    unsafe_allow_html=True,
)
common.deterioration_board(df, full, n=8)

# ---------- 第五層：模型可信度（裁罰驗證摘要）----------
common.section("模型可信度：風險分 vs 實際裁罰", "check")
stats = common.penalty_validation(df)
c_val1, c_val2 = st.columns([1, 1.1], gap="large")
with c_val1:
    common.kpi_band([
        ("高分組裁罰率", f"{stats['high_rate']:.0f}%", True,
         f"風險分 ≥ {stats['threshold']:.0f} 者"),
        ("低分組裁罰率", f"{stats['low_rate']:.0f}%", False,
         f"風險分 < {stats['threshold']:.0f} 者"),
    ])
    lift = (stats["high_rate"] / stats["low_rate"]) if stats["low_rate"] else float("inf")
    lift_txt = "∞" if lift == float("inf") else f"{lift:.1f} 倍"
    st.markdown(
        f"<div class='sw-callout' style='margin-top:12px;'>"
        f"<b>鑑別力驗證</b><br>高分組被裁罰的比率是低分組的 <b>{lift_txt}</b>，"
        "代表本模型算出的高風險分數確實與實際違規行為正相關，"
        "非隨機評分。完整混淆矩陣與命中率見「鑑識分析」頁。</div>",
        unsafe_allow_html=True,
    )
with c_val2:
    st.markdown("<div style='font-weight:600;font-size:.9rem;margin-bottom:6px;'>"
                "分類混淆矩陣（以中位數為門檻）</div>", unsafe_allow_html=True)
    st.markdown(common.confusion_matrix_html(stats), unsafe_allow_html=True)
    st.markdown(
        f"<div style='margin-top:8px;color:{common.MUTED};font-size:.8rem;'>"
        f"精確率 {stats['precision']:.0f}%（判高風險者中確有裁罰的比例）、"
        f"召回率 {stats['recall']:.0f}%（實際被裁罰者中被判高風險的比例）。</div>",
        unsafe_allow_html=True,
    )
