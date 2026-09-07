"""
案件調查工作區（Forensic Investigation Workspace）
==========================================
單一機構的鑑識調查頁：案件標頭 + 風險評估雷達 + 建議行動 +
分頁（財務證據 / AI Findings / 跨年度趨勢 / 稽核軌跡）。
只呈現，不改任何計算或資料邏輯。
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from src import ai_report  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜案件調查",
    header_title="案件調查工作區",
    subtitle="單一受監理機構的鑑識會計調查與風險評估。",
    module="案件調查",
)

df = common.require_data()
full = common.load_full()

# ---------- 選案件 ----------
names = df.sort_values("risk_total", ascending=False)["park_name"].tolist()
qp = st.query_params.get("park")
default_idx = names.index(qp) if qp in names else 0
park = st.selectbox("選擇案件（機構）", names, index=default_idx)

row = df[df["park_name"] == park].iloc[0]
level = row["risk_level"]
color = common.level_color(level)

# ---------- 案件標頭 ----------
common.case_header(row)

# ---------- 三欄：風險評估雷達 / 建議行動 ----------
common.section("風險評估", "shield")
col_radar, col_action = st.columns([1.3, 1], gap="large")

with col_radar:
    dims = [label for _, label in common.RADAR_DIMS]
    vals = [float(row[c]) for c, _ in common.RADAR_DIMS]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]], theta=dims + [dims[0]],
        fill="toself", fillcolor=f"{color}2E",
        line=dict(color=color, width=2.5), name=park,
    ))
    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor=common.BORDER,
                            tickfont=dict(size=10, color=common.INK_MUTED)),
            angularaxis=dict(gridcolor=common.BORDER,
                             tickfont=dict(size=12, color=common.INK)),
            bgcolor="#FFFFFF",
        ),
        showlegend=False,
        title=dict(text="四分項風險組成（0-100，越外圈風險越高）",
                   font=dict(size=13, color=common.INK)),
        font=dict(family="Inter, Noto Sans TC, Microsoft JhengHei"),
        height=380, margin=dict(l=50, r=50, t=50, b=36), paper_bgcolor="#FFFFFF",
    )
    st.plotly_chart(fig, width="stretch")

with col_action:
    # 分項加權貢獻表
    st.markdown("<div style='font-weight:600;font-size:.9rem;margin-bottom:6px;'>"
                "分項加權貢獻</div>", unsafe_allow_html=True)
    dims_w = [("財務異常", "score_financial", 0.45), ("裁罰紀錄", "score_penalty", 0.30),
              ("評鑑結果", "score_eval", 0.15), ("輿情負面", "score_sentiment", 0.10)]
    body = ""
    for name, col, w in dims_w:
        s = row[col]
        body += (f"<tr><td class='l'>{name}</td><td>{s:.1f}</td>"
                 f"<td>{int(w*100)}%</td><td>{s*w:.1f}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>分項</th><th>分項分</th>"
        f"<th>權重</th><th>貢獻分</th></tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    # 建議行動
    action = {"高": "建議優先安排實地稽查，重點查核財務與採購憑證。",
              "中": "建議納入例行稽查追蹤，持續監控指標變化。",
              "低": "風險相對偏低，維持常態管理即可。"}.get(level, "持續觀察。")
    st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
    common.callout(f"<b>建議行動</b><br>{action}")

# ---------- 分頁：證據 / AI / 趨勢 / 稽核軌跡 ----------
tab_ev, tab_ai, tab_trend, tab_audit = st.tabs(
    ["財務證據", "AI 風險研判", "跨年度趨勢", "稽核軌跡"])

with tab_ev:
    common.section("鑑識會計指標", "case")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("收支比", f"{row['expense_income_ratio']:.3f}",
              help="支出/收入，大於 1 代表入不敷出")
    m2.metric("班佛偏離度 MAD", f"{row['benford_mad']:.5f}",
              help="首位數分布偏離自然律的程度，越大越可疑")
    m3.metric("Beneish 操縱分", f"{row['beneish_score']:.1f}",
              help="收支成長背離／應計異常，越高越可能操縱")
    m4.metric("孤立森林異常分", f"{row['iforest_score']:.1f}",
              help="多維財務特徵整體異常度")
    m5, m6, m7, m8 = st.columns(4)
    m5.metric("年度支出增減", common.fmt_pct(row["expense_yoy_pct"]))
    m6.metric("裁罰次數", f"{int(row['penalty_count'])}")
    m7.metric("評鑑等第", str(row["eval_grade"]) if str(row["eval_grade"]) else "無資料")
    m8.metric("班佛樣本數", f"{int(row['benford_sample_n'])}")

    common.section("財務概況", "case")
    f1, f2, f3, f4 = st.columns(4)
    f1.metric("收入決算", common.fmt_money(row["income_actual"]))
    f2.metric("支出決算", common.fmt_money(row["expense_actual"]))
    f3.metric("學雜費收入", common.fmt_money(row["tuition_actual"]))
    surplus = row["surplus"]
    f4.metric("本期賸餘／短絀", common.fmt_money(surplus),
              delta="短絀" if surplus < 0 else "賸餘",
              delta_color="inverse" if surplus < 0 else "normal")

with tab_ai:
    common.section("AI 風險研判（決策支援）", "ai")
    st.caption("以下風險因子由鑑識會計指標推導，每項均可追溯至證據數值。"
               "AI 僅輔助研判，最終判定由稽查人員決定。")
    n_factors = common.risk_factors(row.to_dict())
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if st.button("產生 AI 白話研判報告"):
        with st.spinner("生成中…"):
            has_aws = bool(os.environ.get("AWS_ACCESS_KEY_ID"))
            text, src = ai_report.generate_report(row.to_dict(), prefer_bedrock=has_aws)
        src_txt = "AWS Bedrock 生成" if src == "bedrock" else "規則式範本（未接 Bedrock）"
        st.markdown(
            f"<div class='sw-scorecard' style='margin-top:8px;'>"
            f"<div style='color:{common.MUTED};font-size:.76rem;margin-bottom:6px;'>"
            f"來源：{src_txt}</div>"
            f"<div style='font-size:.95rem;line-height:1.9;color:{common.INK}'>{text}</div></div>",
            unsafe_allow_html=True,
        )

with tab_trend:
    common.section("跨年度趨勢", "clock")
    if full is not None and park in set(full["park_name"]):
        hist = full[full["park_name"] == park].sort_values("year")
        if len(hist) > 1:
            trend = hist[["year", "risk_total", "score_financial"]].copy()
            trend["year"] = trend["year"].astype(str)
            trend = trend.set_index("year").rename(
                columns={"risk_total": "總風險分", "score_financial": "財務異常分"})
            st.line_chart(trend, color=[common.STRUCT, common.LEVEL_COLOR["高"]])
            st.caption("觀察風險分與財務異常分逐年變化，突升代表該年出現異常訊號。")
        else:
            common.empty_state("僅有單一年度資料", "此機構目前只有一個年度的決算資料，無法呈現趨勢。")
    else:
        common.empty_state("無跨年度資料", "此機構未出現在多年度資料集中。")

with tab_audit:
    common.section("稽核軌跡", "clock")
    common.empty_state(
        "尚未接入稽核軌跡",
        "本版本尚無案件複核與稽查作業紀錄。接入案件管理模組後，"
        "此處將依時間軸顯示承辦人、複核決定與處理狀態。",
        icon_name="clock",
    )
