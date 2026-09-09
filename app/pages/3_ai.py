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
from lib import common  # noqa: E402
from src import ai_report  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜AI 決策支援",
    header_title="AI 決策支援",
    subtitle="風險因子與證據追溯、AI 白話研判與人工複核。分數以規則與統計計算，AI 僅輔助決策。",
    module="AI 決策支援",
)

df = common.require_data()
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

# ---------- 一鍵稽查前情報告（結構化，功能10）----------
common.section("一鍵稽查前情報告", "case")
st.caption("把數字翻譯成稽查員出勤前能直接用的行動清單："
           "風險概要 → 可疑點 → 建議查核項目 → 需調閱文件。這是 AI 該做的事——"
           "不是算分，而是替稽查員把厚厚的財報濃縮成待辦。")

brief = ai_report.build_briefing(row.to_dict())


def _brief_list(title, items, tone_color):
    lis = "".join(f"<li style='margin:4px 0;'>{common.html.escape(str(x))}</li>"
                  for x in items)
    return (
        f"<div class='sw-panel' style='border-left:4px solid {tone_color};margin-bottom:12px;'>"
        f"<div style='font-weight:600;color:{common.INK};margin-bottom:6px;'>{title}</div>"
        f"<ul style='margin:0;padding-left:20px;color:{common.INK_2};"
        f"font-size:.9rem;line-height:1.7;'>{lis}</ul></div>"
    )


st.markdown(
    f"<div class='sw-scorecard'><div style='font-size:.98rem;color:{common.INK};"
    f"font-weight:600;'>{common.html.escape(brief['summary'])}</div></div>",
    unsafe_allow_html=True,
)
bc1, bc2 = st.columns(2, gap="large")
with bc1:
    st.markdown(_brief_list("可疑點（依鑑識指標）", brief["suspicions"],
                            common.RISK["high"][0]), unsafe_allow_html=True)
    st.markdown(_brief_list("建議查核項目", brief["checks"],
                            common.PRIMARY), unsafe_allow_html=True)
with bc2:
    st.markdown(_brief_list("需調閱文件", brief["documents"],
                            common.RISK["medium"][0]), unsafe_allow_html=True)
    focus = common.audit_focus(row.to_dict())
    st.markdown(
        f"<div class='sw-panel' style='border-left:4px solid {common.RISK['normal'][0]};'>"
        f"<div style='font-weight:600;color:{common.INK};margin-bottom:6px;'>"
        "現場查核重點（濃縮）</div>"
        f"<div style='color:{common.INK_2};font-size:.9rem;line-height:1.7;'>{focus}</div></div>",
        unsafe_allow_html=True,
    )

# 匯出結構化情報為 TXT
brief_txt = (
    f"【稽查前情報告】{park}\n"
    f"風險概要：{brief['summary']}\n\n"
    "可疑點：\n" + "\n".join(f"  {i+1}. {s}" for i, s in enumerate(brief["suspicions"])) +
    "\n\n建議查核項目：\n" + "\n".join(f"  - {c}" for c in brief["checks"]) +
    "\n\n需調閱文件：\n" + "\n".join(f"  - {d}" for d in brief["documents"])
)
st.download_button("下載稽查前情報告（TXT）",
                   data=brief_txt.encode("utf-8"),
                   file_name=f"稽查前情報告_{park}.txt", mime="text/plain")

# ---------- 人工複核（誠實 Empty State：尚無審核流程資料）----------
common.section("人工複核", "check")
common.empty_state(
    "尚未接入複核流程",
    "本版本尚無審核與簽核資料。接入案件管理模組後，稽查人員可在此記錄"
    "複核決定（同意／退回／補件）、承辦人與時間，形成完整稽核軌跡。",
    icon_name="check",
)

# ---------- 自然語言查詢（功能12）----------
common.section("自然語言查詢（篩選助理）", "ai")
st.caption("用白話問，系統把條件轉成篩選並回表格。降低操作門檻，"
           "長官不必學介面也能查。例如：板橋區 收支比異常 又有裁罰 的高風險機構。")

nlq = st.text_input("輸入查詢",
                    placeholder="例：三重區 高風險 收支比大於1 有裁罰",
                    label_visibility="collapsed")


