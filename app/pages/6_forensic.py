"""
鑑識分析（Forensic Accounting Lab）
====================================
本專案最強護城河：鑑識會計方法的集中呈現與驗證。
- 全體紅旗清單（功能4）：哪幾間觸發哪幾條鑑識規則，白盒子一覽。
- 同儕比較 Peer Benchmarking（功能5）：單園各比率 vs 同類型同儕中位數（±σ）。
- 跨年度趨勢突變偵測（功能6）：單園逐年指標折線，自動標紅突變年。
- 裁罰預測驗證（功能8）：以既有裁罰紀錄驗證風險分的鑑別力（混淆矩陣／命中率）。
分數以規則與統計計算（可解釋），此頁專責把方法「攤開驗證」給評審與稽查員看。
"""
import os
import sys

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜鑑識分析",
    header_title="鑑識會計分析室",
    subtitle="鑑識會計方法的集中呈現與驗證：紅旗清單、同儕比較、趨勢突變、裁罰驗證。",
    module="鑑識分析",
)

df = common.require_data()
full = common.load_full()

tab_flag, tab_peer, tab_trend, tab_valid = st.tabs(
    ["全體紅旗清單", "同儕比較", "跨年度趨勢突變", "裁罰預測驗證"])

# ===========================================================================
# 功能4：全體紅旗清單
# ===========================================================================
with tab_flag:
    common.section("鑑識紅旗總覽", "alert")
    st.markdown(
        f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
        "每條規則皆有明確判定門檻（白盒子），下表統計全體觸發次數，"
        "再往下可逐間展開檢核明細。</div>",
        unsafe_allow_html=True,
    )
    # 各規則觸發統計
    counts = {code: 0 for code, *_ in common.RED_FLAGS}
    for _, r in df.iterrows():
        for code, _n, _d, _nr, hit in common.red_flags_for(r):
            if hit:
                counts[code] += 1
    body = ""
    for code, name, _test, _detail, normal in common.RED_FLAGS:
        n = counts[code]
        pct = n / len(df) * 100
        body += (
            "<tr>"
            f"<td class='l sw-rank'>{code}</td>"
            f"<td class='l'>{name}</td>"
            f"<td class='l' style='color:{common.INK_MUTED};'>{normal}</td>"
            f"<td style='color:{common.RISK['high'][0] if n else common.INK_2};font-weight:600;'>{n}</td>"
            f"<td>{pct:.0f}%</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>代碼</th><th class='l'>鑑識規則</th><th class='l'>合理區間</th>"
        "<th>觸發機構數</th><th>佔比</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

    common.section("逐間紅旗檢核", "case")
    # 依觸發紅旗數排序，最多的在前
    df2 = df.copy()
    df2["nflag"] = df2.apply(lambda r: common.red_flag_count(r), axis=1)
    df2 = df2.sort_values(["nflag", "risk_total"], ascending=False)
    only_flagged = st.checkbox("只顯示有觸發紅旗的機構", value=True)
    show = df2[df2["nflag"] > 0] if only_flagged else df2
    if len(show) == 0:
        common.empty_state("無觸發紅旗的機構", "目前所有機構皆在鑑識規則的合理區間內。", "check")
    for _, r in show.iterrows():
        with st.expander(
                f"{r['park_name']}　·　{r['district']}　·　"
                f"風險 {r['risk_total']:.1f}　·　觸發 {int(r['nflag'])} 面紅旗"):
            common.red_flag_checklist(r)

# ===========================================================================
# 功能5：同儕比較
# ===========================================================================
with tab_peer:
    common.section("同儕比較（Peer Benchmarking）", "shield")
    st.markdown(
        f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
        "把單一機構的財務比率，與「同類型（公校／非營利）」同儕的中位數並排，"
        "標出偏離幾個標準差。稽查前第一問：它跟同類比正不正常。</div>",
        unsafe_allow_html=True,
    )
    names = df.sort_values("risk_total", ascending=False)["park_name"].tolist()
    park = st.selectbox("選擇機構", names, key="peer_park")
    row = df[df["park_name"] == park].iloc[0]
    common.case_header(row)
    common.peer_compare(df, row)

# ===========================================================================
# 功能6：跨年度趨勢突變偵測
# ===========================================================================
with tab_trend:
    common.section("跨年度趨勢突變偵測", "clock")
    st.markdown(
        f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
        "單一機構逐年指標折線，自動以年增率 z-score 標出突變年（紅點），"
        "回應命題「財務異常及早發現」。</div>",
        unsafe_allow_html=True,
    )
    if full is None:
        common.empty_state("無跨年度資料", "找不到多年度資料集 kindergartens.csv。", "clock")
    else:
        names_t = sorted(full["park_name"].dropna().unique().tolist())
        # 預設選風險最高者
        top_name = df.sort_values("risk_total", ascending=False)["park_name"].iloc[0]
        idx = names_t.index(top_name) if top_name in names_t else 0
        park_t = st.selectbox("選擇機構", names_t, index=idx, key="trend_park")
        metric = st.selectbox(
            "觀察指標",
            ["總風險分", "財務異常分", "收支比", "支出決算"],
            index=0)
        col_map = {"總風險分": "risk_total", "財務異常分": "score_financial",
                   "收支比": "expense_income_ratio", "支出決算": "expense_actual"}
        col = col_map[metric]
        hist = full[full["park_name"] == park_t].sort_values("year")
        hist = hist.dropna(subset=[col])
        if len(hist) < 2:
            common.empty_state("資料點不足", "此機構有效年度少於 2，無法偵測突變。", "clock")
        else:
            years = hist["year"].astype(int).tolist()
            vals = pd.to_numeric(hist[col], errors="coerce").tolist()
            # 突變偵測：以逐年變化量的 z-score 判定（|z|>=1.5 視為突變）
            diffs = [vals[i] - vals[i - 1] for i in range(1, len(vals))]
            mutate_years = set()
            if len(diffs) >= 2:
                s = pd.Series(diffs)
                mu, sd = s.mean(), (s.std(ddof=0) or 1e-9)
                for i, d in enumerate(diffs, start=1):
                    if abs((d - mu) / sd) >= 1.5:
                        mutate_years.add(years[i])

            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=years, y=vals, mode="lines+markers",
                line=dict(color=common.PRIMARY, width=2.5),
                marker=dict(size=8, color=common.PRIMARY),
                name=metric))
            # 突變年標紅
            if mutate_years:
                mx = [y for y in years if y in mutate_years]
                my = [vals[years.index(y)] for y in mx]
                fig.add_trace(go.Scatter(
                    x=mx, y=my, mode="markers",
                    marker=dict(size=15, color=common.RISK["high"][0],
                                symbol="circle-open", line=dict(width=3)),
                    name="突變年"))
            fig.update_layout(
                height=380, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
                font=dict(family="Inter, Noto Sans TC, Microsoft JhengHei",
                          color=common.INK),
                xaxis=dict(title="年度（民國）", gridcolor=common.BORDER,
                           dtick=1, tickformat="d"),
                yaxis=dict(title=metric, gridcolor=common.BORDER),
                margin=dict(l=50, r=30, t=30, b=45),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            )
            st.plotly_chart(fig, width="stretch")
            if mutate_years:
                yrs = "、".join(str(y) for y in sorted(mutate_years))
                common.callout(
                    f"<b>偵測到突變年：{yrs}</b><br>"
                    f"該年度「{metric}」相對前一年出現顯著跳動（變化量 z-score ≥ 1.5），"
                    "建議調閱當年度決算與異動原因說明。")
            else:
                common.callout(f"「{metric}」逐年變化平穩，未偵測到顯著突變。")

