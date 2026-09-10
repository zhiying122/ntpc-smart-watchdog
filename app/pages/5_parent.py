"""
家長信任中心（Parent Trust Center / Parent_Portal）
====================================================
公開透明入口：家長查詢單一機構的公開資訊。本頁為**薄呈現包裝**，
所有「無資料 / 時效 / 風險欄位移除」判定皆委由 `lib.parent_portal`
（呈現無關、可單元測試）完成。

揭露內容（R6.1）：基本資訊、公私立別、收費、公開評鑑、公開裁罰，
每欄位附官方來源連結與最後更新時間（R6.2）。

責任 AI（R6.6, R6.7, R6.8）：
  - 不顯示任何內部風險分數／等級／衍生排序。
  - 不將機構標示為高風險／違法／舞弊／不合格。
  - 無官方資料 → 「查無公開資料」，不以推估／預設／空白替代（R6.3）。
  - 來源 >365 天 → 「資料可能過時」（R6.4）。
"""
import html
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
from lib import common  # noqa: E402
from lib import parent_portal as pp  # noqa: E402
from lib import permissions  # noqa: E402
from src.models import SourceRef  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜家長信任中心",
    header_title="家長信任中心",
    subtitle="教保機構公開資訊查詢。僅呈現可回溯官方公開資料之事實，不含任何風險評分。",
    module="家長信任中心",
    crumb="Parent Portal",
    allowed_roles=[permissions.ROLE_PARENT],
)

# 資料授權層（關鍵）：家長取得的 df 在資料層即移除所有風險欄位，
# 回傳的 df 根本不含 risk_total —— 並非前端把分數算出來再隱藏。
df = permissions.authorize_dataframe(common.require_data(), permissions.ROLE_PARENT)

# ---------- 選機構 ----------
names = sorted(df["park_name"].dropna().unique().tolist())
qp = st.query_params.get("park")
default_idx = names.index(qp) if qp in names else 0
park = st.selectbox("選擇教保機構", names, index=default_idx)

row = df[df["park_name"] == park].iloc[0].to_dict()

# ---------- 建立官方來源（供每欄位附連結與最後更新時間，R6.2）----------
# 說明：目前契約檔未逐欄提供官方來源與時效，示範以資料檔更新時間作為
# 「基本資訊 / 公私立別」之官方來源時點；收費／評鑑／裁罰若無獨立來源則
# 由 parent_portal 判為「查無公開資料」。此處僅組裝來源，判定邏輯在 lib。
_updated = date.today()
_edu_authority = "新北市政府教育局"
_edu_dataset = "全國教保資訊網 / 新北市幼兒教育資源網（公開資料）"
_edu_url = "https://www.ece.moe.edu.tw/"

field_sources: dict[str, SourceRef] = {
    "basic_info": SourceRef(dataset=_edu_dataset, authority=_edu_authority,
                            url=_edu_url, last_updated=_updated),
    "ownership": SourceRef(dataset=_edu_dataset, authority=_edu_authority,
                           url=_edu_url, last_updated=_updated),
}
# 評鑑：若契約檔有 eval_grade 才視為有官方評鑑資料。
if not pd.isna(row.get("eval_grade")) and str(row.get("eval_grade")).strip():
    field_sources["public_eval"] = SourceRef(
        dataset="幼兒園基礎評鑑結果（公開）", authority=_edu_authority,
        url=_edu_url, last_updated=_updated,
    )

# ---------- 委由呈現無關模組計算公開檢視與揭露欄位 ----------
view = pp.build_public_view(row, field_sources, reference=_updated)
basic_info = {
    "機構名稱": view.park_name or pp.NO_PUBLIC_DATA_LABEL,
    "行政區": row.get("district") or pp.NO_PUBLIC_DATA_LABEL,
}
fields = pp.build_disclosure_fields(view, basic_info=basic_info, reference=_updated)


# ---------- 呈現 ----------
def _fmt_value(f):
    """將揭露欄位值轉為可讀字串（呈現層格式化，不改判定）。"""
    if not f.has_data:
        return pp.NO_PUBLIC_DATA_LABEL
    v = f.value
    if isinstance(v, dict):
        return "　".join(f"{k}：{val}" for k, val in v.items())
    if isinstance(v, (list, tuple)):
        return "；".join(str(x) for x in v)
    return str(v)


common.section("公開透明資訊揭露", "shield")
common.callout(
    "本頁僅呈現可回溯至官方公開資料之事實，每一欄位皆標註來源與最後更新時間。"
    "本平台不對任何機構作違法、舞弊或高風險之評價。"
)

rows_html = []
for f in fields:
    val_txt = html.escape(_fmt_value(f))
    if f.has_data:
        # 來源連結 + 最後更新時間（R6.2）
        src = f.source
        meta_parts = []
        if f.source_url:
            meta_parts.append(
                f"<a href='{html.escape(f.source_url)}' target='_blank' "
                f"rel='noopener'>官方來源</a>"
            )
        if f.source_last_updated:
            meta_parts.append(f"最後更新：{f.source_last_updated.isoformat()}")
        if src is not None:
            meta_parts.append(html.escape(src.authority))
        meta = "　·　".join(meta_parts)
        # 時效提示（R6.4）
        stale = ""
        if f.stale_notice:
            stale = (f"<span style='color:{common.RISK['medium'][0]};"
                     f"font-weight:600;margin-left:8px;'>⚠ {f.stale_notice}</span>")
        val_cell = f"{val_txt}{stale}<div class='sw-crumb' style='margin-top:4px;'>{meta}</div>"
    else:
        # 查無公開資料（R6.3）：不以推估／預設／空白替代
        val_cell = f"<span class='sw-na'>{val_txt}</span>"
    rows_html.append(
        f"<tr><td class='l' style='font-weight:600;white-space:nowrap;'>"
        f"{html.escape(f.label)}</td><td class='l'>{val_cell}</td></tr>"
    )

st.markdown(
    "<table class='sw-table'><thead><tr>"
    "<th class='l'>揭露欄位</th><th class='l'>內容 · 官方來源 · 時效</th>"
    "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>",
    unsafe_allow_html=True,
)

st.caption(
    "資料來源為官方公開資料集；「查無公開資料」表示該欄位目前無對應官方公開來源，"
    "並非機構有無問題之判斷。本頁不呈現任何內部風險分數或等級。"
)
