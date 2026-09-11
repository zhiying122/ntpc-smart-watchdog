"""
系統健康檢查（System Health Check）— 維運監控
============================================================================
小小守護員 Smart Watchdog Platform — 提供維運人員檢視系統各組件與資料源的
健康狀態，屬政府級系統上線後的必要監控能力（Operability by Design）。

檢查項目：
  - 契約資料檔存在性與新鮮度（最後更新距今天數）。
  - 動態資料源快取狀態（是否有快取、快取時間）。
  - 核心風險引擎模組可載入性（import 健檢）。
  - 資料完整性（關鍵欄位是否齊備、筆數）。

本模組為純邏輯、不 import streamlit，可離線測試；不對外部來源即時發網路
請求（避免健檢本身拖慢或失敗），僅檢視本地狀態。網路源的即時檢測由
live_source 於使用者觸發同步時進行並回報。
"""
from __future__ import annotations

import importlib
import os
import time
from dataclasses import dataclass, field

# 健康狀態常數（對齊 UI 語意色）
OK = "正常"
WARN = "注意"
ERROR = "異常"

_STATUS_ORDER = {OK: 0, WARN: 1, ERROR: 2}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROC = os.path.join(_ROOT, "data", "processed")
_CACHE = os.path.join(_ROOT, "data", "cache")

LATEST_CSV = os.path.join(_PROC, "kindergartens_latest.csv")
PRESCHOOLS_CACHE = os.path.join(_CACHE, "preschools.json")
PUNISH_CACHE = os.path.join(_CACHE, "punish_all.json")

# 資料新鮮度門檻（天）：超過即警示。
DATA_STALE_WARN_DAYS = 90
CACHE_STALE_WARN_DAYS = 30

# 核心引擎模組（import 健檢）。
_CORE_MODULES = (
    "src.forensic", "src.risk_score", "src.anomaly", "src.peer",
    "src.timeline", "src.evidence", "src.alert", "src.allocation",
    "src.simulation", "src.kpi", "src.audit", "src.confidence",
    "src.nlp_engine", "src.ai_report", "src.live_source", "src.penalty_match",
)


@dataclass
class HealthItem:
    """單一健康檢查項目。"""
    name: str
    status: str            # OK / WARN / ERROR
    detail: str
    category: str = "一般"


@dataclass
class HealthReport:
    """整體健康報告。"""
    items: list[HealthItem] = field(default_factory=list)

    @property
    def overall(self) -> str:
        """整體狀態＝所有項目中最嚴重者。"""
        if not self.items:
            return WARN
        worst = max(self.items, key=lambda i: _STATUS_ORDER.get(i.status, 1))
        return worst.status

    def counts(self) -> dict[str, int]:
        c = {OK: 0, WARN: 0, ERROR: 0}
        for it in self.items:
            c[it.status] = c.get(it.status, 0) + 1
        return c


# ---------------------------------------------------------------------------
# 檢查輔助
# ---------------------------------------------------------------------------
def _age_days(path: str) -> float | None:
    """檔案最後修改距今天數；不存在回傳 None。"""
    if not os.path.exists(path):
        return None
    return (time.time() - os.path.getmtime(path)) / 86400.0


def _mtime_str(path: str) -> str:
    if not os.path.exists(path):
        return "—"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(path)))


def check_contract_data() -> HealthItem:
    """檢查主契約資料檔存在性與新鮮度。"""
    age = _age_days(LATEST_CSV)
    if age is None:
        return HealthItem(
            name="契約資料檔", status=ERROR, category="資料",
            detail="找不到 data/processed/kindergartens_latest.csv，系統無法載入。")
    if age > DATA_STALE_WARN_DAYS:
        return HealthItem(
            name="契約資料檔", status=WARN, category="資料",
            detail=f"資料檔已 {age:.0f} 天未更新（>{DATA_STALE_WARN_DAYS} 天），"
                   f"最後更新 {_mtime_str(LATEST_CSV)}。建議重新產生。")
    return HealthItem(
        name="契約資料檔", status=OK, category="資料",
        detail=f"存在且新鮮（{age:.0f} 天內），最後更新 {_mtime_str(LATEST_CSV)}。")


def check_cache(path: str, label: str) -> HealthItem:
    """檢查動態資料源快取狀態。"""
    age = _age_days(path)
    if age is None:
        return HealthItem(
            name=f"{label} 快取", status=WARN, category="動態資料源",
            detail="尚無本地快取。首次「同步最新資料」後將建立，供離線備援。")
    if age > CACHE_STALE_WARN_DAYS:
        return HealthItem(
            name=f"{label} 快取", status=WARN, category="動態資料源",
            detail=f"快取已 {age:.0f} 天（>{CACHE_STALE_WARN_DAYS} 天），"
                   f"最後同步 {_mtime_str(path)}。建議重新同步。")
    return HealthItem(
        name=f"{label} 快取", status=OK, category="動態資料源",
        detail=f"快取新鮮（{age:.0f} 天內），最後同步 {_mtime_str(path)}。")


def check_core_modules() -> list[HealthItem]:
    """逐一 import 核心引擎模組，回報可載入性。"""
    items: list[HealthItem] = []
    for mod in _CORE_MODULES:
        try:
            importlib.import_module(mod)
            items.append(HealthItem(
                name=mod, status=OK, category="核心引擎", detail="模組可正常載入。"))
        except Exception as exc:  # noqa: BLE001 - 健檢須捕捉所有載入錯誤
            items.append(HealthItem(
                name=mod, status=ERROR, category="核心引擎",
                detail=f"模組載入失敗：{exc}"))
    return items


def check_data_integrity(df=None) -> HealthItem:
    """檢查資料完整性（關鍵欄位與筆數）。df 為 None 時嘗試自契約檔載入。"""
    try:
        if df is None:
            import pandas as pd
            if not os.path.exists(LATEST_CSV):
                return HealthItem(
                    name="資料完整性", status=ERROR, category="資料",
                    detail="無契約資料檔可檢查。")
            df = pd.read_csv(LATEST_CSV)
        required = ["park_id", "park_name", "risk_total", "risk_level"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            return HealthItem(
                name="資料完整性", status=ERROR, category="資料",
                detail=f"缺少關鍵欄位：{missing}。")
        if len(df) == 0:
            return HealthItem(
                name="資料完整性", status=ERROR, category="資料",
                detail="資料筆數為 0。")
        return HealthItem(
            name="資料完整性", status=OK, category="資料",
            detail=f"關鍵欄位齊備，共 {len(df)} 筆機構。")
    except Exception as exc:  # noqa: BLE001
        return HealthItem(
            name="資料完整性", status=ERROR, category="資料",
            detail=f"完整性檢查發生錯誤：{exc}")


def run_health_check(df=None) -> HealthReport:
    """執行完整健康檢查，回傳 HealthReport。"""
    report = HealthReport()
    report.items.append(check_contract_data())
    report.items.append(check_data_integrity(df))
    report.items.append(check_cache(PRESCHOOLS_CACHE, "機構基本資料"))
    report.items.append(check_cache(PUNISH_CACHE, "裁罰紀錄"))
    report.items.extend(check_core_modules())
    return report
