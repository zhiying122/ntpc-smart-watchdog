"""
公開新聞蒐集（Public News Crawler）— Google News RSS
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的輿情來源：以機構名為
關鍵字，抓取 **Google News 公開 RSS** 的新聞報導（標題、發布時間、媒體來源、
原文連結），轉為 sentiment_watch 可消費的 records。

合規邊界（重要）：
--------------------------------------------------------------------------
- 只抓 **公開 RSS**（Google News 提供的公開聚合 feed），不需登入、不繞過任何
  存取控制，屬合規範圍。
- **不**抓需登入才可見的內容（如私密社團），**不**爬 Google 商家評論頁（其服務
  條款禁止未授權爬蟲）。此模組僅涵蓋新聞這條合規來源。
- 每則保留原始媒體來源與原文連結，供家長回到原文自行判斷；本平台不轉述
  新聞指控為事實（呈現層負責標明「以下為媒體報導，非本平台認定」）。

責任 AI：新聞標題可能含媒體的指控性用語（如「爆虐童」），那是媒體用語，
不是本平台的認定。本模組只忠實傳遞標題與連結，情緒/主題分類交由
sentiment_watch 的透明規則式邏輯處理；平台自身的分級與建議語不複述指控。

技術：純標準庫解析 RSS（xml.etree），requests 發請求；由呼叫端以 st.cache_data
包裝，避免對公共服務過量請求。
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

#: Google News 公開 RSS 搜尋端點（繁中、台灣）。
_GNEWS_RSS = ("https://news.google.com/rss/search?q={query}"
              "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")

#: Bing News 公開 RSS 搜尋端點（繁中、台灣）。與 Google News 互補的合規新聞
#: 聚合來源，同樣為公開 RSS、免金鑰、不需登入。
_BING_RSS = ("https://www.bing.com/news/search?q={query}"
             "&format=rss&setlang=zh-tw&cc=tw")

#: 多組查詢用的附加關鍵字：以「園名核心詞 + 行政區 + 關鍵字」擴大新聞覆蓋，
#: 這些關鍵字對應家長最關心的面向（收費/評鑑/安全/師資），提高召回率。
#: 空字串代表「只有園名 + 行政區 + 幼兒園」的基本查詢。
_QUERY_TOPICS: tuple[str, ...] = ("", "收費", "評鑑", "家長", "安全")

#: 台灣主要媒體的公開 RSS 直連來源（補強層）。這些為各媒體自家提供的公開
#: 「最新新聞」feed（免金鑰、不需登入），屬合規範圍。與 Google/Bing News
#: 聚合器互補：聚合器負責「按園名搜尋」，直連來源提供「第一手、無聚合延遲」。
#: 因是全站最新 feed（無關鍵字搜尋），抓下後以園名核心詞比對過濾（_title_matches）。
#: 端點皆經實測回傳合法 RSS；(媒體顯示名, RSS URL)。
_MEDIA_RSS: tuple[tuple[str, str], ...] = (
    ("自由時報", "https://news.ltn.com.tw/rss/society.xml"),
    ("自由時報", "https://news.ltn.com.tw/rss/life.xml"),
    ("東森新聞雲", "https://feeds.feedburner.com/ettoday/realtime"),
    ("鏡週刊", "https://www.mirrormedia.mg/rss/rss.xml"),
    ("中央社", "https://feeds.feedburner.com/rsscna/social"),
    ("中央社", "https://feeds.feedburner.com/rsscna/lifehealth"),
    ("聯合報", "https://udn.com/rssfeed/news/2/6638?ch=news"),
    ("Newtalk新聞", "https://newtalk.tw/rss/all"),
)

_HEADERS = {
    "User-Agent": "SmartWatchdog-ParentPortal/1.0 (public kindergarten news aggregation)",
    "Accept-Language": "zh-TW",
}

#: 只保留近 N 年的新聞（避免久遠報導稀釋近期觀測）。
_MAX_AGE_DAYS = 365 * 2


def _clean_title(title: str) -> tuple[str, str]:
    """Google News 標題格式常為「標題 - 媒體名」。拆出 (純標題, 媒體名)。"""
    t = (title or "").strip()
    # 由最後一個 ' - ' 切分媒體名（媒體名通常無多餘的 ' - '）。
    if " - " in t:
        head, _, tail = t.rpartition(" - ")
        if head and tail:
            return head.strip(), tail.strip()
    return t, ""


def _parse_pubdate(pub: str) -> date | None:
    """把 RFC822 pubDate 轉為 date；失敗回 None。"""
    if not pub:
        return None
    try:
        dt = parsedate_to_datetime(pub)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).date()
    except (TypeError, ValueError):
        return None


def name_core(park_name: str) -> str:
    """取園名中具鑑別度的核心詞（處理真實資料的多種園名格式）。

    真實園名格式含：
      - 「新北市私立OO幼兒園」→「OO」
      - 「新北市立OO幼兒園」→「OO」
      - 「新北市新莊非營利幼兒園」→「新莊非營利」
      - 「財團法人…附設新北市私立OO幼兒園」→「OO」（取最後一段附設之後）
      - 「新北市XX區YY國民小學附設幼兒園」→「YY國民小學」
    剝除法人/縣市/公私立/行政區/附設等前綴與「幼兒園」尾綴，留下主體名。
    """
    name = (park_name or "").strip()
    core = name

    # 0) 先去尾端括號說明（委託…辦理）。
    core = re.sub(r"[（(].*$", "", core).strip()

    # 1) 剝除常見前綴（縣市/法人/公私立/行政區），可疊加多次。
    for _ in range(3):
        core = re.sub(r"^財團法人[\u4e00-\u9fff]*?(?=新北市|私立|[\u4e00-\u9fff]{1,4}區)", "", core).strip()
        core = re.sub(r"^社團法人", "", core).strip()
        core = re.sub(r"^新北市立", "", core).strip()
        core = re.sub(r"^新北市私立", "", core).strip()
        core = re.sub(r"^新北市", "", core).strip()
        core = re.sub(r"^私立", "", core).strip()
        core = re.sub(r"^[\u4e00-\u9fff]{1,4}區", "", core).strip()

    # 2) 國小/國中附設幼兒園：取「XX國民小學/國民中學」為核心（具鑑別度）。
    m = re.search(r"^([\u4e00-\u9fff]{2,5}(?:國民小學|國民中學|國小|國中))附設", core)
    if m:
        return m.group(1)

    # 3) 其他「附設」：取最後一個「附設」之後段落（多為真正園名主體），再剝一次前綴。
    if "附設" in core:
        tail = core.rsplit("附設", 1)[1].strip()
        if tail:
            core = tail
            for _ in range(2):
                core = re.sub(r"^新北市立", "", core).strip()
                core = re.sub(r"^新北市私立", "", core).strip()
                core = re.sub(r"^新北市", "", core).strip()
                core = re.sub(r"^私立", "", core).strip()

    # 4) 去尾綴「幼兒園」。
    core = re.sub(r"幼兒園$", "", core).strip()

    return core or re.sub(r"幼兒園$", "", name).strip() or name


def build_query(park_name: str, district: str = "", extra: str = "") -> str:
    """由機構全名 + 行政區（+ 可選關鍵字）組出精確的新聞查詢字串。

    以「園名核心詞 + 行政區 + 幼兒園（+ 關鍵字）」組合，並用雙引號綁定園名
    核心詞，降低同名雜訊。例：核心「新莊非營利」、區「新莊區」、關鍵字「收費」→
        '"新莊非營利" 新莊區 幼兒園 收費'。
    extra 為空時即為基本查詢（向後相容）。
    """
    core = name_core(park_name)
    if not core:
        return ""
    parts = [f'"{core}"']
    d = (district or "").strip()
    if d:
        parts.append(d)
    parts.append("幼兒園")
    e = (extra or "").strip()
    if e:
        parts.append(e)
    return " ".join(parts)


def _is_generic_core(core: str, district: str) -> bool:
    """核心詞是否只是「地區泛稱」（如「林口」「新莊」恰等於行政區名）。

    僅當核心詞**恰等於**行政區名或其去「區」短名時才算泛稱（這類園名多為
    市立園「新北市立OO幼兒園」，去前後綴後只剩地區名，用地區比對極易張冠
    李戴）。若核心詞含額外鑑別詞（如「新莊非營利」），則不算泛稱、可直接
    以核心詞比對。
    """
    d = (district or "").strip()
    d_short = d.rstrip("區")
    return bool(core) and (core == d or core == d_short)


def _title_matches(title: str, core: str, district: str, park_name: str) -> bool:
    """二次過濾：標題是否確實對應本園（避免同名/同地區張冠李戴）。

    分兩種情況：
      1. 核心詞具鑑別度（如「新莊非營利」）：標題含核心詞即視為相關。
      2. 核心詞只是地區泛稱（如「林口」＝行政區名，多為市立園）：地區＋
         「幼兒園」不足以確認（同區其他園、補習班都會命中），必須標題含
         **完整園名**（park_name 或其去縣市前綴版）才算相關，否則不強綁。

    比對不上者由呼叫端標為 matched=False，呈現層據此不將該則計入分級/指數，
    或明確標示「未必為本園」。
    """
    t = title or ""
    if not core:
        return False

    if _is_generic_core(core, district):
        # 地區泛稱（如「林口」）：新聞多以泛稱指涉同區任何園／補習班，無法可靠
        # 對應到「本頁這一間」。採最保守策略——只有標題含**完整全名**
        # （如「新北市立林口幼兒園」）時才視為確認相關；其餘一律不強綁，
        # 寧可少綁也不冤枉特定機構（責任 AI）。
        full = (park_name or "").strip()
        return bool(full and full in t)

    # 具鑑別度的核心詞：含核心詞即相關。
    return core in t


def fetch_news(park_name: str, district: str = "", *, timeout: float = 8.0,
               limit: int = 20, reference: date | None = None) -> list[dict]:
    """以園名 + 行政區精確抓取 Google News 公開 RSS，回傳可消費的 records。

    每筆 record（對齊 sentiment_watch.enrich_item）：
        {source_type:'news', source_name:媒體名, title:標題, excerpt:標題,
         url:原文連結, published:'YYYY-MM-DD', matched:bool}

    精準比對（避免冤枉機構）：
      - 查詢字串綁定園名核心詞 + 行政區（build_query）。
      - 每則再經 _title_matches 二次過濾；標題確實對應本園者 matched=True，
        僅是同名或泛泛提及者 matched=False（呈現層據此決定是否納入分級/標明）。
    連線/解析錯誤一律回空清單（呼叫端退回示範資料），不拋例外。

    參數
    ----
    park_name / district:
        機構全名與行政區（供查詢與比對）。
    timeout / limit / reference:
        逾時秒數 / 最多筆數 / 時效參考日。
    """
    ref = reference or date.today()
    query = build_query(park_name, district)
    if not query:
        return []
    return _fetch_rss(_GNEWS_RSS, query, park_name, district,
                      platform="google_news", timeout=timeout,
                      limit=limit, reference=ref)


def _fetch_rss(endpoint: str, query: str, park_name: str, district: str, *,
               platform: str, timeout: float, limit: int,
               reference: date) -> list[dict]:
    """抓取單一 RSS feed 並解析為 records（Google News / Bing News 共用）。

    純解析＋精準比對，連線/解析錯誤一律回空清單（不拋例外）。每筆 record 附
    source_platform（google_news / bing_news）供聚合層去重與來源計數；沿用
    _title_matches 的責任 AI 精準比對（避免同名/泛稱張冠李戴）。
    """
    core = name_core(park_name)
    url = endpoint.format(query=quote(query))
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except (requests.RequestException, ET.ParseError, ValueError):
        return []

    records: list[dict] = []
    for item in root.findall(".//item"):
        raw_title = item.findtext("title", "") or ""
        link = item.findtext("link", "") or ""
        pub = item.findtext("pubDate", "") or ""
        src_el = item.find("source")
        title, tail_src = _clean_title(raw_title)
        source_name = (src_el.text.strip() if src_el is not None and src_el.text
                       else tail_src)

        pub_date = _parse_pubdate(pub)
        if pub_date is None:
            continue
        if (reference - pub_date).days > _MAX_AGE_DAYS:
            continue
        if not title or not link:
            continue

        records.append({
            "source_type": "news",
            "source_platform": platform,
            "source_name": source_name or "新聞來源",
            "title": title,
            "excerpt": title,
            "url": link,
            "published": pub_date.isoformat(),
            "matched": _title_matches(title, core, district, park_name),
        })
        if len(records) >= limit:
            break

    return records


def _fetch_media_rss(media_name: str, url: str, park_name: str, district: str,
                     *, timeout: float, reference: date) -> list[dict]:
    """抓取單一台灣媒體的全站 RSS，用園名核心詞比對過濾出提到本園的報導。

    與聚合器（Google/Bing）不同：這是「全站最新」feed（無關鍵字搜尋），故抓下
    後只保留標題含園名核心詞的項目——且核心詞為地區泛稱時要求完整全名
    （沿用 _title_matches 的責任 AI 精準比對，避免張冠李戴）。命中率低但命中即
    為第一手來源。連線/解析錯誤回空清單，不拋例外、不影響其他來源。

    媒體名以 feed 對應的固定名稱標記（這些全站 feed 的 item 多無 source 元素）。
    只回傳確實比對到本園（matched=True）的項目，避免把不相干新聞塞進來。
    """
    core = name_core(park_name)
    if not core:
        return []
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
    except (requests.RequestException, ET.ParseError, ValueError):
        return []

    records: list[dict] = []
    for item in root.findall(".//item"):
        title = (item.findtext("title", "") or "").strip()
        link = (item.findtext("link", "") or "").strip()
        pub = item.findtext("pubDate", "") or ""
        if not title or not link:
            continue
        # 全站 feed：只留標題確實對應本園者（精準比對，避免同名/泛稱誤綁）。
        if not _title_matches(title, core, district, park_name):
            continue
        pub_date = _parse_pubdate(pub)
        if pub_date is None:
            continue
        if (reference - pub_date).days > _MAX_AGE_DAYS:
            continue
        records.append({
            "source_type": "news",
            "source_platform": "media_rss",
            "source_name": media_name,
            "title": title,
            "excerpt": title,
            "url": link,
            "published": pub_date.isoformat(),
            "matched": True,
        })
    return records


def _norm_title(title: str) -> str:
    """正規化標題作為跨來源去重鍵：去除標點/空白/全半形差異，取前綴片段。

    同一則新聞在 Google News / Bing / 媒體原站可能有細微標題差異（媒體名後綴、
    空白、標點），純字串比對會漏。這裡移除非中英數字元、轉小寫，讓「同一則」
    在不同來源產生相同的鍵。
    """
    t = (title or "").lower()
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", t)


def _dedupe(records: list[dict]) -> list[dict]:
    """跨來源去重：同一則新聞常同時出現在 Google News / Bing / 媒體原站，
    且三者 URL 各不相同（聚合器用自家轉址連結）。故以「正規化標題 + 發布日」
    為主鍵（跨來源穩定），並輔以 URL 鍵（防同來源分頁重複）。

    偏好保留原站連結：若重複項中出現媒體直連（media_rss，URL 為原文），
    以它取代先前的聚合器轉址版，讓家長點到的是新聞原文。
    依發布日新到舊排序後回傳。
    """
    by_key: dict[str, dict] = {}   # 主鍵（標題+日期）→ 已保留的 record
    order: list[str] = []          # 保留插入順序
    url_seen: dict[str, str] = {}  # URL → 主鍵（防同 URL 重複）

    for r in records:
        title_key = f"{_norm_title(r.get('title', ''))}|{r.get('published', '')}"
        url = (r.get("url") or "").strip().lower()
        # 若此 URL 先前已出現，對應回同一主鍵（同來源分頁等）。
        key = url_seen.get(url, title_key) if url else title_key

        if key not in by_key:
            by_key[key] = r
            order.append(key)
        else:
            # 已有同則：若新的是媒體原站連結而舊的不是，替換為原文版。
            existing = by_key[key]
            if (r.get("source_platform") == "media_rss"
                    and existing.get("source_platform") != "media_rss"):
                by_key[key] = r
        if url:
            url_seen[url] = key

    out = [by_key[k] for k in order]
    out.sort(key=lambda x: x.get("published", ""), reverse=True)
    return out


def fetch_all_news(park_name: str, district: str = "", *, timeout: float = 8.0,
                   per_source_limit: int = 12, limit: int = 30,
                   reference: date | None = None) -> list[dict]:
    """合規多來源新聞聚合：多組 Google News 查詢 + Bing News，去重後回傳。

    來源全部為公開 RSS（免金鑰、不需登入），符合政府級合規邊界。做法：
      - Google News：對 _QUERY_TOPICS 每個關鍵字各查一次（園名+區+幼兒園+關鍵字），
        提高召回率（收費/評鑑/安全/師資等家長關心面向）。
      - Bing News：以基本查詢補一組互補來源。
      - 全部合併後 _dedupe 去重（同則新聞跨來源只留一份），依日期新到舊排序。

    每筆 record 帶 source_platform（google_news/bing_news）與 matched 精準比對
    旗標，呈現層據此標示來源組成與是否納入分級。任一來源失敗只影響該來源
    （回空），不中斷其他來源。

    參數
    ----
    per_source_limit：單一查詢/來源最多筆數。
    limit：去重後回傳總上限。
    """
    ref = reference or date.today()
    if not name_core(park_name):
        return []

    # 併發抓取（效能）：原本序列發 ~14 個 RSS 請求，每個逾時 timeout 秒，最壞
    # 累加達上百秒。改用執行緒池同時發送，總耗時 ≈ 最慢的單一請求；任一來源
    # 失敗只回空、不影響其他來源（各抓取函式已內建例外保護）。
    tasks = []  # list[callable() -> list[dict]]
    # 多組 Google News 查詢（不同關鍵字面向）。
    for topic in _QUERY_TOPICS:
        q = build_query(park_name, district, extra=topic)
        if not q:
            continue
        tasks.append(lambda q=q: _fetch_rss(
            _GNEWS_RSS, q, park_name, district, platform="google_news",
            timeout=timeout, limit=per_source_limit, reference=ref))

    # Bing News（基本查詢，互補來源）。
    q_bing = build_query(park_name, district)
    if q_bing:
        tasks.append(lambda: _fetch_rss(
            _BING_RSS, q_bing, park_name, district, platform="bing_news",
            timeout=timeout, limit=per_source_limit, reference=ref))

    # 台灣主要媒體 RSS 直連（第一手來源，全站 feed 以園名比對過濾）。
    for media_name, media_url in _MEDIA_RSS:
        tasks.append(lambda mn=media_name, mu=media_url: _fetch_media_rss(
            mn, mu, park_name, district, timeout=timeout, reference=ref))

    collected: list[dict] = []
    if tasks:
        with ThreadPoolExecutor(max_workers=min(8, len(tasks))) as ex:
            futures = [ex.submit(t) for t in tasks]
            for fut in as_completed(futures):
                try:
                    collected.extend(fut.result())
                except Exception:  # noqa: BLE001 - 單一來源失敗不影響整體
                    continue

    return _dedupe(collected)[:limit]
