"""
全新北市立案幼兒園名冊抓取與整合（廣度層 / Roster Overlay）
======================================================================
自動從「新北市政府資料開放平台」抓取全市立案幼兒園名冊（約 1,100+ 間、
涵蓋 29 個行政區），與現有已評分的機構（kindergartens_latest.csv，具真實
財務決算的抽樣）合併成「全市涵蓋層」。

設計原則（對齊 project-vision 的抽樣可規模化策略）：
  - 深度層（scored）：現有 latest.csv 的機構，具真實鑑識會計風險分——不動。
  - 廣度層（roster_only）：其餘全市機構，只有基本資料（名稱/類型/行政區/
    地址/電話），財務/風險分為空，明確標示 data_status="roster_only"
    （待接入財務資料），誠實不造假。

輸出：data/processed/kindergartens_roster.csv
  欄位：park_id, park_name, park_type, district, address, tel, lat, lng,
        data_status（scored / roster_only）, risk_total, risk_level
  （scored 者帶入其真實風險分；roster_only 者風險欄位留空。）

座標策略：全市 1,100+ 間逐一上 Nominatim 不切實際（限流 + 耗時），故
roster_only 者採「行政區中心座標 + 小幅抖動」定位（供地圖涵蓋展示）；
scored 者沿用其既有精確座標。此為誠實的展示定位，非精確地址座標。

用法：
    python scripts/fetch_ntpc_roster.py            # 線上抓取最新名冊
    python scripts/fetch_ntpc_roster.py --offline  # 用既有快取檔（不連網）
"""
from __future__ import annotations

import hashlib
import io
import os
import ssl
import sys
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from src.geocode import DISTRICT_CENTER  # noqa: E402
from src.risk_score import score  # noqa: E402  # 白盒單一計分來源

# 新北市政府資料開放平台：公私立立案幼兒園資料（CSV 直接下載端點）
NTPC_ROSTER_URL = (
    "https://data.ntpc.gov.tw/api/datasets/"
    "f563b4cd-b850-41f5-9709-b910f2d147e9/csv/file"
)
RAW_CACHE = os.path.join(ROOT, "data", "external", "ntpc_roster_raw.csv")
LATEST_CSV = os.path.join(ROOT, "data", "processed", "kindergartens_latest.csv")
OUT_CSV = os.path.join(ROOT, "data", "processed", "kindergartens_roster.csv")

# 補齊 geocode 未列的行政區中心（貢寮/雙溪/平溪/坪林/石碇/石門/皆為東北/山區）
_EXTRA_CENTER = {
    "貢寮區": (25.0224, 121.9080), "雙溪區": (25.0335, 121.8660),
    "平溪區": (25.0257, 121.7380), "坪林區": (24.9370, 121.7110),
    "石碇區": (24.9917, 121.6580), "石門區": (25.2905, 121.5680),
}
CENTER = {**DISTRICT_CENTER, **_EXTRA_CENTER}
# 全市預設中心（板橋），任何未知行政區的最終 fallback。
_DEFAULT_CENTER = (25.0117, 121.4593)


def _fetch_raw(online: bool) -> pd.DataFrame:
    """抓取（或讀取快取）新北市立案幼兒園原始名冊。"""
    if online:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(NTPC_ROSTER_URL,
                                     headers={"User-Agent": "ntpc-smart-watchdog/1.0"})
        raw = urllib.request.urlopen(req, timeout=40, context=ctx).read()
        os.makedirs(os.path.dirname(RAW_CACHE), exist_ok=True)
        with open(RAW_CACHE, "wb") as fh:
            fh.write(raw)
        print(f"[OK] 已下載最新名冊 → {RAW_CACHE}（{len(raw)} bytes）")
        return pd.read_csv(io.BytesIO(raw), encoding="utf-8-sig")
    if not os.path.exists(RAW_CACHE):
        raise FileNotFoundError(
            f"離線模式找不到快取 {RAW_CACHE}，請先線上執行一次。")
    print(f"[i] 離線模式：使用既有快取 {RAW_CACHE}")
    return pd.read_csv(RAW_CACHE, encoding="utf-8-sig")


import re  # noqa: E402


