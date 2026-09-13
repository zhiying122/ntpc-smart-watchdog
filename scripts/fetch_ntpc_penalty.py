"""
全新北市幼兒園裁罰紀錄抓取（獨立圖層 / Penalty Overlay）
======================================================================
從教育部「全國教保資訊網 - 教保服務機構裁罰查詢」抓取新北市所有幼兒園之
裁罰紀錄，存為獨立 CSV。此為「唯讀疊加圖層」：僅供在案件頁/名冊呈現真實
裁罰紀錄，**不覆寫**現有 kindergartens_latest.csv 已算好的風險分（安全做法）。

資料來源：https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx
  ASP.NET WebForms 查詢頁；以 __VIEWSTATE/__EVENTVALIDATION 模擬查詢與翻頁。
  縣市代碼：新北市 = "03"。

抓取策略：
  1. GET 取得初始 hidden 欄位。
  2. POST 查詢（ddlCityS=03，園名關鍵字留空 = 全部）。
  3. 解析當頁 GridView 各筆（園名/縣市/鄉鎮/設立別/地址/裁罰情形）。
  4. 若有「下一頁」則以 __doPostBack('PageControl1$lbNextPage','') 翻頁，
     直到無下一頁或達安全上限。

輸出：data/external/ntpc_penalty.csv
  欄位：park_name, city, area, pub_type, address, penalty_count, penalty_detail

用法：
    python scripts/fetch_ntpc_penalty.py
    python scripts/fetch_ntpc_penalty.py --offline   # 用既有 CSV，不連網
"""
from __future__ import annotations

import hashlib
import html as _html
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
import http.cookiejar

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx"
OUT_CSV = os.path.join(ROOT, "data", "external", "ntpc_penalty.csv")
NTPC_CITY_CODE = "03"
MAX_PAGES = 60  # 安全上限，避免意外無限翻頁

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ctx),
        urllib.request.HTTPCookieProcessor(cj))
    op.addheaders = [("User-Agent", "Mozilla/5.0"), ("Referer", URL)]
    return op


def _hidden(html: str, name: str) -> str:
    m = re.search(r'id="' + re.escape(name) + r'"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else ""


def _clean(s: str) -> str:
    """去標籤、解 HTML entity、壓縮空白。"""
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _parse_page(html: str) -> list[dict]:
    """解析當頁所有裁罰卡片。以 GridView1_lblSchName_N 為錨點切分每筆。"""
    rows = []
    anchors = list(re.finditer(r'id="GridView1_lblSchName_(\d+)"[^>]*>([^<]*)</span>', html))
    for i, a in enumerate(anchors):
        idx = a.group(1)
        name = _clean(a.group(2))
        # 該筆卡片範圍：本錨點到下一錨點之間
        start = a.start()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        card = html[start:end]

        def field(fid):
            m = re.search(r'id="GridView1_' + fid + "_" + idx + r'"[^>]*>(.*?)</span>',
                          card, re.S)
            return _clean(m.group(1)) if m else ""

        # 卡片清理後的純文字，供以「標籤：值」方式擷取無獨立 span 的欄位。
        text = _clean(card)

        def by_label(label, stop_labels):
            # 從 "label： 值 下一label" 擷取值
            pat = label + r"：\s*(.*?)\s*(?:" + "|".join(stop_labels) + r"|$)"
            m = re.search(pat, text)
            return m.group(1).strip() if m else ""

        city = field("lblCity") or by_label("縣市", ["鄉鎮", "設立別"])
        area = field("lblArea") or by_label("鄉鎮", ["設立別", "地址"])
        pub = field("lblPub") or by_label("設立別", ["地址", "電話"])
        tel = by_label("電話", ["核定人數", "營運狀態", "裁罰"])
        capacity = by_label("核定人數", ["營運狀態", "裁罰"])
        status = by_label("營運狀態", ["裁罰", "檢視"])
        # 地址在 <a id=...hlAddr...> 內
        ma = re.search(r'id="GridView1_hlAddr_' + idx + r'"[^>]*>(.*?)</a>', card, re.S)
        addr = _clean(ma.group(1)) if ma else by_label("地址", ["電話", "核定"])
        rows.append({
            "park_name": name, "city": city, "area": area, "pub_type": pub,
            "address": addr, "tel": tel, "capacity": capacity, "status": status,
        })
    return rows


def fetch_all() -> pd.DataFrame:
    op = _opener()
    html = op.open(URL, timeout=30).read().decode("utf-8", "replace")

    def form(extra):
        base = {
            "__VIEWSTATE": _hidden(html, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": _hidden(html, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": _hidden(html, "__EVENTVALIDATION"),
        }
        base.update(extra)
        return urllib.parse.urlencode(base).encode("utf-8")

    # 首次查詢：新北市全部
    body = form({"ddlKey": "school_name", "txtKeyNameS": "", "ddlCityS": NTPC_CITY_CODE,
                 "ddlAreaS": "", "btnSearch": "查詢"})
    html = op.open(urllib.request.Request(URL, data=body), timeout=40).read().decode("utf-8", "replace")

    all_rows: list[dict] = []
    seen_pages = set()
    for page in range(MAX_PAGES):
        rows = _parse_page(html)
        all_rows.extend(rows)
        # 循環偵測簽名：用整頁「所有欄位」的雜湊，而非僅園名序列。
        # （僅用園名易誤判：不同頁若園名序列碰巧相同會被當成循環而提早中止、
        #   漏抓後續頁。改用完整內容雜湊，唯有真正翻回同一頁才會命中。）
        sig = hashlib.md5(
            repr([sorted(r.items()) for r in rows]).encode("utf-8")
        ).hexdigest()
        print(f"  第 {page + 1} 頁：{len(rows)} 筆")
        # 是否有「下一頁」（未 disabled）
        has_next = re.search(r'id="PageControl1_lbNextPage"[^>]*__doPostBack', html)
        if not has_next or sig in seen_pages or not rows:
            break
        seen_pages.add(sig)
        # 翻頁：__doPostBack('PageControl1$lbNextPage','')
        body = form({"__EVENTTARGET": "PageControl1$lbNextPage", "__EVENTARGUMENT": "",
                     "ddlKey": "school_name", "txtKeyNameS": "",
                     "ddlCityS": NTPC_CITY_CODE, "ddlAreaS": ""})
        html = op.open(urllib.request.Request(URL, data=body), timeout=40).read().decode("utf-8", "replace")
        time.sleep(0.8)  # 禮貌延遲

    df = pd.DataFrame(all_rows).drop_duplicates(subset=["park_name"])
    return df.reset_index(drop=True)


def main():
    if "--offline" in sys.argv:
        if not os.path.exists(OUT_CSV):
            raise FileNotFoundError(f"離線模式找不到 {OUT_CSV}")
        df = pd.read_csv(OUT_CSV)
        print(f"[i] 離線：{len(df)} 筆")
        return df
    print("[i] 抓取新北市幼兒園裁罰紀錄…")
    df = fetch_all()
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[OK] 已寫入 {OUT_CSV}")
    print(f"     裁罰紀錄 {len(df)} 筆，涉及 {df['park_name'].nunique()} 間機構")
    return df


if __name__ == "__main__":
    main()
