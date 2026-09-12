"""
民眾端預覽（Public View Simulator）
====================================================
政府後台內的「民眾端預覽」頁：讓官員/長官隨時查看「我們開放給民眾看到的
去識別化公開資料長什麼樣子」，確保無任何機密（風險分數／裁罰細節／內部
研判）外洩。此為責任 AI 與資料治理（Responsible AI & Data Privacy）的
具體展示——資料在「資料層」就已投影去識別化，非前端隱藏。

本頁不新增任何計算邏輯，只薄包裝既有、已驗證通過的核心：
  - permissions.authorize_dataframe(df, ROLE_PARENT)：資料層實際移除風險欄位。
  - parent_portal.build_public_view / build_disclosure_fields：家長公開檢視。

呈現策略（Demo 衝擊力）：左「後台實際持有」對比右「民眾實際看到」，
讓評審一眼看出後台滿滿的風險分數/裁罰細節，到民眾端只剩去識別化公開欄位。

allowed_roles 僅政府（治理視角）。
責任 AI：風險（risk）不等於違法（illegality）；家長入口不揭露任何風險分數。
"""
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import parent_portal  # noqa: E402
from lib import permissions  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜民眾端預覽",
    header_title="民眾端預覽（Public View Simulator）",
    subtitle="檢視開放給民眾的去識別化公開資料。風險分數、裁罰細節與內部研判"
             "在資料層即被移除，非前端隱藏——確保無機密外洩。",
    module="民眾端預覽",
    crumb="Public View",
    allowed_roles=[permissions.ROLE_GOV],
)

# 政府視角的完整資料（後台實際持有）。
gov_df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_GOV)
# 民眾視角：資料層授權後的去識別化資料（實際已移除風險欄位）。
public_df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_PARENT)

# ---------- 選機構 ----------
names = gov_df.sort_values("risk_total", ascending=False)["park_name"].tolist()
park = st.selectbox("選擇機構（以最高風險排序，凸顯對比效果）", names, index=0)
gov_row = gov_df[gov_df["park_name"] == park].iloc[0]

# ==========================================================================
# 責任 AI 說明
# ==========================================================================
common.callout(
    "此頁模擬「民眾端公開查詢網」看到的內容。後台的風險分數與內部研判屬公務"
    "稽查用途，依角色、職責與必要性控管；民眾端在資料授權層取得的資料本身"
    "就不含任何風險欄位，並非前端把分數算出來再隱藏。風險不等於違法。"
)

# ==========================================================================
# 核心對比：後台實際持有 vs 民眾實際看到
# ==========================================================================
common.section("資料揭露對比｜後台持有 vs 民眾可見", "shield")

col_gov, col_pub = st.columns(2)

# ---- 左：後台實際持有（含風險/裁罰內部資料）----
with col_gov:
    st.markdown(
        f"<div style='font-weight:700;color:{common.INK};margin-bottom:8px;'>"
        f"{common.icon('shield', 15, common.RISK['high'][0])} 公務後台實際持有"
        f"<span style='color:{common.RISK['high'][0]};font-size:.74rem;"
        f"margin-left:8px;'>機密·僅公務角色</span></div>",
        unsafe_allow_html=True,
    )
    internal_fields = [
        ("總風險分", f"{gov_row.get('risk_total', '—')}"),
        ("風險等級", f"{gov_row.get('risk_level', '—')}"),
        ("財務異常分項", f"{gov_row.get('score_financial', '—')}"),
        ("裁罰分項", f"{gov_row.get('score_penalty', '—')}"),
        ("評鑑分項", f"{gov_row.get('score_eval', '—')}"),
        ("裁罰次數", f"{gov_row.get('penalty_count', '—')}"),
        ("收支比", f"{gov_row.get('expense_income_ratio', '—')}"),
        ("班佛偏離度(MAD)", f"{gov_row.get('benford_mad', '—')}"),
        ("Beneish 操縱分", f"{gov_row.get('beneish_score', '—')}"),
    ]
    body = ""
    for label, val in internal_fields:
        body += (f"<tr><td class='l'>{label}</td>"
                 f"<td style='color:{common.RISK['high'][0]};font-weight:700;'>"
                 f"{val}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>內部欄位</th><th class='l'>值（機密）</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(f"共 {len(gov_df.columns)} 個欄位（含所有風險分數與鑑識指標）")

# ---- 右：民眾實際看到（去識別化公開欄位）----
with col_pub:
    st.markdown(
        f"<div style='font-weight:700;color:{common.INK};margin-bottom:8px;'>"
        f"{common.icon('check', 15, common.RISK['normal'][0])} 民眾端實際看到"
        f"<span style='color:{common.RISK['normal'][0]};font-size:.74rem;"
        f"margin-left:8px;'>公開·去識別化</span></div>",
        unsafe_allow_html=True,
    )

    # 以既有核心邏輯建構家長公開檢視（含來源時效標記）。
    pub_row = public_df[public_df["park_name"] == park]
    record = pub_row.iloc[0].to_dict() if len(pub_row) else {"park_name": park}
    view = parent_portal.build_public_view(record)
    fields = parent_portal.build_disclosure_fields(
        view, basic_info=record.get("park_name"), reference=date.today()
    )

    body = ""
    for f in fields:
        val = f.display_value
        color = common.INK if f.has_data else common.FAINT
        stale = (f"<span style='color:{common.RISK['medium'][0]};font-size:.72rem;"
                 f"margin-left:6px;'>{f.stale_notice}</span>" if f.stale_notice else "")
        body += (f"<tr><td class='l'>{f.label}</td>"
                 f"<td class='l' style='color:{color};'>{val}{stale}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>公開欄位</th><th class='l'>值（去識別化）</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(f"共 {len(public_df.columns)} 個公開欄位（資料層已移除所有風險欄位）")

# ==========================================================================
# 資料治理佐證：民眾端資料確實不含任何風險欄位
# ==========================================================================
common.section("資料治理佐證｜民眾端資料欄位清單", "dashboard")

leaked = [c for c in public_df.columns if parent_portal.is_risk_field(c)]
if leaked:
    common.callout(
        f"警告：偵測到民眾端資料含疑似風險欄位 {leaked}，請檢查授權投影。",
        tone="alert",
    )
else:
    common.kpi_band([
        ("後台欄位總數", f"{len(gov_df.columns)}", False, "含風險分數與鑑識指標"),
        ("民眾端欄位數", f"{len(public_df.columns)}", False, "僅公開透明欄位"),
        ("風險欄位外洩", "0", False, "資料層已完全移除"),
    ])

st.markdown(
    f"<div style='margin-top:8px;color:{common.INK_2};font-size:.84rem;'>"
    "民眾端資料集實際欄位："
    f"<code>{', '.join(public_df.columns)}</code></div>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='margin-top:6px;color:{common.FAINT};font-size:.78rem;'>"
    "上述欄位由 permissions.authorize_dataframe(role=parent_user) 在資料層投影"
    "產生——risk_total / risk_level / score_* 等欄位在此步驟即被移除，民眾端"
    "程式從未接觸過風險分數。此為責任 AI 與個資保護的資料層保證。</div>",
    unsafe_allow_html=True,
)
