"""
動態資料連接器（Live Data Connector）— 官方開放資料即時整合 + 離線備援
============================================================================
小小守護員 Smart Watchdog Platform — 對應題目痛點 1「資料分散與整合困難、
缺乏即時整合機制」。將系統從「靜態一次性資料」升級為「動態串接官方開放
資料源，含快取與離線備援」的整合平台。

資料源（皆為公開、免金鑰、直接 GET）：
--------------------------------------------------------------------------
  1. 幼兒園基本資料 / 收費 / 核定人數（GeoJSON，含經緯度）
     https://kiang.github.io/ap.ece.moe.edu.tw/preschools.json
  2. 全國裁罰紀錄（結構化 JSON）
     https://kiang.github.io/ap.ece.moe.edu.tw/punish_all.json

來源誠實標註（責任 AI / 資料治理）：
--------------------------------------------------------------------------
上述兩個 JSON 為 g0v 社群開發者江明宗（kiang）維護之「台灣幼兒園地圖」
開源專案所整理備份，原始資料來自「全國教保資訊網」（教育部）。屬**二手
整理資料**，非官方保證正確性之來源。系統一律標註：
  「資料來源：全國教保資訊網（教育部），經 g0v 開源專案（江明宗）整理備份」
並記錄抓取時間，供追溯與時效判斷。正式部署應改接官方 API（見
docs/data-integration-plan.md）。

政府級韌性設計（Security/Reliability by Design）：
--------------------------------------------------------------------------
  - 逾時保護：所有網路請求設定 timeout，避免無限等待。
  - 快取優先／離線備援：抓取成功即寫入本地快取；抓取失敗（無網路、來源
    異動、逾時）自動退回最近一次快取，系統**不因外部源失敗而中斷**。
  - 明確狀態回報：每次載入回報 FetchResult（是否即時、來源、抓取時間、
    是否用備援、錯誤訊息），供 UI 誠實顯示資料新鮮度。
  - 純標準庫網路層（urllib），不新增第三方相依；解析為純函式，可離線測試。

本模組不 import streamlit；UI 以 FetchResult 呈現資料狀態。
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# --------------------------------------------------------------------------
# 常數：資料源 URL、快取路徑、逾時
# --------------------------------------------------------------------------
PRESCHOOLS_URL = "https://kiang.github.io/ap.ece.moe.edu.tw/preschools.json"
PUNISH_URL = "https://kiang.github.io/ap.ece.moe.edu.tw/punish_all.json"

SOURCE_ATTRIBUTION = (
    "全國教保資訊網（教育部），經 g0v 開源專案（江明宗 kiang）整理備份"
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(_ROOT, "data", "cache")
PRESCHOOLS_CACHE = os.path.join(CACHE_DIR, "preschools.json")
PUNISH_CACHE = os.path.join(CACHE_DIR, "punish_all.json")

DEFAULT_TIMEOUT = 30  # 秒
_TARGET_CITY = "新北市"


# --------------------------------------------------------------------------
# 結果型別
# --------------------------------------------------------------------------
@dataclass
class FetchResult:
    """單次資料載入的狀態與結果（供 UI 誠實顯示資料新鮮度）。

    - data：解析後的原始資料（GeoJSON dict 或裁罰 dict）；失敗且無快取時為 None。
    - is_live：本次資料是否來自即時網路抓取（True）或離線快取備援（False）。
    - fetched_at：資料取得時間（ISO 字串，UTC）。即時抓取為當下；快取備援
      為快取檔的最後修改時間。
    - source_url：資料來源 URL。
    - attribution：來源標註字串（SOURCE_ATTRIBUTION）。
    - used_fallback：是否因即時抓取失敗而退回快取。
    - error：即時抓取失敗時的錯誤訊息（供診斷）；成功為 None。
    """
    data: Any = None
    is_live: bool = False
    fetched_at: str | None = None
    source_url: str = ""
    attribution: str = SOURCE_ATTRIBUTION
    used_fallback: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        """是否取得可用資料（即時或備援皆算）。"""
        return self.data is not None


@dataclass
class NormalizedInstitution:
    """正規化後的機構資料（新北市，對齊系統既有欄位語意）。"""
    park_id: str
    park_name: str
    park_type: str            # 公立/私立/非營利…（原 type 欄）
    district: str
    address: str
    owner: str                # 負責人（供裁罰比對）
    count_approved: int | None
    monthly: float | None     # 月收費（原 monthly 欄）
    lat: float | None
    lng: float | None
    penalty_flag: str         # 原始 penalty 欄（無/有）
    source_attribution: str = SOURCE_ATTRIBUTION
    raw: dict = field(default_factory=dict)


# --------------------------------------------------------------------------
# 網路抓取（含逾時保護）+ 快取寫入
# --------------------------------------------------------------------------
def _http_get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """對 url 發 GET 並解析 JSON。逾時/HTTP/解析錯誤皆丟出例外由上層處理。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Fiscalint/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        return json.loads(resp.read().decode(charset))


