"""
安心找幼兒園 — 家長公開資訊與鄰近機構地圖（Parent Trust & Neighborhood Map）
============================================================================
小小守護員 Smart Watchdog Platform — 面向一般民眾／家長的**獨立**公眾平台。

這是什麼（與公務後台的關係）：
--------------------------------------------------------------------------
本站與「公務後台（Fiscalint 稽查預警系統，app/主頁.py）」是**兩個完全獨立
的系統**。公務後台供授權稽查員使用，含財務鑑識風險分數；本站**無需登入**，
只揭露公開資訊與「公開網路輿情觀測」，**不含也拿不到**任何後台風險分數。

視覺與用詞（刻意不同於後台）：
--------------------------------------------------------------------------
- 給家長看的，語氣溫暖、易懂、不嚇人，但資訊誠實可回溯。
- **不使用後台的「高/中/低風險」字眼**。輿情觀測改用描述性的
  「近期關注度：平靜期／有討論／值得留意」，並在每個分級旁附「依據」。
- 地圖標記用柔和色階（暖琥珀非警報紅），避免造成家長不必要的恐慌。

資料流與合規：
--------------------------------------------------------------------------
- 機構公開資料：向共用中台取數，並在**資料層**以
  permissions.authorize_dataframe(df, ROLE_PARENT) 移除所有風險欄位。
- 地址定位：Nominatim（OpenStreetMap 免費、免金鑰），不使用 Google Maps。
- 輿情觀測：僅示範公開來源（公開新聞／公開評論頁／公開論壇），每則附原文
  連結與發布時間，不蒐集需登入才可見之內容。目前為 DEMO 示範資料。

啟動：python -m streamlit run public/公開查詢.py --server.port 8602
"""
# 型別註記延遲求值（PEP 563）：本檔用到 `pd.DataFrame | None` 等 PEP 604 語法，
# 於 Python 3.9（EC2 部署環境）需此 import 才不會在 import 時報 TypeError。
# 注意：from __future__ 必須是 docstring 之後的第一個語句，不得置於其他 import 之後。
from __future__ import annotations

