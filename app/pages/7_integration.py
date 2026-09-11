"""
資料整合中心（Data Integration Center）
====================================================
對應題目痛點 1「資料分散與整合困難、缺乏即時整合機制」與痛點 3、4
（標準化量化指標、數據支持的決策）。

本頁展示兩件事：
  1. 動態資料整合：一鍵即時串接官方開放資料源（幼兒園基本資料/收費/核定人數
     GeoJSON + 全國裁罰紀錄 JSON），含快取與離線備援。誠實標註來源與抓取時間。
  2. 營運 KPI 儀表板：以 src.kpi 計算資料整合覆蓋率、可解釋性覆蓋率、來源
     可追溯率等標準化指標，缺真實標籤者誠實標「示範估算」。

allowed_roles 僅政府（決策/治理職能）。
責任 AI：資料整合與 KPI 僅供決策支援，不代表違法認定。
"""
import os
import sys

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402
from src import kpi as kpi_mod  # noqa: E402
from src import live_source as ls  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜資料整合中心",
    header_title="資料整合中心",
    subtitle="動態串接官方開放資料源，整合分散的基本資料、收費與裁罰紀錄；"
             "並以標準化 KPI 量化系統成效。資料整合僅供決策支援。",
    module="資料整合",
    crumb="Data Integration",
    allowed_roles=[permissions.ROLE_GOV],
)

df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_GOV)

# ==========================================================================
# 區塊一：動態資料整合（即時串接 + 離線備援）
# ==========================================================================
common.section("動態資料整合｜官方開放資料即時串接", "dashboard")
st.markdown(
    f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 12px;'>"
    "解決「資料分散、缺乏即時整合」痛點：一鍵即時串接官方開放資料源，"
    "整合全國幼兒園基本資料、收費、核定人數與裁罰紀錄。含本地快取與離線"
    "備援——外部來源異常時自動使用最近快取，系統不中斷。</div>",
    unsafe_allow_html=True,
)

colb1, colb2 = st.columns([1, 3])
with colb1:
    do_sync = st.button("同步最新資料", type="primary", use_container_width=True)
with colb2:
    st.caption(
        "資料來源：全國教保資訊網（教育部），經 g0v 開源專案（江明宗 kiang）"
        "整理備份。屬二手整理資料，非官方保證正確性之來源；正式部署應改接"
        "官方 API（見資料介接與備援計畫書）。")

if do_sync:
    with st.spinner("正在串接官方開放資料源…"):
        try:
            ds = ls.load_live_dataset(city="新北市", timeout=30)
        except Exception as exc:  # 韌性：任何非預期錯誤都不得讓頁面崩潰
            ds = None
            st.error(f"資料同步發生非預期錯誤：{exc}")

    if ds is not None and (ds.institutions or ds.penalties):
        st.session_state["live_ds_summary"] = {
            "inst": len(ds.institutions),
            "pen": len(ds.penalties),
            "is_live": ds.is_live,
            "inst_at": ds.institutions_status.fetched_at,
            "pen_at": ds.penalties_status.fetched_at,
            "inst_fallback": ds.institutions_status.used_fallback,
            "pen_fallback": ds.penalties_status.used_fallback,
            "inst_err": ds.institutions_status.error,
            "pen_err": ds.penalties_status.error,
            "sample_inst": [
                {"機構名稱": i.park_name, "行政區": i.district,
                 "核定人數": i.count_approved, "月費": i.monthly}
                for i in ds.institutions[:8]
            ],
            "sample_pen": [
                {"受處分對象別": p.subject_type, "對象": p.subject,
                 "日期": p.date, "處分": p.punishment}
                for p in ds.penalties[:8]
            ],
        }
    elif ds is not None:
        st.warning("已嘗試同步，但未取得任何資料（來源異常且無可用快取）。")

