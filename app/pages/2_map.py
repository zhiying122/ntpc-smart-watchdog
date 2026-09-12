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
from lib import risk_map  # noqa: E402
from lib import permissions  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜風險地圖",
    header_title="風險地圖",
    subtitle="機構風險的空間分布。底圖 OpenStreetMap（免費、免金鑰），依風險等級著色。"
             "目前為行政區概略定位（同區機構位置相近），用於掌握風險分佈概況。",
    module="風險地圖",
    allowed_roles=[permissions.ROLE_GOV],
)

# 資料授權層：政府為全欄位可見（含座標與風險分），仍走一致流程。
df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_GOV)
districts = sorted(df["district"].dropna().unique().tolist())

# ---------- 篩選 ----------
col_a, col_b = st.columns([1.6, 1.2], gap="large")
with col_a:
    sel_districts = st.multiselect(
        "行政區聚焦（可多選，未選＝全市全區）", districts, default=[],
        help="選擇行政區以聚焦地圖視野並過濾轄內機構與建議巡查路線",
    )
    st.caption("💡 提示：可選取單一或多個行政區（如「三芝區」、「板橋區」），地圖將自動聚焦轄區並即時重算該區稽查路線。")
with col_b:
    show_levels = st.pills("顯示風險等級", ["高", "中", "低"],
                           selection_mode="multi", default=["高", "中", "低"])
    show_route = st.checkbox("顯示高風險稽查建議路線", value=True,
                             help="把高風險園依風險分連成巡查路線，示範精準投放人力")
    show_roster = st.checkbox("顯示全市納管機構（含未評分）", value=True,
                              help="以灰點顯示全新北市立案幼兒園（基本資料已納管、"
                                   "財務資料待接入），展現全市涵蓋與架構可規模化")

geo = df[df["risk_level"].isin(show_levels)].dropna(subset=["lat", "lng"]).copy()
if sel_districts:
    geo = geo[geo["district"].isin(sel_districts)]
n_total = df.dropna(subset=["lat", "lng"]).shape[0]
n_high_all = int((df["risk_level"] == "高").sum())

# 全市涵蓋層（廣度）：全市立案幼兒園名冊，供地圖顯示全市涵蓋。
roster = common.load_roster()
roster_only = None
if roster is not None:
    roster_only = roster[roster["data_status"] == "roster_only"].dropna(
        subset=["lat", "lng"]).copy()
    if sel_districts:
        roster_only = roster_only[roster_only["district"].isin(sel_districts)]

# 全市查有裁罰紀錄機構數（真實裁罰圖層）。
_pen_df = common.load_penalty()
_n_pen = 0 if _pen_df is None else int(_pen_df["park_name"].nunique())

# 地圖統計 KPI
_cov = common.roster_coverage()
if _cov:
    common.kpi_band([
        ("全市納管機構", f"{_cov['total']:,}", False, f"涵蓋 {_cov['districts']} 區"),
        ("已評分並定位", f"{n_total}", False, "紅黃綠風險標示"),
        ("查有裁罰紀錄", f"{_n_pen}", True, "全國教保資訊網·橘點標示"),
        ("高風險機構", f"{n_high_all}", True, "地圖紅點標示"),
    ])
else:
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
st.caption(
    "座標說明（誠實揭露）：目前標記採「行政區概略中心座標」，同一行政區內機構"
    "位置相近，用於一眼看出「哪些區/機構需優先關注」的概況分佈；逐址精確地理"
    "編碼能力已實作（Nominatim 免金鑰，src/geocode.py），線上重跑即可升級。"
)

# ---------- 建立地圖 ----------
if len(geo) > 0:
    center = [geo["lat"].mean(), geo["lng"].mean()]
    zoom_start = 13 if sel_districts else 11
else:
    center = [df["lat"].dropna().mean(), df["lng"].dropna().mean()]
    zoom_start = 11

fmap = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap",
                  control_scale=True)