# ===========================================================================
# 功能8：裁罰預測驗證
# ===========================================================================
with tab_valid:
    common.section("裁罰預測驗證（模型可信度）", "check")
    st.markdown(
        f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
        "用全國教保資訊網的既有裁罰紀錄當「答案」，驗證風險分是否真能鑑別高風險機構。"
        "若模型有效，高分組的裁罰率應顯著高於低分組。</div>",
        unsafe_allow_html=True,
    )
    thr_mode = st.radio("高／低風險分組門檻", ["風險分中位數", "自訂門檻"],
                        horizontal=True)
    if thr_mode == "自訂門檻":
        thr = st.slider("風險分門檻", 0, 100,
                        int(df["risk_total"].median()))
        stats = common.penalty_validation(df, threshold=thr)
    else:
        stats = common.penalty_validation(df)

    common.kpi_band([
        ("分組門檻", f"{stats['threshold']:.0f} 分", False, "≥ 判高風險"),
        ("高分組裁罰率", f"{stats['high_rate']:.0f}%", True,
         f"n = {stats['high_n']}"),
        ("低分組裁罰率", f"{stats['low_rate']:.0f}%", False,
         f"n = {stats['low_n']}"),
        ("有裁罰機構數", f"{stats['total_penalized']}", False, "驗證用標籤"),
    ])

    col_bar, col_cm = st.columns([1, 1], gap="large")
    with col_bar:
        st.markdown("<div style='font-weight:600;font-size:.9rem;margin-bottom:6px;'>"
                    "高分組 vs 低分組　裁罰率對比</div>", unsafe_allow_html=True)
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=["高分組", "低分組"],
            y=[stats["high_rate"], stats["low_rate"]],
            marker_color=[common.RISK["high"][0], common.RISK["low"][0]],
            text=[f"{stats['high_rate']:.0f}%", f"{stats['low_rate']:.0f}%"],
            textposition="outside",
            width=0.5))
        fig.update_layout(
            height=320, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
            font=dict(family="Inter, Noto Sans TC, Microsoft JhengHei",
                      color=common.INK),
            yaxis=dict(title="裁罰率 (%)", range=[0, 100], gridcolor=common.BORDER),
            xaxis=dict(gridcolor=common.BORDER),
            margin=dict(l=50, r=20, t=20, b=40), showlegend=False)
        st.plotly_chart(fig, width="stretch")
    with col_cm:
        st.markdown("<div style='font-weight:600;font-size:.9rem;margin-bottom:6px;'>"
                    "分類混淆矩陣</div>", unsafe_allow_html=True)
        st.markdown(common.confusion_matrix_html(stats), unsafe_allow_html=True)
        st.markdown(
            f"<div style='margin-top:10px;color:{common.INK_2};font-size:.86rem;"
            "line-height:1.8;'>"
            f"精確率（Precision）<b>{stats['precision']:.0f}%</b>：判為高風險者中，實際有裁罰的比例。<br>"
            f"召回率（Recall）<b>{stats['recall']:.0f}%</b>：實際被裁罰者中，被正確判為高風險的比例。"
            "</div>",
            unsafe_allow_html=True,
        )

    lift = (stats["high_rate"] / stats["low_rate"]) if stats["low_rate"] else float("inf")
    lift_txt = "無限大（低分組零裁罰）" if lift == float("inf") else f"{lift:.1f} 倍"
    common.callout(
        f"<b>結論</b><br>高分組被裁罰的比率是低分組的 <b>{lift_txt}</b>。"
        "這代表以鑑識會計＋統計算出的風險分，與實際違規行為正相關，"
        "非黑盒子亂數評分——政府敢用的前提就是這種可驗證的鑑別力。")
    st.caption("註：本驗證為抽樣展示（60 間），裁罰紀錄樣本有限，"
               "命中率會隨資料規模化而更穩定；架構可擴展至全體機構。")