def parse_nlq(q, data):
    """把自然語言關鍵詞轉成 DataFrame 篩選（規則式，可解釋）。回傳 (filtered_df, 條件說明list)。"""
    import re
    res = data.copy()
    conds = []
    if not q or not q.strip():
        return res, conds
    # 行政區
    for d in sorted(data["district"].dropna().unique(), key=len, reverse=True):
        if d in q or d.replace("區", "") in q:
            res = res[res["district"] == d]
            conds.append(f"行政區＝{d}")
            break
    # 風險等級
    if "高風險" in q or ("高" in q and "風險" in q):
        res = res[res["risk_level"] == "高"]
        conds.append("風險等級＝高")
    elif "中風險" in q:
        res = res[res["risk_level"] == "中"]
        conds.append("風險等級＝中")
    elif "低風險" in q:
        res = res[res["risk_level"] == "低"]
        conds.append("風險等級＝低")
    # 機構類型
    if "非營利" in q:
        res = res[res["park_type"] == "非營利"]
        conds.append("類型＝非營利")
    elif "公校" in q or "公立" in q:
        res = res[res["park_type"] == "公校"]
        conds.append("類型＝公校")
    # 收支比
    if "收支比" in q or "入不敷出" in q or "虧損" in q or "短絀" in q:
        m = re.search(r"收支比[大於>＞]{1,2}\s*([\d.]+)", q)
        thr = float(m.group(1)) if m else 1.0
        res = res[res["expense_income_ratio"] > thr]
        conds.append(f"收支比 > {thr:g}")
    # 裁罰
    if "裁罰" in q or "違規" in q or "處分" in q:
        res = res[pd.to_numeric(res["penalty_count"], errors="coerce").fillna(0) > 0]
        conds.append("有裁罰紀錄")
    # 班佛 / 數字造假
    if "班佛" in q or "造假" in q or "數字異常" in q:
        res = res[pd.to_numeric(res["benford_mad"], errors="coerce").fillna(0) >= 0.015]
        conds.append("班佛偏離 ≥ 0.015")
    return res, conds


if nlq.strip():
    result, conds = parse_nlq(nlq, df)
    if conds:
        chips = "　".join(
            f"<span class='sw-badge' style='background:{common.PRIMARY_SOFT};"
            f"color:{common.PRIMARY};border-color:{common.PRIMARY};'>{common.html.escape(c)}</span>"
            for c in conds)
        st.markdown(f"<div style='margin:6px 0 10px;'>解析出的篩選條件：{chips}</div>",
                    unsafe_allow_html=True)
    else:
        st.info("未辨識到具體條件，顯示全部機構。支援關鍵詞："
                "行政區、高／中／低風險、非營利／公校、收支比、裁罰、班佛。")
    result = result.sort_values("risk_total", ascending=False)
    st.markdown(f"<div style='color:{common.MUTED};font-size:.86rem;margin-bottom:8px;'>"
                f"符合 {len(result)} 間。</div>", unsafe_allow_html=True)
    if len(result) > 0:
        body = ""
        for _, r in result.head(30).iterrows():
            body += (
                "<tr>"
                f"<td class='l'>{common.html.escape(str(r['park_name']))}</td>"
                f"<td class='l'>{common.html.escape(str(r['district']))}</td>"
                f"<td class='l'>{common.html.escape(str(r['park_type']))}</td>"
                f"<td>{common.score_bar(r['risk_total'], r['risk_level'])}</td>"
                f"<td class='l'>{common.badge(r['risk_level'])}</td>"
                f"<td>{r['expense_income_ratio']:.3f}</td>"
                f"<td>{int(r['penalty_count'])}</td>"
                "</tr>"
            )
        st.markdown(
            "<table class='sw-table'><thead><tr>"
            "<th class='l'>機構名稱</th><th class='l'>行政區</th><th class='l'>類型</th>"
            "<th>風險分</th><th class='l'>等級</th><th>收支比</th><th>裁罰</th>"
            f"</tr></thead><tbody>{body}</tbody></table>",
            unsafe_allow_html=True,
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
