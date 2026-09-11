"""
系統健康檢查（System Health）— 維運監控
====================================================
政府級系統上線後的維運監控頁：一眼檢視契約資料新鮮度、動態資料源快取狀態、
核心引擎模組可載入性與資料完整性。屬 Operability by Design。

allowed_roles 僅政府（治理/維運職能）。
"""
import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402
from src import health  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜系統健康檢查",
    header_title="系統健康檢查",
    subtitle="維運監控：資料新鮮度、動態資料源快取、核心引擎與資料完整性狀態。",
    module="健康檢查",
    crumb="System Health",
    allowed_roles=[permissions.ROLE_GOV],
)

# 以現有已載入資料進行完整性檢查（避免重複讀檔）。
df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_GOV)
report = health.run_health_check(df)
counts = report.counts()

_STATUS_COLOR = {
    health.OK: common.RISK["normal"][0],
    health.WARN: common.RISK["medium"][0],
    health.ERROR: common.RISK["high"][0],
}

# ---------- 整體狀態帶 ----------
common.section("整體系統狀態", "shield")
overall_color = _STATUS_COLOR.get(report.overall, common.INK_2)
st.markdown(
    f"<div class='sw-panel' style='border-left:4px solid {overall_color};'>"
    f"<span style='font-size:1.1rem;font-weight:700;color:{overall_color};'>"
    f"整體狀態：{report.overall}</span>"
    f"<span style='color:{common.INK_2};margin-left:16px;font-size:.88rem;'>"
    f"正常 {counts[health.OK]}　·　注意 {counts[health.WARN]}　·　"
    f"異常 {counts[health.ERROR]}　（共 {len(report.items)} 項檢查）</span></div>",
    unsafe_allow_html=True,
)

common.kpi_band([
    ("檢查項目", f"{len(report.items)}", False, "全部健檢項"),
    ("正常", f"{counts[health.OK]}", False, "運作正常"),
    ("注意", f"{counts[health.WARN]}", counts[health.WARN] > 0, "建議處理"),
    ("異常", f"{counts[health.ERROR]}", counts[health.ERROR] > 0, "需立即處理"),
])

# ---------- 分類明細 ----------
by_cat: dict[str, list] = {}
for it in report.items:
    by_cat.setdefault(it.category, []).append(it)

for category, items in by_cat.items():
    common.section(category, "dashboard")
    rows = ""
    for it in items:
        color = _STATUS_COLOR.get(it.status, common.INK_2)
        rows += (
            "<tr>"
            f"<td class='l'><span style='display:inline-block;width:8px;height:8px;"
            f"border-radius:50%;background:{color};margin-right:8px;'></span>"
            f"<span style='color:{color};font-weight:600;'>{it.status}</span></td>"
            f"<td class='l' style='font-weight:600;'>{it.name}</td>"
            f"<td class='l' style='color:{common.INK_2};'>{it.detail}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>狀態</th><th class='l'>項目</th><th class='l'>說明</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"<div style='margin-top:10px;color:{common.FAINT};font-size:.78rem;'>"
    "健檢僅檢視本地狀態，不對外部來源即時發網路請求（避免健檢本身受網路影響）。"
    "動態資料源的即時連線狀態於「資料整合中心」按下同步時回報。</div>",
    unsafe_allow_html=True,
)
