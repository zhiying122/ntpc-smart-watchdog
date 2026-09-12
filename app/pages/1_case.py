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
from lib import case_status  # noqa: E402
from lib import common  # noqa: E402
from lib import inspector  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜案件調查",
    header_title="案件調查工作區",
    subtitle="單一受監理機構的鑑識會計調查與風險評估。",
    module="案件調查",
)

# 公務後台全欄位可見（含 risk/score/證據）。
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
triangle = inspector.fraud_triangle_view(row)
multisrc = inspector.multi_source_view(row)

# ---------- 案件標頭（R5.1）----------
common.case_header(row)

# ---------- 真實裁罰紀錄疊加（唯讀，不影響風險分計算）----------
# 來源：全國教保資訊網裁罰查詢。若本機構查有裁罰／處分紀錄，明確標示於標頭
# 下方，供稽查員參考。此為獨立圖層，不覆寫既有 score_penalty / risk_total。
_pen = common.penalty_for(park)
if _pen is not None:
    _pstatus = str(_pen.get("status", "") or "").strip()
    _status_txt = f"　·　營運狀態：{_pstatus}" if _pstatus else ""
    st.markdown(
        f"<div class='sw-callout' style='border-left-color:{common.RISK['high'][0]};"
        f"margin-top:8px;'>"
        f"<b style='color:{common.RISK['high'][0]};'>⚠ 查有裁罰／處分紀錄</b>"
        f"（資料來源：全國教保資訊網{_status_txt}）。"
        f"此為官方公告之真實裁罰事實，作為稽查佐證；本頁風險分仍依既有鑑識會計"
        f"方法計算，未因此疊加分數。</div>",
        unsafe_allow_html=True,
    )

# ---------- 非營利園真實財報決算（AWS Bedrock 視覺抽取，唯讀展示）----------
# 針對非營利園，附上自財報 PDF 以 Bedrock 抽取之真實 113 學年決算數（收入/
# 支出/餘絀），並自我勾稽（收入−支出≈餘絀）。此為資料佐證層，不改風險分。
_npfin = common.nonprofit_financials_for(row.get("park_id"))
if _npfin is not None and _npfin.get("income_actual") is not None:
    _inc = _npfin.get("income_actual")
    _exp = _npfin.get("expense_actual")
    _sur = _npfin.get("surplus")
    _tui = _npfin.get("tuition_actual")
    _conf = _npfin.get("extraction_confidence", "")
    _ratio = (_exp / _inc) if (_inc and _exp) else None
    _ratio_txt = f"　·　收支比 {_ratio:.3f}" if _ratio else ""
    _tui_valid = _tui is not None and str(_tui).lower() != "nan"
    try:
        _tui_valid = _tui_valid and float(_tui) > 0
    except (TypeError, ValueError):
        _tui_valid = False
    _tui_txt = f"　·　學雜費收入 <b>{float(_tui):,.0f}</b> 元" if _tui_valid else ""
    _conf_txt = "勾稽通過（高信心）" if _conf == "high" else "待複核"
    st.markdown(
        f"<div class='sw-callout' style='border-left-color:{common.PRIMARY};margin-top:8px;'>"
        f"<b style='color:{common.PRIMARY};'>113 學年度真實財報決算</b>"
        f"（AWS Bedrock 視覺抽取自財報 PDF · {_conf_txt}）：<br>"
        f"收入 <b>{_inc:,.0f}</b> 元　·　支出 <b>{_exp:,.0f}</b> 元　·　"
        f"餘絀 <b style='color:{common.RISK['high'][0] if (_sur or 0) < 0 else common.RISK['normal'][0]};'>"
        f"{_sur:,.0f}</b> 元{_ratio_txt}{_tui_txt}</div>",
        unsafe_allow_html=True,
    )

# ---------- 稽查決策條（行動優先）----------
# 把「下決定」放在使用者一進頁面就看得到的位置：一句話結論 + 當前狀態 +
# 三顆決策按鈕。決策即時寫入 case_status（跨頁共用、可持久化），並同步送出
# 一筆 HITL 稽核回饋，讓「決策」與「模型回饋」都留下軌跡。
_entity_id = str(row.get("park_id", park))
_rec = case_status.get_status(_entity_id)
common.decision_bar(row, _rec, case_status.PRIMARY_DECISIONS)

# ---- 當前狀態大橫幅：一眼看出目前狀態，決策後顏色即變（解決「案不下去」的體感）----
common.status_banner(_rec)

