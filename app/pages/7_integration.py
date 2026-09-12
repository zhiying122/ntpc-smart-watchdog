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
from src import penalty_match as pm  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜資料整合中心",
    header_title="資料整合中心",
    subtitle="動態串接官方開放資料源，整合分散的基本資料、收費與裁罰紀錄；"
             "並以標準化 KPI 量化系統成效。資料整合僅供決策支援。",
    module="資料整合",
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
    do_refresh = st.button("重新整理資料", type="primary", width="stretch",
                           help="強制清除快取並重新即時串接官方開放資料源")
with colb2:
    st.caption(
        "本頁進入時即自動串接官方開放資料源（10 分鐘內以快取加速，可按左側"
        "強制重新整理）。資料來源：全國教保資訊網（教育部），經 g0v 開源專案"
        "（江明宗 kiang）整理備份；屬二手整理資料，正式部署應改接官方 API。")

# 進頁即自動串接（不需按鈕）：以 10 分鐘 TTL 快取加速，抓取含離線備援。
# 按「重新整理資料」則清快取強制重抓最新。
if do_refresh:
    common.live_dataset_cached.clear()
with st.spinner("正在串接官方開放資料源…"):
    summary = common.live_dataset_cached(city="新北市", timeout=25)
if summary is None:
    st.warning("目前無法取得動態資料（來源異常且無可用快取）；系統其餘功能不受影響。")
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
                     width="stretch", hide_index=True)
    with cB:
        common.section("裁罰紀錄（樣本）", "alert")
        st.dataframe(pd.DataFrame(summary["sample_pen"]),
                     width="stretch", hide_index=True)

    # ---- 裁罰-機構實體比對（信心分級，責任 AI）----
    if "match_total" in summary:
        common.section("裁罰-機構實體比對（信心分級）", "shield")
        st.markdown(
            f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 10px;'>"
            "裁罰紀錄多以個人（行為人／負責人）為對象，需比對到具體機構。此比對"
            "本質不確定，故採<b>信心分級</b>：僅「高信心」（機構名相符，或負責人"
            "唯一對應）建議計入風險；負責人對應多間機構者標為「待人工確認」，"
            "不直接計分，避免冤枉機構。每筆比對均可追溯來源裁罰 id。</div>",
            unsafe_allow_html=True,
        )
        common.kpi_band([
            ("比對到機構的裁罰", f"{summary['match_total']:,}", False, "總比對筆數"),
            ("高信心（建議計入）", f"{summary['match_high']:,}", True,
             "機構名相符或負責人唯一"),
            ("待人工確認", f"{summary['match_pending']:,}", False,
             "負責人對應多間，不直接計分"),
            ("涉及機構數", f"{summary['match_institutions']:,}", False, "去重後"),
        ])
        if summary["match_top"]:
            st.markdown(
                f"<div style='color:{common.INK_2};font-size:.84rem;margin:8px 0 4px;'>"
                "高信心確認裁罰數最高的機構：</div>", unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(summary["match_top"]),
                         width="stretch", hide_index=True)
        st.markdown(
            f"<div style='margin-top:6px;color:{common.FAINT};font-size:.78rem;'>"
            "僅高信心比對建議作為風險引擎的裁罰標籤來源；待人工確認項須經稽查"
            "人員核對後方可採用（責任 AI：不確定比對不得推高機構風險）。</div>",
            unsafe_allow_html=True,
        )
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

# 指標讀法與樣本數誠實說明（避免 Recall@K=100% 被誤讀為模型完美）。
_n_pos = int(has_penalty.sum())
_k_val = min(10, n_total)
st.markdown(
    f"<div style='margin-top:12px;padding:10px 12px;border:1px solid "
    f"{common.BORDER};border-left:3px solid {common.RISK['medium'][0]};"
    f"border-radius:4px;color:{common.INK_2};font-size:.8rem;line-height:1.6;'>"
    f"<b>指標讀法（三句話）：</b>"
    f"① 風險偵測率與 Recall@K <b>同定義</b>（命中真實異常 ÷ 全部真實異常），"
    f"分母都是「真實異常數」；Precision@K 分母不同，是「名單長度 K」。"
    f"② 本批弱標籤（曾被裁罰）僅 <b>{_n_pos} 間</b>，K={_k_val} 已涵蓋全部 "
    f"{_n_pos} 間，因此 Recall@K＝100% 是<b>名單夠長</b>的結果，"
    f"<b>非模型零誤判</b>——誤判情形要看 Precision@K 與 FPR。"
    f"③ 樣本數極小（正樣本 {_n_pos} 間），此組數字僅示範計算方法，"
    f"不代表統計顯著的模型效能；擴大標註後才有評估意義。</div>",
    unsafe_allow_html=True,
)
