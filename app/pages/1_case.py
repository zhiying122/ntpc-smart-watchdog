"""
案件調查工作區（Inspector Investigation Workspace, R5）
==========================================
單一機構的鑑識調查頁（稽查員調查工作台）。本頁為「薄包裝」：
所有計算/組裝邏輯集中於 app/lib/inspector.py（可測試、呈現無關），
本檔僅負責把組裝結果渲染為 Streamlit 介面。

呈現內容（R5）：總風險分與等級、雷達圖四分項組成（加權總和==總分）、
風險時間軸與變化點、財務/收費/營運/法規/NLP 五類分析、同儕比較、
異常偵測結果、證據鏈、前 5 特徵歸因、AI Copilot 入口。
"""
import os
import sys

import plotly.graph_objects as go
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import inspector  # noqa: E402

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

# 組裝該機構所有檢視（呈現無關邏輯）。
population = df.to_dict("records")
history_rows = (full[full["park_name"] == park].to_dict("records")
                if full is not None and park in set(full["park_name"]) else [row.to_dict()])

radar = inspector.radar_breakdown(row)
timeline_view = inspector.risk_timeline(history_rows, entity_id=str(row.get("park_id", "")))
categories = inspector.five_category_analysis(row)
# 各類別來源連結狀態（R5.11, R5.14）：單一來源無法開啟不影響其餘類別。
category_links = inspector.category_source_links(categories)
peers = inspector.peer_comparison(row, population)
anom = inspector.anomaly_summary(row, population, history_rows)
attributions = inspector.top_feature_attributions(row, n=5)
chain = inspector.evidence_chain(row)

# ---------- 案件標頭（R5.1）----------
common.case_header(row)

# ---------- 風險評估雷達 / 分項加權貢獻（R5.1, R5.2）----------
common.section("風險評估", "shield")
col_radar, col_action = st.columns([1.3, 1], gap="large")

