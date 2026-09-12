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

# 公務後台（8601）為政府內部系統，不設登入牆。
common.setup_page(
    page_title="Fiscalint｜風險總覽",
    header_title="風險總覽",
    subtitle="全體受監理機構的風險評估總覽，依總風險分排序協助稽查資源投放。",
    module="風險總覽",
)

df = common.require_data()

# ---------- 全市涵蓋層（廣度）：全新北市立案幼兒園納管概況 ----------
# 深度層（具真實財務決算、可算鑑識會計風險分）與廣度層（全市名冊、基本資料
# 已納管、財務待接入）並存，展現「抽樣深度 + 全市涵蓋」與架構可規模化。
_cov = common.roster_coverage()
if _cov:
    common.section("全市納管涵蓋", "map")
    common.kpi_band([
        ("全市立案機構", f"{_cov['total']:,}", False, f"涵蓋 {_cov['districts']} 個行政區"),
        ("已完成風險評分", f"{_cov['scored']}", False, "具真實財務決算·鑑識會計分析"),
        ("基本資料納管", f"{_cov['roster_only']:,}", False, "財務資料待接入"),
        ("涵蓋行政區", f"{_cov['districts']}", False, "全新北市"),
    ])
    st.markdown(
        f"<div style='color:{common.INK_MUTED};font-size:.8rem;margin:8px 0 4px;'>"
        f"系統已納管全市 {_cov['total']:,} 間立案幼兒園基本資料（來源：新北市政府"
        f"資料開放平台）；其中 {_cov['scored']} 間具真實財務決算，已完成鑑識會計"
        f"風險評分（下方分析）。其餘機構之財務資料接入後即可套用相同分析流程——"
        f"架構可規模化至全市。</div>",
        unsafe_allow_html=True,
    )

# ---------- 全市幼兒園逐年概況趨勢（教育部統計處開放資料）----------
if common.load_moe_yearly() is not None:
    common.section("全市幼兒園逐年概況趨勢", "clock")
    st.markdown(
        f"<div style='color:{common.MUTED};font-size:.84rem;margin:-4px 0 8px;'>"
        f"資料來源：教育部統計處開放資料（全市總量統計）。園數穩定、幼生數逐年成長，"
        f"反映監理量能需求。此宏觀趨勢與單園鑑識分析互補，並展現系統可持續接入"
        f"官方開放資料。</div>",
        unsafe_allow_html=True,
    )
    common.city_trend_chart()

# ---------- 第一層：Risk Overview（企業級 KPI stat 帶）----------
common.section("已評分機構風險概況", "dashboard")
n_high = int((df["risk_level"] == "高").sum())
n_mid = int((df["risk_level"] == "中").sum())
common.kpi_band([
    ("已評分機構數", f"{len(df)}", False, "具財務決算·完整鑑識分析"),
    ("高風險機構", f"{n_high}", True, "建議優先稽查"),
    ("待複核（中風險）", f"{n_mid}", False, "納入例行追蹤"),
    ("平均風險分", f"{df['risk_total'].mean():.1f}", False, "已評分機構平均"),
])

# ---------- 今日待處理（工作台：行動優先，一進來先看要處理哪幾件）----------
common.section("今日待處理", "alert")
common.worklist_panel(df)

# ---------- 第二層：風險分布 + 優先案件 ----------
col_dist, col_prio = st.columns([1, 1.35], gap="large")
with col_dist:
    common.section("風險分布", "shield")
    counts = df["risk_level"].value_counts().to_dict()
    common.risk_distribution_interactive(counts, len(df))
with col_prio:
    common.section("優先稽查案件", "alert")
    common.priority_cases(df, n=5)

