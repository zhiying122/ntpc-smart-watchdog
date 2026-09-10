"""
家長信任中心：公開資訊揭露與來源時效標記（Parent Trust Center）
================================================================
小小守護員 Smart Watchdog Platform — Parent_Portal 的**呈現無關**核心邏輯。

本模組只負責「把一筆機構資料投影為家長可見的公開檢視」，包含：
  1. 欄位白名單投影：移除任何內部風險資訊（risk_total / risk_level /
     score_* 與其衍生排序欄位）後才呈現（R1.5, R6.6）。
  2. 每一揭露欄位附官方來源連結與最後更新時間（R6.1, R6.2）。
  3. 無官方公開資料 → 標示「查無公開資料」，不以推估值／預設值／空白替代
     （R6.3）。
  4. 官方來源最後更新時間距今超過 365 天 → 標示「資料可能過時」（R6.4）。
  5. 僅陳述可回溯官方來源之事實，且不作任何違法／舞弊／高風險標記
     （R6.5, R6.7, R6.8）。

設計原則：本檔不 import streamlit，不含任何呈現副作用，純函式易於單元測試。
Streamlit 頁面（app/pages/5_parent.py）為薄包裝，讀取本模組輸出並渲染。

責任 AI（Responsible AI）：風險（risk）不等於違法（illegality）。家長入口
不揭露任何內部風險分數／等級，亦不對機構作違法／舞弊／高風險評價。

對應 design.md「Parent_Portal 透過 public_view() 白名單投影」章節與 Property 34。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping

# 允許以套件（app.lib）或以 app 目錄為 sys.path 根（lib）兩種方式匯入 models。
try:  # pragma: no cover - 匯入路徑相依於執行情境
    from src.models import PublicInstitutionView, SourceRef
except ImportError:  # pragma: no cover
    import os
    import sys

    _ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from src.models import PublicInstitutionView, SourceRef


# ---------------------------------------------------------------------------
# 常數：時效門檻、標示文字、禁止揭露欄位
# ---------------------------------------------------------------------------
#: 官方來源最後更新時間距今超過此天數即標示「資料可能過時」（R6.4）。
#: 「超過 365 天」= 嚴格大於 365，恰 365 天不算過時（對齊 Property 34 邊界）。
STALENESS_THRESHOLD_DAYS: int = 365

#: 無對應官方公開資料時顯示的固定文字；不得以推估／預設／空白替代（R6.3）。
NO_PUBLIC_DATA_LABEL: str = "查無公開資料"

#: 來源過時的時效提示文字（R6.4）。
STALE_NOTICE_LABEL: str = "資料可能過時"

#: 家長入口一律禁止揭露的內部風險欄位（R1.5, R6.6）。
#: 精確欄位名 + score_ 前綴通配，涵蓋 design.md 契約檔中所有衍生風險欄位。
_FORBIDDEN_EXACT: frozenset[str] = frozenset({
    "risk_total",
    "risk_level",
    "risk_level_abs",
    "risk_rank",
    "risk_percentile",
})
_FORBIDDEN_PREFIXES: tuple[str, ...] = ("score_", "risk_")


def is_risk_field(column: str) -> bool:
    """判斷某欄位是否為「內部風險資訊」而必須自家長入口移除（R1.5, R6.6）。

    涵蓋精確欄位名（risk_total、risk_level、risk_level_abs 等）與前綴
    （score_*、risk_*）。此判定為白名單投影的反向守門，確保沒有任何足以
    還原風險分數／等級的欄位外洩。
    """
    if not isinstance(column, str):
        return False
    key = column.strip().lower()
    if key in _FORBIDDEN_EXACT:
        return True
    return any(key.startswith(p) for p in _FORBIDDEN_PREFIXES)


def strip_risk_fields(record: Mapping[str, Any]) -> dict[str, Any]:
    """自一筆機構資料移除所有內部風險欄位，回傳僅含非風險欄位的新 dict（R6.6）。

    不修改輸入；輸出保證不含任何 `is_risk_field` 為真的鍵。
    """
    return {k: v for k, v in record.items() if not is_risk_field(k)}


# ---------------------------------------------------------------------------
# 時效判定（R6.4，Property 34 之核心）
# ---------------------------------------------------------------------------
def days_since(last_updated: date | None, *, reference: date | None = None) -> int | None:
    """回傳來源最後更新距參考日的天數；last_updated 為 None 時回傳 None。

    reference 預設為今天（date.today）。負值（未來日期）原樣回傳，
    由 `is_stale` 判定為「非過時」。
    """
    if last_updated is None:
        return None
    ref = reference or date.today()
    return (ref - last_updated).days


def is_stale(last_updated: date | None, *, reference: date | None = None) -> bool:
    """官方來源是否「資料可能過時」：距今嚴格超過 365 天為真（R6.4）。

    - last_updated 為 None（無時間資訊）→ 視為非過時（False），該欄位另由
      「查無公開資料」路徑處理，不重複標示。
    - 恰 365 天 → False；366 天（含以上）→ True。此邊界對齊 Property 34
      「若且唯若距今超過 365 天」。

    Validates: Requirements 6.4
    """
    n = days_since(last_updated, reference=reference)
    if n is None:
        return False
    return n > STALENESS_THRESHOLD_DAYS


# ---------------------------------------------------------------------------
# 單一欄位揭露結果
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DisclosureField:
    """家長入口單一揭露欄位的呈現無關結果（R6.1–R6.4）。

    - label：欄位顯示名稱（如「收費資訊」）。
    - has_data：是否有官方公開資料。False 時 value 一律為 None，且
      display_value 為「查無公開資料」（R6.3）。
    - value：實際公開值（僅在 has_data 為真時有意義；不得以推估／預設替代）。
    - source：官方來源（連結 + 最後更新時間，R6.2）；無資料時為 None。
    - stale：來源是否過時（>365 天，R6.4）；無資料時恆為 False。

    不變式（責任 AI）：本物件不含任何風險分數／等級欄位（R6.6），亦不含
    任何違法／舞弊／高風險標記（R6.7, R6.8）。

    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    key: str
    label: str
    has_data: bool
    value: Any = None
    source: SourceRef | None = None
    stale: bool = False

    @property
    def display_value(self) -> Any:
        """呈現用值：無資料時回傳固定「查無公開資料」，不以空白／預設替代（R6.3）。"""
        return self.value if self.has_data else NO_PUBLIC_DATA_LABEL

    @property
    def stale_notice(self) -> str | None:
        """來源過時時回傳「資料可能過時」提示，否則 None（R6.4）。"""
        return STALE_NOTICE_LABEL if self.stale else None

    @property
    def source_url(self) -> str | None:
        """官方來源連結；無資料或來源未提供連結時為 None（R6.2）。"""
        return self.source.url if self.source is not None else None

    @property
    def source_last_updated(self) -> date | None:
        """官方來源最後更新時間；無資料時為 None（R6.2）。"""
        return self.source.last_updated if self.source is not None else None


