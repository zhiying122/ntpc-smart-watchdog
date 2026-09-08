"""
Fiscalint — 儀表板主頁（風險排名表）
====================================================
稽查工具主頁：頂部 KPI 數字帶 + 篩選橫列 + 自訂排名表（掃異常用）。
啟動：streamlit run app/主頁.py
"""
import os
import sys

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

# ---------- 第一層：Risk Overview（企業級 KPI stat 帶）----------
n_high = int((df["risk_level"] == "高").sum())
n_mid = int((df["risk_level"] == "中").sum())
common.kpi_band([
    ("納管機構數", f"{len(df)}", False, "全體受監理教保機構"),
    ("高風險機構", f"{n_high}", True, "建議優先稽查"),
    ("待複核（中風險）", f"{n_mid}", False, "納入例行追蹤"),
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
        ["總風險分", "財務分", "裁罰分", "評鑑分", "輿情分", "收支比"],
        index=0,
    )
with f5:
    sort_dir = st.selectbox("排序", ["由高至低", "由低至高"], index=0)

SORT_MAP = {
    "總風險分": "risk_total", "財務分": "score_financial", "裁罰分": "score_penalty",
    "評鑑分": "score_eval", "輿情分": "score_sentiment", "收支比": "expense_income_ratio",
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
        總風險分 = 財務異常 ×45% + 裁罰紀錄 ×30% + 評鑑結果 ×15% + 輿情負面 ×10%
        ```

        - 財務異常：鑑識會計四層方法（班佛定律、Beneish 改良、Isolation Forest、收支比離群）
        - 裁罰紀錄：0 次 = 0、1 次 = 50、2 次 = 80、3 次以上 = 100
        - 評鑑結果：優 = 0、良 = 20、乙 = 40、待改進 = 90
        - 輿情負面：網路負面評論比例

        目前為假資料（scripts/make_mock_data.py 產生），供介面開發用。
        真資料產出後，直接覆蓋 data/processed/kindergartens_latest.csv 即可，介面不需改動。
        """
    )

# ---------- 第四層：近期稽查活動（誠實 Empty State）----------
common.section("近期稽查活動", "clock")
common.empty_state(
    "尚未接入稽查活動紀錄",
    "本版本尚無案件審核與稽查軌跡資料。接入案件管理模組後，"
    "此處將顯示各機構的複核狀態、承辦人與時間軸。",
    icon_name="clock",
)
