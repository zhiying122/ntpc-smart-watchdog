"""
資料可信度評分（Confidence_Scorer, R18）
=============================================
小小守護員 Smart Watchdog Platform — 為每一機構或資料紀錄計算 0–100 的
資料可信度分數（Data_Confidence_Score）。

設計原則（對應 design.md「7. Confidence_Scorer」）：

    def confidence(record) -> DataConfidence
        \"\"\"0–100 資料可信度(R18.1)；供 Scorer 抑制低可信度推高(R18.2)、
        供介面併同顯示(R18.3)。\"\"\"

可信度是「白盒子」的：總分由數個可解釋的加權因子（factors）加總而成，
每個因子分數落於 0–1（乘以其權重得貢獻），最終縮放至 0–100。呼叫端可
攤開 `factors` 明細，理解「為什麼這筆資料是 72 分」。

責任 AI：低可信度僅代表「資料品質不足」，不等於「機構有問題」；本分數
供 Risk_Scorer 用於抑制低可信度資料單獨推高風險（R18.2），而非放大風險。

本模組僅依賴標準函式庫與 `src.models` 的共用型別 `DataConfidence` /
`FinancialRecord`，不引入額外執行期相依，維持既有基線的可攜性。
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from typing import Any, Mapping

from .models import DataConfidence, FinancialRecord

# --------------------------------------------------------------------------
# 可信度因子權重（合計為 1.0）
# --------------------------------------------------------------------------
# 每個因子輸出 0.0–1.0 的子分數，乘上權重後加總，再縮放為 0–100。
# 權重反映各因子對「這筆資料能否被信任」的相對重要性：
#   - completeness：關鍵財務欄位是否齊全（最重要）
#   - source_traceable：是否附官方來源（可追溯性）
#   - freshness：來源最後更新時效（越新越可信）
#   - enrollment：是否有招生人數（每名幼兒單位成本等指標的前提）
#   - detail_granularity：是否有逐筆明細金額（班佛定律可用性）
FACTOR_WEIGHTS: dict[str, float] = {
    "completeness": 0.40,
    "source_traceable": 0.20,
    "freshness": 0.15,
    "enrollment": 0.10,
    "detail_granularity": 0.15,
}

# completeness 因子檢查的關鍵財務欄位
_KEY_FINANCIAL_FIELDS = (
    "income_actual",
    "expense_actual",
    "tuition_actual",
    "surplus",
    "income_last_year",
    "expense_last_year",
)

# freshness 門檻（天）：<=180 天視為新，>=730 天視為過時，其間線性遞減
_FRESH_DAYS = 180
_STALE_DAYS = 730

# detail_granularity：達到此明細筆數即視為完整可用（班佛定律建議 >=某量）
_DETAIL_TARGET = 10


def _get(record: Any, key: str, default: Any = None) -> Any:
    """統一從 dataclass 或 mapping 取欄位值。"""
    if isinstance(record, Mapping):
        return record.get(key, default)
    return getattr(record, key, default)


def _entity_id(record: Any) -> str:
    """推導 entity_id：優先 park_id，其次 entity_id，再退回 park_name。"""
    for key in ("park_id", "entity_id", "park_name"):
        val = _get(record, key)
        if val:
            return str(val)
    return "unknown"


def _clamp01(x: float) -> float:
    """夾制於 0.0–1.0。"""
    if x < 0.0:
        return 0.0
    if x > 1.0:
        return 1.0
    return x


def _score_completeness(record: Any) -> float:
    """關鍵財務欄位齊全度：非 None 欄位比例（0.0–1.0）。"""
    present = 0
    for name in _KEY_FINANCIAL_FIELDS:
        if _get(record, name) is not None:
            present += 1
    return present / len(_KEY_FINANCIAL_FIELDS)


def _score_source_traceable(record: Any) -> float:
    """是否附官方來源：有 source_ref（且 dataset/url 至少其一）→ 1.0。"""
    src = _get(record, "source_ref")
    if src is None:
        return 0.0
    dataset = _get(src, "dataset")
    url = _get(src, "url")
    if dataset or url:
        return 1.0
    # 有 source 物件但內容空白：給部分分
    return 0.3


def _extract_last_updated(record: Any) -> date | None:
    """取來源最後更新日期（source_ref.last_updated）。"""
    src = _get(record, "source_ref")
    if src is None:
        return None
    last = _get(src, "last_updated")
    if isinstance(last, datetime):
        return last.date()
    if isinstance(last, date):
        return last
    return None


def _score_freshness(record: Any, today: date | None = None) -> float:
    """時效性：<=180 天 → 1.0；>=730 天 → 0.0；其間線性遞減。

    無來源更新日期時回傳 0.0（無法佐證時效，保守處理）。
    """
    last = _extract_last_updated(record)
    if last is None:
        return 0.0
    ref = today or date.today()
    age_days = (ref - last).days
    if age_days <= _FRESH_DAYS:
        return 1.0
    if age_days >= _STALE_DAYS:
        return 0.0
    span = _STALE_DAYS - _FRESH_DAYS
    return _clamp01((_STALE_DAYS - age_days) / span)


def _score_enrollment(record: Any) -> float:
    """招生人數可用性：有正整數招生人數 → 1.0。"""
    enrollment = _get(record, "enrollment")
    if enrollment is None:
        return 0.0
    try:
        return 1.0 if float(enrollment) > 0 else 0.0
    except (TypeError, ValueError):
        return 0.0


def _score_detail_granularity(record: Any) -> float:
    """逐筆明細金額可用性：達 _DETAIL_TARGET 筆 → 1.0，否則按比例。"""
    detail = _get(record, "detail_amounts")
    if not detail:
        return 0.0
    try:
        count = len(detail)
    except TypeError:
        return 0.0
    return _clamp01(count / _DETAIL_TARGET)


def confidence(record: Any, today: date | None = None) -> DataConfidence:
    """計算單一機構或資料紀錄的資料可信度分數（0–100）（R18.1）。

    參數
    ------
    record : FinancialRecord | Mapping | 具相容屬性之物件
        資料紀錄。可為共用型別 `FinancialRecord`、dict，或任何具備
        park_id / income_actual / source_ref / enrollment / detail_amounts
        等屬性的物件。缺少的欄位一律以「不可信」方向保守處理。
    today : date | None
        供時效計算的基準日（測試可注入）；預設為 date.today()。

    回傳
    ------
    DataConfidence
        - score：0–100（含端點）的資料可信度分數。
        - factors：各因子的貢獻明細（已乘權重、縮放至 0–100），
          加總（四捨五入後）等於 score，可攤開解釋。

    不變式
    ------
    - 0.0 <= score <= 100.0
    - round(sum(factors.values()), 4) 約等於 score（浮點誤差內）

    Validates: Requirements 18.1
    """
    subscores = {
        "completeness": _score_completeness(record),
        "source_traceable": _score_source_traceable(record),
        "freshness": _score_freshness(record, today=today),
        "enrollment": _score_enrollment(record),
        "detail_granularity": _score_detail_granularity(record),
    }

    factors: dict[str, float] = {}
    total = 0.0
    for name, weight in FACTOR_WEIGHTS.items():
        sub = _clamp01(subscores.get(name, 0.0))
        contribution = round(sub * weight * 100.0, 4)
        factors[name] = contribution
        total += contribution

    # 夾制於 0–100（浮點與四捨五入後的安全邊界）
    score = round(min(100.0, max(0.0, total)), 4)

    return DataConfidence(
        entity_id=_entity_id(record),
        score=score,
        factors=factors,
    )
