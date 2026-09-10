"""
測試共用 Hypothesis 產生器（Shared Strategies）
==================================================
小小守護員 Smart Watchdog Platform — 屬性測試用的 Hypothesis 策略集中定義。

依 design.md「Testing Strategy」章節，產生器需涵蓋以下邊界：
  - 財務金額含 0、負數（短絀）、缺值（None）、極大值、跨數量級（班佛用）。
  - 分母為 0／缺值情境（R7.11）；樣本數低於方法門檻（R8.5, R13.4）。
  - 機構名稱變體（全形/半形、空白、年度後綴）供實體解析（R17.2）。
  - 財務物件 round-trip 產生器涵蓋特殊字元、編碼、空欄位（解析器附註）。
  - 分派 N 的無效值（0、負、>1000、非整數）與有效邊界（1、1000）（R3.9）。
  - 資料時效邊界（恰 365 天、366 天）（R6.4）。

各具體屬性測試檔案可 `from tests.generators import ...` 取用這些策略，
避免重複並確保邊界覆蓋一致。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from hypothesis import strategies as st

from src.models import (
    FinancialRecord,
    SimParams,
    SourceRef,
)

# --------------------------------------------------------------------------
# 財務金額（涵蓋 0 / 負 / None / 極大 / 跨數量級）
# --------------------------------------------------------------------------

# 有效非缺值財務金額：允許 0、負數（短絀）與極大值，跨多個數量級。
finite_amounts = st.floats(
    min_value=-1e12,
    max_value=1e12,
    allow_nan=False,
    allow_infinity=False,
)

# 可為缺值的財務金額（None 代表資料缺漏）。
optional_amounts = st.one_of(st.none(), finite_amounts)

# 正金額（供需要正值分母的情境，例如收入 / 招生人數 > 0）。
positive_amounts = st.floats(
    min_value=1e-3,
    max_value=1e12,
    allow_nan=False,
    allow_infinity=False,
)

# 「分母危險值」：0 或 None，用於觸發除零／缺值保護（R7.11）。
zero_or_none = st.one_of(st.just(0.0), st.none())

# 跨數量級的整數明細金額（班佛定律用），含小額與大額混合。
detail_amount = st.integers(min_value=1, max_value=10_000_000)


def detail_amounts_lists(min_size: int = 0, max_size: int = 60):
    """逐筆明細金額清單策略；min_size=0 可產生班佛樣本不足情境（R8.5）。"""
    return st.lists(detail_amount, min_size=min_size, max_size=max_size)


# --------------------------------------------------------------------------
# 招生人數（含 0 觸發每名幼兒指標除零 R7.11）
# --------------------------------------------------------------------------
enrollment_values = st.one_of(
    st.none(),
    st.just(0),
    st.integers(min_value=1, max_value=5000),
)


# --------------------------------------------------------------------------
# 機構名稱變體（全形/半形、空白、年度後綴）供實體解析（R17.2）
# --------------------------------------------------------------------------
_BASE_NAMES = [
    "新北市立幼兒園",
    "快樂非營利幼兒園",
    "陽光幼兒園",
    "小天使幼兒園",
    "板橋國小附設幼兒園",
]

_YEAR_SUFFIXES = ["", "（112）", "(113)", " 114年度", "　"]  # 含全形空白
_WHITESPACE_VARIANTS = ["", " ", "  ", "\t", "　"]           # 半形/全形空白


@st.composite
def institution_names(draw) -> str:
    """產生同一機構的名稱變體（前後空白、年度後綴、全形/半形混用）。"""
    base = draw(st.sampled_from(_BASE_NAMES))
    prefix_ws = draw(st.sampled_from(_WHITESPACE_VARIANTS))
    suffix = draw(st.sampled_from(_YEAR_SUFFIXES))
    suffix_ws = draw(st.sampled_from(_WHITESPACE_VARIANTS))
    return f"{prefix_ws}{base}{suffix}{suffix_ws}"


# 供解析器 round-trip 使用：涵蓋特殊字元、空欄位的自由文字名稱。
free_text_names = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),  # 排除代理對，避免編碼問題
    min_size=0,
    max_size=40,
)


# --------------------------------------------------------------------------
# 分派 N 邊界（有效 1..1000；無效 0/負/>1000/非整數）(R3.9)
# --------------------------------------------------------------------------
valid_inspector_n = st.integers(min_value=1, max_value=1000)

invalid_inspector_n = st.one_of(
    st.just(0),
    st.integers(min_value=-1000, max_value=-1),
    st.integers(min_value=1001, max_value=100000),
    st.floats(min_value=0.1, max_value=1000.9, allow_nan=False,
              allow_infinity=False).filter(lambda x: x != int(x)),
)


# --------------------------------------------------------------------------
# 風險分數（0–100）
# --------------------------------------------------------------------------
risk_scores = st.floats(
    min_value=0.0,
    max_value=100.0,
    allow_nan=False,
    allow_infinity=False,
)


# --------------------------------------------------------------------------
# 資料時效邊界（恰 365 天 / 366 天）(R6.4)
# --------------------------------------------------------------------------
def staleness_dates(reference: date | None = None):
    """產生相對參考日的更新日期，涵蓋 365/366 天邊界。

    產出策略包含：今天、恰 364/365/366 天前、以及 0–2000 天前的隨機值。
    """
    ref = reference or date.today()
    boundary = st.sampled_from(
        [
            ref,
            ref - timedelta(days=364),
            ref - timedelta(days=365),
            ref - timedelta(days=366),
        ]
    )
    random_days = st.integers(min_value=0, max_value=2000).map(
        lambda d: ref - timedelta(days=d)
    )
    return st.one_of(boundary, random_days)


# --------------------------------------------------------------------------
# 模擬配額邊界（有效 1..999；無效 0/負/>=1000/非整數）(R4.1, R4.6)
# --------------------------------------------------------------------------
valid_quota = st.integers(min_value=1, max_value=999)

invalid_quota = st.one_of(
    st.just(0),
    st.integers(min_value=-1000, max_value=-1),
    st.integers(min_value=1000, max_value=100000),
    st.floats(min_value=0.1, max_value=999.9, allow_nan=False,
              allow_infinity=False).filter(lambda x: x != int(x)),
)

# 允許的權重方案清單（供模擬與其無效值測試）。
WEIGHT_SCHEMES = ["balanced", "financial_only", "fee_priority"]
weight_schemes = st.sampled_from(WEIGHT_SCHEMES)


# --------------------------------------------------------------------------
# 複合物件策略
# --------------------------------------------------------------------------
@st.composite
def source_refs(draw) -> SourceRef:
    """SourceRef 策略（含可能過時的 last_updated）。"""
    return SourceRef(
        dataset=draw(st.text(min_size=1, max_size=20)),
        authority=draw(st.text(min_size=1, max_size=20)),
        url=draw(st.one_of(st.none(), st.just("https://example.gov.tw/data"))),
        last_updated=draw(st.one_of(st.none(), staleness_dates())),
    )


@st.composite
def financial_records(draw) -> FinancialRecord:
    """FinancialRecord 策略，涵蓋缺值、0、負、極大與跨數量級明細。"""
    return FinancialRecord(
        park_id=draw(st.text(min_size=1, max_size=12)),
        park_name=draw(institution_names()),
        year=draw(st.sampled_from([112, 113, 114])),
        income_actual=draw(optional_amounts),
        expense_actual=draw(optional_amounts),
        tuition_actual=draw(optional_amounts),
        surplus=draw(optional_amounts),
        income_last_year=draw(st.one_of(zero_or_none, finite_amounts)),
        expense_last_year=draw(st.one_of(zero_or_none, finite_amounts)),
        enrollment=draw(enrollment_values),
        detail_amounts=draw(detail_amounts_lists()),
        source_ref=draw(st.one_of(st.none(), source_refs())),
    )


@st.composite
def sim_params(draw) -> SimParams:
    """有效 SimParams 策略（配額 1–999、允許權重方案）。"""
    return SimParams(
        quota=draw(valid_quota),
        weight_scheme=draw(weight_schemes),
        exclude_recent_inspected=draw(st.booleans()),
    )