# ---------- 全市納管機構（未評分）灰點圖層：展現全市涵蓋 ----------
# 先畫灰點（底層），已評分的紅黃綠點稍後畫在上層，確保重點機構不被遮蓋。
if show_roster and roster_only is not None and len(roster_only) > 0:
    for _, r in roster_only.iterrows():
        # 真實裁罰紀錄比對：查有裁罰者以橘點強調
        pen = common.penalty_for(r["park_name"])
        has_pen = pen is not None
        pen_html = ""
        dot_color, dot_fill = "#9AA3AD", "#B7BEC7"
        if has_pen:
            dot_color, dot_fill = "#C0722A", "#E8A868"
            status = str(pen.get("status", "") or "").strip()
            status_line = (f"<br>營運狀態：<b>{status}</b>" if status else "")
            pen_html = (
                f"<hr style='margin:6px 0;border-color:#E3E8EF;'>"
                f"<div style='font-size:12px;color:#B0453A;font-weight:700;'>"
                f"⚠ 查有裁罰／處分紀錄</div>"
                f"<div style='font-size:11px;color:#6B7280;'>資料來源：全國教保資訊網"
                f"{status_line}</div>"
            )
        popup_html = (
            f"<div style=\"font-family:'Microsoft JhengHei',sans-serif;min-width:200px;\">"
            f"<div style='font-size:14px;font-weight:700;color:#1A1F29;'>{r['park_name']}</div>"
            f"<div style='color:#6B7280;font-size:12px;'>{r.get('district','')}　·　"
            f"{r.get('park_type','')}</div>"
            f"<hr style='margin:6px 0;border-color:#E3E8EF;'>"
            f"<div style='font-size:12px;color:#6B7280;'>基本資料已納管<br>"
            f"財務資料待接入，尚未進行鑑識會計風險評分</div>"
            f"{pen_html}</div>"
        )
        folium.CircleMarker(
            location=[r["lat"], r["lng"]], radius=(5 if has_pen else 3.5),
            color=dot_color, fill=True, fill_color=dot_fill,
            fill_opacity=(0.8 if has_pen else 0.55), weight=1,
            popup=folium.Popup(popup_html, max_width=260),
            tooltip=(f"{r['park_name']}（查有裁罰紀錄）" if has_pen
                     else f"{r['park_name']}（基本資料已納管）"),
        ).add_to(fmap)

for _, r in geo.iterrows():
    # 呈現無關的標記描述（顏色映射、風險訊號、缺資料處理）由 risk_map 提供，
    # 頁面僅負責 folium 渲染（薄包裝）。
    mk = risk_map.build_marker(r.to_dict())
    color = mk.color
    district = str(r.get("district", "")) if hasattr(r, "get") else r["district"]
    park_type = str(r.get("park_type", "")) if hasattr(r, "get") else r["park_type"]

    # 主要問題 / 缺資料提示（R2.9, R2.10）
    if mk.has_data:
        problem_html = "<br>".join(f"· {p}" for p in mk.signals_text())
    else:
        problem_html = f"· {risk_map.DATA_UNAVAILABLE}"

    # 分數區塊：缺分數時顯示「資料尚未提供」而非數值（R2.10）
    if mk.score is not None:
        score_block = (f'{mk.score:.1f}'
                       f'<span style="font-size:12px;color:#6B7280;">'
                       f'分　（{mk.level}風險）</span>')
    else:
        score_block = (f'<span style="font-size:14px;color:#6B7280;">'
                       f'{risk_map.DATA_UNAVAILABLE}</span>')

    popup_html = f"""
    <div style="font-family:'Microsoft JhengHei',sans-serif;min-width:210px;">
      <div style="font-size:15px;font-weight:700;color:#1A1F29;">{mk.name}</div>
      <div style="color:#6B7280;font-size:12px;">{district}　·　{park_type}</div>
      <hr style="margin:6px 0;border-color:#E3E8EF;">
      <div style="font-size:22px;font-weight:800;color:{color};">
        {score_block}
      </div>
      <div style="font-size:12px;margin-top:6px;color:#1A1F29;">主要風險訊號：<br>{problem_html}</div>
    </div>
    """
    radius = 6 + (mk.score or 0) / 10
    folium.CircleMarker(
        location=[mk.lat, mk.lng],
        radius=radius,
        color=color,
        fill=True,
        fill_color=color,
        fill_opacity=0.78,
        weight=2,
        popup=folium.Popup(popup_html, max_width=280),
        tooltip=(f"{mk.name}（{mk.score:.0f} 分）" if mk.score is not None
                 else f"{mk.name}（{risk_map.DATA_UNAVAILABLE}）"),
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
    "<div style='margin-top:10px;color:%s;font-size:.82rem;'>圖例：%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s"
    "&nbsp;&nbsp;·&nbsp;&nbsp;圈越大代表風險分越高；紅色虛線為高風險稽查建議路線。"
    "灰點為全市已納管、財務資料待接入之機構。</div>"
    % (common.MUTED,
       common.dot(common.LEVEL_COLOR["高"], "高風險"),
       common.dot(common.LEVEL_COLOR["中"], "中風險"),
       common.dot(common.LEVEL_COLOR["低"], "低風險"),
       common.dot("#B7BEC7", "基本資料已納管"),
       common.dot("#E8A868", "查有裁罰紀錄")),
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