def _norm_name(name) -> str:
    """正規化園名以利深度層/廣度層比對。

    名冊的非營利園名帶「(委託○○基金會辦理)」尾註、公立園有「立」字、
    另有全形括號差異等。此處去除括號附註與常見雜訊字，取核心園名比對，
    降低因命名格式差異導致對應失敗。
    """
    s = "" if pd.isna(name) else str(name).strip()
    # 去除中英文括號及其內容（委託辦理單位附註）
    s = re.sub(r"[（(].*?[）)]", "", s)
    # 去除常見前綴/雜訊字，只留核心園名
    for junk in ("新北市政府", "新北市", "私立", "市立", "立", "　", " "):
        s = s.replace(junk, "")
    return s.strip()


def _clean_address(addr) -> str:
    """去除地址前的郵遞區號標記 [220] 等，回傳乾淨地址字串。"""
    s = "" if pd.isna(addr) else str(addr).strip()
    if s.startswith("[") and "]" in s:
        s = s.split("]", 1)[1].strip()
    return s


def _jitter(base: float, seed: str, scale: float = 0.012) -> float:
    """依名稱雜湊產生穩定、小幅的座標抖動，讓同區多點不重疊（確定性）。"""
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:8], 16)
    frac = (h % 1000) / 1000.0 - 0.5  # -0.5 ~ 0.5
    return base + frac * scale


def _roster_coord(name: str, district: str) -> tuple[float, float]:
    """roster_only 機構的展示座標：行政區中心 + 依名稱穩定抖動。"""
    base = CENTER.get(str(district), _DEFAULT_CENTER)
    return (_jitter(base[0], name + "lat"), _jitter(base[1], name + "lng"))