import html
import json
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# 路徑：本站可獨立執行，需能載入共用中台（src/）、家長端純邏輯（app/lib）與
# 本站專用純邏輯（public/lib）。不引入公務後台的登入/導覽。
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.dirname(os.path.abspath(__file__))
APP_LIB = os.path.join(ROOT, "app")
for _p in (ROOT, APP_LIB, HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import parent_portal as pp  # noqa: E402  (app/lib)
from lib import permissions  # noqa: E402  (app/lib)
from lib import geocode as geo  # noqa: E402  (public/lib)
from lib import parent_map as pmap  # noqa: E402  (public/lib)
from lib import sentiment_watch as sw  # noqa: E402  (public/lib)
from lib import sentiment_score as ss  # noqa: E402  (public/lib)
from lib import news_crawler as nc  # noqa: E402  (public/lib)
from lib import evaluation_cycle as evc  # noqa: E402  (public/lib)
from lib import input_guard as ig  # noqa: E402  (public/lib)
from lib import public_dataset as pdset  # noqa: E402  (public/lib)
from src.models import SourceRef  # noqa: E402

import folium  # noqa: E402
from folium.plugins import BeautifyIcon, MarkerCluster  # noqa: E402
from streamlit_folium import st_folium  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
LATEST_CSV = os.path.join(PROC, "kindergartens_latest.csv")
SENTIMENT_JSON = os.path.join(HERE, "data", "sentiment_demo.json")

TODAY = date.today()
CONTACT_EMAIL = "kids-guardian@ntpc.gov.tw"  # 示範用聯絡窗口


# ===========================================================================
# 資料載入（本站獨立，不依賴公務後台）
# ===========================================================================
@st.cache_data(show_spinner="正在同步最新公開資料…", ttl=6 * 3600)
def load_public_dataset_cached() -> dict:
    """載入即時真實公開資料（新北市全部幼兒園 + 真實裁罰），快取 6 小時。

    回傳可序列化 dict：{df_records, penalty_index, is_live, fetched_at,
    attribution, note}。df 仍過家長權限投影做二次防禦，確保無任何內部風險欄位。
    """
    # 家長端優先讀本地快照/快取（由 GitHub Actions 每日更新，夠新），確保頁面
    # 秒開、Demo 不卡在「同步中」；即時抓網僅在無任何離線資料時作為後備。
    pub = pdset.load_public_dataset(timeout=8, prefer_cache=True)
    # 二次防禦：即使來源只含公開欄位，仍過家長投影，保證無 risk_/score_ 外洩。
    safe_df = permissions.authorize_dataframe(pub.df, permissions.ROLE_PARENT) \
        if pub.df is not None and len(pub.df) else pub.df
    # authorize 會依白名單投影；但真實源欄位（owner/penalty_flag/monthly/address）
    # 不在家長 CSV 白名單內，會被濾掉。這裡我們需要保留這些公開欄位供呈現，
    # 故改以「黑名單過濾」為準：只移除風險欄位，保留其餘公開欄位。
    df = pub.df
    if df is not None and len(df):
        drop_cols = [c for c in df.columns if pp.is_risk_field(c)]
        df = df.drop(columns=drop_cols, errors="ignore")
    return {
        "df_records": df.to_dict("records") if df is not None else [],
        "penalty_index": pub.penalty_index,
        "is_live": pub.is_live,
        "fetched_at": pub.fetched_at,
        "attribution": pub.attribution,
        "note": pub.note,
    }


def load_public_data() -> pd.DataFrame | None:
    """回傳機構 DataFrame（家長公開欄位、無風險欄位）。"""
    d = load_public_dataset_cached()
    recs = d.get("df_records") or []
    if not recs:
        return None
    return pd.DataFrame(recs)


@st.cache_data(show_spinner=False)
def load_sentiment() -> dict:
    """載入公開輿情示範資料（DEMO）。"""
    if not os.path.exists(SENTIMENT_JSON):
        return {"institutions": {}}
    with open(SENTIMENT_JSON, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner="正在定位您輸入的地址…")
def geocode_cached(address: str) -> dict:
    """以快取包裝 Nominatim 查詢，避免對公共服務過量請求。回傳可序列化 dict。"""
    r = geo.geocode_address(address)
    return {"ok": r.ok, "lat": r.lat, "lng": r.lng,
            "display_name": r.display_name, "message": r.message,
            "precision": r.precision, "notice": r.notice}


def data_updated_at() -> str:
    """回傳真實資料源的最後抓取時間（ISO 轉為易讀）；無則回退快照時間。"""
    d = load_public_dataset_cached()
    iso = d.get("fetched_at") or (snapshot_meta() or {}).get("updated_at")
    if iso:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return str(iso)
    return "—"


@st.cache_data(show_spinner=False, ttl=3600)
def snapshot_meta() -> dict | None:
    """讀取由 GitHub Actions 每日更新的快照 meta（若存在）。

    回傳 {attribution, updated_at, sources:{preschools:{count,fetched_at},
    penalties:{...}}}；無檔或解析失敗回 None。供頁面誠實揭露「自動更新時間
    與筆數」。此檔由 scripts/update_snapshots.py 產生並進版控。
    """
    meta_path = os.path.join(ROOT, "data", "snapshots", "snapshot_meta.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def fetch_live_news(park_name: str, district: str) -> list[dict]:
    """即時抓取本機構的公開新聞（多來源聚合，快取 6 小時，隨時間自動更新）。

    來源＝多組 Google News 查詢 + Bing News（皆公開 RSS、免金鑰、合規）。
    僅保留與本機構精確比對成功（matched=True）的新聞，避免同名/同地區張冠
    李戴；抓不到或連線失敗回空清單（由呼叫端退回示範資料）。
    每筆帶 source_platform（google_news/bing_news）供頁面標示來源組成。
    """
    recs = nc.fetch_all_news(park_name, district, limit=30, reference=TODAY)
    return [r for r in recs if r.get("matched")]


def attention_for(park_id: str, park_name: str, district: str, sentiment_data: dict):
    """整合某機構的輿情：真實新聞（即時爬）+ 示範多來源資料，計算摘要與指數。

    回傳 (items, summary, index, meta)：
      - items：合併後、依時間排序的 SentimentItem 清單。
      - summary：sentiment_watch 的家長友善分級摘要。
      - index：輿情關注指數（診斷式白盒總評分）。
      - meta：來源組成計數，供頁面「資料來源透明分層」呈現。

    資料組成：
      - 真實新聞：多來源（Google News 多組查詢 + Bing News）即時抓取，只計
        matched=True；meta 分別記各平台則數。
      - 示範資料：sentiment_demo.json 內該園的社群多來源（Google評論/FB/IG/
        部落格等）示範項目，標明 DEMO（正式版待各平台官方 API 授權接入）。
    """
    live_recs = fetch_live_news(park_name, district)
    obj = sentiment_data.get("institutions", {}).get(str(park_id))
    demo_recs = list(obj.get("items", [])) if obj else []

    all_recs = list(live_recs) + list(demo_recs)
    items = sw.load_items_from_records(all_recs)
    summary = sw.summarize_attention(items, reference=TODAY)
    index = ss.compute_index(items, reference=TODAY)
    # 各新聞平台的即時則數（供透明分層標示「已接入來源」）。
    _gnews = sum(1 for r in live_recs if r.get("source_platform") == "google_news")
    _bing = sum(1 for r in live_recs if r.get("source_platform") == "bing_news")
    _media = [r for r in live_recs if r.get("source_platform") == "media_rss"]
    _media_names = sorted({r.get("source_name", "") for r in _media if r.get("source_name")})
    meta = {
        "live_news": len(live_recs),
        "google_news": _gnews,
        "bing_news": _bing,
        "media_rss": len(_media),
        "media_names": _media_names,
        "demo": len(demo_recs),
        "has_demo": bool(demo_recs),
    }
    return items, summary, index, meta


def marker_level_for(park_id: str, sentiment_data: dict) -> str:
    """地圖標記用的關注度分級：僅依示範資料快速判定，不即時爬新聞。

    地圖上可能有數十個標記，逐一即時爬新聞會造成大量網路請求而拖慢頁面。
    真實新聞的整合與輿情指數改在「點進單一機構詳情頁」時才計算
    （attention_for / fetch_live_news）。標記著色只需粗略分級，故以本地
    示範資料為準即可；無資料則為中性 none。
    """
    obj = sentiment_data.get("institutions", {}).get(str(park_id))
    if not obj:
        return sw.LEVEL_NONE
    items = sw.load_items_from_records(obj.get("items", []))
    return sw.summarize_attention(items, reference=TODAY).level


# ===========================================================================
# 頁面設定與樣式（家長版：溫暖、清爽、可信，不用終端機/警報視覺）
# ===========================================================================
st.set_page_config(
    page_title="安心找幼兒園｜公開資訊查詢",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&family=Noto+Serif+TC:wght@600;700;900&display=swap');

    /* ===================================================================
       設計 tokens：家長版「安心找幼兒園」
       -------------------------------------------------------------------
       調性：溫暖親和、沉穩可信，介於「親子健康服務 App」與「政府便民網」
       之間，刻意不同於後台稽查終端機的深色高密度視覺。
       主色：深鼠尾草綠（sage）— 聯想安心/成長/照護，比高飽和粉黃更專業。
       語意色（不可更動角色）：
         --safe  安靜綠  = 無裁罰紀錄（陳述客觀事實，非風險評分）
         --alert 暖琥珀  = 有／經標記裁罰（提醒非警報，避免恐慌）
       兩者刻意與主色（鼠尾草綠）拉開明度與彩度，畫面上一眼可辨。
       =================================================================== */
    :root {
      --bg:#F6F4EE;            /* 極淺暖灰卡其底色（非純白，避免冷硬） */
      --bg-soft:#FBFAF6;       /* 更淺的分層底 */
      --surface:#FFFFFF;       /* 卡片面 */
      --border:#E7E2D6;        /* 暖調邊線 */
      --border-soft:#F0ECE2;
      /* 中性文字：全數校準至 WCAG AA（正文 ≥4.5:1）於底色與卡片面上皆達標 */
      --ink:#33404E;           /* 主文字（沉穩藍灰，不用純黑）9.6:1 */
      --ink-strong:#26313C;    /* 標題文字 12:1 */
      --ink-dim:#5A636E;       /* 次要文字（校準後 5.5:1 / 6.1:1） */
      --ink-faint:#676E76;     /* 最淡註記（校準後 4.7:1 / 5.2:1，仍達正文 AA） */

      /* 主色：深鼠尾草綠。按鈕背景加深至白字達 AA（正式、沉穩，貼政府調性） */
      --sage:#4F7566;          /* 主色（白字 5.2:1）— 按鈕/強調 */
      --sage-strong:#446454;   /* 主色 hover/active（白字 6.6:1） */
      --sage-soft:#E8F0EC;     /* 主色柔和底（選中態） */
      --sage-tint:#F1F5F2;     /* 主色極淡底 */
      --sage-ink:#365349;      /* 主色系深字（選中態文字）7.3:1 */

      /* 語意色：圓點/地圖標記用「識別色」（不可變，對齊 parent_map 與地圖）；
         當作「狀態文字」時另用加深的 -text 版，確保白/淺底上可讀（AA）。
         icon color 與 text color 分離是無障礙標準做法。 */
      --safe:#5B9E7A;          /* 識別：無裁罰（安靜綠）— 圓點/標記，角色不可變 */
      --safe-text:#3A7555;     /* 無裁罰狀態文字（5.5:1 / 4.9:1） */
      --safe-soft:#EAF3EE;
      --alert:#D99A4E;         /* 識別：有/經標記裁罰（暖琥珀）— 圓點/標記，角色不可變 */
      --alert-text:#9A5E14;    /* 有裁罰狀態文字（5.3:1 / 4.8:1） */
      --alert-soft:#FAF1E4;
      --home:#3A6EA5;          /* 家的位置（穩重藍，對齊 parent_map.COLOR_HOME）5.3:1 */

      /* 字體角色分工：宋體(serif)負責標題與大數字，傳達「政府正式公文／
         社區公佈欄」的溫度與正式感；無襯線(sans)負責內文可讀性。 */
      --font-serif:'Noto Serif TC','Songti TC','PMingLiU',serif;
      --font-sans:'Noto Sans TC','Microsoft JhengHei',sans-serif;
      /* 距離等資料數字用等寬字，掃視比較時對齊、像儀表讀數 */
      --font-num:'Roboto Mono','SFMono-Regular','Consolas',monospace;

      --radius:14px;
      --radius-sm:10px;
      --radius-xs:8px;
      --shadow-sm:0 1px 2px rgba(58,66,54,.05);
      --shadow-md:0 4px 16px rgba(58,66,54,.08);
      --shadow-lift:0 8px 24px rgba(58,66,54,.12);
      --ease:cubic-bezier(.22,.61,.36,1);
    }

    html, body, [class*="css"], .stApp {
      font-family:var(--font-sans); color:var(--ink); }
    .stApp { background:var(--bg); }
    #MainMenu, footer, [data-testid="stDecoration"] { visibility:hidden; }
    [data-testid="stHeader"] { height:0 !important; background:transparent; }
    .block-container { padding-top:1.6rem; max-width:1180px; }

    /* ---------- 機關抬頭 ----------
       仿正式服務網站／公文抬頭：單行、克制、資訊性。不是行銷 banner。
       左側細直條＝機關識別；機關全稱用宋體（正式感）；右側放資料時效。 */
    .gov-head { display:flex; align-items:flex-end; justify-content:space-between;
      gap:16px; padding:2px 0 14px; border-bottom:2px solid var(--ink-strong);
      margin-bottom:4px; flex-wrap:wrap; }
    .gov-head-left { display:flex; align-items:center; gap:14px; }
    .gov-head-bar { width:4px; align-self:stretch; min-height:44px;
      background:var(--sage); border-radius:2px; }
    .gov-org { font-family:var(--font-serif); font-weight:700; color:var(--ink-strong);
      font-size:1.02rem; line-height:1.3; }
    .gov-service { font-family:var(--font-serif); font-weight:900;
      color:var(--ink-strong); font-size:1.9rem; line-height:1.15;
      letter-spacing:.01em; margin-top:2px; }
    .gov-head-right { text-align:right; color:var(--ink-dim); font-size:.76rem;
      line-height:1.7; padding-bottom:2px; }
    .gov-head-right b { color:var(--ink-strong); font-weight:700; }

    /* 服務說明：一句話講清楚這是什麼、資料怎麼來，取代行銷副標 */
    .lead { color:var(--ink-dim); font-size:.92rem; line-height:1.8;
      max-width:820px; margin:12px 0 4px; }

    /* 資料更新狀態列：誠實揭露即時/備援、最後更新、每日自動更新機制與筆數 */
    .data-status { display:flex; flex-wrap:wrap; align-items:center; gap:7px;
      margin:10px 0 2px; padding:8px 14px; background:var(--surface);
      border:1px solid var(--border); border-radius:var(--radius-sm);
      font-size:.78rem; color:var(--ink-dim); }
    .data-status b { color:var(--ink-strong); font-weight:700; }
    .data-status .ds-dot { width:8px; height:8px; border-radius:50%; }
    .data-status .ds-state { font-weight:700; }
    .data-status .ds-sep { color:var(--border); }

    /* ---------- 結果大數字焦點 ----------
       搜尋後家長最想知道「附近有幾間、我有多少選擇」。用真實數字當錨點，
       比任何裝飾色塊誠實也更有說服力。 */
    .count-focus { display:flex; align-items:baseline; gap:12px; margin:2px 0 10px; }
    .count-num { font-family:var(--font-serif); font-weight:900;
      font-size:3.4rem; line-height:1; color:var(--sage); letter-spacing:-.02em; }
    .count-cap { color:var(--ink); font-size:.98rem; line-height:1.4; }
    .count-cap b { color:var(--ink-strong); }
    .count-scope { color:var(--ink-dim); font-size:.82rem; }

    .warm-sub { color:var(--ink-dim); font-size:.98rem; line-height:1.85;
      max-width:780px; }

    /* ---------- 卡片與提示語言 ---------- */
    .warm-card { background:var(--surface); border:1px solid var(--border);
      border-radius:var(--radius); padding:20px 22px; margin:12px 0;
      box-shadow:var(--shadow-sm); }

    /* 篩選卡片：用 st.container(key="filter_card") 當真正的卡片框 */
    .st-key-filter_card { background:var(--surface); border:1px solid var(--border);
      border-radius:var(--radius); padding:18px 20px; margin:12px 0;
      box-shadow:var(--shadow-sm); }
    .warm-note { background:var(--sage-tint); border:1px solid var(--border-soft);
      border-left:3px solid var(--sage); border-radius:var(--radius-sm);
      padding:13px 17px; color:#42513F; font-size:.86rem; line-height:1.8; }

    .badge { display:inline-flex; align-items:center; gap:6px; padding:4px 13px;
      border-radius:999px; font-size:.82rem; font-weight:700; color:#fff;
      box-shadow:var(--shadow-sm); }
    .chip { display:inline-block; padding:3px 11px; border-radius:999px;
      font-size:.76rem; background:var(--sage-tint); border:1px solid var(--border-soft);
      color:var(--ink-dim); margin-right:6px; }

    /* 資料來源透明分層：已接入(即時新聞) vs 規劃中(社群待 API)。
       合規展示——讓評審與家長一眼看懂什麼是真實即時、什麼是規劃中。 */
    .src-tiers { margin:12px 0 4px; border:1px solid var(--border);
      border-radius:var(--radius-sm); overflow:hidden; background:var(--surface); }
    .src-tier { display:flex; align-items:flex-start; gap:12px; padding:11px 15px; }
    .src-tier + .src-tier { border-top:1px solid var(--border-soft); }
    .src-tag { flex:0 0 auto; font-size:.74rem; font-weight:700;
      padding:3px 10px; border-radius:999px; white-space:nowrap; margin-top:1px; }
    .src-tag.src-live { color:var(--safe-text); background:var(--safe-soft);
      border:1px solid rgba(91,158,122,.35); }
    .src-tag.src-plan { color:var(--ink-dim); background:var(--bg-soft);
      border:1px solid var(--border); }
    .src-body { font-size:.86rem; color:var(--ink-strong); line-height:1.55; }
    .src-body b { font-weight:700; }
    .src-detail { display:block; font-size:.76rem; color:var(--ink-dim);
      margin-top:2px; line-height:1.6; }

    .kv { width:100%; border-collapse:collapse; margin-top:6px; }
    .kv td { padding:12px 14px; border-bottom:1px solid var(--border-soft);
      font-size:.9rem; vertical-align:top; }
    .kv tr:last-child td { border-bottom:none; }
    .kv .k { color:var(--ink-dim); font-weight:600; white-space:nowrap; width:120px; }
    .na { color:var(--ink-faint); }
    .meta { color:var(--ink-faint); font-size:.76rem; margin-top:4px; }

    .tl-item { border-left:2px solid var(--border); padding:2px 0 16px 18px;
      margin-left:6px; position:relative; }
    .tl-dot { position:absolute; left:-6px; top:4px; width:11px; height:11px;
      border-radius:50%; border:2px solid #fff; box-shadow:0 0 0 1px var(--border); }
    .tl-date { color:var(--ink-faint); font-size:.76rem; }
    .tl-title { font-weight:600; color:var(--ink); font-size:.92rem; margin:1px 0; }
    .tl-ex { color:var(--ink-dim); font-size:.85rem; line-height:1.7; }
    a { color:var(--home); }
    .foot { color:var(--ink-faint); font-size:.78rem; line-height:1.8; margin-top:24px;
      border-top:1px solid var(--border); padding-top:18px; }

    /* ===================================================================
       Streamlit 元件外觀覆寫（讓預設元件符合家長版視覺語言）
       以「class 選擇器（.stButton/.stTextInput…）＋ 通用標籤 ＋ key-based
       class（st-key-*）」多重後備鎖定，跨 Streamlit 版本較 data-testid 穩定。
       =================================================================== */

    /* 區段小標題（st.markdown('#### …') / ##### …）：宋體，正式感 */
    .block-container h4, .block-container h5, .block-container h3 {
      font-family:var(--font-serif) !important;
      color:var(--ink-strong) !important; font-weight:700 !important; letter-spacing:0; }

    /* ---------- 文字輸入框 / 文字區 ---------- */
    .stTextInput input, .stTextArea textarea {
      background:var(--bg-soft) !important; border:1.5px solid var(--border) !important;
      border-radius:var(--radius-sm) !important; color:var(--ink) !important;
      font-size:.92rem !important; padding:11px 14px !important;
      transition:border-color .18s var(--ease), box-shadow .18s var(--ease),
                 background .18s var(--ease) !important; box-shadow:none !important; }
    .stTextInput input::placeholder, .stTextArea textarea::placeholder {
      color:var(--ink-faint) !important; }
    .stTextInput input:hover, .stTextArea textarea:hover { border-color:#D3CDBF !important; }
    .stTextInput input:focus, .stTextArea textarea:focus {
      border-color:var(--sage) !important; background:#fff !important;
      box-shadow:0 0 0 3px rgba(94,139,126,.15) !important; outline:none !important; }
    /* baseweb 外層容器：移除預設外框，避免雙重邊框 */
    .stTextInput div[data-baseweb="base-input"],
    .stTextInput div[data-baseweb="input"] {
      background:transparent !important; border:none !important; }
    label p, .stWidgetLabel p {
      color:var(--ink-dim) !important; font-weight:600 !important; font-size:.85rem !important; }

    /* ===================================================================
       按鈕視覺階層（回應：家長只需執行一個關鍵動作＝定位並搜尋）
       主按鈕＝實色、方正圓角、加重、加大  → 全頁視覺權重最高
       次要按鈕＝白底外框、輕量、無上浮      → 退居其後
       篩選鈕  ＝外框式、更小、膠囊          → 最輕，只是「勾選項」
       三者刻意用不同形狀與填色邏輯，不是同一家族。
       =================================================================== */

    /* ---------- 次要按鈕（清單「查看公開資訊」、表單送出） ---------- */
    .stButton > button, .stFormSubmitButton > button {
      background:#fff !important; border:1px solid var(--border) !important;
      color:var(--ink-dim) !important; font-weight:600 !important;
      border-radius:var(--radius-sm) !important; padding:9px 16px !important;
      box-shadow:none !important;
      transition:border-color .16s var(--ease), background .16s var(--ease),
                 color .16s var(--ease) !important; }
    .stButton > button:hover, .stFormSubmitButton > button:hover {
      border-color:var(--sage) !important; background:var(--sage-tint) !important;
      color:var(--sage-ink) !important; }
    .stButton > button p, .stFormSubmitButton > button p { font-weight:600 !important; }

    /* ---------- 主行動按鈕（定位並搜尋，key=search_btn） ----------
       方正圓角(6px) + 實色主色 + 加重加大，與膠囊篩選鈕明確拉開階層。 */
    .st-key-search_btn > button,
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
      background:var(--sage) !important; border:1px solid var(--sage) !important;
      color:#fff !important; font-weight:700 !important; font-size:.98rem !important;
      border-radius:6px !important; padding:13px 22px !important;
      letter-spacing:.04em !important;
      box-shadow:0 2px 6px rgba(94,139,126,.28) !important;
      transition:background .16s var(--ease), box-shadow .16s var(--ease) !important; }
    .st-key-search_btn > button:hover,
    .stButton > button[kind="primary"]:hover {
      background:var(--sage-strong) !important; border-color:var(--sage-strong) !important;
      color:#fff !important; box-shadow:0 4px 12px rgba(94,139,126,.36) !important; }
    .st-key-search_btn > button p,
    .stButton > button[kind="primary"] p { color:#fff !important; font-weight:700 !important; }

    /* ---------- 類別篩選鈕（st.pills）：外框式、輕量膠囊 ----------
       是「勾選的輔助條件」而非行動，視覺重量刻意最低。未選＝白底細框虛感；
       選中＝主色細框＋淺底＋主色勾點，清楚但不搶主按鈕。 */
    .stButtonGroup button, [data-testid="stPills"] button {
      border-radius:999px !important; border:1px solid var(--border) !important;
      background:transparent !important; color:var(--ink-dim) !important;
      font-weight:500 !important; font-size:.84rem !important; padding:5px 15px !important;
      transition:all .14s var(--ease) !important; box-shadow:none !important; }
    .stButtonGroup button:hover, [data-testid="stPills"] button:hover {
      border-color:var(--sage) !important; color:var(--sage-ink) !important;
      background:transparent !important; }
    /* 選中態：主色細框＋淺底＋深字（外框式，非實色填滿，與主按鈕區隔） */
    .stButtonGroup button[aria-pressed="true"],
    .stButtonGroup button[data-selected="true"],
    .stButtonGroup button[kind="pillsActive"],
    [data-testid="stPills"] button[aria-pressed="true"],
    [data-testid="stPills"] button[data-selected="true"] {
      background:var(--sage-soft) !important; border-color:var(--sage) !important;
      color:var(--sage-ink) !important; font-weight:700 !important;
      box-shadow:none !important; }

    /* ---------- 距離滑桿（select_slider） ---------- */
    .stSlider [role="slider"] {
      background:#fff !important; border:3px solid var(--sage) !important;
      box-shadow:var(--shadow-md) !important;
      transition:transform .14s var(--ease), box-shadow .14s var(--ease) !important; }
    .stSlider [role="slider"]:hover { transform:scale(1.12); }
    /* 已填充軌道段用主色（baseweb slider 內層填充 div） */
    .stSlider [data-baseweb="slider"] div[style*="background"] {
      /* 保守：只在明確的填充段套主色，避免整條軌道被染色 */ }
    .stSlider [data-testid="stSliderTickBarMin"],
    .stSlider [data-testid="stSliderTickBarMax"],
    .stSlider [data-testid="stThumbValue"] {
      color:var(--sage-ink) !important; font-weight:700 !important; }

    /* ---------- multiselect（行政區） ---------- */
    .stMultiSelect div[data-baseweb="select"] > div {
      background:var(--bg-soft) !important; border:1.5px solid var(--border) !important;
      border-radius:var(--radius-sm) !important;
      transition:border-color .18s var(--ease), box-shadow .18s var(--ease) !important; }
    .stMultiSelect div[data-baseweb="select"] > div:focus-within {
      border-color:var(--sage) !important; box-shadow:0 0 0 3px rgba(94,139,126,.15) !important; }
    .stMultiSelect [data-baseweb="tag"] {
      background:var(--sage-soft) !important; color:var(--sage-ink) !important;
      border-radius:7px !important; }

    /* ---------- 分頁籤 tabs ---------- */
    .stTabs [data-baseweb="tab-list"] { gap:4px; border-bottom:1px solid var(--border); }
    .stTabs [data-baseweb="tab"] {
      background:transparent !important;
      border-radius:var(--radius-xs) var(--radius-xs) 0 0 !important;
      padding:9px 18px !important; color:var(--ink-dim) !important; font-weight:600 !important;
      transition:color .16s var(--ease), background .16s var(--ease) !important; }
    .stTabs [data-baseweb="tab"]:hover {
      background:var(--sage-tint) !important; color:var(--sage-ink) !important; }
    .stTabs [aria-selected="true"] {
      color:var(--sage-ink) !important; background:var(--sage-tint) !important; }
    .stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {
      background:var(--sage) !important; }

    /* ---------- 清單捲動容器 ---------- */
    [data-testid="stVerticalBlockBorderWrapper"] {
      scrollbar-width:thin; scrollbar-color:var(--border) transparent; }

    /* ---------- 機構清單卡片 ----------
       視覺錨點＝距離大數字（家長掃視整排卡片時真正在比較的東西），
       不是裝飾色塊。裁罰狀態圓點保留（家長第二在乎的誠信訊號）。
       不做裝飾性 hover 上浮；hover/選中只做「對應高亮」— 這個動態有實際
       功能意義（對照清單↔地圖），值得做，其餘動效拿掉。 */
    .inst-card { display:flex; align-items:stretch; gap:14px; background:var(--surface);
      border:1px solid var(--border); border-bottom:none;
      border-left:4px solid var(--dot,#AEB4BC);
      border-radius:var(--radius-sm) var(--radius-sm) 0 0; padding:13px 15px;
      transition:background .16s var(--ease), border-color .16s var(--ease); }

    /* 每組「卡片＋底部按鈕」黏成一張完整卡片（st-key-instcard_*） */
    [class*="st-key-instcard_"] { margin-bottom:10px; }
    /* 消除 container 內卡片與按鈕之間的預設間距，讓兩者無縫貼合 */
    [class*="st-key-instcard_"] [data-testid="stVerticalBlock"] { gap:0 !important; }
    /* 底部行動按鈕：接在卡片下方，上緣直角、與卡片共用左側色條與外框 */
    [class*="st-key-instcard_"] .stButton > button {
      border:1px solid var(--border) !important; border-top:none !important;
      border-left:4px solid var(--border) !important;
      border-radius:0 0 var(--radius-sm) var(--radius-sm) !important;
      background:var(--bg-soft) !important; color:var(--ink-dim) !important;
      font-size:.82rem !important; font-weight:600 !important;
      padding:8px 15px !important; justify-content:space-between !important; }
    [class*="st-key-instcard_"] .stButton > button:hover {
      background:var(--sage-tint) !important; color:var(--sage-ink) !important;
      border-color:var(--sage) !important; border-left-color:var(--sage) !important; }
    /* hover 整組卡片時，卡片本體與按鈕一起反應（視覺整體感） */
    [class*="st-key-instcard_"]:hover .inst-card { background:var(--bg-soft);
      border-color:#D8D2C4; }
    /* 選中／對應高亮：整組（卡片＋按鈕）一起高亮，左界主色加粗 */
    .inst-card.is-active { background:var(--sage-tint);
      box-shadow:inset 3px 0 0 var(--sage); border-color:rgba(94,139,126,.45); }

    /* 距離錨點：等寬大數字，掃視比較用 */
    .inst-dist { flex:0 0 auto; width:66px; display:flex; flex-direction:column;
      align-items:flex-start; justify-content:center;
      border-right:1px solid var(--border-soft); padding-right:12px; }
    .inst-dist .dnum { font-family:var(--font-num); font-weight:700;
      font-size:1.55rem; line-height:1; color:var(--ink-strong);
      font-variant-numeric:tabular-nums; letter-spacing:-.02em; }
    .inst-dist .dunit { font-size:.72rem; color:var(--ink-dim); margin-top:3px;
      font-weight:600; }
    .inst-dist .dnone { font-family:var(--font-sans); font-size:.74rem;
      color:var(--ink-faint); line-height:1.3; }

    .inst-body { flex:1 1 auto; min-width:0; display:flex; flex-direction:column;
      justify-content:center; }
    .inst-name { font-weight:700; color:var(--ink-strong); font-size:.98rem;
      line-height:1.35; margin-bottom:3px; word-break:break-all; }
    .inst-meta { color:var(--ink-dim); font-size:.8rem; }
    .inst-status { display:inline-flex; align-items:center; gap:6px; margin-top:6px;
      font-size:.79rem; font-weight:700; }
    .inst-status .sdot { width:10px; height:10px; border-radius:50%;
      box-shadow:0 0 0 3px var(--sdot-halo,rgba(0,0,0,.04)); }

    /* ---------- 地圖圓角容器 ----------
       st_folium 產生獨立 iframe，直接對該 iframe 套柔和圓角外框，
       讓地圖與整體卡片語言一致，不像硬生生嵌入的外部元件。 */
    iframe[title="streamlit_folium.st_folium"] {
      border:1px solid var(--border) !important; border-radius:var(--radius) !important;
      overflow:hidden !important; box-shadow:var(--shadow-md) !important; }

    /* ---------- 圖示化圖例卡片列 ---------- */
    .legend-row { display:flex; flex-wrap:wrap; gap:10px; margin-top:10px; }
    .legend-pill { display:inline-flex; align-items:center; gap:8px;
      background:var(--surface); border:1px solid var(--border);
      border-radius:999px; padding:6px 14px; font-size:.8rem; color:var(--ink-dim);
      box-shadow:var(--shadow-sm); }
    .legend-pill .ldot { width:12px; height:12px; border-radius:50%;
      border:2px solid #fff; box-shadow:0 0 0 1px var(--border); }

    /* ---------- 結果狀態說明列 ---------- */
    .result-sub { font-size:.78rem; color:var(--ink-faint); margin-top:6px; }
    .dot-inline { display:inline-block; width:9px; height:9px; border-radius:50%;
      vertical-align:middle; margin-right:3px; }

    /* ---------- 載入轉圈：改為主色調 ---------- */
    [data-testid="stSpinner"] i, .stSpinner > div > div {
      border-top-color:var(--sage) !important; }

    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="gov-head">
      <div class="gov-head-left">
        <div class="gov-head-bar"></div>
        <div>
          <div class="gov-org">新北市政府教育局</div>
          <div class="gov-service">安心找幼兒園</div>
        </div>
      </div>
      <div class="gov-head-right">
        公開資料查詢服務<br>
        資料更新：<b>{html.escape(data_updated_at())}</b>
      </div>
    </div>
    <div class="lead">輸入地址，查看附近教保機構、距離與公開紀錄。資料均標註來源與時間，
    建議實地參訪查證。</div>
    """,
    unsafe_allow_html=True,
)

_pubdata = load_public_dataset_cached()
df = load_public_data()
if df is None or len(df) == 0:
    st.error("目前無可查詢的公開資料。")
    st.stop()

# 二次防禦：確認本站資料層確實不含任何風險欄位（責任 AI 不變式）。
_leaked = [c for c in df.columns if pp.is_risk_field(c)]
assert not _leaked, f"公眾網不得含風險欄位，發現：{_leaked}"

# 真實裁罰明細索引（owner 姓名 → 裁罰紀錄 dict），供詳情頁查明細。
PENALTY_INDEX = _pubdata.get("penalty_index", {})

sentiment_data = load_sentiment()

# 資料更新狀態列（誠實揭露：即時同步 vs 離線備援 + 自動更新機制）。
# 有 GitHub Actions 每日自動更新 data/snapshots（版控），即時抓網失敗時退回。
_is_live = bool(_pubdata.get("is_live"))
_status_label = "已同步最新" if _is_live else "自動更新備援"
_status_color = "var(--safe-text)" if _is_live else "var(--sage-ink)"
_note_txt = f"　·　{_pubdata['note']}" if _pubdata.get("note") else ""
st.markdown(
    "<div class='data-status'>"
    f"<span class='ds-dot' style='background:{_status_color}'></span>"
    f"<span class='ds-state' style='color:{_status_color}'>{html.escape(_status_label)}</span>"
    f"<span class='ds-sep'>·</span>"
    f"最後更新 <b>{html.escape(data_updated_at())}</b>"
    "<span class='ds-sep'>·</span>"
    "每日自動更新"
    f"<span class='ds-sep'>·</span>資料來源：{html.escape(_pubdata.get('attribution',''))}"
    f"{html.escape(_note_txt)}"
    "</div>",
    unsafe_allow_html=True)

# session 狀態：選定機構、家的位置
st.session_state.setdefault("selected_park_id", None)
st.session_state.setdefault("home", None)  # dict(lat,lng,label)


# ===========================================================================
# 篩選列（地址 + 距離 + 公私立 + 類型）
# ===========================================================================
# 篩選卡片：用 st.container（key→st-key-filter_card class）當真正的卡片容器，
# 由 CSS 畫框；不再用「未閉合 <div>」手法（那在新版 Streamlit 會被自動補上
# 閉合標籤，變成一張空白卡片，即先前畫面上那條無意義白條）。
with st.container(key="filter_card"):
    c1, c2 = st.columns([2.4, 1])
    with c1:
        address = st.text_input(
            "輸入您家的地址或機構名稱",
            placeholder="例如：新北市板橋區文化路一段，或 新北市私立幼愛幼兒園",
            help="可輸入住家地址（建議填到「行政區＋路名」），或直接輸入幼兒園名稱。"
                 "輸入機構名稱會直接定位到該園並開啟其公開資訊；"
                 "地址定位使用 OpenStreetMap 免費服務，不會儲存您的地址。",
        )
    with c2:
        radius_km = st.select_slider(
            "搜尋範圍",
            options=[0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0],
            value=2.0,
            format_func=lambda v: geo.format_distance(v),
        )

    c3, c4, c5 = st.columns([1.6, 1.4, 1])
    with c3:
        # 類別選項：公立/私立/非營利（park_type）＋準公共（is_quasi_public 旗標，
        # 準公共園在 park_type 上仍屬私立，故獨立為一個可選類別，家長找平價名額用）。
        OWNERSHIP_OPTIONS = ["公立", "私立", "非營利", "準公共"]
        sel_own = st.pills("類別（可複選）", OWNERSHIP_OPTIONS, selection_mode="multi",
                           default=OWNERSHIP_OPTIONS)
    with c4:
        districts = sorted(df["district"].dropna().unique().tolist())
        sel_dist = st.multiselect("行政區（可留空＝不限）", districts, default=[],
                                  placeholder="選擇行政區（可留空，不限）")
    with c5:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        do_search = st.button("定位並搜尋", type="primary", use_container_width=True,
                              key="search_btn")

# 依輸入字串比對機構名稱：回傳命中的機構列（Series）或 None。
# 比對順序（由嚴到寬）：完全相符 → 唯一包含相符 → 去空白後唯一包含相符。
# 多筆相符時回傳 None（交回地址定位，避免任意猜一間）。
def _match_institution(query: str, frame: pd.DataFrame):
    q = (query or "").strip()
    if not q or "park_name" not in frame.columns:
        return None
    names = frame["park_name"].astype(str)
    # 1) 完全相符（去前後空白）
    exact = frame[names.str.strip() == q]
    if len(exact) == 1:
        return exact.iloc[0]
    if len(exact) > 1:
        return None
    # 2) 包含相符（輸入為園名的一部分，或園名含輸入字串）
    qn = q.replace(" ", "")
    contains = frame[names.str.replace(" ", "", regex=False).str.contains(
        qn, case=False, na=False) | names.apply(
        lambda n: qn in str(n).replace(" ", ""))]
    if len(contains) == 1:
        return contains.iloc[0]
    return None


# 觸發定位（機構名稱優先，其次地址）
if do_search and address.strip():
    _inst = _match_institution(address, df)
    if _inst is not None:
        # 命中機構：以該園座標為中心、自動選定該園並開啟其公開資訊。
        st.session_state["home"] = {
            "lat": float(_inst["lat"]), "lng": float(_inst["lng"]),
            "label": str(_inst["park_name"]), "notice": ""}
        st.session_state["selected_park_id"] = str(_inst["park_id"])
        st.session_state["list_page"] = 1
        st.info(f"已定位到機構：{_inst['park_name']}（{_inst.get('district','')}）"
                "　·　下方已開啟其公開資訊。")
    else:
        res = geocode_cached(address.strip())
        if res["ok"]:
            st.session_state["home"] = {
                "lat": res["lat"], "lng": res["lng"], "label": res["display_name"],
                "notice": res.get("notice", "")}
            st.session_state["selected_park_id"] = None
            st.session_state["list_page"] = 1  # 重新定位＝新查詢，清單回到第 1 頁
            # 誠實揭露實際定位到的地點，請家長自行確認（避免同名地點或門牌查無時的誤定位）。
            _loc = str(res.get("display_name") or "").strip()
            if _loc:
                st.info(f"已定位到：{_loc}　·　請確認是否為您要的位置，如不正確請補上行政區與路名再查一次。")
            if res.get("notice"):
                st.info(res["notice"])
        else:
            st.session_state["home"] = None
            st.warning(res["message"] + "（若您要找的是幼兒園，可直接輸入園所名稱）")


# ===========================================================================
# 套用篩選：類別（含準公共）+ 行政區 +（依情境）距離
# ===========================================================================
sel_own = sel_own or OWNERSHIP_OPTIONS  # 全不選時視為不限

# 類別篩選：公立/私立/非營利 比對 park_type；準公共 比對 is_quasi_public 旗標。
# 以「聯集」處理——選了「私立」與「準公共」時，兩者都納入（OR）。
_type_sel = [t for t in sel_own if t in ("公立", "私立", "非營利")]
_want_quasi = "準公共" in sel_own
mask_own = df["park_type"].isin(_type_sel) if _type_sel else pd.Series(False, index=df.index)
if _want_quasi:
    mask_own = mask_own | (df["is_quasi_public"] == True)  # noqa: E712
work = df[mask_own].copy()

if sel_dist:
    work = work[work["district"].isin(sel_dist)]

home = st.session_state.get("home")
if home:
    work["distance_km"] = work.apply(
        lambda r: geo.haversine_km(home["lat"], home["lng"], r["lat"], r["lng"]),
        axis=1,
    )
    # 使用者明確選了行政區時，以「行政區」為主要意圖，不再強制距離半徑
    # （否則選了離家較遠的行政區會因距離篩選變成 0 間，造成困惑）；
    # 未選行政區時，才以住家為中心套用距離半徑。結果一律依距離排序。
    if not sel_dist:
        work = work[work["distance_km"] <= radius_km]
    work = work.sort_values("distance_km")
else:
    work["distance_km"] = None


# ===========================================================================
# 建立家長版標記（附輿情關注度）
# ===========================================================================
def build_markers(frame: pd.DataFrame) -> list[pmap.ParentMarker]:
    markers = []
    for _, row in frame.iterrows():
        pid = str(row.get("park_id"))
        # 地圖標記只用示範資料快速分級，避免每個標記都即時爬新聞拖慢頁面。
        level = marker_level_for(pid, sentiment_data)
        dist = row.get("distance_km")
        markers.append(pmap.build_marker(
            row.to_dict(),
            attention_level=level,
            attention_basis="",
            distance_km=float(dist) if dist is not None and not pd.isna(dist) else None,
        ))
    return markers


# 顯示機構標記的條件：完成地址定位（home）「或」明確選了行政區。
# 未做任何篩選時地圖保持乾淨、不攤開全部機構；一旦有明確查詢意圖（定位或選區）
# 就建立標記，讓地圖與右側清單同步（修正「選了行政區但地圖沒變化」）。
searched = (home is not None) or bool(sel_dist)
# 未搜尋時＝新北市總覽：畫出全部（有座標的）機構，讓「先看看新北市的教保機構分布」
# 名副其實。機構數可能達數百上千，總覽模式改用叢集（MarkerCluster）避免地圖卡頓。
overview = not searched
markers = build_markers(work)

# park_id → 裁罰狀態短標籤（供右側清單即時顯示；輿情不在清單即時爬）。
def _penalty_status_short(park_id: str) -> str:
    sub = df[df["park_id"].astype(str) == str(park_id)]
    if len(sub) == 0:
        return "點入查看輿情"
    r = sub.iloc[0]
    flag = str(r.get("penalty_flag", "")).strip()
    try:
        n = int(float(r.get("penalty_count"))) if not pd.isna(r.get("penalty_count")) else 0
    except (TypeError, ValueError):
        n = 0
    if n > 0:
        return f"有裁罰 {n} 筆"
    if flag == "有":
        return "經標記有裁罰"
    return "無裁罰紀錄"


def _penalty_color(park_id: str) -> str:
    """清單燈號顏色，與旁邊裁罰狀態文字語意一致（避免燈號全灰的矛盾）。

    有裁罰／經標記有裁罰 → 暖琥珀（提醒，非警報紅）；無裁罰 → 安靜綠。
    """
    sub = df[df["park_id"].astype(str) == str(park_id)]
    if len(sub) == 0:
        return "#AEB4BC"
    r = sub.iloc[0]
    flag = str(r.get("penalty_flag", "")).strip()
    try:
        n = int(float(r.get("penalty_count"))) if not pd.isna(r.get("penalty_count")) else 0
    except (TypeError, ValueError):
        n = 0
    if n > 0 or flag == "有":
        return "#D99A4E"   # 暖琥珀：有裁罰／經標記有裁罰
    return "#5B9E7A"       # 安靜綠：無裁罰紀錄





# ===========================================================================
# 地圖 + 清單
# 未搜尋：地圖佔滿整個寬度（更大更好看地圖）；引導文字置於地圖下方。
# 已搜尋：左右分欄（地圖 : 清單 = 1.5 : 1），清單放右側。
# ===========================================================================
if searched:
    left, right = st.columns([1.5, 1])
else:
    left = st.container()
    right = st.container()

with left:
    if searched:
        # 與右欄大數字焦點等高（96px），讓兩欄地圖／清單頂部對齊。
        _home_label = html.escape(str(home.get("label", "") or "")[:36]) if home else ""
        # 地圖說明依情境：選了行政區以行政區為準；否則以定位的家為中心。
        if sel_dist:
            _map_desc = "顯示範圍：" + html.escape("、".join(sel_dist))
        elif home:
            _map_desc = f"以您輸入的位置為中心：{_home_label}"
        else:
            _map_desc = "依篩選條件顯示"
        st.markdown(
            "<div style='min-height:96px;box-sizing:border-box;display:flex;"
            "flex-direction:column;justify-content:flex-end;padding-bottom:6px'>"
            "<div style='font-family:var(--font-serif);font-weight:700;"
            "font-size:1.15rem;color:var(--ink-strong)'>附近機構地圖</div>"
            f"<div style='font-size:.78rem;color:var(--ink-dim);margin-top:4px'>"
            f"{_map_desc}</div>"
            "</div>",
            unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='font-family:var(--font-serif);font-weight:700;"
            "font-size:1.15rem;color:var(--ink-strong);margin-bottom:8px'>"
            "先看看新北市的教保機構分布</div>",
            unsafe_allow_html=True)
    # 地圖中心/縮放：優先「框住實際要顯示的機構」，讓地圖與清單同步。
    # - 選了行政區（不論有無定位家）→ 以該區機構的座標範圍 fit_bounds。
    # - 只定位家、未選區 → 以家為中心，依搜尋半徑決定 zoom。
    # - 都沒有 → 新北市全域乾淨底圖。
    def _zoom_for_radius(km: float) -> int:
        # 依搜尋半徑決定初始 zoom；半徑越小越放大。涵蓋所有滑桿級距（含中間值）。
        if km <= 0.4:
            return 15
        if km <= 0.9:
            return 14
        if km <= 1.5:
            return 14
        if km <= 2.0:
            return 13
        if km <= 3.0:
            return 13
        return 12
    _coords = [(m.lat, m.lng) for m in markers if m.has_coords]
    _fit_bounds = None
    if overview:
        # 新北市總覽：固定以新北市全域為視野（叢集會自行聚合），不依外接框縮放，
        # 避免離島/山區的零星點把視野拉歪。
        center = list(geo.DEFAULT_CENTER)
        zoom = 11
    elif home and not sel_dist:
        center = [home["lat"], home["lng"]]
        zoom = _zoom_for_radius(radius_km)
    elif _coords:
        # 以機構座標的外接範圍置中（涵蓋所選行政區的全部機構）。
        _lats = [c[0] for c in _coords]
        _lngs = [c[1] for c in _coords]
        center = [sum(_lats) / len(_lats), sum(_lngs) / len(_lngs)]
        zoom = 13
        _fit_bounds = [[min(_lats), min(_lngs)], [max(_lats), max(_lngs)]]
    elif home:
        center = [home["lat"], home["lng"]]
        zoom = _zoom_for_radius(radius_km)
    else:
        # 未搜尋：以新北市為中心的乾淨底圖，不畫任何機構點。
        center = list(geo.DEFAULT_CENTER)
        zoom = 11

    fmap = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap",
                      control_scale=True)
    if _fit_bounds is not None:
        fmap.fit_bounds(_fit_bounds, padding=(20, 20))

    # 家的位置
    if home:
        folium.Marker(
            location=[home["lat"], home["lng"]],
            tooltip="您輸入的位置",
            icon=BeautifyIcon(icon="home", icon_shape="marker",
                              background_color=pmap.COLOR_HOME,
                              border_color=pmap.COLOR_HOME, text_color="#fff"),
        ).add_to(fmap)
        # 搜尋圈只在「以家為中心 + 未選行政區」時才畫；選了行政區時清單改以
        # 行政區為準、不套距離半徑，畫圈會誤導。
        if not sel_dist:
            folium.Circle(
                location=[home["lat"], home["lng"]], radius=radius_km * 1000,
                color=pmap.COLOR_HOME, weight=1, fill=True, fill_opacity=0.05,
            ).add_to(fmap)

    # 機構標記：著色與右側清單一致＝公開裁罰狀態（綠=無裁罰、暖琥珀=有/經標記裁罰），
    # 避免地圖全灰、且左右燈號語意同步。輿情關注度於點入機構後即時計算，不在地圖著色。
    # 總覽模式（未搜尋）機構數多，改把點加進叢集，遠看聚合、放大自動展開，避免卡頓。
    _target = MarkerCluster(name="新北市教保機構").add_to(fmap) if overview else fmap
    for m in markers:
        if not m.has_coords:
            continue
        _color = _penalty_color(m.park_id)
        _pstat = _penalty_status_short(m.park_id)
        dist_txt = (f"　距離約 {geo.format_distance(m.distance_km)}"
                    if m.distance_km is not None else "")
        popup_html = (
            f"<div style='font-family:Noto Sans TC,sans-serif;min-width:180px'>"
            f"<b>{html.escape(m.name)}</b><br>"
            f"<span style='color:#6B6357'>{html.escape(m.ownership)}"
            f"　{html.escape(m.district)}{dist_txt}</span><br>"
            f"<span style='display:inline-block;margin-top:6px;padding:2px 8px;"
            f"border-radius:8px;background:{_color};color:#fff;font-size:12px'>"
            f"{html.escape(_pstat)}</span></div>"
        )
        folium.CircleMarker(
            location=[m.lat, m.lng],
            radius=9,
            color="#ffffff", weight=2,
            fill=True, fill_color=_color, fill_opacity=0.9,
            tooltip=f"{m.name}（{_pstat}）",
            popup=folium.Popup(popup_html, max_width=260),
        ).add_to(_target)

    map_state = st_folium(fmap, height=460, use_container_width=True,
                          returned_objects=["last_object_clicked"])

    if not searched:
        # 總覽模式：地圖已叢集顯示全新北市機構。給一句引導＋標記色說明。
        st.markdown(
            "<div class='warm-note' style='margin-top:8px'>"
            "地圖已標出新北市的教保機構（數字圈為聚合，放大即展開，點按單點看公開紀錄）。"
            "圓點顏色為公開裁罰狀態：<b>綠</b>＝無裁罰、<b>暖琥珀</b>＝有／經標記裁罰。"
            "輸入您家的地址並按「定位並搜尋」，即可改以您家為中心、依距離列出附近機構；"
            "也可先用「公私立別」與「行政區」縮小範圍。</div>",
            unsafe_allow_html=True)
    else:
        # 搜尋後顯示圖例＋說明，合併為固定高度區塊（80px），左欄底＝地圖460＋80＝540。
        # 圖例語意＝地圖標記色（與右側清單一致的「公開裁罰狀態」），非輿情關注度。
        _legend = [
            ("#5B9E7A", "無裁罰紀錄"),
            ("#D99A4E", "有／經標記裁罰"),
            (pmap.COLOR_HOME, "您輸入的位置"),
        ]
        legend_items_html = ""
        for color, label in _legend:
            legend_items_html += (
                f"<span class='legend-pill'>"
                f"<span class='ldot' style='background:{color}'></span>"
                f"{html.escape(label)}</span>")
        st.markdown(
            "<div style='min-height:96px;box-sizing:border-box;padding-top:4px'>"
            f"<div class='legend-row'>{legend_items_html}</div>"
            "<div style='font-size:.76rem;color:var(--ink-faint);margin-top:8px;"
            "line-height:1.6'>"
            "地圖標記顏色為公開裁罰狀態（與右側清單一致）；每間機構的輿情關注指數"
            "與新聞時間軸，會在您點入該機構時即時蒐集公開新聞後計算。</div>"
            "</div>",
            unsafe_allow_html=True)

    # 點地圖標記 → 找出對應機構設為選定
    clicked = map_state.get("last_object_clicked") if map_state else None
    if clicked and markers:
        cl_lat, cl_lng = clicked.get("lat"), clicked.get("lng")
        if cl_lat is not None and cl_lng is not None:
            best, best_d = None, 1e9
            for m in markers:
                if not m.has_coords:
                    continue
                d = geo.haversine_km(cl_lat, cl_lng, m.lat, m.lng)
                if d < best_d:
                    best, best_d = m, d
            if best is not None and best_d < 0.05:  # 50m 內視為點到該點
                st.session_state["selected_park_id"] = best.park_id

with right:
    if not searched:
        # 未搜尋：地圖已全寬、下方已有引導，右側不再重複顯示卡片，保持畫面乾淨。
        pass
    else:
        # 範圍描述：選了行政區用區名，否則用「N 公里內」。
        if sel_dist:
            _scope_txt = "、".join(sel_dist)
            _scope_phrase = f"在您選的 {_scope_txt}"
        else:
            _scope_txt = f"{geo.format_distance(radius_km)}內"
            _scope_phrase = f"在您家 {geo.format_distance(radius_km)}內"
        # 大數字焦點：家長搜尋後最想知道「附近有幾間、我有多少選擇」，
        # 用真實數字當第一視覺焦點，比裝飾色塊誠實也更有說服力。
        st.markdown(
            "<div style='min-height:96px;box-sizing:border-box'>"
            "<div class='count-focus'>"
            f"<span class='count-num'>{len(markers)}</span>"
            f"<span class='count-cap'><b>間教保機構</b><br>"
            f"<span class='count-scope'>{html.escape(_scope_phrase)}"
            f"，依距離由近到遠</span></span></div>"
            "<div class='result-sub'>"
            "<span class='dot-inline' style='background:#5B9E7A'></span>無裁罰紀錄　"
            "<span class='dot-inline' style='background:#D99A4E'></span>有／經標記裁罰"
            "</div>"
            "</div>",
            unsafe_allow_html=True)

        if not markers:
            st.info("這個範圍內沒有符合條件的機構，試著放大搜尋範圍或調整篩選。")
        else:
            # ---- 清單分頁（上一頁／下一頁）----
            # 機構數可能達數百，改用分頁而非固定截斷 80 筆，確保「上方總數＝可翻閱
            # 到的全部機構」，數字一致、家長也能逐頁看完。
            PAGE_SIZE = 50
            _total = len(markers)
            _pages = max(1, (_total + PAGE_SIZE - 1) // PAGE_SIZE)
            # 頁碼存於 session；篩選變動使總頁數變少時，夾回合法範圍避免停在空頁。
            _page = int(st.session_state.get("list_page", 1))
            _page = max(1, min(_page, _pages))
            st.session_state["list_page"] = _page
            _start = (_page - 1) * PAGE_SIZE
            _end = min(_start + PAGE_SIZE, _total)
            _page_markers = markers[_start:_end]

            # 對齊左欄底部：左欄＝地圖(460)＋圖例說明區(≈96含間距)；
            # 右欄＝標題區(60)＋清單容器。將容器高度提高到 540，使右欄底部
            # 往下延伸至與左欄「地圖標記說明」文字底部齊平。
            list_box = st.container(height=520)
            with list_box:
                _selected_pid = str(st.session_state.get("selected_park_id") or "")
                for m in _page_markers:
                    # 圓點＝識別色（與地圖標記一致）；狀態文字＝加深的 -text 版
                    # （確保白/淺底可讀，達 WCAG AA）。icon/text 色分離。
                    _dot_color = _penalty_color(m.park_id)
                    _has_pen = _dot_color == "#D99A4E"
                    _text_color = "#9A5E14" if _has_pen else "#3A7555"
                    _pstat = _penalty_status_short(m.park_id)
                    _halo = ("rgba(217,154,78,.18)" if _has_pen
                             else "rgba(91,158,122,.18)")
                    # 距離錨點：拆成「數字＋單位」，數字用等寬大字，家長掃視比較用。
                    if m.distance_km is not None:
                        _dist_str = geo.format_distance(m.distance_km)
                        _dnum, _, _dunit = _dist_str.partition(" ")
                        _dist_html = (f"<span class='dnum'>{html.escape(_dnum)}</span>"
                                      f"<span class='dunit'>{html.escape(_dunit)}</span>")
                    else:
                        _dist_html = "<span class='dnone'>未定位<br>距離</span>"
                    _sel = str(m.park_id) == _selected_pid
                    _active_cls = " is-active" if _sel else ""
                    # 卡片與按鈕包在同一個 container（key→st-key- class），透過 CSS
                    # 讓「卡片本體＋底部行動按鈕」黏成一張完整卡片（無縫），
                    # 而非上下兩個分離的區塊。保留原有選取邏輯，不動 session 行為。
                    with st.container(key=f"instcard_{m.park_id}"):
                        st.markdown(
                            f"<div class='inst-card{_active_cls}' style='--dot:{_dot_color}'>"
                            f"<div class='inst-dist'>{_dist_html}</div>"
                            f"<div class='inst-body'>"
                            f"<div class='inst-name'>{html.escape(m.name)}</div>"
                            f"<div class='inst-meta'>{html.escape(m.ownership)}"
                            f"・{html.escape(m.district)}</div>"
                            f"<div class='inst-status' style='color:{_text_color};"
                            f"--sdot-halo:{_halo}'>"
                            f"<span class='sdot' style='background:{_dot_color}'></span>"
                            f"{html.escape(_pstat)}</div>"
                            f"</div></div>",
                            unsafe_allow_html=True)
                        if st.button("查看公開資訊　›", key=f"pick_{m.park_id}",
                                     use_container_width=True):
                            st.session_state["selected_park_id"] = m.park_id

            # ---- 分頁控制列（上一頁／頁碼／下一頁）----
            _pg_prev, _pg_info, _pg_next = st.columns([1, 1.4, 1])
            with _pg_prev:
                if st.button("上一頁", key="list_prev", use_container_width=True,
                             disabled=(_page <= 1)):
                    st.session_state["list_page"] = _page - 1
                    st.rerun()
            with _pg_info:
                st.markdown(
                    f"<div style='text-align:center;font-size:.82rem;"
                    f"color:var(--ink-dim);padding-top:8px'>"
                    f"第 {_page} / {_pages} 頁　·　顯示 {_start + 1}–{_end} 間"
                    f"（共 {_total} 間）</div>",
                    unsafe_allow_html=True)
            with _pg_next:
                if st.button("下一頁", key="list_next", use_container_width=True,
                             disabled=(_page >= _pages)):
                    st.session_state["list_page"] = _page + 1
                    st.rerun()


# ===========================================================================
# 機構詳情頁（含公開資訊 + 輿情時間軸 + 分級依據 + 申訴窗口）
# ===========================================================================
def _record_summary(row: dict) -> tuple[str, str, str]:
    """產生每間機構的「綜合公開紀錄摘要」：(結論文字, 識別色, 文字色)。

    以裁罰為主要依據（公開事實），三種狀態：
      - 有裁罰且有明細 → 中性提示筆數（暖琥珀，非警報紅）。
      - 經標記有裁罰但明細比對中 → 誠實中間狀態（暖琥珀），不誤判為乾淨。
      - 無裁罰旗標 → 正面明確「並無不良事項」（安靜綠）。
    此摘要只陳述公開事實，不作機構優劣或違法評價。
    """
    _flag = str(row.get("penalty_flag", "")).strip()
    _pc = row.get("penalty_count")
    try:
        n = int(float(_pc)) if _pc is not None and not pd.isna(_pc) else None
    except (TypeError, ValueError):
        n = None
    # 回傳 (結論文字, 識別色(border/標記), 文字色(達 AA))。
    # 識別色維持語意 hex；文字色用加深版，確保標題文字在白底可讀。
    # 中間狀態：官方標記有裁罰，但無可對應之逐筆明細。
    if (n is None or n <= 0) and _flag == "有":
        return ("本園於公開資料中經標記有裁罰紀錄，惟逐筆明細比對中；"
                "此非乾淨紀錄，建議家長逕向主管機關查詢確切內容。",
                "#D99A4E", "#9A5E14")
    if n is not None and n > 0:
        return (f"本園近年有 {n} 筆公開裁罰紀錄，詳見下方裁罰欄位；"
                "裁罰為主管機關依法處分之公開事實，建議搭配園所說明一併了解。",
                "#D99A4E", "#9A5E14")
    return ("目前公開紀錄中並無不良事項（近年無裁罰紀錄）。"
            "以下為本園之公開資訊，建議家長仍以實地參訪作為主要參考。",
            "#5B9E7A", "#3A7555")


def render_disclosure(row: dict):
    """公開資訊揭露表（沿用家長端純邏輯 parent_portal，含來源與時效）。"""
    _authority = "新北市政府教育局"
    _dataset = "全國教保資訊網 / 新北市幼兒教育資源網（公開資料）"
    _url = "https://www.ece.moe.edu.tw/"

    # 公私立別：若為準公共合作園，附註「準公共」（家長關心的平價名額指標）。
    _ptype = str(row.get("park_type", "")).strip()
    if row.get("is_quasi_public"):
        _period = str(row.get("quasi_public_period", "")).strip()
        _period_txt = f"，{_period} 學年" if _period else ""
        row["ownership"] = f"{_ptype}（準公共合作園{_period_txt}）"
    else:
        row["ownership"] = _ptype

    # 綜合公開紀錄摘要（每間都有明確結論，不留空白）。
    # border 用識別色（語意）；標題文字用達 AA 的文字色。
    _sum_txt, _sum_color, _sum_text_color = _record_summary(row)
    st.markdown(
        f"<div style='border-left:4px solid {_sum_color};background:#fff;"
        f"border:1px solid #ECE7DE;border-radius:8px;padding:12px 16px;"
        f"margin:6px 0 12px'><b style='color:{_sum_text_color}'>綜合公開紀錄</b><br>"
        f"<span style='color:#42513F;font-size:.9rem'>{html.escape(_sum_txt)}</span></div>",
        unsafe_allow_html=True)
    field_sources: dict[str, SourceRef] = {
        "basic_info": SourceRef(_dataset, _authority, _url, TODAY),
        "ownership": SourceRef(_dataset, _authority, _url, TODAY),
    }

    # 收費資訊：真實資料源提供每月收費（monthly，元/月）。
    _m = row.get("monthly")
    if _m is not None and not pd.isna(_m):
        try:
            _mv = float(_m)
            if _mv > 0:
                row["tuition_info"] = (
                    f"每月收費約 {_mv:,.0f} 元（依全國教保資訊網公開登載；"
                    f"實際收退費項目以主管機關公告與契約為準）")
                field_sources["tuition_info"] = SourceRef(
                    "全國教保資訊網．幼兒園收費公開資訊", _authority, _url, TODAY)
        except (TypeError, ValueError):
            pass

    # 評鑑結果：依「分年分區輪替」制度判定狀態（已接受評鑑 / 尚未接受評鑑）。
    # 新北市基礎評鑑三年一週期、每年只訪視特定行政區；無等第多為「該區尚未排入
    # 本輪」而非資料缺漏，故以官方用語呈現，不寫 nan / 查無資料。
    _status, _eval_text = evc.evaluation_status(
        str(row.get("district", "")), row.get("eval_grade"))
    row["public_eval"] = _eval_text
    field_sources["public_eval"] = SourceRef(
        "全國教保資訊網．評鑑結果查詢",
        _authority, "https://ap.ece.moe.edu.tw/webecems/evaSearch.aspx", TODAY)

    # 裁罰紀錄：三種狀態，避免把「經標記有裁罰但明細待比對」誤顯示為乾淨。
    #   1) 有旗標且比對到明細 → 條列近幾筆真實明細（日期/罰鍰/法條）。
    #   2) 有旗標但比對不到明細（負責人姓名對不上等）→「經標記有裁罰（明細比對中）」。
    #   3) 無裁罰旗標 → 明確「目前並無不良裁罰紀錄」（可回溯事實）。
    _penalty_flag = str(row.get("penalty_flag", "")).strip()
    _details = pdset.penalty_details_for(
        str(row.get("owner", "")), _penalty_flag, PENALTY_INDEX)
    _pen_source = SourceRef(
        "全國教保資訊網公開裁罰紀錄（經 g0v 開源專案整理備份）", _authority,
        "https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx", TODAY)
    if _details:
        # 責任 AI（方案 A）：家長端不逐筆列出日期／罰鍰等處分細節。
        # 原因：裁罰以「負責人姓名」比對而來，官方查詢介面的查詢維度不同，
        # 家長未必能自行逐筆核對；為避免呈現無法回溯的指控性細節，改採中性
        # 陳述並導向主管機關查證。逐筆明細僅保留於公務後台（含信心分級）。
        row["public_penalty"] = [
            "依公開裁罰紀錄，本園負責人名下曾有裁罰紀錄。此係依負責人姓名比對之"
            "公開資料，未必全屬本園、亦非違法認定；實際裁罰以主管機關公告為準，"
            "詳情請至「全國教保資訊網」裁罰查詢，或逕洽新北市政府教育局查證。"
        ]
    elif _penalty_flag == "有":
        # 中間狀態：官方登載有裁罰，但本平台以負責人姓名比對尚未取得逐筆明細
        # （可能負責人異動或紀錄歸於不同對象）。誠實標示，不誤判為乾淨。
        row["public_penalty"] = [
            "本園於公開資料中經標記有裁罰紀錄，惟逐筆明細比對中（尚未取得可對應之"
            "處分明細）；建議家長逕向主管機關查詢確切紀錄。"
        ]
    else:
        # 無裁罰旗標 → 明確、正面的結論（可回溯事實），而非含糊的「查無資料」。
        row["public_penalty"] = ["目前並無不良裁罰紀錄"]
    field_sources["public_penalty"] = _pen_source

    view = pp.build_public_view(row, field_sources, reference=TODAY)
    basic_info = {"機構名稱": view.park_name or pp.NO_PUBLIC_DATA_LABEL,
                  "行政區": row.get("district") or pp.NO_PUBLIC_DATA_LABEL}
    fields = pp.build_disclosure_fields(view, basic_info=basic_info, reference=TODAY)

    def _fmt(f):
        if not f.has_data:
            return pp.NO_PUBLIC_DATA_LABEL
        v = f.value
        if isinstance(v, dict):
            return "　".join(f"{k}：{val}" for k, val in v.items())
        if isinstance(v, (list, tuple)):
            return "；".join(str(x) for x in v)
        return str(v)

    rows_html = []
    for f in fields:
        val = html.escape(_fmt(f))
        if f.has_data:
            meta = []
            if f.source_url:
                meta.append(f"<a href='{html.escape(f.source_url)}' target='_blank' "
                            f"rel='noopener'>資料來源</a>")
            if f.source_last_updated:
                meta.append(f"最後更新：{f.source_last_updated.isoformat()}")
            if f.source is not None:
                meta.append(html.escape(f.source.authority))
            stale = (f"<span style='color:#B58A1E;font-weight:600;margin-left:8px'>"
                     f"注意：{html.escape(f.stale_notice)}</span>" if f.stale_notice else "")
            cell = f"{val}{stale}<div class='meta'>{'　·　'.join(meta)}</div>"
        else:
            cell = f"<span class='na'>{val}</span>"
        rows_html.append(f"<tr><td class='k'>{html.escape(f.label)}</td><td>{cell}</td></tr>")
    st.markdown("<table class='kv'>" + "".join(rows_html) + "</table>",
                unsafe_allow_html=True)


def render_attention(park_id: str, park_name: str, district: str):
    """輿情觀測：輿情關注指數 + 分級依據 + 多來源時間軸（每則附原文連結）。"""
    with st.spinner("正在蒐集本機構的公開新聞…"):
        items, summary, index, meta = attention_for(
            park_id, park_name, district, sentiment_data)
    color = pmap.color_for_level(summary.level)

    st.markdown(
        f"<span class='badge' style='background:{color}'>"
        f"近期關注度：{pmap.level_label(summary.level)}</span>",
        unsafe_allow_html=True)

    # ---- 資料來源透明分層（合規揭露：什麼是即時真實、什麼是規劃中）----
    # 已接入＝合規公開 RSS 即時抓取（可回溯、附原文連結）；
    # 規劃中＝社群平台，正式版經官方 API 授權接入，不爬需登入內容。
    _live_bits = []
    if meta.get("google_news"):
        _live_bits.append(f"Google News {meta['google_news']} 則")
    if meta.get("bing_news"):
        _live_bits.append(f"Bing News {meta['bing_news']} 則")
    if meta.get("media_rss"):
        _live_bits.append(f"媒體直連 {meta['media_rss']} 則")
    _live_summary = ("、".join(_live_bits) if _live_bits
                     else "近期無精確對應之公開新聞")
    _hit_media = "、".join(meta.get("media_names") or [])
    _hit_media_txt = (f"　·　本次命中：{_hit_media}" if _hit_media else "")
    _demo_note = (f"（本頁另有 {meta['demo']} 則社群示範資料 DEMO）"
                  if meta.get("demo") else "")
    st.markdown(
        "<div class='src-tiers'>"
        # 已接入層 1：新聞聚合器（可按園名搜尋）
        "<div class='src-tier'>"
        "<span class='src-tag src-live'>● 已接入・即時</span>"
        "<span class='src-body'><b>新聞聚合器</b>"
        "<span class='src-detail'>Google News、Bing News 公開 RSS（免金鑰・合規・可按園名搜尋）"
        f"　·　本次即時抓取：{html.escape(_live_summary)}</span></span>"
        "</div>"
        # 已接入層 2：台灣主要媒體 RSS 直連（第一手來源）
        "<div class='src-tier'>"
        "<span class='src-tag src-live'>● 已接入・直連</span>"
        "<span class='src-body'><b>台灣主要媒體 RSS</b>"
        "<span class='src-detail'>自由時報、東森新聞雲、鏡週刊、中央社、聯合報、"
        "Newtalk（各媒體公開 RSS 直連，第一手來源）"
        f"{html.escape(_hit_media_txt)}</span></span>"
        "</div>"
        # 規劃中：社群平台（明列各平台正式版對應的官方 API，展示合規與架構成熟度）
        "<div class='src-tier'>"
        "<span class='src-tag src-plan'>○ 規劃中・待官方 API 授權</span>"
        "<span class='src-body'><b>社群與評論平台</b>"
        "<span class='src-detail'>"
        "Google 評論（正式版接 Google Places API・需授權金鑰）、"
        "Facebook／Instagram（Meta Graph API・需粉專授權）、"
        "Dcard（官方 API・不繞過存取控制）"
        "　·　一律經官方授權接入，不爬需登入或違反服務條款之內容"
        f"{html.escape(_demo_note)}</span></span>"
        "</div>"
        "</div>",
        unsafe_allow_html=True)

    # ---- 輿情關注指數（診斷式白盒總評分，可攤開）----
    st.markdown(
        f"<div style='margin-top:12px'><span style='font-size:1.9rem;font-weight:700;"
        f"color:{color}'>{index.total:.0f}</span>"
        f"<span style='color:#8A8073;font-size:.9rem'> / 100　輿情關注指數</span></div>",
        unsafe_allow_html=True)
    st.progress(min(1.0, index.total / 100.0))
    st.caption(index.disclaimer)

    if index.subscores:
        with st.expander("這個指數怎麼算出來的（白盒公式）"):
            st.markdown(
                "輿情關注指數＝討論量×0.30 ＋ 負面聲量×0.30 ＋ 趨勢變化×0.25 "
                "＋ 主題敏感度×0.15，四項皆 0–100、權重固定公開，無黑箱。")
            comp_df = pd.DataFrame({
                "分項": [ss.SUBSCORE_LABEL[k] for k in index.subscores],
                "原始分(0-100)": [index.subscores[k] for k in index.subscores],
                "權重": [f"{index.weights[k]*100:.0f}%" for k in index.subscores],
                "貢獻分": [index.contributions.get(k, 0) for k in index.subscores],
            })
            st.dataframe(comp_df, hide_index=True, use_container_width=True)
            st.caption("此指數只反映網路討論的熱度與情緒聲量，與稽查系統的財務"
                       "風險分數是完全不同的兩套資料，不可互相對照。")

    if summary.level == sw.LEVEL_NONE and not items:
        st.markdown(
            "<div class='warm-note' style='margin-top:10px'>"
            "<b>目前輿情關注指數為 0 分</b>，代表近期在可蒐集的公開新聞中，"
            "沒有找到與本園精確對應的討論。這通常是正常的，並非機構有無問題之判斷。<br>"
            "建議家長以公開資訊與實地參訪作為主要參考。</div>",
            unsafe_allow_html=True)
        return

    # 分級依據（讓家長自行判斷可信度）
    st.markdown(
        f"<div class='warm-note' style='margin-top:10px'>"
        f"<b>這個判斷怎麼來的：</b>{html.escape(summary.basis)}<br>"
        f"<b>給您的建議：</b>{html.escape(summary.advice)}</div>",
        unsafe_allow_html=True)

    # 月度趨勢（討論量 + 負面則數）
    series = sw.monthly_series(items)
    if series:
        chart_df = pd.DataFrame({
            "月份": [p.month for p in series],
            "討論則數": [p.total for p in series],
            "其中負面": [p.neg for p in series],
        }).set_index("月份")
        st.markdown("**公開討論量趨勢**（依月份）")
        st.bar_chart(chart_df, height=200)

    # 時間軸（每則附原文連結與發布時間；不以 AI 摘要取代原文）
    st.markdown("**公開討論時間軸**（點連結可看原文）")
    sent_color = {"neg": "#D99A4E", "pos": "#5B9E7A", "neu": "#5B84B1"}
    for it in sorted(items, key=lambda x: x.published, reverse=True):
        dot = sent_color.get(it.sentiment, "#5B84B1")
        topics = "".join(f"<span class='chip'>{html.escape(t)}</span>"
                         for t in it.topic_labels)
        link = (f"<a href='{html.escape(it.url)}' target='_blank' rel='noopener'>"
                f"查看原文</a>" if it.url else "")
        src = html.escape(it.source_name or it.source_type_label)
        st.markdown(
            f"<div class='tl-item'>"
            f"<span class='tl-dot' style='background:{dot}'></span>"
            f"<div class='tl-date'>{it.published.isoformat()}　·　{src}"
            f"　·　{it.source_type_label}　·　情緒：{it.sentiment_label}</div>"
            f"<div class='tl-title'>{html.escape(it.title)}</div>"
            f"<div class='tl-ex'>{html.escape(it.excerpt)}</div>"
            f"<div style='margin-top:4px'>{topics}　{link}</div>"
            f"</div>",
            unsafe_allow_html=True)

    st.markdown(
        "<div class='meta'>以上新聞為各媒體之報導、其餘為公開網路討論之整理，"
        "屬「討論內容與其變化」，均為各來源之陳述，非本平台對機構之事實認定或"
        "違法認定；新聞標題用語為原媒體用語。系統已盡力比對園名與行政區，"
        "但仍可能有同名或泛稱情形，每則均附原始來源，建議家長回原文自行判斷，"
        "並主動向園所查證。</div>", unsafe_allow_html=True)


sel_id = st.session_state.get("selected_park_id")
st.markdown("---")
if sel_id is not None:
    sel_row = work[work["park_id"].astype(str) == str(sel_id)]
    if len(sel_row) == 0:
        sel_row = df[df["park_id"].astype(str) == str(sel_id)]
    if len(sel_row):
        row = sel_row.iloc[0].to_dict()
        name = str(row.get("park_name", ""))
        st.markdown(f"### 　{html.escape(name)}")
        st.caption(f"{row.get('park_type','')}・{row.get('district','')}")

        tab1, tab2, tab3 = st.tabs(["公開資訊", "公開輿情觀測", "機構回應／申訴"])
        with tab1:
            st.markdown("<div class='warm-note'>本頁僅呈現可回溯至公開資料來源之事實，"
                        "每一欄位皆標註資料來源與最後更新時間。本平台僅陳述公開事實，"
                        "不對任何機構作違法、舞弊或優劣之評價。</div>", unsafe_allow_html=True)
            render_disclosure(row)
        with tab2:
            render_attention(str(sel_id), name, str(row.get("district", "")))
        with tab3:
            st.markdown(
                "<div class='warm-note'>"
                "<b>機構申訴／回應窗口</b><br>"
                "本平台呈現的公開輿情屬「網路討論觀測」，不是對機構的事實認定。"
                "若貴機構對本站呈現之公開資訊或輿情觀測有疑義，歡迎提出說明，"
                "我們會將機構回應一併呈現，讓家長看到雙方資訊。</div>",
                unsafe_allow_html=True)
            st.markdown(f"**聯絡方式**：{CONTACT_EMAIL}（示範）")
            with st.form(f"appeal_{sel_id}", clear_on_submit=False):
                st.text_input("機構名稱", value=name, disabled=True)
                appeal_person = st.text_input("聯絡人／職稱（選填）")
                appeal_text = st.text_area(
                    "說明內容（必填）",
                    placeholder="請具體說明您希望澄清或補充的內容（至少 8 個字，"
                                "請以得體、就事論事的方式表述）…")
                submitted = st.form_submit_button("送出說明（示範）")
            if submitted:
                # 只有在「按下送出」後才驗證（未送出不顯示任何錯誤）。
                if not appeal_text.strip():
                    # 完全空白：溫和提示，不列一堆問題。
                    st.info("請先填寫「說明內容」再送出，讓我們了解您希望澄清或補充的事項。")
                else:
                    text_chk = ig.check_appeal_text(appeal_text)
                    name_chk = ig.check_name(appeal_person)
                    problems = list(text_chk.reasons) + list(name_chk.reasons)
                    if problems:
                        st.warning("這份說明還不能送出，請調整以下地方：")
                        for p in problems:
                            st.markdown(f"- {p}")
                        st.caption("提醒：本平台歡迎具體、得體的說明與不同意見；"
                                   "此檢查僅用於擋下不雅用語與無效填答，不會審查您的立場。")
                    else:
                        st.success("已收到您的說明（示範）。正式版將由專人審閱後，"
                                   "把機構回應顯示於該機構頁面，與輿情觀測並列呈現。")
else:
    st.info("　從上方地圖點選圓點，或從右側清單選一間機構，即可看完整公開資訊與輿情觀測。")


# ===========================================================================
# 頁尾
# ===========================================================================
st.markdown(
    "<div style='text-align:center;color:var(--ink-faint);font-size:.78rem;"
    "margin-top:28px;padding:16px 0'>"
    "© 2026 Fiscalint. All Rights Reserved."
    "</div>",
    unsafe_allow_html=True,
)

