"""
稽查派工決策台 — 呈現無關橋接層（Dispatch Decision Desk / bridge）
====================================================================
小小守護員 Smart Watchdog Platform — 將既有資料集橋接到後端兩大決策引擎：
  - src.allocation：智慧稽查分派最佳化（風險覆蓋最大化 + 確定性 tie-break，R3）
  - src.simulation：What-if 情境模擬（配額 / 權重方案 / 排除近期已稽查，R4）

設計原則（對齊本專案架構）：本檔為**純邏輯**、不 import streamlit，可離線
單元測試；Streamlit 頁面（app/pages/5_dispatch.py）為薄呈現包裝，只呼叫本層
並渲染結果。所有最佳化與重排序皆委由 src/ 既有引擎（單一事實來源），本層
只負責「DataFrame → 引擎輸入型別 → 結果整理」的橋接與格式化，不重寫演算法。

責任 AI：分派與模擬僅為稽查資源建議排序，不代表任何違法認定。
"""
from __future__ import annotations

import os
import sys
from typing import Any

import pandas as pd

# 載入後端引擎（相容 Streamlit 執行與離線測試）。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import allocation as _alloc  # noqa: E402
from src import simulation as _sim  # noqa: E402
from src.models import SimParams  # noqa: E402

# 對外公開允許的權重方案（供 UI 下拉選單），沿用引擎的單一事實來源。
WEIGHT_SCHEMES: dict[str, str] = {
    "balanced": "均衡（財務 50 / 裁罰 34 / 評鑑 16）",
    "financial_only": "純財務（僅財務異常）",
    "penalty_priority": "裁罰優先（拉高裁罰權重）",
    "eval_priority": "評鑑優先（拉高評鑑權重）",
}

MIN_INSPECTORS = _alloc.MIN_INSPECTORS
MAX_INSPECTORS = _alloc.MAX_INSPECTORS


# ---------------------------------------------------------------------------
# DataFrame → 引擎輸入型別
# ---------------------------------------------------------------------------
def to_institutions(df: pd.DataFrame) -> list[_alloc.Institution]:
    """將機構 DataFrame 轉為 allocation.Institution 清單（分派輸入）。"""
    out: list[_alloc.Institution] = []
    for _, r in df.iterrows():
        score = r.get("risk_total")
        try:
            score = float(score)
        except (TypeError, ValueError):
            continue
        out.append(_alloc.Institution(
            park_id=str(r.get("park_id")),
            risk_score=score,
            district=(None if pd.isna(r.get("district")) else str(r.get("district"))),
            attributes={"park_name": str(r.get("park_name", ""))},
        ))
    return out


def to_baseline(df: pd.DataFrame) -> list[_sim.BaselineInstitution]:
    """將機構 DataFrame 轉為 simulation.BaselineInstitution 清單（模擬輸入）。"""
    out: list[_sim.BaselineInstitution] = []
    for _, r in df.iterrows():
        try:
            total = float(r.get("risk_total"))
        except (TypeError, ValueError):
            continue

        def _comp(col):
            v = r.get(col)
            try:
                return float(v)
            except (TypeError, ValueError):
                return 0.0

        out.append(_sim.BaselineInstitution(
            park_id=str(r.get("park_id")),
            risk_total=total,
            components={
                "financial": _comp("score_financial"),
                "penalty": _comp("score_penalty"),
                "eval": _comp("score_eval"),
            },
            last_inspected=None,  # 目前資料集無稽查日期欄位；接入後可帶入（R4.3）
            attributes={"park_name": str(r.get("park_name", ""))},
        ))
    return out


# ---------------------------------------------------------------------------
# 名稱查找（park_id → 顯示名/行政區），供結果表格附上可讀資訊
# ---------------------------------------------------------------------------
def build_lookup(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """建立 park_id → {park_name, district} 對照，供結果表格顯示。"""
    lut: dict[str, dict[str, Any]] = {}
    for _, r in df.iterrows():
        lut[str(r.get("park_id"))] = {
            "park_name": str(r.get("park_name", "")),
            "district": ("" if pd.isna(r.get("district")) else str(r.get("district"))),
        }
    return lut


# ---------------------------------------------------------------------------
# 分派最佳化（R3）
# ---------------------------------------------------------------------------
def run_allocation(df: pd.DataFrame, n: int,
                   allowed_districts: set[str] | None = None,
                   inspected: set[str] | None = None):
    """執行分派最佳化，回傳 (AllocationResult, lookup)。純委派 src.allocation。"""
    institutions = to_institutions(df)
    region = _alloc.RegionFilter(allowed_districts=allowed_districts)
    result = _alloc.optimize(institutions, n, region_filter=region,
                             inspected=inspected or set())
    return result, build_lookup(df)


def allocation_to_dataframe(result, lookup: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """將 AllocationResult 轉為可顯示 / 可下載的 DataFrame（含機構名與行政區）。"""
    rows = []
    for i, item in enumerate(result.selected, start=1):
        info = lookup.get(str(item.park_id), {})
        rows.append({
            "派工序": i,
            "機構名稱": info.get("park_name", item.park_id),
            "行政區": info.get("district", ""),
            "風險分": round(item.risk_score, 1),
            "入選理由": item.reason,
        })
    return pd.DataFrame(rows, columns=["派工序", "機構名稱", "行政區", "風險分", "入選理由"])


# ---------------------------------------------------------------------------
# What-if 情境模擬（R4）
# ---------------------------------------------------------------------------
def run_simulation(df: pd.DataFrame, quota: int, weight_scheme: str,
                   exclude_recent_inspected: bool = False):
    """執行 What-if 模擬，回傳 (SimulationResult, lookup)。純委派 src.simulation。"""
    base = to_baseline(df)
    params = SimParams(quota=quota, weight_scheme=weight_scheme,
                       exclude_recent_inspected=exclude_recent_inspected)
    result = _sim.simulate(base, params)
    return result, build_lookup(df)


def simulation_to_dataframe(result, lookup: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """將 SimulationResult 轉為可顯示 DataFrame（含機構名與行政區）。"""
    rows = []
    for item in result.ranked:
        info = lookup.get(str(item.park_id), {})
        rows.append({
            "模擬名次": item.rank,
            "機構名稱": info.get("park_name", item.park_id),
            "行政區": info.get("district", ""),
            "模擬分": round(item.sim_score, 1),
        })
    return pd.DataFrame(rows, columns=["模擬名次", "機構名稱", "行政區", "模擬分"])