def _write_cache(path: str, data: Any) -> None:
    """將資料寫入快取（容錯：寫入失敗不得中斷主流程）。"""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
    except OSError:
        pass


def _read_cache(path: str) -> tuple[Any, str | None]:
    """讀取快取，回傳 (data, 快取檔最後修改時間 ISO)；不存在回傳 (None, None)。"""
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        mtime = datetime.fromtimestamp(
            os.path.getmtime(path), tz=timezone.utc).isoformat()
        return data, mtime
    except (OSError, json.JSONDecodeError):
        return None, None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url: str, cache_path: str,
               timeout: int = DEFAULT_TIMEOUT,
               prefer_cache: bool = False) -> FetchResult:
    """抓取 JSON，快取優先／離線備援（政府級韌性）。

    流程：
      - prefer_cache=True 且快取存在 → 直接用快取（離線 Demo 模式）。
      - 否則嘗試即時抓取；成功 → 寫快取並回傳 is_live=True。
      - 即時抓取失敗（無網路/逾時/來源異動）→ 退回快取，used_fallback=True，
        並附 error；若連快取也無 → data=None（由上層決定退回內建靜態資料）。
    """
    if prefer_cache:
        data, mtime = _read_cache(cache_path)
        if data is not None:
            return FetchResult(data=data, is_live=False, fetched_at=mtime,
                               source_url=url, used_fallback=False)

    try:
        data = _http_get_json(url, timeout=timeout)
        _write_cache(cache_path, data)
        return FetchResult(data=data, is_live=True, fetched_at=_now_iso(),
                           source_url=url, used_fallback=False)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        data, mtime = _read_cache(cache_path)
        if data is not None:
            return FetchResult(data=data, is_live=False, fetched_at=mtime,
                               source_url=url, used_fallback=True,
                               error=f"即時抓取失敗，已退回離線快取：{exc}")
        return FetchResult(data=None, is_live=False, fetched_at=None,
                           source_url=url, used_fallback=True,
                           error=f"即時抓取失敗且無可用快取：{exc}")


# --------------------------------------------------------------------------
# 解析／正規化（純函式，可離線測試）
# --------------------------------------------------------------------------
def _to_int(v: Any) -> int | None:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _to_float(v: Any) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_preschools(geojson: Any, city: str = _TARGET_CITY
                     ) -> list[NormalizedInstitution]:
    """將 preschools GeoJSON 解析為指定縣市的正規化機構清單。

    - 僅保留 properties.city == city 的機構。
    - 經緯度取自 geometry.coordinates（GeoJSON 為 [lng, lat]）。
    - 空值安全：缺欄位以 None／空字串處理，不中斷整批解析。
    """
    out: list[NormalizedInstitution] = []
    if not isinstance(geojson, dict):
        return out
    for feat in geojson.get("features", []):
        if not isinstance(feat, dict):
            continue
        p = feat.get("properties", {}) or {}
        if p.get("city") != city:
            continue
        geom = feat.get("geometry", {}) or {}
        coords = geom.get("coordinates") if isinstance(geom, dict) else None
        lng = lat = None
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lng = _to_float(coords[0])
            lat = _to_float(coords[1])
        out.append(NormalizedInstitution(
            park_id=str(p.get("id") or p.get("reg_no") or ""),
            park_name=str(p.get("title") or ""),
            park_type=str(p.get("type") or ""),
            district=str(p.get("town") or ""),
            address=str(p.get("address") or ""),
            owner=str(p.get("owner") or ""),
            count_approved=_to_int(p.get("count_approved")),
            monthly=_to_float(p.get("monthly")),
            lat=lat, lng=lng,
            penalty_flag=str(p.get("penalty") or ""),
            raw=p,
        ))
    return out


