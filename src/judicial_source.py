"""
司法院裁判書連接器（Judicial Source Connector）— 事實層（L2 JUDICIAL）
============================================================================
小小守護員 Smart Watchdog Platform — 以機構名比對司法院公開裁判書／行政處分，
作為「事實層」風險訊號（tier=fact 者可支持正式風險判讀，非社群輿情）。

可信度分層（對齊 multi_source 的 tier 設計，責任 AI）：
--------------------------------------------------------------------------
  - 判決／處分「確定」→ tier=FACT（事實，可支持稽查判讀）。
  - 偵查／起訴／審理中 → tier=EVENT（過程訊號，不等於有罪）。
  「被檢舉 ≠ 被調查 ≠ 被起訴 ≠ 被判決有罪」——階段嚴格區分，絕不以起訴中
  案件作為違法認定（R19 責任 AI）。

抓取能力與合規（誠實揭露，對齊 data_source_matrix / collector_registry）：
--------------------------------------------------------------------------
  司法院裁判書公開查詢（judgment.judicial.gov.tw）為 ASP.NET WebForm，需
  ViewState + session + POST，非穩定可即時爬取；本連接器提供**標準查詢介面**
  與**離線結構化資料**（data/raw/judicial_records.json，自公開判決整理之樣本），
  確保計分與 Demo 可跑，且誠實標示為「官方公開查詢，架構可接官方 API/開放資料」，
  不誇稱即時全量爬取。正式部署以司法院開放資料或授權 API 介接。

本模組僅依賴標準庫（json/os/dataclass），維持既有基線可攜性。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_PATH = os.path.join(_ROOT, "data", "raw", "judicial_records.json")

JUDICIAL_QUERY_URL = "https://judgment.judicial.gov.tw/FJUD/default.aspx"

# 階段 → tier（沿用 multi_source 的司法階段判定精神）。
STAGE_FACT = ("判決確定", "有罪確定", "處分確定", "裁罰確定", "定讞")
STAGE_PROCESS = ("偵查", "起訴", "審理中", "檢舉", "調查", "上訴中", "繫屬中")

TIER_FACT = "fact"
TIER_EVENT = "event"


@dataclass
class JudicialRecord:
    """單筆司法／行政處分紀錄（正規化）。"""
    park_name_match: str      # 機構名比對鍵（子字串比對）
    title: str                # 案由／處分摘要
    stage: str                # 司法階段（判決確定／起訴／偵查…）
    tier: str                 # fact / event（依 stage 判定）
    court: str                # 法院／處分機關
    case_no: str              # 字號
    date: str                 # 日期
    url: str                  # 原始連結（可追溯）
    is_demo_sample: bool = True
    collection_method: str = "official_api"  # 官方公開查詢


def _resolve_tier(stage: str) -> str:
    """依司法階段判定 tier：確定=fact，其餘（偵查/起訴/審理中）=event。"""
    s = (stage or "").strip()
    if any(k in s for k in STAGE_FACT):
        return TIER_FACT
    return TIER_EVENT


def load_records(data_path: str | None = None) -> list[JudicialRecord]:
    """載入司法紀錄結構化資料；缺檔/格式錯誤 → 空清單（優雅降級）。"""
    path = data_path or DEFAULT_DATA_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    out: list[JudicialRecord] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        stage = str(it.get("stage", "")).strip()
        out.append(JudicialRecord(
            park_name_match=str(it.get("park_name_match", "")).strip(),
            title=str(it.get("title", "")).strip(),
            stage=stage,
            tier=_resolve_tier(stage),
            court=str(it.get("court", "")).strip(),
            case_no=str(it.get("case_no", "")).strip(),
            date=str(it.get("date", "")).strip(),
            url=str(it.get("url", "")).strip(),
            is_demo_sample=bool(it.get("is_demo_sample", True)),
            collection_method=str(it.get("collection_method", "official_api")).strip(),
        ))
    return out


def query(park_name: str, data_path: str | None = None) -> list[JudicialRecord]:
    """查詢某機構的司法／行政處分紀錄（以名稱子字串比對）。

    回傳該機構適用的紀錄清單（含 tier 標記）。無紀錄回空清單。
    正式部署可將本函式改為對司法院開放資料/授權 API 的即時查詢，介面不變。
    """
    name = (park_name or "").strip()
    if not name:
        return []
    out = []
    for rec in load_records(data_path):
        key = rec.park_name_match
        if key and (key in name or name in key):
            out.append(rec)
    return out


def fact_flag(park_name: str, data_path: str | None = None) -> bool:
    """該機構是否有「確定」的司法／行政處分事實（tier=fact）。

    供風險判讀參考：有確定處分事實者，屬事實層強訊號（非輿情）。
    """
    return any(r.tier == TIER_FACT for r in query(park_name, data_path))
