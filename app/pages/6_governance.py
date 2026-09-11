"""
資料治理權限矩陣（Data Governance / RBAC Matrix）
====================================================
展示 A+ RBAC 的核心：**權限在資料層擋，不是 UI 藏**。

呈現：
  - 資料權限矩陣表（政府/稽查員/家長 × 各資料類別，值為 完整可見/部分可見/不可見）。
  - 責任 AI 說明（家長模式在資料授權層取得的資料本身就不含 risk_total）。
  - 最近的 Audit Log（登入/登出/存取遭拒/檢視）。

本頁 allowed_roles 給政府 + 稽查員（治理視角）。
"""
import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import auth  # noqa: E402
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜資料治理權限矩陣",
    header_title="資料治理權限矩陣",
    subtitle="以角色、職責與必要性決定誰可以看到哪些資料。權限在資料層控管，非前端隱藏。",
    module="資料治理",
    crumb="Data Governance",
    allowed_roles=[permissions.ROLE_GOV, permissions.ROLE_INSPECTOR],
)

# ---------- 角色一覽 ----------
common.section("三種角色（RBAC）", "shield")
cols = st.columns(3)
for col, role in zip(cols, permissions.VALID_ROLES):
    perm = permissions.get_role_permissions(role)
    with col:
        st.markdown(
            f"<div class='sw-panel'>"
            f"<div style='font-size:1.6rem;'>{perm['emoji']}</div>"
            f"<div style='font-weight:700;color:{common.INK};margin-top:4px;'>{perm['name']}</div>"
            f"<div style='color:{common.INK_2};font-size:.82rem;margin-top:6px;'>"
            f"可見資料類別：{len(perm['visible_categories'])} 類<br>"
            f"可見頁面：{len(perm['navigation'])} 頁<br>"
            f"全欄位可見：{'是' if perm['full_access'] else '否'}</div></div>",
            unsafe_allow_html=True,
        )

# ---------- 資料權限矩陣表 ----------
common.section("資料權限矩陣（角色 × 資料類別）", "dashboard")
matrix = permissions.permission_matrix_table()

# 以 HTML 表格呈現（沿用設計系統 .sw-table 樣式）。
header_cells = "".join(f"<th>{c}</th>" if i > 0 else f"<th class='l'>{c}</th>"
                       for i, c in enumerate(matrix.columns))
body_rows = ""
for _, r in matrix.iterrows():
    cells = ""
    for i, c in enumerate(matrix.columns):
        val = str(r[c])
        if i == 0:
            cells += f"<td class='l'>{val}</td>"
        else:
            color = (common.RISK["normal"][0] if val == permissions.FULL
                     else common.RISK["medium"][0] if val == permissions.PARTIAL
                     else common.RISK["high"][0])
            cells += f"<td style='color:{color};font-weight:700;'>{val}</td>"
    body_rows += f"<tr>{cells}</tr>"

st.markdown(
    f"<table class='sw-table'><thead><tr>{header_cells}</tr></thead>"
    f"<tbody>{body_rows}</tbody></table>",
    unsafe_allow_html=True,
)
st.caption(f"圖例：{permissions.FULL} 完整可見　·　{permissions.PARTIAL} 部分可見　·　"
           f"{permissions.NONE} 不可見")

# ---------- 責任 AI 說明 ----------
common.section("責任 AI：權限在資料層控管", "check")
common.callout(
    "風險資訊不是越多人看越好，而是由角色、職責與必要性決定誰可以看到。"
    "家長模式在資料授權層取得的資料本身就不含 risk_total，"
    "並非前端把分數算出來再隱藏。"
)

# ---------- 最近 Audit Log ----------
common.section("最近稽核軌跡（Audit Log）", "clock")
log = auth.get_audit_log()
entries = log.query_audit()
if entries:
    recent = entries[-20:][::-1]  # 最近 20 筆、由新到舊
    body = ""
    for e in recent:
        ts = e.ts.strftime("%Y-%m-%d %H:%M:%S") if hasattr(e.ts, "strftime") else str(e.ts)
        body += (f"<tr><td class='l'>{ts}</td><td class='l'>{e.actor}</td>"
                 f"<td class='l'>{e.action}</td><td class='l'>{e.target}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>時間 (UTC)</th>"
        "<th class='l'>操作者</th><th class='l'>操作</th><th class='l'>對象</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
else:
    common.empty_state("尚無稽核紀錄",
                       "登入、登出、存取遭拒與檢視行為將記錄於此。", "clock")
