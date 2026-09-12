"""
政府指揮中心核心邏輯（Gov_Console Core Logic）
============================================================
小小守護員 Smart Watchdog Platform — 政府指揮中心（Gov_Console）的
「呈現無關」（presentation-independent）核心計算邏輯。

本模組**只負責計算**：風險等級分級、KPI 計數、行政區風險排名、高風險機構
排名、近三年趨勢與風險熱點。所有函式皆為純函式（pure），輸入 pandas
DataFrame / 標量，輸出 dataclass 或標量，**不含任何 Streamlit 呈現邏輯**，
以便單元測試與屬性測試（Property 5/6/8）。

Gov_Console 的 Streamlit 頁面（app/主頁.py 等）應作為薄包裝（thin wrapper），
呼叫本模組取得結果後再渲染，確保計算與呈現分離。

資料契約（見 app/lib/common.py 與 docs/data-dictionary.md）：
- `kindergartens_latest.csv`（每園一列）欄位含 `risk_total`、`risk_level`、
  `district`、`park_id`、`park_name`、`iforest_score` 等。
- `kindergartens.csv`（每園每年一列）欄位同上並含 `year`，供近三年趨勢。

分級門檻（R2.2，與 requirements Requirement 2 對齊）：
    分數 >= 70 → 高；40 <= 分數 <= 69 → 中；分數 < 40 → 低。
邊界一致性：恰 70 判為「高」、恰 40 判為「中」（Property 5）。

責任 AI（Responsible AI）：風險（risk）不等於違法（illegality）。本模組僅
產出分級、計數、排序與熱點聚合，不作任何違法/舞弊認定。

對應 design.md「政府指揮中心（R2）」章節與 Property 5/6/8。
Validates: Requirements 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 分級門檻常數（R2.2）
# ---------------------------------------------------------------------------
#: 高風險門檻：分數 >= HIGH_THRESHOLD 判為「高」。
HIGH_THRESHOLD: float = 70.0
#: 中風險門檻：MID_THRESHOLD <= 分數 < HIGH_THRESHOLD 判為「中」。
MID_THRESHOLD: float = 40.0

#: 三個風險等級標籤（與既有資料 `risk_level` 中文標籤一致）。
LEVEL_HIGH = "高"
LEVEL_MID = "中"
LEVEL_LOW = "低"

#: 高風險機構排名清單最多顯示筆數（R2.6）。
MAX_RANKING = 20


# ---------------------------------------------------------------------------
# 分級（R2.2, Property 5）
# ---------------------------------------------------------------------------
def grade(score: float) -> str:
    """依風險分數分級為三個等級（R2.2）。

    分級規則（邊界一致，Property 5）：
        - 分數 >= 70            → 高（LEVEL_HIGH）
        - 40 <= 分數 <= 69（含）→ 中（LEVEL_MID）
        - 分數 < 40             → 低（LEVEL_LOW）

    以連續門檻 `score >= 70`、`score >= 40` 實作，故「40–69」自然涵蓋
    39.x 之上、70 以下的所有實數（含 69.9），邊界 40 與 70 判定明確。

    參數
    ----
    score:
        風險分數，通常介於 0–100；本函式對任意實數皆給出確定分級
        （> 70 恆為高、< 40 恆為低），不限制上下界以利屬性測試。

    回傳
    ----
    str: 「高」/「中」/「低」三者之一。

    Validates: Requirements 2.2
    """
    s = float(score)
    if s >= HIGH_THRESHOLD:
        return LEVEL_HIGH
    if s >= MID_THRESHOLD:
        return LEVEL_MID
    return LEVEL_LOW


def _is_missing(v: object) -> bool:
    """判定值是否缺失（None 或 NaN）。"""
    if v is None:
        return True
    try:
        return bool(math.isnan(float(v)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False


def _is_high(level_val: object, score: float) -> bool:
    """判定單列是否為「高風險」，全站一致的單一判準。

    優先採用契約檔既有的 `risk_level`（百分位分級，與 KPI 帶、排名、地圖
    著色同源）；僅當該值缺失或非三級標籤時，才退回以 `grade()` 絕對門檻
    （>=70）由分數即時判定。此舉消除同頁「KPI 用百分位、熱點/行政區排名用
    絕對門檻」導致的高風險計數矛盾（例如 KPI 顯示高風險 N 間，但熱點卻為 0）。
    """
    if level_val is not None and str(level_val) in (LEVEL_HIGH, LEVEL_MID, LEVEL_LOW):
        return str(level_val) == LEVEL_HIGH
    return grade(score) == LEVEL_HIGH


# ---------------------------------------------------------------------------
# KPI 計數（R2.3, Property 6）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class KpiCounts:
    """Gov_Console KPI 計數（R2.3）。

    各計數皆為非負整數；`high + mid + low == gradable`（可分級機構總數），
    此不變式為 Property 6 所驗證。`new_anomaly` 為新增異常機構數（非負整數），
    獨立計算，不納入分級總數不變式。

    Validates: Requirements 2.3
    """
    high: int = 0            # 高風險機構數（優先取 risk_level==高；缺則 grade()>=70）
    mid: int = 0             # 中風險機構數（優先取 risk_level==中；缺則 grade() 40–69）
    low: int = 0             # 低風險機構數（優先取 risk_level==低；缺則 grade()<40）
    new_anomaly: int = 0     # 新增異常機構數
    gradable: int = 0        # 可分級機構數（有有效風險分數者）= high + mid + low
    ungradable: int = 0      # 無法分級機構數（風險分數缺失）


def _iter_scores(df, score_col: str = "risk_total"):
    """由 DataFrame 逐列產出風險分數（保留缺失以計 ungradable）。"""
    if df is None or score_col not in getattr(df, "columns", []):
        return
    for v in df[score_col].tolist():
        yield v


def kpi_counts(df, score_col: str = "risk_total",
               anomaly_col: str = "iforest_score",
               anomaly_threshold: float = 70.0,
               level_col: str = "risk_level") -> KpiCounts:
    """計算 Gov_Console 的 KPI 計數（R2.3, Property 6）。

    分級來源（重要，避免跨頁數字矛盾）：**優先採用契約檔既有的 `risk_level`
    欄位**（由 src/risk_score.py 的分機構類型百分位分級產生，高/中/低），
    與主頁 KPI 帶、風險分布、地圖著色、排名表完全同源。僅當該列 `risk_level`
    缺失（或整份資料無此欄）時，才退回以 `grade()` 的絕對門檻（70/40）即時
    分級（fallback）。

    為何不直接一律用 `grade()` 絕對門檻：本專案 `risk_total` 是「稽查優先序」
    的相對分數，實務分布多落在 60 分以下（例：目前資料最高約 57）。若用絕對
    70/40 門檻計數，會算出「高風險 0 間」，與主頁依 `risk_level` 顯示的高風險
    間數對不上，造成同一畫面數字矛盾。改採 `risk_level` 為主、絕對門檻為
    fallback，確保 KPI 與全站一致。

    風險分數缺失（None/NaN）且無 `risk_level` 者計入 `ungradable`，不計入
    high/mid/low，確保 `high+mid+low == gradable`。

    「新增異常機構數」以異常分數欄位（預設 `iforest_score`）達門檻
    （預設 70）之機構數估算——此為可 Demo 的近似定義；缺該欄位時為 0。

    參數
    ----
    df:
        機構 DataFrame（每園一列），至少含 `score_col` 或 `level_col`。
    score_col:
        風險分數欄位名（預設 `risk_total`），供 fallback 絕對門檻分級用。
    anomaly_col:
        異常分數欄位名（預設 `iforest_score`），供估算新增異常數。
    anomaly_threshold:
        異常分數達此值（含）視為異常（預設 70.0）。
    level_col:
        既有等級欄位名（預設 `risk_level`），百分位分級主來源；缺則 fallback。

    回傳
    ----
    KpiCounts: 各計數皆為非負整數，且 high+mid+low == gradable。

    Validates: Requirements 2.3
    """
    high = mid = low = ungradable = 0
    has_level = df is not None and level_col in getattr(df, "columns", [])
    levels = df[level_col].tolist() if has_level else []
    scores = list(_iter_scores(df, score_col))
    n = max(len(levels), len(scores))
    for i in range(n):
        # 主來源：既有 risk_level（百分位三級，與主頁/地圖同源）。
        lvl = None
        if has_level and i < len(levels):
            raw = levels[i]
            if raw is not None and str(raw) in (LEVEL_HIGH, LEVEL_MID, LEVEL_LOW):
                lvl = str(raw)
        # Fallback：該列無有效 risk_level 時，才以 grade() 絕對門檻由分數即時分級。
        if lvl is None:
            v = scores[i] if i < len(scores) else None
            if _is_missing(v):
                ungradable += 1
                continue
            lvl = grade(v)
        if lvl == LEVEL_HIGH:
            high += 1
        elif lvl == LEVEL_MID:
            mid += 1
        else:
            low += 1

    new_anomaly = 0
    if df is not None and anomaly_col in getattr(df, "columns", []):
        for v in df[anomaly_col].tolist():
            if not _is_missing(v) and float(v) >= float(anomaly_threshold):
                new_anomaly += 1

    return KpiCounts(
        high=high, mid=mid, low=low,
        new_anomaly=new_anomaly,
        gradable=high + mid + low,
        ungradable=ungradable,
    )


# ---------------------------------------------------------------------------
# 排名（R2.5 行政區、R2.6 高風險機構，Property 8）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class DistrictRank:
    """單一行政區的風險排名項（R2.5）。"""
    district: str
    avg_risk: float          # 該區平均風險分（用於排序，非遞增）
    max_risk: float          # 該區最高風險分
    count: int               # 該區可分級機構數
    high_count: int          # 該區高風險機構數


@dataclass(frozen=True)
class InstitutionRank:
    """單一高風險機構的排名項（R2.6）。"""
    park_id: str
    park_name: str
    district: str
    risk_total: float
    risk_level: str


def district_risk_ranking(df, score_col: str = "risk_total",
                          district_col: str = "district",
                          level_col: str = "risk_level") -> list[DistrictRank]:
    """各行政區依平均風險分由高至低排序的風險排名（R2.5, Property 8）。

    僅納入有有效風險分數（非缺失）的機構參與聚合；無有效機構的行政區不列入。
    排序鍵為（平均風險分 desc），平均分相同時以（行政區名 asc）作確定性 tie-break，
    確保相同輸入產生相同輸出。

    參數
    ----
    df:
        機構 DataFrame（每園一列）。
    score_col / district_col:
        風險分數與行政區欄位名。

    回傳
    ----
    list[DistrictRank]: 依平均風險分非遞增排序。

    Validates: Requirements 2.5
    """
    cols = getattr(df, "columns", [])
    if df is None or score_col not in cols or district_col not in cols:
        return []

    # 聚合：district -> (scores list, high_count)
    # 高風險判定與 KPI/排名/地圖同源：優先用既有 risk_level（百分位），
    # 缺則以 grade() 絕對門檻 fallback（見 _is_high）。
    has_level = level_col in cols
    buckets: dict[str, list[float]] = {}
    highs: dict[str, int] = {}
    agg_cols = [district_col, score_col] + ([level_col] if has_level else [])
    for _, row in df[agg_cols].iterrows():
        d = row[district_col]
        s = row[score_col]
        if _is_missing(d) or _is_missing(s):
            continue
        d = str(d)
        s = float(s)
        buckets.setdefault(d, []).append(s)
        lvl = row[level_col] if has_level else None
        if _is_high(lvl, s):
            highs[d] = highs.get(d, 0) + 1

    ranks: list[DistrictRank] = []
    for d, scores in buckets.items():
        if not scores:
            continue
        ranks.append(DistrictRank(
            district=d,
            avg_risk=round(sum(scores) / len(scores), 4),
            max_risk=round(max(scores), 4),
            count=len(scores),
            high_count=highs.get(d, 0),
        ))

    # 平均風險分 desc；tie-break 行政區名 asc（確定性）。
    ranks.sort(key=lambda r: (-r.avg_risk, r.district))
    return ranks


def high_risk_ranking(df, score_col: str = "risk_total",
                      id_col: str = "park_id",
                      name_col: str = "park_name",
                      district_col: str = "district",
                      level_col: str = "risk_level",
                      limit: int = MAX_RANKING) -> list[InstitutionRank]:
    """高風險機構排名清單，依風險分由高至低排序，最多前 `limit` 筆（R2.6, Property 8）。

    納入所有有有效風險分數的機構（不限「高」等級），依風險分非遞增排序後
    截斷至 `limit`（預設 20）。排序 tie-break 以（park_id asc）確保確定性。

    參數
    ----
    df:
        機構 DataFrame（每園一列）。
    score_col / id_col / name_col / district_col / level_col:
        對應欄位名。缺 level_col 時以 `grade()` 即時分級補上。
    limit:
        最多顯示筆數（預設 MAX_RANKING=20，R2.6）。

    回傳
    ----
    list[InstitutionRank]: 依風險分非遞增排序，長度 <= limit。

    Validates: Requirements 2.5, 2.6
    """
    cols = getattr(df, "columns", [])
    if df is None or score_col not in cols:
        return []

    items: list[InstitutionRank] = []
    for _, row in df.iterrows():
        s = row[score_col]
        if _is_missing(s):
            continue
        s = float(s)
        pid = "" if id_col not in cols or _is_missing(row.get(id_col)) else str(row[id_col])
        name = "" if name_col not in cols or _is_missing(row.get(name_col)) else str(row[name_col])
        dist = "" if district_col not in cols or _is_missing(row.get(district_col)) else str(row[district_col])
        if level_col in cols and not _is_missing(row.get(level_col)):
            lvl = str(row[level_col])
        else:
            lvl = grade(s)
        items.append(InstitutionRank(
            park_id=pid, park_name=name, district=dist,
            risk_total=round(s, 4), risk_level=lvl,
        ))

    # 風險分 desc；tie-break park_id asc（確定性）。
    items.sort(key=lambda it: (-it.risk_total, it.park_id))
    if limit is not None and limit >= 0:
        items = items[:limit]
    return items


# ---------------------------------------------------------------------------
# 近三年趨勢（R2.7, R7.7）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TrendPoint:
    """趨勢單點：某年度的聚合風險統計（R2.7）。"""
    year: int
    avg_risk: float          # 該年度平均風險分
    high_count: int          # 該年度高風險機構數
    count: int               # 該年度可分級機構數


def risk_trend(full_df, score_col: str = "risk_total",
               year_col: str = "year", years: int = 3,
               level_col: str = "risk_level") -> list[TrendPoint]:
    """近 `years` 個年度的風險趨勢，依年度由舊到新排序（R2.7）。

    以每園每年一列的 `kindergartens.csv`（full_df）為輸入，取最近 `years`
    個年度（預設 3）並依年度由舊到新排序輸出各年度平均風險分與高風險數。
    若可得年度不足 `years` 個，則取全部可得年度（對齊 R7.7 語意）。

    參數
    ----
    full_df:
        每園每年一列的 DataFrame（含 `year_col` 與 `score_col`）。
    score_col / year_col:
        風險分數與年度欄位名。
    years:
        取最近幾個年度（預設 3，對應「近三年趨勢」R2.7）。

    回傳
    ----
    list[TrendPoint]: 依年度由舊到新排序，長度 <= years。

    Validates: Requirements 2.7
    """
    cols = getattr(full_df, "columns", [])
    if full_df is None or score_col not in cols or year_col not in cols:
        return []

    has_level = level_col in cols
    per_year: dict[int, list[float]] = {}
    per_year_high: dict[int, int] = {}
    trend_cols = [year_col, score_col] + ([level_col] if has_level else [])
    for _, row in full_df[trend_cols].iterrows():
        y = row[year_col]
        s = row[score_col]
        if _is_missing(y) or _is_missing(s):
            continue
        try:
            yi = int(y)
        except (TypeError, ValueError):
            continue
        s = float(s)
        per_year.setdefault(yi, []).append(s)
        lvl = row[level_col] if has_level else None
        if _is_high(lvl, s):
            per_year_high[yi] = per_year_high.get(yi, 0) + 1

    if not per_year:
        return []

    # 取最近 years 個年度，再由舊到新排序（R2.7）。
    all_years = sorted(per_year.keys())
    recent = all_years[-years:] if years is not None and years > 0 else all_years

    points: list[TrendPoint] = []
    for y in recent:  # already ascending (old -> new)
        scores = per_year[y]
        points.append(TrendPoint(
            year=y,
            avg_risk=round(sum(scores) / len(scores), 4),
            high_count=per_year_high.get(y, 0),
            count=len(scores),
        ))
    return points


# ---------------------------------------------------------------------------
# 風險熱點（R2.8）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Hotspot:
    """風險熱點：高風險機構聚集的行政區（R2.8）。"""
    district: str
    high_count: int          # 高風險機構數（熱度）
    total_count: int         # 該區可分級機構總數
    high_ratio: float        # 高風險占比（0–1）
    avg_risk: float          # 該區平均風險分


def risk_hotspots(df, score_col: str = "risk_total",
                  district_col: str = "district",
                  top: int = 5) -> list[Hotspot]:
    """風險熱點區域：依高風險機構數由多至少排序的行政區（R2.8）。

    以行政區為單位聚合高風險機構數作為熱度（高風險判定與 KPI/排名同源：
    優先用 risk_level 百分位分級，缺則以 grade() 絕對門檻 fallback，見
    _is_high），依（高風險數 desc、高風險占比 desc、行政區名 asc）確定性
    排序，取前 `top` 個作為熱點。僅列有至少一間高風險機構的行政區。

    參數
    ----
    df:
        機構 DataFrame（每園一列）。
    score_col / district_col:
        風險分數與行政區欄位名。
    top:
        最多回傳熱點數（預設 5）。

    回傳
    ----
    list[Hotspot]: 依熱度非遞增排序，長度 <= top。

    Validates: Requirements 2.8
    """
    ranks = district_risk_ranking(df, score_col=score_col, district_col=district_col)
    hotspots: list[Hotspot] = []
    for r in ranks:
        if r.high_count <= 0:
            continue
        ratio = round(r.high_count / r.count, 4) if r.count else 0.0
        hotspots.append(Hotspot(
            district=r.district,
            high_count=r.high_count,
            total_count=r.count,
            high_ratio=ratio,
            avg_risk=r.avg_risk,
        ))

    hotspots.sort(key=lambda h: (-h.high_count, -h.high_ratio, h.district))
    if top is not None and top >= 0:
        hotspots = hotspots[:top]
    return hotspots


# ---------------------------------------------------------------------------
# 綜合彙整（供薄包裝頁面一次取得所有 Gov_Console 概覽資料）
# ---------------------------------------------------------------------------
@dataclass
class GovOverview:
    """Gov_Console 概覽彙整（供頁面薄包裝直接渲染）。

    Validates: Requirements 2.1, 2.3, 2.5, 2.6, 2.7, 2.8
    """
    kpi: KpiCounts
    district_ranking: list[DistrictRank] = field(default_factory=list)
    high_risk_ranking: list[InstitutionRank] = field(default_factory=list)
    trend: list[TrendPoint] = field(default_factory=list)
    hotspots: list[Hotspot] = field(default_factory=list)


def build_overview(latest_df, full_df=None) -> GovOverview:
    """由契約檔 DataFrame 彙整 Gov_Console 概覽（R2.1, R2.3, R2.5–R2.8）。

    參數
    ----
    latest_df:
        `kindergartens_latest.csv` 載入的每園一列 DataFrame（load_latest()）。
    full_df:
        `kindergartens.csv` 載入的每園每年一列 DataFrame（load_full()），
        供近三年趨勢；為 None 時 trend 為空清單。

    回傳
    ----
    GovOverview: 全轄區風險總覽所需的計算結果集合。

    Validates: Requirements 2.1, 2.3, 2.5, 2.6, 2.7, 2.8
    """
    return GovOverview(
        kpi=kpi_counts(latest_df),
        district_ranking=district_risk_ranking(latest_df),
        high_risk_ranking=high_risk_ranking(latest_df),
        trend=risk_trend(full_df) if full_df is not None else [],
        hotspots=risk_hotspots(latest_df),
    )
