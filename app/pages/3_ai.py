"""
AI 決策支援（AI-assisted Decision Support）
================================
把鑑識會計數字轉為「風險因子 → 證據 → AI 研判 → 人工複核」的決策鏈。
分數以規則與統計計算（可解釋），AI 僅輔助研判，最終判定由稽查人員決定。
Bedrock 未設定/失敗時自動用規則式範本，確保可正常展示。
"""
import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import auth  # noqa: E402
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402
from src import ai_report  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜AI 決策支援",
    header_title="AI 決策支援",
    subtitle="風險因子與證據追溯、AI 白話研判與人工複核。分數以規則與統計計算，AI 僅輔助決策。",
    module="AI 決策支援",
    allowed_roles=[permissions.ROLE_GOV, permissions.ROLE_INSPECTOR],
)

# 資料授權層：政府/稽查員皆為全欄位可見，仍走一致流程。
df = permissions.authorize_dataframe(common.require_data(),
                                     auth.get_current_role() or permissions.ROLE_GOV)
has_aws = bool(os.environ.get("AWS_ACCESS_KEY_ID"))

# ---------- 選案件 ----------
names = df.sort_values("risk_total", ascending=False)["park_name"].tolist()
qp = st.query_params.get("park")
default_idx = names.index(qp) if qp in names else 0
park = st.selectbox("選擇案件（機構）", names, index=default_idx)
row = df[df["park_name"] == park].iloc[0]

# ---------- 案件標頭 ----------
common.case_header(row)

# ---------- 風險因子 → 證據（決策支援核心）----------
common.section("風險因子與證據追溯", "ai")
st.caption("每項風險因子均可追溯至具體證據數值，建立「AI 研判 → 風險因子 → 證據 → 人工複核」的可稽核鏈。")
n_factors = common.risk_factors(row.to_dict())

# ---------- AI 白話研判 ----------
common.section("AI 白話研判", "ai")
if has_aws:
    st.caption("已偵測到 AWS 憑證，將呼叫 Bedrock 生成研判（失敗時自動改用規則式範本）。")
else:
    st.caption("未偵測到 AWS 憑證，使用規則式範本生成研判。接上 Bedrock 只需在 .env 設定金鑰。")

if st.button("產生 AI 白話研判", type="primary"):
    with st.spinner("生成中…"):
        text, source = ai_report.generate_report(row.to_dict(), prefer_bedrock=has_aws)
    st.session_state["report_text"] = text
    st.session_state["report_source"] = source
    st.session_state["report_park"] = park

if st.session_state.get("report_park") == park and "report_text" in st.session_state:
    src = st.session_state["report_source"]
    src_color = common.RISK["normal"][0] if src == "bedrock" else common.RISK["medium"][0]
    src_text = "AWS Bedrock 生成" if src == "bedrock" else "規則式範本（未接 Bedrock）"
    st.markdown(
        f"<div class='sw-scorecard'>"
        f"<div style='margin-bottom:8px;color:{common.MUTED};font-size:.76rem;'>"
        f"<span style='width:8px;height:8px;border-radius:50%;background:{src_color};"
        f"display:inline-block;margin-right:6px;'></span>來源：{src_text}</div>"
        f"<div style='font-size:.98rem;line-height:1.95;color:{common.INK};'>"
        f"{st.session_state['report_text']}</div></div>",
        unsafe_allow_html=True,
    )
    st.download_button(
        "下載研判報告（TXT）",
        data=st.session_state["report_text"].encode("utf-8"),
        file_name=f"AI研判_{park}.txt",
        mime="text/plain",
    )

# ---------- 人工複核（誠實 Empty State：尚無審核流程資料）----------
common.section("人工複核", "check")
common.empty_state(
    "尚未接入複核流程",
    "本版本尚無審核與簽核資料。接入案件管理模組後，稽查人員可在此記錄"
    "複核決定（同意／退回／補件）、承辦人與時間，形成完整稽核軌跡。",
    icon_name="check",
)

# ---------- 批次研判 ----------
common.section("批次研判（高風險案件）", "alert")
st.caption("展示可規模化：一鍵為所有高風險案件產生研判，稽查人員不需逐一閱讀財報。")
if st.button("為所有高風險案件產生研判"):
    high = df[df["risk_level"] == "高"].sort_values("risk_total", ascending=False)
    for _, r in high.iterrows():
        text, _ = ai_report.generate_report(r.to_dict(), prefer_bedrock=False)
        st.markdown(
            f"<div class='sw-panel' style='margin-bottom:8px;'>"
            f"<div style='font-weight:600;color:{common.INK};'>{r['park_name']}　"
            f"<span style='color:{common.level_color(r['risk_level'])};'>"
            f"{r['risk_total']:.1f} 分</span></div>"
            f"<div style='color:{common.INK_2};font-size:.88rem;line-height:1.8;margin-top:4px;'>"
            f"{text}</div></div>",
            unsafe_allow_html=True,
        )