@dataclass
class PenaltyRecord:
    """單筆裁罰紀錄（正規化）。"""
    subject: str          # 受處分對象（行為人/負責人名稱）
    subject_type: str     # 行為人 / 負責人 / 其他
    date: str
    law: str
    punishment: str
    record_id: str
    source_attribution: str = SOURCE_ATTRIBUTION


def parse_penalties(punish: Any) -> list[PenaltyRecord]:
    """將 punish_all JSON 解析為裁罰紀錄清單。

    原始結構：{ "行為人：名稱" 或 "負責人：名稱": [ {date, law, punishment, id}, ... ] }
    subject_type 取自 key 的前綴（冒號前），subject 取冒號後名稱。
    """
    out: list[PenaltyRecord] = []
    if not isinstance(punish, dict):
        return out
    for key, records in punish.items():
        if "：" in key:
            stype, _, sname = key.partition("：")
        else:
            stype, sname = "其他", key
        if not isinstance(records, list):
            continue
        for rec in records:
            if not isinstance(rec, dict):
                continue
            out.append(PenaltyRecord(
                subject=sname.strip(),
                subject_type=stype.strip(),
                date=str(rec.get("date") or ""),
                law=str(rec.get("law") or ""),
                punishment=str(rec.get("punishment") or ""),
                record_id=str(rec.get("id") or ""),
            ))
    return out


# --------------------------------------------------------------------------
# 便利入口：載入新北市機構 + 裁罰（含備援）
# --------------------------------------------------------------------------
@dataclass
class LiveDataset:
    """一次載入的完整動態資料集（機構 + 裁罰 + 各自狀態）。"""
    institutions: list[NormalizedInstitution]
    penalties: list[PenaltyRecord]
    institutions_status: FetchResult
    penalties_status: FetchResult

    @property
    def is_live(self) -> bool:
        """兩個資料源是否皆為即時抓取（任一使用備援即為 False）。"""
        return self.institutions_status.is_live and self.penalties_status.is_live


def load_live_dataset(city: str = _TARGET_CITY,
                      timeout: int = DEFAULT_TIMEOUT,
                      prefer_cache: bool = False) -> LiveDataset:
    """載入指定縣市的機構與裁罰資料（即時優先、離線備援）。

    此為 UI「同步最新資料」按鈕的後端入口：即時抓取兩個官方開放資料源，
    解析並篩出指定縣市，回傳含狀態的 LiveDataset。任一源抓取失敗會自動
    退回快取，確保 Demo 不中斷。
    """
    ins_status = fetch_json(PRESCHOOLS_URL, PRESCHOOLS_CACHE,
                            timeout=timeout, prefer_cache=prefer_cache)
    pen_status = fetch_json(PUNISH_URL, PUNISH_CACHE,
                            timeout=timeout, prefer_cache=prefer_cache)
    institutions = parse_preschools(ins_status.data, city=city) if ins_status.ok else []
    penalties = parse_penalties(pen_status.data) if pen_status.ok else []
    return LiveDataset(
        institutions=institutions,
        penalties=penalties,
        institutions_status=ins_status,
        penalties_status=pen_status,
    )
