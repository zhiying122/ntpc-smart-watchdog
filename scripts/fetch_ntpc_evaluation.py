"""
全新北市幼兒園基礎評鑑結果抓取
======================================================================
從教育部「全國教保資訊網 - 評鑑結果查詢」抓取新北市已接受基礎評鑑之機構，
寫入 data/external/ntpc_evaluation.csv，供 8602 公眾查詢網合併公開評鑑狀態。

資料來源：https://ap.ece.moe.edu.tw/webecems/evaSearch.aspx
"""
from __future__ import annotations

import argparse
import html as _html
import http.cookiejar
import os
import re
import ssl
import time
import urllib.parse
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://ap.ece.moe.edu.tw/webecems/evaSearch.aspx"
OUT_CSV = os.path.join(ROOT, "data", "external", "ntpc_evaluation.csv")
NTPC_CITY_CODE = "03"
MAX_PAGES = 200

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _opener():
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=_ctx),
        urllib.request.HTTPCookieProcessor(cj),
    )
    op.addheaders = [("User-Agent", "Mozilla/5.0"), ("Referer", URL)]
    return op


def _hidden(html: str, name: str) -> str:
    m = re.search(r'id="' + re.escape(name) + r'"[^>]*value="([^"]*)"', html)
    return m.group(1) if m else ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _normalize_grade(result: str) -> str:
    r = (result or "").strip()
    if not r:
        return ""
    if "不通過" in r:
        return "不通過"
    if "部分" in r and "通過" in r:
        return "部分通過"
    if "通過" in r:
        return "通過"
    for g in ("優", "甲", "良", "乙", "中", "丙", "待改進"):
        if g in r:
            return g
    return r[:40]


def _parse_page(html: str) -> list[dict]:
    rows: list[dict] = []
    anchors = list(
        re.finditer(r'id="GridView1_lblSchName_(\d+)"[^>]*>([^<]*)</span>', html)
    )
    for i, a in enumerate(anchors):
        idx = a.group(1)
        name = _clean(a.group(2))
        start = a.start()
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(html)
        card = html[start:end]

        def field(fid: str) -> str:
            m = re.search(
                rf'id="GridView1_{fid}_{idx}"[^>]*>(.*?)</(?:span|a)>',
                card,
                re.S,
            )
            return _clean(m.group(1)) if m else ""

        years = re.findall(
            rf'id="GridView1_GridView11_{idx}_lblSYear_(\d+)"[^>]*>([^<]*)</span>',
            card,
        )
        dates = {
            m.group(1): _clean(m.group(2))
            for m in re.finditer(
                rf'id="GridView1_GridView11_{idx}_lblDate_(\d+)"[^>]*>([^<]*)</span>',
                card,
            )
        }
        results = {
            m.group(1): _clean(m.group(2))
            for m in re.finditer(
                rf'id="GridView1_GridView11_{idx}_lblResult_(\d+)"[^>]*>([^<]*)</span>',
                card,
            )
        }
        eval_year = eval_date = eval_result = ""
        if years:
            y_idx, eval_year = years[0][0], _clean(years[0][1])
            eval_date = dates.get(y_idx, "")
            eval_result = results.get(y_idx, "")
        elif results:
            first_key = next(iter(results))
            eval_result = results[first_key]
            eval_date = dates.get(first_key, "")

        ma = re.search(rf'id="GridView1_hlAddr_{idx}"[^>]*>(.*?)</a>', card, re.S)
        addr = _clean(ma.group(1)) if ma else ""

        rows.append(
            {
                "park_name": name,
                "city": field("lblCity"),
                "area": field("lblArea"),
                "pub_type": field("lblPub"),
                "address": addr,
                "eval_year": eval_year,
                "eval_date": eval_date,
                "eval_result": eval_result,
                "eval_grade": _normalize_grade(eval_result),
                "eval_status": "已接受評鑑",
            }
        )
    return rows


def fetch_all(result_filter: str = "1") -> pd.DataFrame:
    op = _opener()
    html = op.open(URL, timeout=40).read().decode("utf-8", "replace")

    def form(extra: dict) -> bytes:
        base = {
            "__VIEWSTATE": _hidden(html, "__VIEWSTATE"),
            "__VIEWSTATEGENERATOR": _hidden(html, "__VIEWSTATEGENERATOR"),
            "__EVENTVALIDATION": _hidden(html, "__EVENTVALIDATION"),
            "__VIEWSTATEENCRYPTED": _hidden(html, "__VIEWSTATEENCRYPTED"),
        }
        base.update(extra)
        return urllib.parse.urlencode(base).encode("utf-8")

    body = form(
        {
            "txtSchNameS": "",
            "ddlCityS": NTPC_CITY_CODE,
            "ddlAreaS": "",
            "ddlEResult": result_filter,
            "btnSearch": "查詢",
        }
    )
    html = op.open(urllib.request.Request(URL, data=body), timeout=60).read().decode(
        "utf-8", "replace"
    )

    all_rows: list[dict] = []
    seen_pages: set[tuple] = set()
    for page in range(MAX_PAGES):
        rows = _parse_page(html)
        all_rows.extend(rows)
        sig = tuple(r["park_name"] for r in rows)
        print(f"  第 {page + 1} 頁：{len(rows)} 筆（累計 {len(all_rows)}）")
        has_next = re.search(r'id="PageControl1_lbNextPage"[^>]*__doPostBack', html)
        if not has_next or sig in seen_pages or not rows:
            break
        seen_pages.add(sig)
        body = form(
            {
                "__EVENTTARGET": "PageControl1$lbNextPage",
                "__EVENTARGUMENT": "",
                "txtSchNameS": "",
                "ddlCityS": NTPC_CITY_CODE,
                "ddlAreaS": "",
                "ddlEResult": result_filter,
            }
        )
        html = op.open(urllib.request.Request(URL, data=body), timeout=60).read().decode(
            "utf-8", "replace"
        )
        time.sleep(0.6)

    df = pd.DataFrame(all_rows)
    if df.empty:
        return df
    df["_y"] = pd.to_numeric(df["eval_year"], errors="coerce").fillna(-1)
    df = (
        df.sort_values(["park_name", "_y"], ascending=[True, False])
        .drop_duplicates(subset=["park_name"], keep="first")
        .drop(columns=["_y"])
        .reset_index(drop=True)
    )
    return df


def main(argv: list[str] | None = None) -> pd.DataFrame:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args(argv)

    if args.offline:
        if not os.path.exists(OUT_CSV):
            raise FileNotFoundError(f"離線模式找不到 {OUT_CSV}")
        df = pd.read_csv(OUT_CSV)
        print(f"[i] 離線：{len(df)} 筆")
        return df

    filt = "" if args.all else "1"
    label = "全部" if args.all else "已接受評鑑"
    print(f"[i] 抓取新北市幼兒園評鑑結果（{label}）…")
    df = fetch_all(result_filter=filt)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[OK] 已寫入 {OUT_CSV}")
    print(f"     {len(df)} 間機構")
    if "eval_grade" in df.columns and not df.empty:
        print(df["eval_grade"].value_counts().to_string())
    return df


if __name__ == "__main__":
    main()
