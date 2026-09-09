"""
稽查行動（Inspection Action Center）
====================================
把風險分數轉成「可直接派工」的稽查行動：
- 派工清單自動生成（功能1）：勾選要查的機構，含「為何查／查什麼」，可匯出 Excel/CSV。
- 稽查路線最佳化摘要（功能2）：對選定機構做最近鄰路線排序 + 預估車程。
- 人力配置模擬器（功能3）：拉 slider 看「N 位稽查員能覆蓋風險前幾 %」。
只呈現與純資料整形，計算仍以既有風險欄位為基礎（白盒子可解釋）。
"""
import math
import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜稽查行動",
    header_title="稽查行動中心",
    subtitle="把風險分數轉為可派工的稽查行動：派工清單、路線最佳化、人力配置模擬。",
    module="稽查行動",
)

df = common.require_data().sort_values("risk_total", ascending=False).reset_index(drop=True)

# ---------- KPI ----------
n_high = int((df["risk_level"] == "高").sum())
n_mid = int((df["risk_level"] == "中").sum())
common.kpi_band([
    ("待派工機構", f"{len(df)}", False, "全體納管"),
    ("高風險（建議優先）", f"{n_high}", True, "本週優先派工"),
    ("中風險（例行）", f"{n_mid}", False, "納入排程追蹤"),
])

# ===========================================================================
# 功能1：派工清單自動生成
# ===========================================================================
common.section("稽查派工清單（自動生成）", "case")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "系統依風險分與觸發的鑑識紅旗，自動排出本週建議派工清單，"
    "每筆含「為何要查」與「建議查核重點」，稽查員可直接帶著出勤。</div>",
    unsafe_allow_html=True,
)

fc1, fc2, fc3 = st.columns([1.3, 1.4, 1.2])
with fc1:
    scope = st.pills("派工範圍", ["僅高風險", "高＋中風險", "全部"],
                     selection_mode="single", default="僅高風險")
with fc2:
    districts = sorted(df["district"].dropna().unique().tolist())
    sel_d = st.multiselect("限定行政區（空＝不限）", districts, default=[])
with fc3:
    topn = st.number_input("最多派工筆數", min_value=3, max_value=len(df),
                           value=min(10, len(df)), step=1)

work = df.copy()
if scope == "僅高風險":
    work = work[work["risk_level"] == "高"]
elif scope == "高＋中風險":
    work = work[work["risk_level"].isin(["高", "中"])]
if sel_d:
    work = work[work["district"].isin(sel_d)]
work = work.head(int(topn)).reset_index(drop=True)

if len(work) == 0:
    common.empty_state("目前條件下無派工對象", "請放寬派工範圍或行政區條件。", "check")
    st.stop()

# 組派工清單表格
body = ""
export_rows = []
for i, r in work.iterrows():
    reason = common.dispatch_reason(r)
    focus = common.audit_focus(r)
    nflag = common.red_flag_count(r)
    body += (
        "<tr>"
        f"<td class='l sw-rank'>{i+1}</td>"
        f"<td class='l'>{r['park_name']}</td>"
        f"<td class='l'>{r['district']}</td>"
        f"<td>{common.score_bar(r['risk_total'], r['risk_level'])}</td>"
        f"<td class='l'>{common.badge(r['risk_level'])}</td>"
        f"<td style='color:{common.RISK['high'][0] if nflag else common.INK_MUTED};"
        f"font-weight:600;'>{nflag}</td>"
        f"<td class='l' style='color:{common.INK_2};'>{reason}</td>"
        f"<td class='l' style='color:{common.INK_2};'>{focus}</td>"
        "</tr>"
    )
    export_rows.append({
        "派工順序": i + 1, "機構名稱": r["park_name"], "行政區": r["district"],
        "機構類型": r["park_type"], "總風險分": round(float(r["risk_total"]), 1),
        "風險等級": r["risk_level"], "觸發紅旗數": nflag,
        "為何要查": reason, "建議查核重點": focus,
    })

st.markdown(
    "<table class='sw-table'><thead><tr>"
    "<th class='l'>#</th><th class='l'>機構名稱</th><th class='l'>行政區</th>"
    "<th>風險分</th><th class='l'>等級</th><th>紅旗數</th>"
    "<th class='l'>為何要查</th><th class='l'>建議查核重點</th>"
    f"</tr></thead><tbody>{body}</tbody></table>",
    unsafe_allow_html=True,
)

export_df = pd.DataFrame(export_rows)
st.download_button(
    "下載派工清單（CSV，可用 Excel 開啟）",
    data=export_df.to_csv(index=False).encode("utf-8-sig"),
    file_name="稽查派工清單.csv",
    mime="text/csv",
    type="primary",
)

# ===========================================================================
# 功能2：稽查路線最佳化摘要（最近鄰）
# ===========================================================================
common.section("稽查路線最佳化", "map")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "以上派工清單中具座標的機構，用最近鄰法排出巡查順序並估算里程，"
    "讓一趟出勤能多跑幾間。地圖視覺化見「風險地圖」頁。</div>",
    unsafe_allow_html=True,
)

