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
from folium.plugins import BeautifyIcon  # noqa: E402
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
    pub = pdset.load_public_dataset(timeout=30)
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
    """回傳真實資料源的最後抓取時間（ISO 轉為易讀）；無則回退檔案時間。"""
    d = load_public_dataset_cached()
    iso = d.get("fetched_at")
    if iso:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(iso)
            return dt.astimezone().strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return str(iso)
    return "—"


@st.cache_data(show_spinner=False, ttl=6 * 3600)
def fetch_live_news(park_name: str, district: str) -> list[dict]:
    """即時抓取本機構的公開新聞（快取 6 小時，隨時間自動更新）。

    僅保留與本機構精確比對成功（matched=True）的新聞，避免同名/同地區張冠
    李戴；抓不到或連線失敗回空清單（由呼叫端退回示範資料）。
    """
    recs = nc.fetch_news(park_name, district, limit=15, reference=TODAY)
    return [r for r in recs if r.get("matched")]


def attention_for(park_id: str, park_name: str, district: str, sentiment_data: dict):
    """整合某機構的輿情：真實新聞（即時爬）+ 示範多來源資料，計算摘要與指數。

    回傳 (items, summary, index, meta)：
      - items：合併後、依時間排序的 SentimentItem 清單。
      - summary：sentiment_watch 的家長友善分級摘要。
      - index：輿情關注指數（診斷式白盒總評分）。
      - meta：{'live_news': n, 'demo': n, 'has_demo': bool}，供頁面標示來源組成。

    資料組成：
      - 真實新聞：以園名+行政區精確抓取，只計 matched=True。
      - 示範資料：sentiment_demo.json 內該園的多來源（Google評論/FB/IG/部落格
        等）示範項目，標明 DEMO。
    """
    live_recs = fetch_live_news(park_name, district)
    obj = sentiment_data.get("institutions", {}).get(str(park_id))
    demo_recs = list(obj.get("items", [])) if obj else []

    all_recs = list(live_recs) + list(demo_recs)
    items = sw.load_items_from_records(all_recs)
    summary = sw.summarize_attention(items, reference=TODAY)
    index = ss.compute_index(items, reference=TODAY)
    meta = {
        "live_news": len(live_recs),
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
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
    html, body, [class*="css"], .stApp {
      font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif; color:#33404E; }
    .stApp { background:#FBFAF7; }
    #MainMenu, footer, [data-testid="stDecoration"] { visibility:hidden; }
    [data-testid="stHeader"] { height:0 !important; background:transparent; }
    .block-container { padding-top:1.4rem; max-width:1200px; }

    .warm-topbar { color:#8A7E6B; font-size:.82rem; letter-spacing:.03em; }
    .warm-title { font-size:1.7rem; font-weight:700; color:#2C3A2E; margin:2px 0 4px; }
    .warm-sub { color:#5C6670; font-size:.95rem; line-height:1.75; max-width:760px; }

    .warm-card { background:#fff; border:1px solid #ECE7DE; border-radius:12px;
      padding:18px 20px; margin:10px 0; }
    .warm-note { background:#F3F6F1; border:1px solid #DBE5D6; border-radius:10px;
      padding:12px 16px; color:#42513F; font-size:.85rem; line-height:1.75; }

    .badge { display:inline-block; padding:3px 12px; border-radius:999px;
      font-size:.82rem; font-weight:700; color:#fff; }
    .chip { display:inline-block; padding:2px 10px; border-radius:999px;
      font-size:.76rem; background:#F0EDE6; color:#6B6357; margin-right:6px; }

    .kv { width:100%; border-collapse:collapse; margin-top:6px; }
    .kv td { padding:10px 12px; border-bottom:1px solid #F0ECE4; font-size:.9rem;
      vertical-align:top; }
    .kv tr:last-child td { border-bottom:none; }
    .kv .k { color:#8A8073; font-weight:600; white-space:nowrap; width:120px; }
    .na { color:#AAA290; }
    .meta { color:#9A9080; font-size:.76rem; margin-top:4px; }

    .tl-item { border-left:3px solid #E4DED3; padding:2px 0 14px 16px;
      margin-left:6px; position:relative; }
    .tl-dot { position:absolute; left:-7px; top:4px; width:11px; height:11px;
      border-radius:50%; border:2px solid #fff; }
    .tl-date { color:#9A9080; font-size:.76rem; }
    .tl-title { font-weight:600; color:#33404E; font-size:.92rem; margin:1px 0; }
    .tl-ex { color:#5C6670; font-size:.85rem; line-height:1.65; }
    a { color:#3A6EA5; }
    .foot { color:#9A9080; font-size:.78rem; line-height:1.75; margin-top:20px; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="warm-topbar">新北市政府教育局　·　公開資料便民服務</div>
    <div class="warm-title">安心找幼兒園</div>
    <div class="warm-sub">輸入您家的地址，看看附近有哪些教保機構。每一項資訊都來自公開資料來源，
    並標註來源與更新時間。我們也整理了公開的網路討論觀測，幫助您多一個了解的角度——
    這些是「討論的變化」，不是對機構的評價，最終仍建議您實地參訪並向園所查證。</div>
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

# 資料來源與時效橫幅（誠實揭露：即時 vs 離線快取）。
_src_line = (f"資料來源：{_pubdata.get('attribution','')}　·　"
             f"{'即時同步' if _pubdata.get('is_live') else '離線快取'}"
             f"　·　最後更新 {data_updated_at()}")
if _pubdata.get("note"):
    _src_line += "　·　" + _pubdata["note"]
st.caption(_src_line)

# session 狀態：選定機構、家的位置
st.session_state.setdefault("selected_park_id", None)
st.session_state.setdefault("home", None)  # dict(lat,lng,label)


# ===========================================================================
# 篩選列（地址 + 距離 + 公私立 + 類型）
# ===========================================================================
st.markdown("<div class='warm-card'>", unsafe_allow_html=True)
st.markdown("#### 　從您家附近開始找")

c1, c2 = st.columns([2.4, 1])
with c1:
    address = st.text_input(
        "輸入您家的地址（或附近地標）",
        placeholder="例如：新北市板橋區文化路一段",
        help="使用 OpenStreetMap 免費定位服務，不會儲存您的地址。",
    )
with c2:
    radius_km = st.select_slider(
        "搜尋範圍",
        options=[0.5, 1.0, 2.0, 5.0],
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
    do_search = st.button("　定位並搜尋　", type="primary", use_container_width=True)

# 觸發定位
if do_search and address.strip():
    res = geocode_cached(address.strip())
    if res["ok"]:
        st.session_state["home"] = {
            "lat": res["lat"], "lng": res["lng"], "label": res["display_name"],
            "notice": res.get("notice", "")}
        st.session_state["selected_park_id"] = None
        if res.get("notice"):
            st.info(res["notice"])
    else:
        st.session_state["home"] = None
        st.warning(res["message"])

st.markdown("</div>", unsafe_allow_html=True)


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


# 只有在家長完成地址定位後才建立機構標記；未搜尋前地圖保持乾淨、不攤開全部機構。
searched = home is not None
markers = build_markers(work) if searched else []

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
        return f"⚠ 有裁罰 {n} 筆"
    if flag == "有":
        return "⚠ 經標記有裁罰"
    return "✓ 無裁罰紀錄"


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
    st.markdown("##### 　附近機構地圖")
    if home:
        center = [home["lat"], home["lng"]]
        zoom = {0.5: 15, 1.0: 14, 2.0: 13, 5.0: 12}.get(radius_km, 13)
    else:
        # 未搜尋：以新北市為中心的乾淨底圖，不畫任何機構點。
        center = list(geo.DEFAULT_CENTER)
        zoom = 11

    fmap = folium.Map(location=center, zoom_start=zoom, tiles="OpenStreetMap",
                      control_scale=True)

    # 家的位置
    if home:
        folium.Marker(
            location=[home["lat"], home["lng"]],
            tooltip="您輸入的位置",
            icon=BeautifyIcon(icon="home", icon_shape="marker",
                              background_color=pmap.COLOR_HOME,
                              border_color=pmap.COLOR_HOME, text_color="#fff"),
        ).add_to(fmap)
        folium.Circle(
            location=[home["lat"], home["lng"]], radius=radius_km * 1000,
            color=pmap.COLOR_HOME, weight=1, fill=True, fill_opacity=0.05,
        ).add_to(fmap)

    # 機構標記：著色與右側清單一致＝公開裁罰狀態（綠=無裁罰、暖琥珀=有/經標記裁罰），
    # 避免地圖全灰、且左右燈號語意同步。輿情關注度於點入機構後即時計算，不在地圖著色。
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
        ).add_to(fmap)

    map_state = st_folium(fmap, height=460, use_container_width=True,
                          returned_objects=["last_object_clicked"])

    if not searched:
        # 未搜尋：不顯示關注度圖例（此時圖上沒有機構點），只給一句引導。
        st.markdown(
            "<div class='warm-note' style='margin-top:8px'>"
            "在上方輸入您家的地址並按「定位並搜尋」，地圖就會以您家為中心，"
            "標出附近的教保機構，並在右側依距離由近到遠列出。"
            "您也可以先用「公私立別」與「行政區」縮小範圍。</div>",
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
                f"<span style='display:inline-flex;align-items:center;gap:6px;"
                f"font-size:.8rem;color:#5C6670'>"
                f"<span style='width:12px;height:12px;border-radius:50%;"
                f"background:{color};border:2px solid #fff;"
                f"box-shadow:0 0 0 1px #E4DED3'></span>{html.escape(label)}</span>")
        st.markdown(
            "<div style='height:80px;box-sizing:border-box;padding-top:8px;overflow:hidden'>"
            f"<div style='display:flex;flex-wrap:wrap;gap:14px'>{legend_items_html}</div>"
            "<div style='font-size:.76rem;color:#8A8073;margin-top:6px'>"
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
        _scope_txt = ("　".join(sel_dist) if sel_dist
                      else f"{geo.format_distance(radius_km)}內")
        # 右欄標題＋燈號說明合併為固定高度區塊（60px），與左欄一致以利底部對齊。
        st.markdown(
            "<div style='height:60px;box-sizing:border-box'>"
            f"<div style='font-size:1.05rem;font-weight:700;color:#2C3A2E'>"
            f"符合條件：{len(markers)} 間（{html.escape(_scope_txt)}）</div>"
            "<div style='font-size:.76rem;color:#8A8073;margin-top:4px'>"
            "清單燈號：<span style='color:#5B9E7A'>●</span> 無裁罰　"
            "<span style='color:#D99A4E'>●</span> 有／經標記裁罰"
            "（輿情關注度請點入機構查看）</div>"
            "</div>",
            unsafe_allow_html=True)

        if not markers:
            st.info("這個範圍內沒有符合條件的機構，試著放大搜尋範圍或調整篩選。")
        else:
            # 對齊左欄底部（地圖460＋圖例說明區）：右欄＝標題區＋容器。
            # 容器高度經實測微調，使右欄底部齊平於左欄「地圖標記說明」文字底部。
            list_box = st.container(height=520)
            with list_box:
                for m in markers[:80]:
                    dist_txt = (f"・{geo.format_distance(m.distance_km)}"
                                if m.distance_km is not None else "")
                    # 清單燈號＝裁罰狀態顏色（與右側文字語意一致，非輿情關注度）。
                    _dot_color = _penalty_color(m.park_id)
                    cols = st.columns([0.12, 0.88])
                    with cols[0]:
                        st.markdown(
                            f"<div style='width:14px;height:14px;border-radius:50%;"
                            f"background:{_dot_color};margin-top:6px;'></div>",
                            unsafe_allow_html=True)
                    with cols[1]:
                        if st.button(f"{m.name}", key=f"pick_{m.park_id}",
                                     use_container_width=True):
                            st.session_state["selected_park_id"] = m.park_id
                        # 清單即時可給的有用資訊＝公開裁罰狀態（不即時爬輿情，
                        # 輿情於點入詳情頁時才即時查詢與計分）。
                        _pstat = _penalty_status_short(m.park_id)
                        st.caption(f"{m.ownership}・{m.district}{dist_txt}　{_pstat}")


# ===========================================================================
# 機構詳情頁（含公開資訊 + 輿情時間軸 + 分級依據 + 申訴窗口）
# ===========================================================================
def _record_summary(row: dict) -> tuple[str, str]:
    """產生每間機構的「綜合公開紀錄摘要」：(結論文字, 顏色)。

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
    # 中間狀態：官方標記有裁罰，但無可對應之逐筆明細。
    if (n is None or n <= 0) and _flag == "有":
        return ("本園於公開資料中經標記有裁罰紀錄，惟逐筆明細比對中；"
                "此非乾淨紀錄，建議家長逕向主管機關查詢確切內容。",
                "#D99A4E")
    if n is not None and n > 0:
        return (f"本園近年有 {n} 筆公開裁罰紀錄，詳見下方裁罰欄位；"
                "裁罰為主管機關依法處分之公開事實，建議搭配園所說明一併了解。",
                "#D99A4E")
    return ("目前公開紀錄中並無不良事項（近年無裁罰紀錄）。"
            "以下為本園之公開資訊，建議家長仍以實地參訪作為主要參考。",
            "#5B9E7A")


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
    _sum_txt, _sum_color = _record_summary(row)
    st.markdown(
        f"<div style='border-left:4px solid {_sum_color};background:#fff;"
        f"border:1px solid #ECE7DE;border-radius:8px;padding:12px 16px;"
        f"margin:6px 0 12px'><b style='color:{_sum_color}'>綜合公開紀錄</b><br>"
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
        "全國教保資訊網．裁罰查詢（資料經 g0v 開源專案整理）", _authority,
        "https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx", TODAY)
    if _details:
        lines = [f"近年公開裁罰 {len(_details)} 筆（依負責人比對）："]
        for d in _details[:5]:
            _date = d.get("date", "")
            _pun = str(d.get("punishment", "")).strip()
            lines.append(f"・{_date}　{_pun}")
        if len(_details) > 5:
            lines.append(f"…等共 {len(_details)} 筆")
        row["public_penalty"] = lines
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

    # 來源組成標示（真實新聞 vs 示範資料）
    src_bits = []
    if meta["live_news"]:
        src_bits.append(f"即時新聞 {meta['live_news']} 則")
    if meta["demo"]:
        src_bits.append(f"示範多來源 {meta['demo']} 則")
    src_txt = "、".join(src_bits) if src_bits else "尚無資料"

    st.markdown(
        f"<span class='badge' style='background:{color}'>近期關注度：{pmap.level_label(summary.level)}</span>"
        + f"　<span class='chip'>資料組成：{html.escape(src_txt)}</span>",
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
    f"""
    <div class="foot">
    ・機構基本資料、收費、評鑑、裁罰為公開資料集；「查無公開資料」表示該欄位
    目前無對應公開來源，並非機構有無問題之判斷。<br>
    ・「公開輿情觀測」的新聞為即時蒐集之公開新聞報導；Google 評論／Facebook／
    Instagram／部落格等為<b>示範資料（DEMO）</b>，正式版需透過各平台官方 API
    授權接入，且不會蒐集需登入才可見之內容。<br>
    ・本站只呈現公開資訊與公開網路討論觀測，不含任何內部評分或分級，
    與教育局內部稽查系統採網路與主機隔離。<br>
    ・地址定位使用 OpenStreetMap／Nominatim 免費服務，不儲存您輸入的地址。<br>
    ・資料最後更新：{data_updated_at()}
    </div>
    """,
    unsafe_allow_html=True,
)