# 決策動作 → 送出後對應的 HITL 回饋標籤（供模型改進，與狀態互補）
_DECISION_FEEDBACK = {
    "建議派查": "需進一步稽查",
    "存疑待補": "資料問題",
    "不成立結案": "誤報",
    "結案·屬實": "確認屬實",
}

_is_closed = _rec.status in case_status.CLOSED_STATUSES

if _is_closed:
    # ---- 已結案：明確提示 + 重新開啟（讓使用者可反悔，不會卡死）----
    _closed_kind = "屬實" if _rec.status == "closed_confirmed" else "不成立"
    st.markdown(
        f"<div class='sw-callout' style='border-left-color:{common.level_color(row['risk_level'])};'>"
        f"本案已結案（{_closed_kind}），已移出「待處理」清單。"
        f"如需重啟調查，可點右側「重新開啟案件」，案件將回到「待研判」並重新納入待辦。</div>",
        unsafe_allow_html=True,
    )
    _rc = st.columns([1.2, 3])
    with _rc[0]:
        if st.button("重新開啟案件", key=f"reopen::{_entity_id}",
                     width="stretch", type="primary"):
            _new = case_status.set_status(_entity_id, "pending", actor="inspector",
                                          note="重新開啟案件")
            st.toast("案件已重新開啟，回到「待研判」", icon="🔄")
            st.rerun()
    with _rc[1]:
        st.markdown(
            f"<div style='color:{common.INK_MUTED};font-size:.78rem;line-height:1.5;"
            f"padding-top:8px;'>結案為可逆操作：重新開啟不會刪除既有處理歷程，"
            f"僅在歷程新增一筆「重新開啟」，維持完整稽核軌跡。</div>",
            unsafe_allow_html=True,
        )
else:
    # ---- 未結案：四顆決策按鈕（含新增的「結案·屬實」）----
    _DECISIONS = ["建議派查", "存疑待補", "結案·屬實", "不成立結案"]
    _dc = st.columns(len(_DECISIONS))
    for _i, _label in enumerate(_DECISIONS):
        with _dc[_i]:
            _is_primary = (_label == "建議派查")
            if st.button(_label, key=f"decision::{_entity_id}::{_label}",
                         width="stretch",
                         type=("primary" if _is_primary else "secondary")):
                _new = case_status.set_status(_entity_id, _label, actor="inspector")
                _fb_label = _DECISION_FEEDBACK.get(_label)
                if _fb_label:
                    inspector.submit_hitl_feedback(
                        _entity_id, f"risk::{_entity_id}::{row.get('year', '')}", _fb_label)
                st.toast(f"已將本案標記為「{_new.status_label()}」", icon="✅")
                st.rerun()
    st.markdown(
        f"<div style='color:{common.INK_MUTED};font-size:.78rem;line-height:1.6;"
        f"margin-top:8px;'>決策即時記錄並跨頁同步："
        f"「建議派查」進入派工名單、「存疑待補」轉為調查中、"
        f"「結案·屬實／不成立結案」關閉案件並移出待處理。"
        f"風險不等於違法，最終處置由稽查人員負責。</div>",
        unsafe_allow_html=True,
    )

# ---------- 風險評估雷達 / 分項加權貢獻（R5.1, R5.2）----------
common.section("風險評估", "shield")

# 評分檔別（R26）：財務鑑識園（有決算）/ 行為監測園（無獨立財報，如國小附設幼兒園）。
# 行為監測園併同顯示揭露訊息，讓稽查員得知該分數所依據之資料面向（R26.5, R26.6）。
_profile_label = ("財務鑑識園（具獨立財務決算）"
                  if radar.scoring_profile == "forensic"
                  else "行為監測園（無獨立財報）")
_profile_color = common.PRIMARY if radar.scoring_profile == "forensic" else common.RISK["medium"][0]
st.markdown(
    f"<div style='display:inline-block;padding:3px 12px;border-radius:999px;"
    f"border:1px solid {_profile_color};color:{_profile_color};font-size:.78rem;"
    f"font-weight:600;margin-bottom:8px;'>評分檔：{_profile_label}</div>",
    unsafe_allow_html=True,
)
if radar.profile_notice:
    st.markdown(
        f"<div class='sw-callout' style='margin-bottom:12px;'>{radar.profile_notice}</div>",
        unsafe_allow_html=True,
    )

col_radar, col_action = st.columns([1.3, 1], gap="large")