route_src = work.dropna(subset=["lat", "lng"]).copy()
if len(route_src) < 2:
    common.empty_state("可定位機構不足", "派工清單中具座標的機構少於 2 間，無法排路線。", "map")
else:
    def haversine(a, b):
        R = 6371.0
        lat1, lng1, lat2, lng2 = map(math.radians, [a[0], a[1], b[0], b[1]])
        dlat, dlng = lat2 - lat1, lng2 - lng1
        h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
        return 2 * R * math.asin(math.sqrt(h))

    pts = route_src[["park_name", "district", "lat", "lng", "risk_total"]].to_dict("records")
    # 從風險最高者出發，最近鄰貪婪法
    unvisited = pts[:]
    ordered = [unvisited.pop(0)]
    while unvisited:
        last = ordered[-1]
        nxt = min(unvisited, key=lambda p: haversine(
            (last["lat"], last["lng"]), (p["lat"], p["lng"])))
        unvisited.remove(nxt)
        ordered.append(nxt)

    total_km = 0.0
    body = ""
    for idx, p in enumerate(ordered):
        if idx == 0:
            leg = 0.0
        else:
            leg = haversine((ordered[idx - 1]["lat"], ordered[idx - 1]["lng"]),
                            (p["lat"], p["lng"]))
            total_km += leg
        leg_txt = "起點" if idx == 0 else f"{leg:.1f} km"
        body += (
            "<tr>"
            f"<td class='l sw-rank'>{idx+1}</td>"
            f"<td class='l'>{p['park_name']}</td>"
            f"<td class='l'>{p['district']}</td>"
            f"<td>{p['risk_total']:.1f}</td>"
            f"<td>{leg_txt}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>順序</th><th class='l'>機構名稱</th><th class='l'>行政區</th>"
        "<th>風險分</th><th>距上一站</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    # 估算：市區平均車速 ~25km/h + 每站停留 40 分鐘
    drive_min = total_km / 25 * 60
    stop_min = len(ordered) * 40
    total_min = drive_min + stop_min
    common.kpi_band([
        ("巡查站數", f"{len(ordered)}", False, "本路線機構數"),
        ("總里程", f"{total_km:.1f} km", False, "最近鄰估算"),
        ("預估耗時", f"{total_min/60:.1f} 小時", False, "含車程與每站約 40 分"),
    ])
    st.caption("里程為直線距離的最近鄰估算，作為排程參考；實際請以導航道路距離為準。")

# ===========================================================================
# 功能3：人力配置模擬器
# ===========================================================================
common.section("人力配置模擬器", "shield")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "在有限稽查人力下，量化「能覆蓋到風險前幾 % 的機構」，"
    "供編列人力與預算時做取捨決策。</div>",
    unsafe_allow_html=True,
)

sc1, sc2 = st.columns(2)
with sc1:
    n_auditors = st.slider("可用稽查員人數", 1, 12, 3)
with sc2:
    cap = st.slider("每位稽查員本季可查機構數", 1, 15, 5)

capacity = n_auditors * cap
ranked = df.sort_values("risk_total", ascending=False).reset_index(drop=True)
covered = ranked.head(capacity)
coverage_pct = min(capacity, len(df)) / len(df) * 100
# 高風險覆蓋率
high_total = int((df["risk_level"] == "高").sum())
high_covered = int((covered["risk_level"] == "高").sum())
high_cov_pct = (high_covered / high_total * 100) if high_total else 100.0
# 覆蓋到的風險分佔比（覆蓋風險量／總風險量）
risk_covered_pct = covered["risk_total"].sum() / df["risk_total"].sum() * 100

common.kpi_band([
    ("本季可查量能", f"{capacity}", False, f"{n_auditors} 人 × {cap} 間"),
    ("機構覆蓋率", f"{coverage_pct:.0f}%", False, f"{min(capacity, len(df))} / {len(df)} 間"),
    ("高風險覆蓋率", f"{high_cov_pct:.0f}%", high_cov_pct < 100,
     f"{high_covered} / {high_total} 間"),
    ("風險量覆蓋率", f"{risk_covered_pct:.0f}%", False, "已涵蓋的風險分佔全體比例"),
])

if high_cov_pct >= 100:
    common.callout(
        f"<b>建議</b><br>目前量能（{capacity} 間）足以覆蓋全部 {high_total} 間高風險機構，"
        "剩餘量能可投入中風險例行追蹤。")
else:
    need = math.ceil(high_total / cap)
    common.callout(
        f"<b>建議</b><br>目前量能僅能覆蓋 {high_cov_pct:.0f}% 的高風險機構。"
        f"若要全覆蓋 {high_total} 間高風險機構，在每人可查 {cap} 間的前提下，"
        f"至少需 <b>{need}</b> 位稽查員。")

st.caption("此模擬假設稽查資源優先投向風險分最高者（精準投放），"
           "覆蓋率為量化決策參考，非硬性排程。")
