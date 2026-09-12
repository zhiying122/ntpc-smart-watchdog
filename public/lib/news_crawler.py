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
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests

#: Google News 公開 RSS 搜尋端點（繁中、台灣）。
_GNEWS_RSS = ("https://news.google.com/rss/search?q={query}"
              "&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")

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


def build_query(park_name: str, district: str = "") -> str:
    """由機構全名 + 行政區組出精確的新聞查詢字串。

    以「園名核心詞 + 行政區 + 幼兒園」組合，並用雙引號綁定園名核心詞，
    降低同名雜訊。例：核心「新莊非營利」、區「新莊區」→
        '"新莊非營利" 新莊區 幼兒園'。
    """
    core = name_core(park_name)
    if not core:
        return ""
    parts = [f'"{core}"']
    d = (district or "").strip()
    if d:
        parts.append(d)
    parts.append("幼兒園")
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
    core = name_core(park_name)
    query = build_query(park_name, district)
    if not query:
        return []
    ref = reference or date.today()

    url = _GNEWS_RSS.format(query=quote(query))
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
        if (ref - pub_date).days > _MAX_AGE_DAYS:
            continue
        if not title or not link:
            continue

        records.append({
            "source_type": "news",
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