with col_radar:
    dims = [d.label for d in radar.dimensions]
    vals = [d.subscore for d in radar.dimensions]
    fig = go.Figure()
    if not vals:
        # 防禦：分項為空時不畫雷達（正常資料不會發生）。
        common.empty_state("無分項資料", "此機構缺可呈現的風險分項。")
        st.stop()
    fig.add_trace(go.Scatterpolar(
        r=vals + [vals[0]], theta=dims + [dims[0]],
        fill="toself", fillcolor=common.hex_rgba(color, 0.18),
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
    st.plotly_chart(fig, use_container_width=True)

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
    st.plotly_chart(tfig, use_container_width=True)
    if timeline_view.change_points:
        for cp in timeline_view.change_points:
            st.caption(f"變化點：{cp.trigger}")
    else:
        st.caption("涵蓋所有可取得年度（由舊到新）；未偵測到統計顯著變化點。")
else:
    common.empty_state("無跨年度資料", "此機構未出現在多年度資料集中。")

# ---------- 歷年風險組成趨勢（分項堆疊 + 總分折線雙軸，對齊政府級動態圖）----------
common.section("歷年風險組成趨勢", "dashboard")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.84rem;margin:-4px 0 8px;'>"
    f"各年度風險分依分項（財務／裁罰／評鑑）堆疊，折線為總風險分；"
    f"游標移入可見該年拆解，看出哪一年惡化、由哪個分項推升。</div>",
    unsafe_allow_html=True,
)
common.risk_trend_chart(full, park)

# ---------- 五類分析 / 同儕 / 異常 / 證據 / 歸因 / Copilot ----------
tab_cat, tab_peer, tab_anom, tab_src, tab_ft, tab_ev, tab_attr, tab_ai = st.tabs(
    ["五類分析", "同儕比較", "異常偵測", "多來源示警", "舞弊三角", "證據鏈", "特徵歸因", "AI 稽查助手"])

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
            # 破窗效應累犯軌跡（R25.6, R25.7）：法規類別下，若有逐筆裁罰明細
            # （含日期）則攤開「頻繁/近期/未改善」累積軌跡，凸顯破窗惡化趨勢。
            if cat.category == "法規":
                bw = inspector.broken_window_trace(row)
                if bw.has_detail:
                    rows_html = ""
                    for r in bw.rows:
                        sev_color = (common.RISK["high"][0] if r.severity == "major"
                                     else common.RISK["medium"][0] if r.severity == "moderate"
                                     else common.INK_2)
                        rows_html += (
                            f"<tr><td class='l'>{r.description}</td>"
                            f"<td style='color:{sev_color};'>{r.severity_label}</td>"
                            f"<td>{r.months_since:.0f} 月前</td>"
                            f"<td>{r.time_decay:.2f}</td>"
                            f"<td>{r.contribution:.2f}</td></tr>")
                    st.markdown(
                        f"<div class='sw-callout' style='margin-bottom:10px;'>"
                        f"破窗效應累犯加權：<b>{bw.score:.1f}</b> 分"
                        f"（{bw.n_counted} 筆違規，頻率放大 ×{bw.frequency_amplifier:.2f}）。"
                        f"近期、頻繁、未改善的違規累積被指數式突顯，時效衰減使久遠違規權重降低。</div>"
                        f"<table class='sw-table'><thead><tr><th class='l'>違規事由</th>"
                        f"<th>嚴重度</th><th>距今</th><th>時效衰減</th><th>加權貢獻</th></tr></thead>"
                        f"<tbody>{rows_html}</tbody></table>",
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
        z = f"{p.z_score:+.2f}" if p.z_score is not None else "—"
        rob = f"{p.robust_deviation:+.2f}" if p.robust_deviation is not None else "—"
        body += (f"<tr><td class='l'>{p.label}</td><td>{val}</td><td>{med}</td>"
                 f"<td>{pct}</td><td>{z}</td><td>{rob}</td>"
                 f"<td class='l'>{p.position}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>分項</th><th>本機構</th>"
        "<th>同儕中位數</th><th>百分位</th><th>z 分數</th><th>穩健偏差</th>"
        "<th class='l'>相對位置</th></tr></thead>"
        f"<tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption("z 分數 =（本機構 − 同儕平均）/ 標準差；穩健偏差以中位數與 MAD 為基礎、"
               "抗離群。兩者皆為可解釋的同儕相對位置統計量（±1 以上代表明顯偏離同儕）。")

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

    # ---- 七方法明細（護城河可視化：每種方法各自怎麼判、適用什麼、有何限制）----
    if anom.methods:
        common.section("偵測方法明細（七法交叉驗證）", "alert")
        mbody = ""
        for m in anom.methods:
            if m.applicable:
                hit = "命中" if m.flag else "未命中"
                hit_color = common.RISK_BAR["high"] if m.flag else common.INK_MUTED
                score_txt = f"{m.score:.1f}"
            else:
                hit = "樣本不足"
                hit_color = common.INK_MUTED
                score_txt = "—"
            mbody += (
                f"<tr><td class='l'>{m.label}</td><td class='l'>{m.anomaly_type}</td>"
                f"<td>{score_txt}</td><td>{m.threshold:.0f}</td>"
                f"<td class='l' style='color:{hit_color};'>{hit}</td>"
                f"<td class='l' style='font-size:.78rem;color:{common.INK_MUTED};'>"
                f"假設：{m.assumption}<br>限制：{m.limitation}</td></tr>")
        st.markdown(
            "<table class='sw-table'><thead><tr><th class='l'>偵測方法</th>"
            "<th class='l'>異常類型</th><th>異常分</th><th>門檻</th>"
            "<th class='l'>判定</th><th class='l'>適用性（假設／限制）</th></tr></thead>"
            f"<tbody>{mbody}</tbody></table>",
            unsafe_allow_html=True,
        )
        st.caption("七種方法各自獨立偵測、交叉驗證：≥2 種方法命中才研判為高可信度異常，"
                   "降低單一方法誤判。樣本不足的方法會誠實標示並跳過，不影響其餘方法。")

# ---- 多來源風險交叉驗證（五層公開資訊：官方/司法/新聞/陳情/社群）----
with tab_src:
    common.section("多來源風險交叉驗證", "shield")
    _lvl = multisrc.cross_validation_level()
    _lvl_tone = {"corroborated": "critical", "converging": "high",
                 "single_source": "medium", "none": "normal"}[_lvl]
    _lvl_label = {"corroborated": "多來源交叉佐證", "converging": "多來源訊號集中",
                  "single_source": "單一來源訊號", "none": "無多來源訊號"}[_lvl]
    _lfg = common.RISK[_lvl_tone][0]
    st.markdown(
        f"<div class='sw-callout' style='border-left-color:{_lfg};'>"
        f"<b style='color:{_lfg};'>{_lvl_label}</b>（{multisrc.distinct_layer_count} 類獨立來源）"
        f"　·　{multisrc.attention_notice()}</div>",
        unsafe_allow_html=True,
    )

    # 五層來源發現數「風險雷達」列（官方/司法/新聞/陳情/社群）。
    _layer_icon = {"official": "🏛 官方裁罰", "judicial": "⚖ 司法資料",
                   "news": "📰 新聞事件", "petition": "📣 陳情紀錄",
                   "social": "💬 網路輿情"}
    _counts = multisrc.count_by_layer()
    _cols = st.columns(5)
    for _c, _lk in zip(_cols, ["official", "judicial", "news", "petition", "social"]):
        _n = _counts.get(_lk, 0)
        _fg = common.RISK["high"][0] if _n > 0 else common.INK_MUTED
        with _c:
            st.markdown(
                f"<div class='sw-panel' style='text-align:center;'>"
                f"<div style='font-size:.72rem;color:{common.INK_MUTED};'>{_layer_icon[_lk]}</div>"
                f"<div style='font-size:1.6rem;font-weight:700;color:{_fg};"
                f"font-variant-numeric:tabular-nums;'>{_n}</div>"
                f"<div style='font-size:.68rem;color:{common.INK_MUTED};'>筆</div></div>",
                unsafe_allow_html=True,
            )

    # 微弱訊號（早期預警）。
    if multisrc.all_weak_signals:
        _ws = "、".join(multisrc.all_weak_signals)
        common.callout(f"<b>輿情微弱訊號（早期預警）</b>：{_ws}")

    # 逐筆訊號明細：嚴格標示層別與「事實/事件/輿情」，附來源連結。
    if multisrc.signals:
        _tier_label = {"fact": "事實", "event": "事件", "sentiment": "輿情"}
        _tier_color = {"fact": common.RISK["high"][0],
                       "event": common.RISK["medium"][0],
                       "sentiment": common.RISK["low"][0]}
        body = ""
        for s in multisrc.signals:
            _demo = "（示範樣本）" if s.is_demo_sample else ""
            _stage = f"｜{s.judicial_stage}" if s.judicial_stage else ""
            _link = (f"<a href='{s.url}' target='_blank'>{s.source}</a>"
                     if s.url else s.source)
            body += (
                f"<tr><td class='l'>{s.layer_label}</td>"
                f"<td class='l' style='color:{_tier_color.get(s.tier, common.INK_MUTED)};'>"
                f"{_tier_label.get(s.tier, s.tier)}{_stage}</td>"
                f"<td class='l'>{s.text}{_demo}</td>"
                f"<td class='l' style='font-size:.76rem;'>{_link}<br>"
                f"<span style='color:{common.INK_MUTED};'>{s.date}</span></td></tr>")
        st.markdown(
            "<table class='sw-table'><thead><tr><th class='l'>來源層</th>"
            "<th class='l'>性質</th><th class='l'>內容</th>"
            "<th class='l'>來源／日期</th></tr></thead>"
            f"<tbody>{body}</tbody></table>",
            unsafe_allow_html=True,
        )
        st.caption("多來源交叉驗證：不同獨立來源在同一機構集中出現時提高關注度；"
                   "「事實」（官方裁罰／判決確定）可進正式風險計分，「事件」（新聞／"
                   "陳情／偵查起訴中）與「輿情」（社群評論）僅為關注訊號。"
                   "被檢舉 ≠ 被調查 ≠ 被起訴 ≠ 被判決有罪。"
                   "AI 只發現訊號，不作違法認定；風險不等於違法。")
    else:
        common.empty_state("無多來源訊號", "目前查無此機構的公開新聞、社群或司法訊號。", "check")

# ---- 舞弊三角理論（Cressey 1953，質化特徵結構化框架）----
with tab_ft:
    common.section("舞弊三角研判（壓力 · 機會 · 合理化）", "shield")
    _ft_tone = {"complete": "critical", "partial": "high",
                "weak": "medium", "none": "normal"}[triangle.completeness]
    _ft_label = {"complete": "三角完整成形（3/3）", "partial": "部分成形（2/3）",
                 "weak": "單一構面（1/3）", "none": "未成形（0/3）"}[triangle.completeness]
    _ft_fg, _ft_bg, _ft_bd = common.RISK[_ft_tone]
    st.markdown(
        f"<div class='sw-callout' style='border-left-color:{_ft_fg};'>"
        f"<b style='color:{_ft_fg};'>{_ft_label}</b>　·　{triangle.narrative}</div>",
        unsafe_allow_html=True,
    )
    _factors = [
        ("壓力 Pressure", triangle.pressure, "財務困境／收支壓力（Altman Z''、收支比、短絀）"),
        ("機會 Opportunity", triangle.opportunity, "內控／治理弱點與帳務異常空間（評鑑、班佛/Beneish、勾稽）"),
        ("合理化 Rationalization", triangle.rationalization, "重複違規行為型態與負面輿情（裁罰破窗、輿情）"),
    ]
    _cols = st.columns(3)
    for _col, (_name, _f, _desc) in zip(_cols, _factors):
        _tone = ("critical" if _f.score >= 75 else "high" if _f.present
                 else "medium" if _f.score >= 30 else "normal")
        _fg, _bg, _bd = common.RISK[_tone]
        _mark = "✓ 達門檻" if _f.present else "未達門檻"
        _sigs = "".join(
            f"<li style='margin-bottom:2px;'>{s}</li>" for s in _f.signals)
        with _col:
            st.markdown(
                f"<div class='sw-panel' style='border-top:3px solid {_fg};'>"
                f"<div style='font-weight:700;color:{common.INK};'>{_name}</div>"
                f"<div style='font-size:1.8rem;font-weight:700;color:{_fg};"
                f"line-height:1.1;font-variant-numeric:tabular-nums;'>{_f.score:.0f}"
                f"<span style='font-size:.8rem;color:{common.INK_MUTED};font-weight:500;'>/100</span></div>"
                f"<div style='color:{_fg};font-size:.76rem;font-weight:600;margin:2px 0 6px;'>{_mark}</div>"
                f"<div style='color:{common.INK_MUTED};font-size:.72rem;margin-bottom:6px;'>{_desc}</div>"
                f"<ul style='color:{common.INK_2};font-size:.78rem;margin:0;padding-left:16px;'>{_sigs}</ul>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.caption("舞弊三角理論（Cressey, 1953；經 AICPA SAS No. 99 納入審計準則）："
               "壓力、機會、合理化三構面同時具備時舞弊風險最高。本研判非黑盒模型，"
               "三構面分數皆由風險引擎已算好的可解釋分項對映而來，可完整追溯。"
               "三構面皆達門檻者建議列為優先深度查核對象。")

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
