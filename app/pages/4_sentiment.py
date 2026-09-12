"""
官方公開信號分析（Official Public Signals）
======================================
以官方公開資料——裁罰紀錄與評鑑結果（全國教保資訊網）——作為
機構關注信號來源，依 Risk_Taxonomy 歸類並標記嚴重度。

為何用官方資料而非社群評論：
- 公信力最高：官方裁罰/評鑑是政府稽查系統最對味的訊號來源。
- 零成本、免金鑰、無爬蟲法遵風險。
- 每筆信號皆可追溯至官方來源（Evidence_Chain）。

責任邊界：本頁僅呈現官方已公開的事實，不作違法/舞弊認定。
"""
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lib import auth  # noqa: E402
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402
from src import official_signals as osig  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜官方公開信號",
    header_title="官方公開信號分析",
    subtitle="以裁罰紀錄與評鑑結果（全國教保資訊網）呈現機構關注信號，依風險類別歸類。",
    module="官方公開信號",
    allowed_roles=[permissions.ROLE_GOV, permissions.ROLE_INSPECTOR],
)

# 資料授權層：政府/稽查員皆為全欄位可見，仍走一致流程。
df = permissions.authorize_dataframe(common.require_data(),
                                     auth.get_current_role() or permissions.ROLE_GOV)

LABEL_TEXT = {"pos": "正向", "neg": "負向關注", "neu": "中性"}
LABEL_COLOR = {"pos": common.LEVEL_COLOR["低"], "neg": common.LEVEL_COLOR["高"],
               "neu": common.MUTED}
LABEL_BG = {"pos": common.LEVEL_BG["低"], "neg": common.LEVEL_BG["高"], "neu": "#EEF0F3"}
SEVERITY_COLOR = {
    osig.SEVERITY_MAJOR: common.LEVEL_COLOR["高"],
    osig.SEVERITY_MODERATE: common.LEVEL_COLOR["中"],
    osig.SEVERITY_MINOR: common.LEVEL_COLOR["低"],
    "一般": common.MUTED,
}

# ---------- 機構選擇 ----------
park_names = sorted(
    n for n in df["park_name"].dropna().astype(str).unique() if n.strip()
)
if not park_names:
    common.empty_state("目前無機構資料", "資料尚未載入。", icon_name="database")
    st.stop()

park = st.selectbox("選擇機構", park_names)
row = df[df["park_name"].astype(str) == park].iloc[0].to_dict()
report = osig.build_report(row)

common.section(f"{park}　官方公開信號", "sentiment")

common.kpi_band([
    ("信號則數", f"{report.total_count}"),
    ("負向關注則數", f"{report.negative_count}"),
    ("負向比例", f"{report.negative_ratio*100:.0f}%", report.negative_ratio >= 0.5),
    ("裁罰次數", f"{report.penalty_count}"),
])

# ---------- 信號明細表 ----------
common.section("信號明細（含來源與風險類別）", "sentiment")
if report.total_count == 0:
    common.empty_state("查無官方公開信號",
                       "該機構在裁罰與評鑑欄位查無公開資料。", icon_name="inbox")
else:
    body = ""
    for s in report.signals:
        tag = (f"<span class='sw-badge' style='background:{LABEL_BG[s.sentiment]};"
               f"color:{LABEL_COLOR[s.sentiment]};'>{LABEL_TEXT[s.sentiment]}</span>")
        sev_color = SEVERITY_COLOR.get(s.severity, common.MUTED)
        sev = (f"<span style='color:{sev_color};font-weight:600;'>{s.severity}</span>")
        body += (
            f"<tr><td class='l'>{s.text}</td>"
            f"<td class='l'>{s.category}</td>"
            f"<td class='l'>{sev}</td>"
            f"<td class='l'>{tag}</td>"
            f"<td class='l' style='color:{common.MUTED};font-size:.82rem;'>{s.source}</td></tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>信號內容</th><th class='l'>風險類別</th>"
        "<th class='l'>嚴重度</th><th class='l'>關注傾向</th>"
        "<th class='l'>資料來源</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

# 關注傾向圖例
st.markdown(
    "<div style='margin-top:10px;color:%s;font-size:.82rem;'>關注傾向：%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s</div>"
    % (common.MUTED,
       common.dot(LABEL_COLOR["pos"], "正向"),
       common.dot(LABEL_COLOR["neg"], "負向關注"),
       common.dot(LABEL_COLOR["neu"], "中性")),
    unsafe_allow_html=True,
)

common.callout(
    "本頁信號全數取自<b>官方公開資料</b>（全國教保資訊網之裁罰紀錄與評鑑結果），"
    "每筆皆標示<b>資料來源</b>可供追溯。裁罰與評鑑已透過各自分項計入總風險分，"
    "本頁提供依<b>風險類別與嚴重度</b>拆解的可解釋視圖。"
    "本頁僅呈現官方已公開之事實，<b>不構成</b>對機構違法或不合格之認定。"
)

with st.expander("這個功能如何規模化（架構說明）"):
    st.markdown(
        """
        目前以新北市立園的官方裁罰與評鑑資料示範，驗證「官方公開信號 → 風險類別歸類
        → 可解釋呈現」的流程可跑。

        規模化路徑（架構相同、資料量放大）：
        1. 定期同步全國教保資訊網之裁罰紀錄、評鑑結果、收費明細（官方公開、免金鑰）。
        2. 用 AWS Bedrock（Claude）對裁罰處分書全文做語意歸類與嚴重度判讀，
           比關鍵詞法更準、能理解裁罰情節。
        3. 選用擴充：家長／社群輿情微弱訊號（受 15 分上限約束），架構已於規格預留。

        官方資料公信力最高，是政府稽查系統最對味的信號來源。
        """
    )
