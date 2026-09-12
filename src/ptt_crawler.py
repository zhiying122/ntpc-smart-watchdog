"""
PTT 公開看板爬蟲（PTT Public Board Crawler）— 社群輿情層（L5 SOCIAL）
============================================================================
小小守護員 Smart Watchdog Platform — 以機構名核心詞比對 PTT 親子相關看板的
**公開文章標題**，作為社群輿情訊號來源之一（與新聞 RSS 互補）。

合規邊界（重要，對齊 multi_source.LIVE_COLLECTABLE 之認定）：
--------------------------------------------------------------------------
- 只抓 www.ptt.cc 的**公開看板列表頁**（無需登入、無反爬 JS，屬合規範圍）。
- BabyMother / BabyProducts 等看板無 over18 年齡牆，可直接 GET。
- 只讀公開文章「標題 + 連結 + 日期」，不抓需登入內容、不繞過任何存取控制。
- 每則保留原文連結供追溯；責任 AI：PTT 討論為「網路輿情訊號」，非違法認定。

技術：
- 純 requests + 標準庫 html.parser 解析看板列表頁（不依賴第三方 HTML 套件，
  維持既有基線可攜性）。
- 逾時保護；任何連線/解析錯誤一律回空清單（不拋例外），確保離線/失敗時
  系統以缺值中性處理、不中斷。
- 以園名核心詞（沿用 news_crawler.name_core 的正規化）在標題中比對，
  同名／地區泛稱採保守策略（避免張冠李戴）。
"""
from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser

import requests

# 親子／幼兒相關公開看板（皆無 over18 年齡牆，可直接抓列表頁）。
_BOARDS: tuple[str, ...] = ("BabyMother", "BabyProducts")

_BASE = "https://www.ptt.cc"
_HEADERS = {
    "User-Agent": "SmartWatchdog/1.0 (public board sentiment; contact: hackathon)",
    "Accept-Language": "zh-TW",
}
# 只保留近 N 年（與新聞一致，避免久遠討論稀釋近期觀測）。
_MAX_AGE_DAYS = 365 * 2


class _ListParser(HTMLParser):
    """解析 PTT 看板列表頁，抽出每篇文章的標題、連結、日期。

    PTT 列表頁結構（穩定多年）：
      <div class="r-ent">
        <div class="title"><a href="/bbs/Board/M.xxx.html">標題</a></div>
        <div class="meta"><div class="date"> M/DD</div>...</div>
      </div>
    被刪除的文章 title 內無 <a>（只有純文字），自動略過。
    """

    def __init__(self):
        super().__init__()
        self.items: list[dict] = []
        self._in_title = False
        self._in_date = False
        self._cur_href = ""
        self._cur_title = ""
        self._cur_date = ""
        self._depth_title = 0

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        cls = d.get("class", "")
        if tag == "div" and "title" in cls.split():
            self._in_title = True
            self._cur_href = ""
            self._cur_title = ""
        elif tag == "a" and self._in_title:
            self._cur_href = d.get("href", "")
        elif tag == "div" and "date" in cls.split():
            self._in_date = True
            self._cur_date = ""

    def handle_endtag(self, tag):
        if tag == "div" and self._in_title:
            # title div 結束：若有連結與標題則收錄（日期稍後由 meta 補）。
            if self._cur_href and self._cur_title.strip():
                self.items.append({
                    "title": self._cur_title.strip(),
                    "href": self._cur_href.strip(),
                    "date": "",
                })
            self._in_title = False
        elif tag == "div" and self._in_date:
            self._in_date = False
            # 把日期補給「最近一筆尚無日期」的項目（同一 r-ent 內）。
            if self.items and not self.items[-1]["date"]:
                self.items[-1]["date"] = self._cur_date.strip()

    def handle_data(self, data):
        if self._in_title:
            self._cur_title += data
        elif self._in_date:
            self._cur_date += data


def _fetch_board_page(board: str, timeout: float) -> list[dict]:
    """抓單一看板首頁（最新文章列表），回傳原始項目清單。失敗回空。"""
    url = f"{_BASE}/bbs/{board}/index.html"
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=timeout)
        resp.raise_for_status()
    except requests.RequestException:
        return []
    parser = _ListParser()
    try:
        parser.feed(resp.text)
    except Exception:  # noqa: BLE001 - 解析容錯
        return []
    return parser.items


def _parse_ptt_date(mmdd: str, ref: date) -> date | None:
    """PTT 列表頁日期只有 'M/DD'（無年份）。以參考日推年份：

    若該 月/日 晚於今日（跨年情境），視為去年；否則今年。失敗回 None。
    """
    s = (mmdd or "").strip()
    m = re.match(r"(\d{1,2})/(\d{1,2})", s)
    if not m:
        return None
    month, day = int(m.group(1)), int(m.group(2))
    try:
        d = date(ref.year, month, day)
    except ValueError:
        return None
    if d > ref:  # 例如今天 1/5、文章 12/30 → 去年
        try:
            d = date(ref.year - 1, month, day)
        except ValueError:
            return None
    return d


def fetch_ptt(park_name: str, district: str = "", *, timeout: float = 8.0,
              limit: int = 20, reference: date | None = None,
              match_title=None) -> list[dict]:
    """抓 PTT 親子看板公開文章，回傳比對到本園的社群輿情 records。

    每筆 record（對齊 news_crawler / sentiment_watch 慣例）：
        {source_type:'social', source_platform:'ptt', source_name:'PTT <板>',
         title:標題, excerpt:標題, url:原文連結, published:'YYYY-MM-DD',
         matched:bool}

    參數
    ----
    park_name / district：機構全名與行政區（供比對）。
    match_title：可注入的標題比對函式 (title, core, district, park_name)->bool；
        預設沿用 news_crawler._title_matches（責任 AI 精準比對，避免張冠李戴）。
    連線/解析錯誤一律回空清單（呼叫端以缺值中性處理），不拋例外。
    """
    ref = reference or date.today()

    # 沿用新聞爬蟲的核心詞與精準比對邏輯，保持跨來源一致的責任 AI 標準。
    try:
        from public.lib.news_crawler import name_core, _title_matches
    except Exception:
        try:
            import importlib.util
            import os
            _spec = importlib.util.spec_from_file_location(
                "news_crawler",
                os.path.join(os.path.dirname(os.path.dirname(
                    os.path.abspath(__file__))),
                    "public", "lib", "news_crawler.py"))
            _nc = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_nc)
            name_core, _title_matches = _nc.name_core, _nc._title_matches
        except Exception:
            return []

    matcher = match_title or _title_matches
    core = name_core(park_name)
    if not core:
        return []

    records: list[dict] = []
    for board in _BOARDS:
        for it in _fetch_board_page(board, timeout=timeout):
            title = it.get("title", "")
            if not matcher(title, core, district, park_name):
                continue
            pub = _parse_ptt_date(it.get("date", ""), ref)
            if pub is None:
                continue
            if (ref - pub).days > _MAX_AGE_DAYS:
                continue
            href = it.get("href", "")
            url = f"{_BASE}{href}" if href.startswith("/") else href
            records.append({
                "source_type": "social",
                "source_platform": "ptt",
                "source_name": f"PTT {board}",
                "title": title,
                "excerpt": title,
                "url": url,
                "published": pub.isoformat(),
                "matched": True,
            })
            if len(records) >= limit:
                return records
    return records