with col_radar:
    dims = [d.label for d in radar.dimensions]
    vals = [d.subscore for d in radar.dimensions]
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
    # 分項加權貢獻表：貢獻加總 == 總分（R5.2）。
    st.markdown("<div style='font-weight:600;font-size:.9rem;margin-bottom:6px;'>"
                "分項加權貢獻</div>", unsafe_allow_html=True)
    body = ""
    for d in radar.dimensions:
        body += (f"<tr><td class='l'>{d.label}</td><td>{d.subscore:.1f}</td>"
                 f"<td>{int(round(d.weight*100))}%</td><td>{d.contribution:.1f}</td></tr>")
    body += (f"<tr><td class='l'><b>加權總分</b></td><td></td><td></td>"
             f"<td><b>{radar.total:.1f}</b></td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>分項</th><th>分項分</th>"
        f"<th>權重</th><th>貢獻分</th></tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(radar.not_illegality_notice)

# ---------- 風險時間軸（R5.3）----------
common.section("風險時間軸", "clock")
tl_years = [y for y, v in zip(timeline_view.years, timeline_view.values) if v is not None]
tl_vals = [v for v in timeline_view.values if v is not None]
if len(tl_vals) >= 1:
    tfig = go.Figure()
    tfig.add_trace(go.Scatter(
        x=[str(y) for y in tl_years], y=tl_vals, mode="lines+markers",
        line=dict(color=common.PRIMARY, width=2.5), marker=dict(size=8),
        name="總風險分",
    ))
    # 標記變化點。
    cp_years, cp_vals, cp_text = [], [], []
    for cp in timeline_view.change_points:
        if 0 <= cp.index < len(timeline_view.years):
            cp_years.append(str(timeline_view.years[cp.index]))
            cp_vals.append(cp.value)
            cp_text.append(cp.trigger)
    if cp_years:
        tfig.add_trace(go.Scatter(
            x=cp_years, y=cp_vals, mode="markers",
            marker=dict(size=14, color=common.RISK_BAR["high"], symbol="diamond"),
            name="變化點", text=cp_text, hovertemplate="%{text}<extra></extra>",
        ))
    tfig.update_layout(
        height=300, margin=dict(l=40, r=20, t=20, b=36),
        paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
        yaxis=dict(title="風險分", range=[0, 100], gridcolor=common.BORDER),
        xaxis=dict(title="年度"), showlegend=True,
        font=dict(family="Inter, Noto Sans TC, Microsoft JhengHei"),
    )
    st.plotly_chart(tfig, width="stretch")
    if timeline_view.change_points:
        for cp in timeline_view.change_points:
            st.caption(f"⚑ {cp.trigger}")
    else:
        st.caption("涵蓋所有可取得年度（由舊到新）；未偵測到統計顯著變化點。")
else:
    common.empty_state("無跨年度資料", "此機構未出現在多年度資料集中。")

# ---------- 五類分析 / 同儕 / 異常 / 證據 / 歸因 / Copilot ----------
tab_cat, tab_peer, tab_anom, tab_ev, tab_attr, tab_ai = st.tabs(
    ["五類分析", "同儕比較", "異常偵測", "證據鏈", "特徵歸因", "AI 稽查助手"])

# ---- 五類分析（R5.4, R5.11, R5.12）----
with tab_cat:
    common.section("財務／收費／營運／法規／NLP 五類分析", "case")
    for cat, link in zip(categories, category_links):
        if cat.has_data:
            ev = "　".join(f"{k}：<b>{v}</b>" for k, v in cat.evidence)
            # 來源連結：可開啟則呈現連結，無法開啟則顯示提示（R5.11, R5.14）。
            if link.accessible and link.url:
                src_body = (f"<a href='{link.url}' target='_blank' "
                            f"style='color:{common.PRIMARY};'>{link.label}</a>")
            elif cat.source is not None:
                src_body = f"{link.label}　<span style='color:{common.INK_MUTED};'>（{link.notice}）</span>"
            else:
                src_body = ""
            src_line = ""
            if src_body:
                src_line = (f"<div style='color:{common.INK_MUTED};font-size:.74rem;"
                            f"margin-top:6px;'>{common.icon('check',12,common.INK_MUTED)} "
                            f"來源：{src_body}</div>")
            st.markdown(
                f"<div class='sw-panel' style='margin-bottom:10px;'>"
                f"<div style='font-weight:600;color:{common.INK};'>{cat.category}</div>"
                f"<div style='color:{common.INK_2};font-size:.86rem;margin-top:4px;'>{cat.conclusion}</div>"
                f"<div style='color:{common.INK_2};font-size:.82rem;margin-top:6px;'>{ev}</div>"
                f"{src_line}</div>",
                unsafe_allow_html=True,
            )
        else:
            common.empty_state(f"{cat.category}：無資料",
                               "此分析類別目前無可用資料。", "clock")

# ---- 同儕比較（R5.5）----
with tab_peer:
    common.section("同儕比較（相同機構類型）", "case")
    if peers and peers[0].insufficient:
        common.empty_state("同儕樣本不足",
                           "相同機構類型的同儕數量低於可靠比較門檻，比較結果暫不可靠。")
    body = ""
    for p in peers:
        val = f"{p.value:.1f}" if p.value is not None else "—"
        med = f"{p.peer_median:.1f}" if p.peer_median is not None else "—"
        pct = f"{p.percentile:.0f}%" if p.percentile is not None else "—"
        body += (f"<tr><td class='l'>{p.label}</td><td>{val}</td><td>{med}</td>"
                 f"<td>{pct}</td><td class='l'>{p.position}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>分項</th><th>本機構</th>"
        "<th>同儕中位數</th><th>百分位</th><th class='l'>相對位置</th></tr></thead>"
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

# ---- 異常偵測（R5.6）----
with tab_anom:
    common.section("異常偵測結果", "alert")
    label_txt = {"high_confidence": "高可信度異常（≥2 種方法命中）",
                 "to_confirm": "待確認異常（單一方法命中）",
                 "none": "未達異常判定"}.get(anom.confidence_label, anom.confidence_label)
    common.callout(f"<b>一致性研判</b>：{label_txt}　·　命中方法數 {anom.hit_count}")
    body = ""
    for it in anom.items:
        flag_txt = "是" if it.flag else "否"
        triggers = "、".join(it.trigger_metrics) if it.trigger_metrics else "—"
        body += (f"<tr><td class='l'>{it.anomaly_type}</td><td>{flag_txt}</td>"
                 f"<td>{it.score:.1f}</td><td class='l'>{triggers}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>異常類型</th><th>是否異常</th>"
        "<th>異常分</th><th class='l'>觸發來源指標</th></tr></thead>"
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

# ---- 證據鏈（R5.7）----
with tab_ev:
    common.section("證據鏈（結論 → 特徵 → 原始值 → 官方來源）", "shield")
    st.markdown(
        f"<div class='sw-scorecard'><div style='font-weight:600;color:{common.INK};'>風險結論</div>"
        f"<div style='color:{common.INK_2};font-size:.88rem;margin-top:4px;'>{chain.conclusion}</div></div>",
        unsafe_allow_html=True,
    )
    if chain.links:
        body = ""
        for lk in chain.links:
            src = lk.source
            src_txt = f"{src.dataset}（{src.authority}）" if src else "—"
            body += (f"<tr><td class='l'>{lk.feature}</td><td class='l'>{lk.raw_value}</td>"
                     f"<td class='l'>{src_txt}</td></tr>")
        st.markdown(
            "<table class='sw-table'><thead><tr><th class='l'>特徵歸因</th>"
            "<th class='l'>原始資料值</th><th class='l'>官方來源</th></tr></thead>"
            f"<tbody>{body}</tbody></table>",
            unsafe_allow_html=True,
        )
        traceable = "完整可追溯" if chain.is_fully_traceable() else "部分可追溯"
        st.caption(f"證據鏈狀態：{traceable}")
    else:
        common.empty_state("無證據鏈", "此機構未偵測到可歸因的風險特徵。", "check")

# ---- 特徵歸因（R5.8）----
with tab_attr:
    common.section("可解釋 AI 特徵歸因（前 5 項）", "ai")
    if attributions:
        body = ""
        for a in attributions:
            arrow = "▲" if a.direction == "提高" else "▼"
            dcolor = common.RISK_BAR["high"] if a.direction == "提高" else common.RISK_BAR["normal"]
            body += (f"<tr><td class='l'>{a.label}</td><td>{a.raw_value}</td>"
                     f"<td style='color:{dcolor};'>{arrow} {a.direction}</td>"
                     f"<td>{a.contribution:+.2f}</td></tr>")
        st.markdown(
            "<table class='sw-table'><thead><tr><th class='l'>特徵</th><th>原始值</th>"
            "<th>方向</th><th>貢獻量</th></tr></thead>"
            f"<tbody>{body}</tbody></table>",
            unsafe_allow_html=True,
        )
        st.caption("貢獻方向：▲ 提高風險、▼ 降低風險。歸因為白盒可解釋輸出，可追溯至鑑識指標。")
    else:
        common.empty_state("無顯著特徵歸因", "各項特徵均在中性基準附近。", "check")

# ---- AI 稽查助手（R5.10）----
with tab_ai:
    common.section("AI 稽查助手（Copilot）", "ai")
    st.caption("以該機構實際資料為依據回答，關鍵陳述附來源；資料不足明確告知不杜撰。"
               "AI 僅輔助研判，最終判定由稽查人員決定。")
    q = st.text_input("向 AI 稽查助手提問", placeholder="例如：這間機構的財務風險如何？")
    if st.button("送出提問") and q:
        with st.spinner("研判中…"):
            ans = inspector.copilot_answer(q, row)
        grounded = "以機構資料為依據" if ans.grounded else "資料不足，未杜撰"
        src_txt = ("　·　來源：" + "、".join(ans.sources)) if ans.sources else ""
        st.markdown(
            f"<div class='sw-scorecard' style='margin-top:8px;'>"
            f"<div style='color:{common.MUTED};font-size:.76rem;margin-bottom:6px;'>"
            f"{grounded}{src_txt}</div>"
            f"<div style='font-size:.95rem;line-height:1.9;color:{common.INK}'>{ans.text}</div></div>",
            unsafe_allow_html=True,
        )

# ---------- 調查檢核清單（R5.9）----------
common.section("調查檢核清單", "check")
_ck_state_key = f"checklist::{row.get('park_id', park)}"
if _ck_state_key not in st.session_state:
    st.session_state[_ck_state_key] = {}
checklist = inspector.apply_checklist_state(
    inspector.default_checklist(), st.session_state[_ck_state_key])
for it in checklist:
    checked = st.checkbox(it.label, value=it.done, key=f"{_ck_state_key}::{it.key}",
                          help=it.hint or None)
    st.session_state[_ck_state_key][it.key] = checked
_done, _total = inspector.checklist_progress(
    inspector.apply_checklist_state(checklist, st.session_state[_ck_state_key]))
st.caption(f"檢核進度：{_done} / {_total} 項已完成")

# ---------- 人在迴路（HITL）審核回饋（R20.1）----------
common.section("審核回饋（HITL）", "shield")
st.caption("稽查員對本機構風險判定的回饋，將關聯機構與判定並寫入稽核軌跡；"
           "回饋不改寫既有風險分數，僅供後續模型改進。")
_verdict_ref = f"risk::{row.get('park_id', park)}::{row.get('year', '')}"
fb_cols = st.columns(len(inspector.feedback_labels()))
for _col, _label in zip(fb_cols, inspector.feedback_labels()):
    with _col:
        if st.button(_label, key=f"fb::{_verdict_ref}::{_label}"):
            fb_res = inspector.submit_hitl_feedback(
                str(row.get("park_id", park)), _verdict_ref, _label)
            if fb_res.ok:
                st.success(fb_res.message)
            else:
                st.error(fb_res.message)