def build() -> pd.DataFrame:
    online = "--offline" not in sys.argv
    raw = _fetch_raw(online)
    # 原始欄位：type, district, areacode, title, tel, zipcode, address
    raw = raw.rename(columns={"type": "park_type", "title": "park_name"})
    raw["park_name"] = raw["park_name"].astype(str).str.strip()
    raw["district"] = raw["district"].astype(str).str.strip()
    raw["address"] = raw["address"].map(_clean_address)
    raw = raw.drop_duplicates(subset=["park_name"]).reset_index(drop=True)
    print(f"[i] 全市名冊：{len(raw)} 間、{raw['district'].nunique()} 個行政區")

    # 載入已評分機構（深度層），以「正規化園名」為鍵對應。
    scored = pd.read_csv(LATEST_CSV)
    scored_by_key = {}
    for _, r in scored.iterrows():
        scored_by_key[_norm_name(str(r["park_name"]))] = r
    print(f"[i] 已評分機構（深度層）：{len(scored)} 間")

    # 載入全國教保資訊網真實裁罰（ntpc_penalty.csv），供行為監測園（behavioral）計分
    pen_csv = os.path.join(ROOT, "data", "external", "ntpc_penalty.csv")
    pen_by_key = {}
    if os.path.exists(pen_csv):
        pen_df = pd.read_csv(pen_csv)
        for _, pr in pen_df.iterrows():
            pen_by_key[_norm_name(str(pr["park_name"]))] = pr
        print(f"[i] 全國教保資訊網裁罰紀錄：{len(pen_by_key)} 間機構有案")

    rows = []
    used_scored_keys = set()

    # (1) 先放名冊中的機構：
    #     - 能對應到已評分者標 scored（沿用深度層真實財務與裁罰分數）
    #     - 對應到真實裁罰者標 scored，套用行為監測檔（behavioral：裁罰50%+評鑑30%+輿情20%）進行計算
    #     - 其餘標 roster_only（僅基本資料、無裁罰與財報者風險留空）。
    for i, r in raw.iterrows():
        name = r["park_name"]
        district = r["district"]
        ptype = str(r.get("park_type", "")).strip()
        addr = r["address"]
        tel = "" if pd.isna(r.get("tel")) else str(r.get("tel")).strip()

        key = _norm_name(name)
        srow = scored_by_key.get(key)
        prow = pen_by_key.get(key)

        if srow is not None:
            used_scored_keys.add(key)
            lat = srow.get("lat")
            lng = srow.get("lng")
            if pd.isna(lat) or pd.isna(lng):
                lat, lng = _roster_coord(name, district or srow.get("district", ""))
            rows.append({
                "park_id": srow.get("park_id"),
                "park_name": name,
                "park_type": ptype or srow.get("park_type", ""),
                "district": district or srow.get("district", ""),
                "address": addr, "tel": tel, "lat": lat, "lng": lng,
                "data_status": "scored",
                "risk_total": srow.get("risk_total"),
                "risk_level": srow.get("risk_level"),
                "scoring_profile": srow.get("scoring_profile", "forensic"),
                "score_penalty": srow.get("score_penalty"),
                "penalty_count": srow.get("penalty_count", 0),
            })
        elif prow is not None:
            # 命中真實裁罰名單但無財報：套用 behavioral 行為評分檔。
            # 【單一計分來源】裁罰基底分與總分/等級一律走白盒 score()（behavioral
            # 三分項：裁罰0.50/評鑑0.30/輿情0.20），不在此手算，確保未來調整
            # PROFILE_WEIGHTS 時本路徑自動同步、可解釋性一致（避免雙套計分）。
            lat, lng = _roster_coord(name, district)
            pstatus = str(prow.get("status", "") or "")
            is_revoked = "廢止" in pstatus
            # 裁罰嚴重度：廢止許可屬情節重大(95)，一般公告裁罰(65)；次數為代理。
            p_score = 95.0 if is_revoked else 65.0
            p_cnt = 3 if is_revoked else 1
            breakdown = score(
                {"score_penalty": p_score},
                profile="behavioral",
            )
            b_total = breakdown.total
            b_level = "高" if b_total >= 60 else ("中" if b_total >= 35 else "低")
            rows.append({
                "park_id": f"P{i:04d}",
                "park_name": name,
                "park_type": ptype or prow.get("pub_type", "私立"),
                "district": district or prow.get("area", ""),
                "address": addr or prow.get("address", ""),
                "tel": tel or prow.get("tel", ""),
                "lat": lat, "lng": lng,
                "data_status": "roster_only",
                "risk_total": b_total,
                "risk_level": b_level,
                "scoring_profile": "behavioral",
                "score_penalty": p_score,
                "penalty_count": p_cnt,
            })
        else:
            lat, lng = _roster_coord(name, district)
            rows.append({
                "park_id": f"R{i:04d}",
                "park_name": name, "park_type": ptype, "district": district,
                "address": addr, "tel": tel, "lat": lat, "lng": lng,
                "data_status": "roster_only", "risk_total": pd.NA, "risk_level": pd.NA,
                "scoring_profile": "behavioral",
                "score_penalty": 0.0,
                "penalty_count": 0,
            })

    # (2) 反向補位：名冊未涵蓋到的已評分機構（少數命名對不上者），仍保底納入，
    #     確保 61 間深度層機構「一間都不漏」，且不與名冊重複。
    for _, srow in scored.iterrows():
        key = _norm_name(str(srow["park_name"]))
        if key in used_scored_keys:
            continue
        used_scored_keys.add(key)
        lat = srow.get("lat")
        lng = srow.get("lng")
        district = "" if pd.isna(srow.get("district")) else str(srow.get("district"))
        if pd.isna(lat) or pd.isna(lng):
            lat, lng = _roster_coord(str(srow["park_name"]), district)
        rows.append({
            "park_id": srow.get("park_id"),
            "park_name": srow["park_name"],
            "park_type": srow.get("park_type", ""),
            "district": district, "address": "", "tel": "",
            "lat": lat, "lng": lng, "data_status": "scored",
            "risk_total": srow.get("risk_total"), "risk_level": srow.get("risk_level"),
            "scoring_profile": srow.get("scoring_profile", "forensic"),
            "score_penalty": srow.get("score_penalty"),
            "penalty_count": srow.get("penalty_count", 0),
        })

    n_matched = sum(1 for r in rows if r["data_status"] == "scored")

    out = pd.DataFrame(rows)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[OK] 已寫入 {OUT_CSV}")
    print(f"     總計 {len(out)} 間：已評分(scored) {n_matched}、"
          f"待接入(roster_only) {len(out) - n_matched}")
    print(f"     涵蓋行政區：{out['district'].nunique()} 個")
    return out


if __name__ == "__main__":
    build()