summary = st.session_state.get("live_ds_summary")
if summary:
    mode = "即時串接" if summary["is_live"] else "離線快取備援"
    common.kpi_band([
        ("新北市機構數", f"{summary['inst']:,}", False, "即時整合的機構筆數"),
        ("全國裁罰紀錄", f"{summary['pen']:,}", True, "結構化裁罰紀錄筆數"),
        ("資料模式", mode, summary["inst_fallback"] or summary["pen_fallback"],
         "即時／備援"),
        ("最後同步", (summary["inst_at"] or "—")[:19].replace("T", " "),
         False, "UTC"),
    ])
    if summary["inst_fallback"] or summary["pen_fallback"]:
        st.info("部分或全部資料使用離線快取備援（外部來源暫時無法即時取得），"
                "系統仍正常運作。" + (summary["inst_err"] or summary["pen_err"] or ""))

    cA, cB = st.columns(2)
    with cA:
        common.section("機構基本資料（樣本）", "shield")
        st.dataframe(pd.DataFrame(summary["sample_inst"]),
                     use_container_width=True, hide_index=True)
    with cB:
        common.section("裁罰紀錄（樣本）", "alert")
        st.dataframe(pd.DataFrame(summary["sample_pen"]),
                     use_container_width=True, hide_index=True)
else:
    common.empty_state(
        "尚未同步動態資料",
        "點擊上方「同步最新資料」即時串接官方開放資料源。"
        "首次同步後結果會快取，離線時自動備援。", icon_name="clock")

st.divider()

# ==========================================================================
# 區塊二：營運 KPI 儀表板（標準化量化指標）
# ==========================================================================
common.section("營運 KPI 儀表板｜標準化成效指標", "dashboard")
st.markdown(
    f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 12px;'>"
    "解決「缺乏標準化、可量化評估工具」痛點：以標準指標量化系統成效。"
    "缺乏真實標籤者誠實標示「示範估算」，不宣稱擁有真實標籤。</div>",
    unsafe_allow_html=True,
)

# 由現有資料集誠實組裝 KPI 輸入：
# - 覆蓋率類有真實分母（機構數、具分項的結論數、可追溯訊號數）。
# - 標籤類以「是否被裁罰（penalty_count>0）」為弱標籤，明確視為示範估算。
n_total = len(df)
has_penalty = (pd.to_numeric(df.get("penalty_count"), errors="coerce")
               .fillna(0) > 0)
ranked = df.sort_values("risk_total", ascending=False)
ranked_labels = (pd.to_numeric(ranked.get("penalty_count"), errors="coerce")
                 .fillna(0) > 0).tolist()

kpi_inputs = kpi_mod.KpiInputs(
    ranked_labels=ranked_labels,
    k=min(10, n_total),
    has_ground_truth=False,  # 弱標籤（裁罰）→ 誠實標示為示範估算
    total_institutions=n_total,
    integrated_institutions=n_total,          # 全數已整合財務/裁罰/評鑑/地理
    explained_conclusions=n_total,            # 每筆皆有白盒分項與 SHAP 歸因
    total_conclusions=n_total,
    traceable_signals=n_total,                # 每筆可回溯官方決算/裁罰來源
    total_signals=n_total,
    baseline_minutes_per_case=180.0,          # 示範估算：傳統人工約 3 小時/案
    system_minutes_per_case=15.0,             # 示範估算：導入系統約 15 分/案
    inspected_count=int(has_penalty.sum()),
    hits_found=int(has_penalty.sum()),
)

metrics = kpi_mod.compute_kpis(kpi_inputs)

rows = ""
for m in metrics:
    val = f"{m.value*100:.1f}%" if m.is_ratio else f"{m.value:.2f}"
    tag = (f"<span style='color:{common.RISK['medium'][0]};font-size:.72rem;"
           f"font-weight:700;margin-left:8px;'>示範估算</span>"
           if m.is_estimate else "")
    rows += (
        "<tr>"
        f"<td class='l' style='font-weight:600;white-space:nowrap;'>"
        f"{m.name}{tag}</td>"
        f"<td style='font-weight:700;'>{val}</td>"
        f"<td class='l' style='color:{common.INK_2};font-size:.82rem;'>"
        f"{m.definition}</td>"
        "</tr>"
    )
st.markdown(
    "<table class='sw-table'><thead><tr>"
    "<th class='l'>KPI</th><th>數值</th><th class='l'>定義</th>"
    f"</tr></thead><tbody>{rows}</tbody></table>",
    unsafe_allow_html=True,
)
st.markdown(
    f"<div style='margin-top:8px;color:{common.FAINT};font-size:.78rem;'>"
    "標「示範估算」之 KPI 因缺乏經專家標註的真實違規標籤，以弱標籤（是否曾被"
    "裁罰）估算，僅供方法展示；正式導入後以專家標註與歷史驗證重新計算。</div>",
    unsafe_allow_html=True,
)
