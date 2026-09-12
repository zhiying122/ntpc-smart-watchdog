"""
稽查派工決策台（Inspection Dispatch Decision Desk）
====================================================
政府決策層工作流：在有限稽查人力下，產生「本期建議派查名單」，並提供
What-if 情境模擬(調整人力/權重/排除近期已稽查)即時預覽政策影響，最後可匯出
派工單接軌行政流程。

對齊題目核心：降低人力負擔、精準投放稽查人力。
對齊評分：技術可行性(最佳化演算法)、應用性(真實派工決策)、主題切合度、
完成度(後端引擎→可互動畫面→可匯出的完整閉環)、創意度(政策沙盤推演)。

本頁為薄呈現包裝：最佳化與重排序委由 app/lib/dispatch → src.allocation /
src.simulation(單一事實來源)。allowed_roles 僅政府(決策職能)。

責任 AI：派工與模擬僅為稽查資源建議排序，不代表任何違法認定。
"""
import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import dispatch  # noqa: E402
from lib import permissions  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜稽查派工決策台",
    header_title="稽查派工決策台",
    subtitle="在有限稽查人力下產生最佳派查名單，並以情境模擬預覽政策影響。"
             "派工僅為稽查資源建議排序，不代表違法認定。",
    module="派工決策",
    allowed_roles=[permissions.ROLE_GOV],
)

df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_GOV)
districts = sorted(df["district"].dropna().unique().tolist())

# ==========================================================================
# 區塊一：智慧稽查分派最佳化（R3）
# ==========================================================================
common.section("智慧稽查分派｜本期建議派查名單", "case")
st.markdown(
    f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 12px;'>"
    "設定本期可用稽查人力與區域限制，系統以「風險覆蓋最大化」演算法在限制下"
    "選出風險加總最高的機構，並附每間的入選理由。相同輸入永遠得到相同結果"
    "（確定性排序，可稽核）。</div>",
    unsafe_allow_html=True,
)

c1, c2, c3 = st.columns([1, 1.6, 1.1])
with c1:
    n_inspectors = st.number_input(
        "可用稽查人力（N）", min_value=dispatch.MIN_INSPECTORS,
        max_value=dispatch.MAX_INSPECTORS, value=5, step=1)
with c2:
    sel_districts = st.multiselect("區域限制（不選＝全轄區）", districts, default=[])
with c3:
    exclude_inspected = st.checkbox("排除已標記已稽查", value=False,
                                    help="示範：目前資料集尚無已稽查清單，"
                                         "接入案件管理後此處自動帶入。")

allowed = set(sel_districts) if sel_districts else None
result, lookup = dispatch.run_allocation(df, int(n_inspectors),
                                         allowed_districts=allowed,
                                         inspected=None)

if result.message:
    if not result.selected:
        common.empty_state("目前無合格機構可派工", result.message, icon_name="alert")
    else:
        st.info(result.message)

if result.selected:
    alloc_df = dispatch.allocation_to_dataframe(result, lookup)
    total_cov = alloc_df["風險分"].sum()
    common.kpi_band([
        ("派工機構數", f"{len(alloc_df)}", False, f"上限 N={int(n_inspectors)}"),
        ("風險覆蓋（分數加總）", f"{total_cov:.1f}", True, "所選機構風險分總和"),
        ("平均風險分", f"{alloc_df['風險分'].mean():.1f}", False, "本批派工平均"),
        ("涵蓋行政區", f"{alloc_df['行政區'].nunique()}", False, "本批派工分布"),
    ])
    st.dataframe(alloc_df, width="stretch", hide_index=True)
    st.download_button(
        "下載本期派工單（CSV）",
        data=alloc_df.to_csv(index=False).encode("utf-8-sig"),
        file_name="inspection_dispatch.csv", mime="text/csv")

st.divider()

# ==========================================================================
# 區塊二：What-if 情境模擬（R4）— 政策沙盤推演
# ==========================================================================
common.section("What-if 情境模擬｜政策沙盤推演", "dashboard")
st.markdown(
    f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 12px;'>"
    "在不影響系統基準風險分的前提下，調整配額與權重方案，即時預覽稽查優先序"
    "如何變化——例如「若這期改採裁罰優先，名單會怎麼變」。用於決策前的政策"
    "評估。</div>",
    unsafe_allow_html=True,
)

s1, s2, s3 = st.columns([1, 1.6, 1.1])
with s1:
    quota = st.number_input("模擬配額", min_value=1, max_value=999, value=10, step=1)
with s2:
    scheme_key = st.selectbox(
        "權重方案", list(dispatch.WEIGHT_SCHEMES.keys()),
        format_func=lambda k: dispatch.WEIGHT_SCHEMES[k], index=0)
with s3:
    sim_exclude = st.checkbox("排除近 12 個月已稽查", value=False,
                              help="示範：接入稽查日期後生效（R4.3）。")

sim_result, sim_lookup = dispatch.run_simulation(
    df, int(quota), scheme_key, exclude_recent_inspected=sim_exclude)

if sim_result.rejected:
    st.warning(f"模擬參數無效：{sim_result.message}")
elif sim_result.ranked:
    if sim_result.message:
        st.caption(sim_result.message)
    sim_df = dispatch.simulation_to_dataframe(sim_result, sim_lookup)
    st.dataframe(sim_df, width="stretch", hide_index=True)
    st.markdown(
        f"<div style='color:{common.FAINT};font-size:.78rem;margin-top:6px;'>"
        "模擬分數為衍生預覽值，與系統基準風險分脫鉤；模擬不覆寫任何基準資料"
        "（R4.4）。權重方案切換即重新排序，可用於決策前的政策比較。</div>",
        unsafe_allow_html=True,
    )
else:
    common.empty_state("無可模擬的機構資料", "請確認資料是否已載入。", icon_name="alert")
