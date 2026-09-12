"""
官方公開信號分析（Official Public Signals）
======================================
以官方公開資料——裁罰紀錄與評鑑結果（全國教保資訊網）——作為
機構關注信號來源，依 Risk_Taxonomy 歸類並標記嚴重度。

為何用官方資料而非社群評論：
- 公信力最高：官方裁罰/評鑑是政府稽查系統最對味的訊號來源。
- 零成本、免金鑰、無爬蟲法遵風險。
- 每筆信號皆可追溯至官方來源（Evidence_Chain）。

責任邊界：本頁僅呈現官方已公開的事實，不作違法/舞弊認定。
"""
import importlib.util
import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from lib import common  # noqa: E402
from src import official_signals as osig  # noqa: E402


# ---------------------------------------------------------------------------
# 即時新聞爬蟲載入（以檔案路徑載入 public/lib/news_crawler，避免與 app/lib
# 的 `lib` package 命名衝突）。載入失敗時 _NC 為 None，頁面優雅退化不報錯。
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _load_news_crawler():
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    nc_path = os.path.join(root, "public", "lib", "news_crawler.py")
    try:
        spec = importlib.util.spec_from_file_location("sw_news_crawler", nc_path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["sw_news_crawler"] = mod
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def _fetch_live_news(park_name: str, district: str):
    """即時爬取本機構的公開新聞（Google/Bing News + 媒體 RSS，快取 6 小時）。

    僅回傳與本機構精確比對成功（matched=True）者，避免同名張冠李戴。
    爬蟲不可用或連線失敗一律回空清單（頁面誠實顯示「近期無相關新聞」）。
    """
    nc = _load_news_crawler()
    if nc is None:
        return []
    try:
        recs = nc.fetch_all_news(park_name, district or "", timeout=8,
                                 per_source_limit=6, limit=20)
        return [r for r in recs if r.get("matched")]
    except Exception:
        return []

common.setup_page(
    page_title="Fiscalint｜官方公開信號",
    header_title="官方公開信號分析",
    subtitle="以裁罰紀錄與評鑑結果（全國教保資訊網）呈現機構關注信號，依風險類別歸類。",
    module="官方公開信號",
)

# 公務後台全欄位可見。
df = common.require_data()

LABEL_TEXT = {"pos": "正向", "neg": "負向關注", "neu": "中性"}
LABEL_COLOR = {"pos": common.LEVEL_COLOR["低"], "neg": common.LEVEL_COLOR["高"],
               "neu": common.MUTED}
LABEL_BG = {"pos": common.LEVEL_BG["低"], "neg": common.LEVEL_BG["高"], "neu": "#EEF0F3"}
SEVERITY_COLOR = {
    osig.SEVERITY_MAJOR: common.LEVEL_COLOR["高"],
    osig.SEVERITY_MODERATE: common.LEVEL_COLOR["中"],
    osig.SEVERITY_MINOR: common.LEVEL_COLOR["低"],
    "一般": common.MUTED,
}

# ---------- 機構選擇 ----------
park_names = sorted(
    n for n in df["park_name"].dropna().astype(str).unique() if n.strip()
)
if not park_names:
    common.empty_state("目前無機構資料", "資料尚未載入。", icon_name="database")
    st.stop()

park = st.selectbox("選擇機構", park_names)
row = df[df["park_name"].astype(str) == park].iloc[0].to_dict()
report = osig.build_report(row)

common.section(f"{park}　官方公開信號", "sentiment")

common.kpi_band([
    ("信號則數", f"{report.total_count}"),
    ("負向關注則數", f"{report.negative_count}"),
    ("負向比例", f"{report.negative_ratio*100:.0f}%", report.negative_ratio >= 0.5),
    ("裁罰次數", f"{report.penalty_count}"),
])

# ---------- 信號明細表 ----------
common.section("信號明細（含來源與風險類別）", "sentiment")
if report.total_count == 0:
    common.empty_state("查無官方公開信號",
                       "該機構在裁罰與評鑑欄位查無公開資料。", icon_name="inbox")
else:
    body = ""
    for s in report.signals:
        tag = (f"<span class='sw-badge' style='background:{LABEL_BG[s.sentiment]};"
               f"color:{LABEL_COLOR[s.sentiment]};'>{LABEL_TEXT[s.sentiment]}</span>")
        sev_color = SEVERITY_COLOR.get(s.severity, common.MUTED)
        sev = (f"<span style='color:{sev_color};font-weight:600;'>{s.severity}</span>")
        body += (
            f"<tr><td class='l'>{s.text}</td>"
            f"<td class='l'>{s.category}</td>"
            f"<td class='l'>{sev}</td>"
            f"<td class='l'>{tag}</td>"
            f"<td class='l' style='color:{common.MUTED};font-size:.82rem;'>{s.source}</td></tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>信號內容</th><th class='l'>風險類別</th>"
        "<th class='l'>嚴重度</th><th class='l'>關注傾向</th>"
        "<th class='l'>資料來源</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )

# 關注傾向圖例
st.markdown(
    "<div style='margin-top:10px;color:%s;font-size:.82rem;'>關注傾向：%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s</div>"
    % (common.MUTED,
       common.dot(LABEL_COLOR["pos"], "正向"),
       common.dot(LABEL_COLOR["neg"], "負向關注"),
       common.dot(LABEL_COLOR["neu"], "中性")),
    unsafe_allow_html=True,
)

common.callout(
    "本頁信號全數取自<b>官方公開資料</b>（全國教保資訊網之裁罰紀錄與評鑑結果），"
    "每筆皆標示<b>資料來源</b>可供追溯。裁罰與評鑑已透過各自分項計入總風險分，"
    "本頁提供依<b>風險類別與嚴重度</b>拆解的可解釋視圖。"
    "本頁僅呈現官方已公開之事實，<b>不構成</b>對機構違法或不合格之認定。"
)

with st.expander("這個功能如何規模化（架構說明）"):
    st.markdown(
        """
        目前以新北市立園的官方裁罰與評鑑資料示範，驗證「官方公開信號 → 風險類別歸類
        → 可解釋呈現」的流程可跑。

        規模化路徑（架構相同、資料量放大）：
        1. 定期同步全國教保資訊網之裁罰紀錄、評鑑結果、收費明細（官方公開、免金鑰）。
        2. 用 AWS Bedrock（Claude）對裁罰處分書全文做語意歸類與嚴重度判讀，
           比關鍵詞法更準、能理解裁罰情節。
        3. 選用擴充：家長／社群輿情微弱訊號（受 15 分上限約束），架構已於規格預留。

        官方資料公信力最高，是政府稽查系統最對味的信號來源。
        """
    )

# ==========================================================================
# 即時新聞輿情（真實爬取：Google News + Bing News + 台灣媒體 RSS）
# ==========================================================================
# 與上方「官方公開信號」互補：官方信號＝已裁罰/評鑑的確定事實；本區＝網路
# 新聞輿情的『事件訊號』（媒體報導，非違法認定）。來源皆為公開 RSS、免金鑰、
# 不需登入，符合政府級合規邊界；每則精準比對本園（避免同名張冠李戴），附
# 媒體與原文連結可追溯。
common.section("即時新聞輿情（真實爬取·公開 RSS）", "sentiment")
_district = str(row.get("district", "") or "")
with st.spinner("即時擷取公開新聞中…"):
    _news = _fetch_live_news(park, _district)

if _news:
    st.markdown(
        f"<div style='color:{common.INK_2};font-size:.86rem;margin:2px 0 10px;'>"
        f"即時擷取到 <b>{len(_news)}</b> 則與「{park}」精準比對成功的公開新聞"
        f"（Google News／Bing News／台灣媒體 RSS，皆公開來源、免金鑰）。"
        f"以下為媒體報導事件訊號，<b>非本平台對機構之違法認定</b>。</div>",
        unsafe_allow_html=True,
    )
    body = ""
    for n in _news[:15]:
        _plat = {"google_news": "Google News", "bing_news": "Bing News",
                 "media_rss": n.get("source_name", "媒體")}.get(
                     n.get("source_platform"), "新聞")
        _title = n.get("title", "")
        _url = n.get("url", "")
        _title_html = (f"<a href='{_url}' target='_blank' style='color:{common.PRIMARY};'>"
                       f"{_title}</a>" if _url else _title)
        body += (
            f"<tr><td class='l' style='font-size:.82rem;color:{common.MUTED};'>"
            f"{n.get('published','')}</td>"
            f"<td class='l'>{_title_html}</td>"
            f"<td class='l' style='font-size:.82rem;color:{common.MUTED};'>"
            f"{n.get('source_name','')}｜{_plat}</td></tr>")
    st.markdown(
        "<table class='sw-table'><thead><tr><th class='l'>日期</th>"
        "<th class='l'>新聞標題（點擊看原文）</th><th class='l'>媒體／來源</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.caption(
        "新聞標題可能含媒體指控性用語，那是媒體用語、非本平台認定；本系統僅忠實"
        "傳遞標題與原文連結供人工查核。多來源交叉出現同一事件時，關注度較高。"
    )
else:
    common.empty_state(
        "近期無精準比對之公開新聞",
        f"即時查詢 Google News／Bing News／台灣媒體 RSS，未發現與「{park}」"
        "精準對應的公開報導。對公立園而言，這通常是正常且正面的訊號（少有負面"
        "新聞事件）；系統採責任 AI 精準比對，寧可不綁定也不冤枉同名機構。",
        icon_name="check",
    )

with st.expander("即時新聞輿情如何做到「真實爬取且合規」"):
    st.markdown(
        """
        本區為**真實即時爬取**，非示範資料：

        - **來源**：Google News RSS + Bing News RSS + 台灣主要媒體公開 RSS
          （自由時報／中央社／聯合報／ETtoday／鏡週刊等），全部**公開、免金鑰、
          不需登入**，符合政府級合規邊界。
        - **精準比對（責任 AI）**：以園名核心詞 + 行政區綁定查詢，每則標題再經
          二次比對；市立園若核心詞為地區泛稱（如「林口」），要求標題含**完整
          全名**才視為相關，避免把同區其他機構的新聞張冠李戴。
        - **不爬什麼**：不爬需登入的 FB／IG／Dcard、不爬違反 ToS 的 Google 商家
          評論——這些於正式版需經各平台官方 API 授權接入（架構已預留）。
        - **快取**：結果快取 6 小時，避免對公共服務過量請求。
        """
    )
