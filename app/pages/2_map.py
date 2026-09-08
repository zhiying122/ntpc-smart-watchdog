"""
風險地圖（Leaflet + OpenStreetMap）
================================
把每間園標成一個點，依風險等級著色。點擊看園名、風險分、主要問題。
加分：把高風險園連成一條建議稽查路線，展現精準投放人力。
"""
import os
import sys

import folium
import streamlit as st
from folium.plugins import AntPath
from streamlit_folium import st_folium

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜風險地圖",
    header_title="風險地圖",
    subtitle="機構風險的空間分布。底圖 OpenStreetMap（免費、免金鑰），依風險等級著色。",
    module="風險地圖",
)

df = common.require_data()

# ---------- 篩選 ----------
col_a, col_b = st.columns([3, 1])
with col_b:
    show_levels = st.pills("顯示風險等級", ["高", "中", "低"],
                           selection_mode="multi", default=["高", "中", "低"])
    show_route = st.checkbox("顯示高風險稽查建議路線", value=True,
                             help="把高風險園依風險分連成巡查路線，示範精準投放人力")

geo = df[df["risk_level"].isin(show_levels)].dropna(subset=["lat", "lng"]).copy()
n_total = df.dropna(subset=["lat", "lng"]).shape[0]
n_high_all = int((df["risk_level"] == "高").sum())

# 地圖統計 KPI
common.kpi_band([
    ("已定位機構", f"{n_total}", False, "具座標可上圖"),
    ("目前顯示", f"{len(geo)}", False, "符合篩選條件"),
    ("高風險機構", f"{n_high_all}", True, "地圖紅點標示"),
])

if len(geo) == 0:
    common.empty_state("目前條件下沒有可顯示的機構",
                       "請放寬風險等級篩選，或確認資料含 lat/lng 座標欄位。", "map")
    st.stop()

common.section("風險空間分布", "map")

# ---------- 建立地圖 ----------
center = [geo["lat"].mean(), geo["lng"].mean()]
fmap = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap",
                  control_scale=True)

for _, r in geo.iterrows():
    color = common.level_color(r["risk_level"])
    problems = []
    if r["expense_income_ratio"] > 1:
        problems.append(f"入不敷出（收支比 {r['expense_income_ratio']:.2f}）")
    if r["penalty_count"] and int(r["penalty_count"]) > 0:
        problems.append(f"裁罰 {int(r['penalty_count'])} 次")
    if r["score_financial"] >= 40:
        problems.append("財務指標異常")
    if not problems:
        problems.append("綜合分數偏高" if r["risk_level"] != "低" else "風險低")
    problem_html = "<br>".join(f"· {p}" for p in problems)

    popup_html = f"""
    <div style="font-family:'Microsoft JhengHei',sans-serif;min-width:210px;">
      <div style="font-size:15px;font-weight:700;color:#1A1F29;">{r['park_name']}</div>
      <div style="color:#6B7280;font-size:12px;">{r['district']}　·　{r['park_type']}</div>
      <hr style="margin:6px 0;border-color:#E3E8EF;">
      <div style="font-size:22px;font-weight:800;color:{color};">
        {r['risk_total']:.1f}
        <span style="font-size:12px;color:#6B7280;">分　（{r['risk_level']}風險）</span>
      </div>
      <div style="font-size:12px;margin-top:6px;color:#1A1F29;">主要問題：<br>{problem_html}</div>
    </div>
    """
    folium.CircleMarker(
        location=[r["lat"], r["lng"]],
        radius=6 + r["risk_total"] / 10,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.78,
        weight=2,
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=f"{r['park_name']}（{r['risk_total']:.0f} 分）",
    ).add_to(fmap)

# ---------- 高風險稽查建議路線 ----------
high = geo[geo["risk_level"] == "高"].sort_values("risk_total", ascending=False)
if show_route and len(high) >= 2:
    route = high[["lat", "lng"]].values.tolist()
    AntPath(route, color=common.LEVEL_COLOR["高"], weight=4, delay=800,
            dash_array=[10, 20], tooltip="建議稽查路線（依風險分由高至低）").add_to(fmap)
    for order, (_, r) in enumerate(high.iterrows(), start=1):
        folium.Marker(
            location=[r["lat"], r["lng"]],
            icon=folium.DivIcon(html=(
                f'<div style="background:{common.LEVEL_COLOR["高"]};color:#fff;'
                f'border-radius:50%;width:22px;height:22px;line-height:22px;'
                f'text-align:center;font-weight:700;font-size:12px;'
                f'border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.3);">{order}</div>')),
        ).add_to(fmap)

st_folium(fmap, width=1120, height=560, returned_objects=[])

# ---------- 圖例 ----------
st.markdown(
    "<div style='margin-top:10px;color:%s;font-size:.82rem;'>圖例：%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s"
    "&nbsp;&nbsp;·&nbsp;&nbsp;圈越大代表風險分越高；紅色虛線為高風險稽查建議路線。</div>"
    % (common.MUTED,
       common.dot(common.LEVEL_COLOR["高"], "高風險"),
       common.dot(common.LEVEL_COLOR["中"], "中風險"),
       common.dot(common.LEVEL_COLOR["低"], "低風險")),
    unsafe_allow_html=True,
)

if len(high) >= 2:
    common.section("建議稽查路線順序", "alert")
    body = ""
    for order, (_, r) in enumerate(high.iterrows(), start=1):
        body += (f"<tr><td class='l sw-rank'>{order}</td>"
                 f"<td class='l'>{r['park_name']}</td>"
                 f"<td class='l'>{r['district']}</td>"
                 f"<td>{common.score_bar(r['risk_total'], r['risk_level'])}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>順序</th><th class='l'>園所名稱</th>"
        "<th class='l'>行政區</th><th>風險分</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