def build_field(
    key: str,
    label: str,
    value: Any,
    source: SourceRef | None,
    *,
    reference: date | None = None,
) -> DisclosureField:
    """由原始值與來源建構單一揭露欄位（套用無資料與時效規則）。

    「無官方公開資料」的判定（R6.3）：value 為 None，或去空白後為空字串／
    空清單／空字典（視為無實質公開資料）。此時 has_data=False、value=None、
    source 略去、stale=False，display_value 固定為「查無公開資料」。

    有資料時：保留原值、附來源，並依 `is_stale` 判定時效提示（R6.4）。

    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    if _is_empty(value):
        return DisclosureField(
            key=key, label=label, has_data=False, value=None, source=None, stale=False,
        )

    stale = is_stale(source.last_updated if source else None, reference=reference)
    return DisclosureField(
        key=key, label=label, has_data=True, value=value, source=source, stale=stale,
    )


def _is_empty(value: Any) -> bool:
    """判斷值是否代表「無實質公開資料」（None / 空字串 / 空集合）。"""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


# ---------------------------------------------------------------------------
# 家長公開檢視組裝
# ---------------------------------------------------------------------------
#: 家長入口揭露欄位順序與顯示名稱（R6.1）。
#: key 對應 PublicInstitutionView / field_sources 的鍵。
DISCLOSURE_ORDER: tuple[tuple[str, str], ...] = (
    ("basic_info", "基本資訊"),
    ("ownership", "公私立別"),
    ("tuition_info", "收費資訊"),
    ("public_eval", "公開評鑑結果"),
    ("public_penalty", "公開裁罰紀錄"),
)


def build_disclosure_fields(
    view: PublicInstitutionView,
    *,
    basic_info: Any = None,
    reference: date | None = None,
) -> list[DisclosureField]:
    """將 PublicInstitutionView 組裝為家長可見的揭露欄位清單（R6.1–R6.4）。

    依 DISCLOSURE_ORDER 逐欄產生 DisclosureField：
      - 每欄取 view.field_sources 中對應的官方來源（R6.2）。
      - 無值 → 「查無公開資料」（R6.3）。
      - 來源 >365 天 → 「資料可能過時」（R6.4）。
    basic_info 為額外的「基本資訊」內容（view 未直接持有時由呼叫端提供）。

    回傳清單不含任何風險分數／等級欄位（R6.6），亦不含違法／舞弊標記（R6.7）。

    Validates: Requirements 6.1, 6.2, 6.3, 6.4
    """
    values: dict[str, Any] = {
        "basic_info": basic_info,
        "ownership": view.ownership,
        "tuition_info": view.tuition_info,
        "public_eval": view.public_eval,
        "public_penalty": view.public_penalty,
    }
    fields: list[DisclosureField] = []
    for key, label in DISCLOSURE_ORDER:
        source = view.field_sources.get(key)
        fields.append(
            build_field(key, label, values.get(key), source, reference=reference)
        )
    return fields


def build_public_view(
    record: Mapping[str, Any],
    field_sources: Mapping[str, SourceRef] | None = None,
    *,
    reference: date | None = None,
) -> PublicInstitutionView:
    """自一筆（可能含風險欄位的）機構資料建構家長公開檢視（R6.6, R1.5）。

    流程：
      1. 先移除所有內部風險欄位（strip_risk_fields），確保無法還原分數／等級。
      2. 僅取用公開透明欄位（park_name / ownership / tuition / eval / penalty）。
      3. 帶入各欄位官方來源與時效旗標（R6.2, R6.4）。

    park_name 與 ownership 缺值時以空字串佔位（型別要求非 None），但其對應
    揭露欄位仍會在 build_disclosure_fields 中被判為「查無公開資料」。

    Validates: Requirements 6.6, 6.1, 6.2, 6.4, 1.5
    """
    safe = strip_risk_fields(record)
    srcs: dict[str, SourceRef] = dict(field_sources or {})

    view = PublicInstitutionView(
        park_name=str(safe.get("park_name") or ""),
        ownership=str(safe.get("ownership") or safe.get("park_type") or ""),
        tuition_info=_normalize_optional(safe.get("tuition_info")),
        public_eval=_normalize_optional(safe.get("public_eval") or safe.get("eval_grade")),
        public_penalty=_normalize_optional(safe.get("public_penalty")),
        field_sources=srcs,
    )

    # 依各欄位來源時效填入 stale_flags（R6.4）。
    for key, src in srcs.items():
        view.stale_flags[key] = is_stale(src.last_updated, reference=reference)

    return view


def _normalize_optional(value: Any) -> Any:
    """將空值正規化為 None（供 PublicInstitutionView 之 Optional 欄位）。"""
    return None if _is_empty(value) else value