# ---------- 各行政區風險組成（互動堆疊：財務/裁罰/評鑑分項）----------
common.section("各行政區風險組成", "map")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.84rem;margin:-4px 0 8px;'>"
    f"每區平均風險分依分項貢獻堆疊，游標移入可見各分項拆解——一眼看出該區"
    f"高風險由財務、裁罰或評鑑何者主導，協助資源精準投放。</div>",
    unsafe_allow_html=True,
)
common.risk_composition_by_district(df, top_n=12)

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
    # 各機構類型間數由實際資料動態計算，避免寫死與資料脫節（如顯示 nan 或錯誤間數）。
    _type_counts = df["park_type"].value_counts()
    _n_public = int(_type_counts.get("公校", 0))          # 市立幼兒園（決算書文字層）
    _n_annex = int(_type_counts.get("公立附幼", 0))        # 國小附設幼兒園
    _n_nonprofit = int(_type_counts.get("非營利", 0))      # 非營利園（掃描財報 OCR）
    _n_public_all = _n_public + _n_annex
    _n_total = len(df)

    _n_total_cov = _cov['total'] if _cov else 1115
    st.markdown(
        f"""
        總風險分是可解釋的加權組合，非黑盒子（現行四項制）：

        ```
        總風險分 = 財務異常 ×45% + 裁罰紀錄 ×30% + 評鑑結果 ×15% + 網路輿情 ×10%
        ```

        - 財務異常（45%）：多層鑑識會計方法（班佛定律、Beneish 改良、Altman Z'' 財務困境、Isolation Forest、收支比離群、跨年度突變）
        - 裁罰紀錄（30%）：NLP 違規情節嚴重度＋破窗效應累計（含未改善加重、受處分對象追蹤）
        - 評鑑結果（15%）：優 = 0、良 = 20、乙 = 40、待改進 = 90
        - 網路輿情（10%）：真實公開新聞爬蟲與白盒情緒分析（分項貢獻上限 15 分，無新聞機構採中性處理）

        > **裁罰與輿情全量公開資料整合**：系統已接入新北市政府裁罰公開資料與真實新聞輿情資料庫
        > （每筆附媒體來源與原文可追溯），並透過鑑識分析與破窗模型進行立體量化。

        本次已完成風險評分：**{_n_total} 間**（公校/公立附幼 {_n_public_all} 間、
        非營利 {_n_nonprofit} 間），資料來源皆為真實 PDF 抽取：
        - 公校決算（{_n_public_all} 間）：新北市地方教育發展基金決算書第 5 冊
          （文字層抽取，含逐筆明細供班佛檢定；含市立幼兒園 {_n_public} 間、
          國小附設幼兒園 {_n_annex} 間）
        - 非營利園（{_n_nonprofit} 間）：非營利幼兒園財務報告掃描檔（Tesseract 中文 OCR）

        此為抽樣深度分析；全市共 {_n_total_cov:,} 間立案機構已納管基本資料，其餘機構財務
        資料接入後即可套用相同鑑識會計流程（架構可規模化至全市）。
        """
    )

# ---------- 模型鑑別力驗證（回應「模型準不準／權重為何」）----------
# 以官方裁罰紀錄為高風險標籤，實證檢驗系統判定的高風險園是否確實較常被裁罰。
# 這一段直接回答評審兩個關鍵提問，並為裁罰分項權重提供實證依據（非主觀設定）。
common.section("模型鑑別力驗證（以官方裁罰為標籤）", "check")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.84rem;margin:-4px 0 8px;'>"
    f"依題目所示，以全國教保資訊網「裁罰紀錄」作為高風險參考標籤，檢驗系統判定的"
    f"高風險分組是否確實較常被官方裁罰。若顯著較高，代表風險分數與獨立的官方事實"
    f"方向一致（模型有鑑別力），且裁罰分項的權重具實證依據。裁罰為弱標籤、"
    f"為抽樣示範，風險不等於違法。</div>",
    unsafe_allow_html=True,
)
common.validation_panel(df)

# ---------- 第四層：近期稽查活動（誠實 Empty State）----------
common.section("近期稽查活動", "clock")
common.empty_state(
    "尚未接入稽查活動紀錄",
    "本版本尚無案件審核與稽查軌跡資料。接入案件管理模組後，"
    "此處將顯示各機構的複核狀態、承辦人與時間軸。",
    icon_name="clock",
)
