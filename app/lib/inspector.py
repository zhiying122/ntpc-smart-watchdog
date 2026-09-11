"""
稽查員調查工作台 — 檢視組裝邏輯（Inspector Workspace assembly, R5）
=====================================================================
小小守護員 Smart Watchdog Platform — 單一機構調查檢視的「呈現無關」組裝層。

本模組把 `src/` 既有的白盒計算模組（風險評分、時間軸、同儕、異常、證據鏈、
AI 助手）組裝為 Inspector_Workspace（R5）所需的資料結構，供 Streamlit 頁面
（app/pages/1_case.py）以「薄包裝」方式呈現。所有計算集中於此、可被單元測試
覆蓋，頁面本身不含計算邏輯。

對應需求（R5 稽查員調查工作台）：
  - R5.1：總風險分數（0–100）與風險等級。
  - R5.2：雷達圖分項組成（財務/裁罰/評鑑/輿情），各分項加權總和 == 總分。
  - R5.3：風險時間軸，涵蓋所有可取得年度且由舊到新排序。
  - R5.4：財務/收費/營運/法規/NLP 五類分析，每類含判讀結論與佐證數據。
  - R5.5：與同儕群組（相同機構類型）在各風險分項的比較數值。
  - R5.6：異常偵測結果，每筆標示異常類型與觸發來源指標。
  - R5.7：證據鏈，每筆風險判讀可追溯至來源證據項目。
  - R5.8：可解釋 AI 特徵歸因，列出貢獻最高前 5 項特徵及其貢獻方向（提高/降低）。
  - R5.9：可操作的調查檢核清單，每項可被標記為已完成或未完成。
  - R5.10：AI 稽查助手（Copilot）互動入口。
  - R5.11：為每一分析結果提供連結至原始資料來源。
  - R5.12：某分析類別無資料時顯示「無資料」狀態（見 five_category_analysis）。
  - R5.13：工作台資料載入失敗時顯示訊息並提供重新載入，且不覆寫既有已顯示資料。
  - R5.14：某原始來源連結無法開啟時顯示提示，其餘工作台內容維持可操作。
  - R20.1：HITL 審核回饋（確為異常/誤報/資料問題/需進一步稽查），關聯機構與判定。

責任 AI：本模組僅「發現異常、排序、解釋、提供證據、建議稽查方向」，
風險（risk）不等於違法（illegality）。
"""
from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass, field

# 讓本模組可被 app 頁面（sys.path 已含專案根）與測試（由根執行）匯入 src。
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import ai_report  # noqa: E402
from src import anomaly  # noqa: E402
from src import audit  # noqa: E402
from src import evidence  # noqa: E402
from src import peer  # noqa: E402
from src import risk_score  # noqa: E402
from src import timeline  # noqa: E402
from src.models import HITLFeedback, SourceRef  # noqa: E402


# ==========================================================================
# 呈現無關的資料結構（供頁面渲染）
# ==========================================================================
@dataclass
class RadarDimension:
    """雷達圖單一分項（R5.2）。

    - key：分項鍵（financial/penalty/eval/sentiment）。
    - label：顯示名稱（財務異常/裁罰紀錄/評鑑結果/輿情）。
    - subscore：分項原始分（0–100）。
    - weight：顯示權重（0–1）。
    - contribution：加權貢獻 = weight × subscore（各分項貢獻加總 == 總分）。
    """
    key: str
    label: str
    subscore: float
    weight: float
    contribution: float


@dataclass
class RadarBreakdown:
    """總風險分與其雷達圖分項組成（R5.1, R5.2）。

    不變式（R5.2）：round(sum(d.contribution for d in dimensions), 1) == total。
    """
    total: float
    level: str
    dimensions: list[RadarDimension] = field(default_factory=list)
    not_illegality_notice: str = ""
    data_confidence: float = 100.0


@dataclass
class TimelineView:
    """風險時間軸與變化點（R5.3, R12）。

    - years/values：由舊到新排序、涵蓋所有可取得年度。
    - change_points：偵測到的顯著變化點（每點附觸發說明）。
    """
    metric: str
    years: list[int] = field(default_factory=list)
    values: list[float | None] = field(default_factory=list)
    change_points: list[timeline.ChangePoint] = field(default_factory=list)


@dataclass
class CategoryAnalysis:
    """五類分析中的單一類別（R5.4）。

    - category：財務/收費/營運/法規/NLP。
    - conclusion：判讀結論（無資料時為「無資料」狀態文字）。
    - evidence：佐證數據項目清單（(標籤, 值) tuple）。
    - has_data：該類別是否有可用資料（R5.12 供頁面顯示「無資料」狀態）。
    - source：原始資料來源（R5.11）。
    """
    category: str
    conclusion: str
    evidence: list[tuple[str, str]] = field(default_factory=list)
    has_data: bool = True
    source: SourceRef | None = None


@dataclass
class PeerRow:
    """同儕比較單列（R5.5）。"""
    label: str
    value: float | None
    peer_median: float | None
    percentile: float | None
    position: str
    insufficient: bool
    # 同儕統計量（peer_stats 已算，過去未帶出）：z-score 與穩健偏差。
    # z_score = (x − 同儕平均)/標準差；robust_deviation 以中位數與 MAD 為基礎抗離群。
    z_score: float | None = None
    robust_deviation: float | None = None


@dataclass
class FeatureAttribution:
    """前 5 特徵歸因單項（R5.8）。

    - direction：'提高' 或 '降低'（貢獻方向）。
    - contribution：帶號貢獻量（正=提高風險，負=降低風險）。
    """
    feature: str
    label: str
    raw_value: str
    contribution: float
    direction: str


# ==========================================================================
# 工具：安全取值
# ==========================================================================
def _get(row, key, default=None):
    """從 dict 或 pandas.Series 取值；缺值/NaN 視為 default。"""
    if row is None:
        return default
    if hasattr(row, "get"):
        v = row.get(key, default)
    else:
        v = row[key] if key in row else default
    if v is None:
        return default
    if isinstance(v, float) and math.isnan(v):
        return default
    return v


def _to_dict(row):
    """把 pandas.Series/dict 統一轉為純 dict（供 src 模組使用）。"""
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "to_dict"):
        return row.to_dict()
    return dict(row)


# ==========================================================================
# 分項顯示定義（R5.2）
# ==========================================================================
# 雷達圖四分項：財務/裁罰/評鑑/輿情。權重沿用白盒 risk_score.WEIGHTS
# （financial 0.50 + penalty 0.34 + eval 0.16）。輿情尚未接入真實資料源，
# 依既有基線不納入計分（權重 0），但仍於雷達圖顯示以呈現四分項組成（誠實標示）。
RADAR_LABELS = {
    "financial": "財務異常",
    "penalty": "裁罰紀錄",
    "eval": "評鑑結果",
    "sentiment": "輿情",
}
_RADAR_ORDER = ("financial", "penalty", "eval", "sentiment")
_SUBSCORE_COL = {
    "financial": "score_financial",
    "penalty": "score_penalty",
    "eval": "score_eval",
    "sentiment": "score_sentiment",
}


# ==========================================================================
# R5.1 / R5.2：總風險分與雷達圖分項組成（加權總和 == 總分）
# ==========================================================================
def radar_breakdown(row, data_confidence=None) -> RadarBreakdown:
    """組裝總風險分與雷達圖四分項（R5.1, R5.2）。

    以白盒 `risk_score.score()` 取得可加性保證的分項貢獻，確保
    round(sum(contributions), 1) == total（R5.2 不變式）。�apply 輿情分項
    以權重 0 併入雷達圖顯示（不影響總分），維持「四分項組成」的呈現需求。

    參數：
      row：單一機構資料（dict 或 pandas.Series），含 score_* 或可計算來源欄位。
      data_confidence：資料可信度（0–100 或 DataConfidence），併同顯示（R18.3）。

    回傳：
      RadarBreakdown，dimensions 依 財務/裁罰/評鑑/輿情 順序排列；
      前三項貢獻加總（四捨五入一位小數）等於 total。
    """
    entity = _to_dict(row)
    breakdown = risk_score.score(entity, confidence=data_confidence)

    dims: list[RadarDimension] = []
    for key in _RADAR_ORDER:
        weight = breakdown.weights.get(key, 0.0)
        subscore = _radar_subscore(entity, key)
        # 貢獻取自白盒分解（保證可加性）；未計分分項（輿情）貢獻為 0。
        contribution = round(breakdown.contributions.get(key, 0.0), 4)
        dims.append(RadarDimension(
            key=key,
            label=RADAR_LABELS[key],
            subscore=round(float(subscore), 1),
            weight=round(float(weight), 4),
            contribution=contribution,
        ))

    return RadarBreakdown(
        total=breakdown.total,
        level=breakdown.level,
        dimensions=dims,
        not_illegality_notice=breakdown.not_illegality_notice,
        data_confidence=breakdown.data_confidence,
    )


def _radar_subscore(entity, key) -> float:
    """取分項顯示用原始分（0–100）。優先用已算好的 score_*，否則即時計算。"""
    col = _SUBSCORE_COL[key]
    pre = _get(entity, col)
    if pre is not None:
        try:
            return float(pre)
        except (TypeError, ValueError):
            pass
    if key == "financial":
        return float(risk_score.score_financial(entity))
    if key == "penalty":
        return float(risk_score.score_penalty(_get(entity, "penalty_count", 0)))
    if key == "eval":
        return float(risk_score.score_eval(_get(entity, "eval_grade", "")))
    if key == "sentiment":
        # 輿情尚未接入真實資料源 → 中性顯示值（不影響總分，權重為 0）。
        return float(risk_score.score_sentiment(_get(entity, "neg_ratio")))
    return 0.0


# ==========================================================================
# R5.3：風險時間軸（涵蓋所有年度、由舊到新）+ 變化點
# ==========================================================================
def risk_timeline(history_rows, metric="risk_total", entity_id="") -> TimelineView:
    """由某機構的多年度紀錄組裝風險時間軸與變化點（R5.3, R12）。

    參數：
      history_rows：該機構的多年度紀錄清單（list[dict] 或可轉為 dict 的列）。
      metric：時間軸指標欄位（預設 risk_total）。
      entity_id：機構識別碼（可留空由紀錄推得）。

    回傳：
      TimelineView，years/values 由舊到新排序且涵蓋所有可取得年度；
      change_points 由 `timeline.detect_change_points` 產出，每點附觸發說明。
    """
    records = [_to_dict(r) for r in (history_rows or [])]
    tl = timeline.build_timeline(records, metric=metric, entity_id=entity_id)
    values = [p.value for p in tl.points]
    change_points = timeline.detect_change_points(values, metric=metric)
    return TimelineView(
        metric=metric,
        years=[p.year for p in tl.points],
        values=values,
        change_points=change_points,
    )


# ==========================================================================
# R5.4：財務/收費/營運/法規/NLP 五類分析
# ==========================================================================
# 各類別的官方來源（R5.11）。
_SOURCE_FINANCE = SourceRef(dataset="公校決算書／機構財報", authority="新北市政府教育局")
_SOURCE_FEE = SourceRef(dataset="全國教保資訊網—收退費", authority="教育部")
_SOURCE_OPS = SourceRef(dataset="全國教保資訊網—基本資料", authority="教育部")
_SOURCE_LEGAL = SourceRef(dataset="全國教保資訊網—裁罰紀錄", authority="教育部")
_SOURCE_NLP = SourceRef(dataset="評鑑／裁罰／公告文本 NLP 分析", authority="新北市政府教育局")


def _fmt(v, digits=2, suffix=""):
    """數值格式化（去尾零）；缺值回傳「無資料」。"""
    if v is None:
        return "無資料"
    if isinstance(v, float) and math.isnan(v):
        return "無資料"
    if isinstance(v, float):
        s = f"{v:.{digits}f}".rstrip("0").rstrip(".")
        return f"{s}{suffix}"
    return f"{v}{suffix}"


def five_category_analysis(row) -> list[CategoryAnalysis]:
    """組裝財務/收費/營運/法規/NLP 五類分析（R5.4）。

    每一類別提供判讀結論與佐證數據；無可用資料的類別 has_data=False 且
    conclusion 為「無資料」狀態文字（供頁面依 R5.12 顯示無資料狀態），
    並附原始資料來源（R5.11）。
    """
    entity = _to_dict(row)
    out: list[CategoryAnalysis] = []

    # ---- 1) 財務 ----
    ratio = _get(entity, "expense_income_ratio")
    income = _get(entity, "income_actual")
    expense = _get(entity, "expense_actual")
    surplus = _get(entity, "surplus")
    fin_evidence = []
    if ratio is not None:
        fin_evidence.append(("收支比", _fmt(ratio, 3)))
    if income is not None:
        fin_evidence.append(("收入決算", _fmt(income, 0)))
    if expense is not None:
        fin_evidence.append(("支出決算", _fmt(expense, 0)))
    if surplus is not None:
        fin_evidence.append(("本期賸餘／短絀", _fmt(surplus, 0)))
    if fin_evidence:
        if ratio is not None and float(ratio) > 1:
            fin_concl = f"支出達收入的 {float(ratio):.2f} 倍，呈現入不敷出，需查核支出結構。"
        elif surplus is not None and float(surplus) < 0:
            fin_concl = "本期呈現短絀，基金可能受侵蝕，建議檢視收支平衡。"
        else:
            fin_concl = "財務收支大致平衡，未見明顯失衡訊號。"
        out.append(CategoryAnalysis("財務", fin_concl, fin_evidence, True, _SOURCE_FINANCE))
    else:
        out.append(CategoryAnalysis("財務", "無資料", [], False, _SOURCE_FINANCE))

    # ---- 2) 收費 ----
    tuition = _get(entity, "tuition_actual")
    if tuition is not None:
        fee_evidence = [("學雜費收入", _fmt(tuition, 0))]
        if income is not None and float(income) > 0:
            share = float(tuition) / float(income) * 100
            fee_evidence.append(("學雜費占收入", _fmt(share, 1, "%")))
            fee_concl = f"學雜費占收入約 {share:.1f}%，可對照公告收費標準核對是否超收。"
        else:
            fee_concl = "已取得學雜費收入，建議對照公告收費標準核對。"
        out.append(CategoryAnalysis("收費", fee_concl, fee_evidence, True, _SOURCE_FEE))
    else:
        out.append(CategoryAnalysis("收費", "無資料", [], False, _SOURCE_FEE))

    # ---- 3) 營運 ----
    yoy = _get(entity, "expense_yoy_pct")
    if yoy is not None:
        ops_evidence = [("年度支出增減", _fmt(yoy, 1, "%"))]
        if abs(float(yoy)) >= 20:
            ops_concl = f"年度支出較前年變動 {float(yoy):.0f}%，波動偏大，建議查核大額支出。"
        else:
            ops_concl = "營運支出年度變動在常態範圍。"
        out.append(CategoryAnalysis("營運", ops_concl, ops_evidence, True, _SOURCE_OPS))
    else:
        out.append(CategoryAnalysis("營運", "無資料", [], False, _SOURCE_OPS))

    # ---- 4) 法規（裁罰/評鑑）----
    pen = _get(entity, "penalty_count")
    grade = _get(entity, "eval_grade")
    legal_evidence = []
    if pen is not None:
        legal_evidence.append(("裁罰次數", f"{int(float(pen))}"))
    if grade not in (None, ""):
        legal_evidence.append(("評鑑等第", str(grade)))
    if legal_evidence:
        if pen is not None and int(float(pen)) > 0:
            legal_concl = f"已有 {int(float(pen))} 次裁罰紀錄，屬已知風險標的，建議查核改善情形。"
        else:
            legal_concl = "查無裁罰紀錄；評鑑結果供綜合研判參考。"
        out.append(CategoryAnalysis("法規", legal_concl, legal_evidence, True, _SOURCE_LEGAL))
    else:
        out.append(CategoryAnalysis("法規", "無資料", [], False, _SOURCE_LEGAL))

    # ---- 5) NLP（文字分析）----
    mad = _get(entity, "benford_mad")
    beneish = _get(entity, "beneish_score")
    nlp_evidence = []
    if mad is not None:
        nlp_evidence.append(("班佛偏離度 MAD", _fmt(mad, 5)))
    if beneish is not None:
        nlp_evidence.append(("Beneish 操縱分", _fmt(beneish, 1)))
    if nlp_evidence:
        nlp_concl = ("財務文本與數字分布指標可作為文字分析之量化佐證，"
                     "供 NLP 事件摘要對照。")
        out.append(CategoryAnalysis("NLP", nlp_concl, nlp_evidence, True, _SOURCE_NLP))
    else:
        out.append(CategoryAnalysis("NLP", "無資料", [], False, _SOURCE_NLP))

    return out


# ==========================================================================
# R5.5：同儕比較（相同機構類型）
# ==========================================================================
# 同儕比較的分項指標（相同機構類型群組）。
_PEER_METRICS = [
    ("risk_total", "總風險分"),
    ("score_financial", "財務異常分"),
    ("score_penalty", "裁罰分"),
    ("score_eval", "評鑑分"),
]


def peer_comparison(row, population, by=("park_type",)) -> list[PeerRow]:
    """組裝機構與同儕群組（預設相同機構類型）在各分項的比較（R5.5, R13）。

    參數：
      row：受評機構（dict 或 pandas.Series）。
      population：全體機構清單（list[dict] 或可轉為 dict 的列）。
      by：同儕分群維度，預設 ("park_type",)（相同機構類型，R5.5）。

    回傳：
      list[PeerRow]，每列為一分項的同儕統計量（中位數/百分位/相對位置）；
      群組樣本不足時 insufficient=True。
    """
    entity = _to_dict(row)
    pop = [_to_dict(r) for r in (population or [])]
    group = peer.build_peer_group(entity, pop, by=tuple(by))

    rows: list[PeerRow] = []
    for metric, label in _PEER_METRICS:
        comp = peer.peer_stats(entity, group, metric=metric)
        rows.append(PeerRow(
            label=label,
            value=comp.value,
            peer_median=comp.median,
            percentile=comp.percentile,
            position=comp.position or "無法判定",
            insufficient=comp.insufficient,
            z_score=comp.z_score,
            robust_deviation=comp.robust_deviation,
        ))
    return rows


# ==========================================================================
# R5.6：異常偵測結果（每筆標示異常類型與觸發來源指標）
# ==========================================================================
# 供異常偵測的財務特徵欄位（作為多維特徵矩陣的來源）。
_ANOMALY_FEATURE_COLS = [
    "score_financial", "expense_income_ratio", "benford_mad",
    "beneish_score", "iforest_score", "expense_yoy_pct",
]


@dataclass
class AnomalyView:
    """單一異常類型的整合檢視（R5.6）。"""
    anomaly_type: str          # 點異常/情境異常/集體異常
    flag: bool
    score: float
    trigger_metrics: list[str] = field(default_factory=list)


@dataclass
class AnomalyMethodDetail:
    """單一異常偵測方法的明細（R8.2, R8.3）。

    露出 anomaly.detect 每個方法的個別結果與其適用性說明（method_applicability），
    讓稽查員看見「七種方法各自怎麼判、適用什麼、有何限制」——白盒可解釋、
    多方法交叉驗證的護城河可視化。
    """
    method: str                # 方法內部名（isolation_forest/lof/zscore…）
    label: str                 # 中文顯示名
    anomaly_type: str          # 點異常/情境異常/集體異常
    score: float               # 0–100 異常分
    threshold: float           # 判定門檻
    flag: bool                 # 是否達門檻
    applicable: bool           # 樣本是否足夠（False=樣本不足跳過）
    assumption: str = ""       # 資料前提/假設
    limitation: str = ""       # 已知限制


@dataclass
class AnomalySummary:
    """機構整體異常偵測摘要（R5.6, R8）。"""
    items: list[AnomalyView] = field(default_factory=list)
    confidence_label: str = "to_confirm"
    hit_count: int = 0
    # 七種方法的個別明細（含適用性/假設/限制），供護城河可視化。
    methods: list[AnomalyMethodDetail] = field(default_factory=list)


# 方法內部名 → 中文顯示名。
_ANOMALY_METHOD_LABEL = {
    "isolation_forest": "孤立森林",
    "lof": "局部離群因子 (LOF)",
    "zscore": "Z-score",
    "robust": "穩健統計 (MAD)",
    "timeseries": "時間序列 (YoY)",
    "changepoint": "變化點偵測",
    "clustering": "分群離群",
}


_ANOMALY_TYPE_LABEL = {
    "point": "點異常",
    "contextual": "情境異常",
    "collective": "集體異常",
}


def anomaly_summary(row, population, history_rows=None) -> AnomalySummary:
    """組裝機構的異常偵測結果，標示異常類型與觸發來源指標（R5.6, R8）。

    以機構在群體中的 risk_total 分布（point/collective 判定）與跨年度序列
    （contextual 判定）為輸入，呼叫 `anomaly.detect`；再整合一致性標籤。

    參數：
      row：受評機構（dict 或 pandas.Series）。
      population：全體機構清單（供同儕母體與特徵矩陣）。
      history_rows：該機構的多年度紀錄（供時間序列／變化點情境異常）。

    回傳：
      AnomalySummary，items 為 點/情境/集體 三類異常的旗標、分數與觸發指標；
      並附一致性標籤（≥2 方法命中 → high_confidence）。
    """
    entity = _to_dict(row)
    pop = [_to_dict(r) for r in (population or [])]
    hist = [_to_dict(r) for r in (history_rows or [])]

    target_value = _get(entity, "risk_total")
    population_values = [
        float(_get(r, "risk_total"))
        for r in pop
        if _get(r, "risk_total") is not None
    ]

    # 多維特徵矩陣：母體各機構的財務特徵 + 目標機構特徵。
    matrix = []
    for r in pop:
        feats = [float(_get(r, c, 0.0) or 0.0) for c in _ANOMALY_FEATURE_COLS]
        matrix.append(feats)
    target_features = [float(_get(entity, c, 0.0) or 0.0) for c in _ANOMALY_FEATURE_COLS]

    # 時間序列（由舊到新的 risk_total）供情境異常。
    series = []
    if hist:
        tl = timeline.build_timeline(hist, metric="risk_total")
        series = [p.value for p in tl.points if p.value is not None]

    ctx = {
        "value": target_value,
        "population": population_values,
        "series": series,
        "features": target_features,
        "feature_matrix": matrix if matrix else None,
    }

    result = anomaly.detect(ctx)
    consolidated = anomaly.consolidate(result.methods)

    # 各類型的觸發來源指標（命中該類型的適用方法名稱）。
    trigger_by_type: dict[str, list[str]] = {"point": [], "contextual": [], "collective": []}
    for m in result.methods:
        if not m.applicable:
            continue
        atype = m.note.get("anomaly_type")
        if atype in trigger_by_type and m.flag:
            trigger_by_type[atype].append(m.method)

    items = []
    for atype, (flag, score) in (
        ("point", result.point),
        ("contextual", result.contextual),
        ("collective", result.collective),
    ):
        items.append(AnomalyView(
            anomaly_type=_ANOMALY_TYPE_LABEL[atype],
            flag=flag,
            score=score,
            trigger_metrics=trigger_by_type[atype],
        ))

    # 七方法個別明細：帶出每個方法的分數/門檻/旗標與適用性說明（假設/限制）。
    # 這些資料 anomaly.detect 已算出，過去被丟棄；此處保留以做護城河可視化。
    method_details: list[AnomalyMethodDetail] = []
    for m in result.methods:
        try:
            note = anomaly.method_applicability(m.method)
            assumption, limitation = note.assumption, note.limitation
            atype = note.anomaly_type
        except ValueError:
            assumption = limitation = ""
            atype = m.note.get("anomaly_type", "") if m.note else ""
        method_details.append(AnomalyMethodDetail(
            method=m.method,
            label=_ANOMALY_METHOD_LABEL.get(m.method, m.method),
            anomaly_type=_ANOMALY_TYPE_LABEL.get(atype, atype),
            score=round(float(m.score), 1),
            threshold=round(float(m.threshold), 1),
            flag=bool(m.flag),
            applicable=bool(m.applicable),
            assumption=assumption,
            limitation=limitation,
        ))

    return AnomalySummary(
        items=items,
        confidence_label=consolidated.confidence_label,
        hit_count=consolidated.hit_count,
        methods=method_details,
    )


# ==========================================================================
# R5.8：前 5 特徵歸因（含貢獻方向）
# ==========================================================================
# 可歸因特徵 → (顯示標籤, 中性基準值, 方向語意)。
# 每個特徵以「與中性基準的偏離」估其對總風險分的帶號貢獻（正=提高、負=降低）。
_ATTRIBUTION_FEATURES = {
    "score_financial": ("財務異常分項", 0.0),
    "score_penalty": ("裁罰分項", 0.0),
    "score_eval": ("評鑑分項", 30.0),
    "expense_income_ratio": ("收支比", 1.0),
    "benford_mad": ("班佛偏離度 MAD", 0.006),
    "beneish_score": ("Beneish 操縱分", 0.0),
    "iforest_score": ("孤立森林異常分", 0.0),
    "expense_yoy_pct": ("年度支出增減", 0.0),
}


def top_feature_attributions(row, n=5) -> list[FeatureAttribution]:
    """列出對總風險分貢獻最高的前 n 項特徵及其貢獻方向（R5.8）。

    以各特徵相對中性基準的帶號偏離估其貢獻（正=提高風險、負=降低風險），
    取絕對值最大的前 n 項回傳。此為可解釋的白盒歸因（非黑箱），與雷達圖分項
    及鑑識指標一致、可追溯。

    參數：
      row：單一機構資料（dict 或 pandas.Series）。
      n：回傳的特徵數上限（預設 5）。

    回傳：
      list[FeatureAttribution]，依 |contribution| 由大到小排序，至多 n 筆。
    """
    entity = _to_dict(row)
    scored: list[FeatureAttribution] = []
    for feat, (label, neutral) in _ATTRIBUTION_FEATURES.items():
        raw = _get(entity, feat)
        if raw is None:
            continue
        try:
            val = float(raw)
        except (TypeError, ValueError):
            continue
        contribution = round(val - float(neutral), 4)
        if contribution == 0:
            continue
        direction = "提高" if contribution > 0 else "降低"
        scored.append(FeatureAttribution(
            feature=feat,
            label=label,
            raw_value=_fmt(val, 4) if isinstance(val, float) else str(val),
            contribution=contribution,
            direction=direction,
        ))

    scored.sort(key=lambda a: abs(a.contribution), reverse=True)
    return scored[:n]


# ==========================================================================
# R5.7：證據鏈（每筆風險判讀可追溯至來源證據）
# ==========================================================================
def evidence_chain(row) -> evidence.EvidenceChain:
    """由機構的風險特徵組裝可追溯證據鏈（R5.7, R11）。

    以前 5 特徵歸因作為結論的特徵歸因來源，建立
    「結論 → 特徵 → 原始資料值 → 官方來源」的完整證據鏈；每一環皆可追溯
    （is_fully_traceable() 為 True，當至少一項歸因時）。

    參數：
      row：單一機構資料（dict 或 pandas.Series）。

    回傳：
      evidence.EvidenceChain。
    """
    entity = _to_dict(row)
    entity_id = str(_get(entity, "park_id", _get(entity, "park_name", "")))
    name = str(_get(entity, "park_name", "該機構"))
    total = _get(entity, "risk_total")
    total_txt = f"{float(total):.1f}" if total is not None else "—"
    conclusion_text = (
        f"{name}總風險分 {total_txt}，主要由財務異常與法規/評鑑等分項訊號構成，"
        "屬需進一步查核之風險排序參考（風險不等於違法）。"
    )

    attributions = []
    for attr in top_feature_attributions(entity, n=5):
        # 依特徵對應官方來源（R11.4）。
        if attr.feature in ("score_penalty",):
            source = _SOURCE_LEGAL
        elif attr.feature in ("score_eval",):
            source = SourceRef(dataset="教保機構評鑑結果", authority="新北市政府教育局")
        else:
            source = _SOURCE_FINANCE
        attributions.append(evidence.FeatureAttribution(
            feature=attr.label,
            raw_value=attr.raw_value,
            source=source,
            contribution=attr.contribution,
            method="rule",
        ))

    conclusion = evidence.RiskConclusion(
        entity_id=entity_id,
        conclusion=conclusion_text,
        attributions=attributions,
    )
    return evidence.build_evidence_chain(conclusion)


# ==========================================================================
# R5.10：AI 稽查助手（Copilot）入口
# ==========================================================================
def copilot_answer(question, row) -> ai_report.CopilotAnswer:
    """以機構資料為依據回答稽查員提問（R5.10, R15）。

    直接委派 `ai_report.answer`，回答以該機構資料為依據、關鍵陳述附來源、
    資料不足明確告知不杜撰，且不作違法/舞弊斷言。

    參數：
      question：稽查員提問文字。
      row：單一機構資料（dict 或 pandas.Series）。

    回傳：
      ai_report.CopilotAnswer。
    """
    entity = _to_dict(row)
    return ai_report.answer(question, entity)


# ==========================================================================
# R5.9：可操作的調查檢核清單（每項可標記已完成/未完成）
# ==========================================================================
@dataclass
class ChecklistItem:
    """調查檢核清單單一項目（R5.9）。

    - key：項目穩定鍵（供頁面 widget key 與狀態保存）。
    - label：顯示文字。
    - done：是否已完成（可被稽查員切換）。
    - hint：操作提示（可空）。
    """
    key: str
    label: str
    done: bool = False
    hint: str = ""


# 預設調查檢核清單：對齊鑑識會計調查流程與五類分析（R5.4/R5.9）。
_DEFAULT_CHECKLIST: tuple[tuple[str, str, str], ...] = (
    ("finance", "核對財務決算收支與收支比是否失衡", "對照決算書收入/支出/賸餘"),
    ("fee", "核對學雜費是否符合公告收費標準", "對照全國教保資訊網收退費公告"),
    ("penalty", "查核既有裁罰紀錄之改善情形", "對照裁罰紀錄與限期改善結果"),
    ("eval", "檢視評鑑等第與待改善事項", "對照最近一次評鑑報告"),
    ("benford", "檢視班佛偏離度等鑑識指標是否異常", "MAD 偏高需查核數字造假可能"),
    ("evidence", "確認每一風險判讀均可追溯至官方來源", "檢視證據鏈完整可追溯"),
    ("onsite", "研判是否需實地稽查或要求補件", "綜合風險分項與異常研判"),
)


def default_checklist() -> list[ChecklistItem]:
    """回傳預設調查檢核清單（全部未完成）（R5.9）。

    頁面可將本清單渲染為可勾選項目；每次呼叫回傳全新物件，
    避免跨機構/跨 session 的狀態污染。
    """
    return [
        ChecklistItem(key=k, label=label, done=False, hint=hint)
        for (k, label, hint) in _DEFAULT_CHECKLIST
    ]


def apply_checklist_state(items, state) -> list[ChecklistItem]:
    """依外部狀態（key -> bool）套用勾選狀態，回傳更新後清單（R5.9）。

    供頁面於 rerun 後由 session_state 還原勾選狀態；未在 state 中出現的項目
    維持原 done 值。回傳新 list（不就地修改輸入），保持呈現無關與可測性。

    參數：
      items：ChecklistItem 清單。
      state：dict[str, bool]，key 對應項目 key。
    """
    st = dict(state or {})
    out: list[ChecklistItem] = []
    for it in items:
        done = st.get(it.key, it.done)
        out.append(ChecklistItem(key=it.key, label=it.label,
                                  done=bool(done), hint=it.hint))
    return out


def checklist_progress(items) -> tuple[int, int]:
    """回傳檢核清單完成度 (已完成數, 總數)（R5.9）。"""
    items = list(items or [])
    done = sum(1 for it in items if it.done)
    return done, len(items)


# ==========================================================================
# R20.1：HITL 審核回饋（確為異常/誤報/資料問題/需進一步稽查）
# ==========================================================================
# 回饋標籤沿用 src.audit 的權威定義，確保與後端驗證一致（R20.1）。
FEEDBACK_LABELS: tuple[str, ...] = audit.FEEDBACK_LABELS


@dataclass
class FeedbackResult:
    """HITL 回饋提交結果（呈現無關）（R20.1）。

    - ok：是否成功寫入。
    - message：供頁面顯示的結果訊息（成功確認或錯誤原因）。
    - feedback：成功時的已記錄回饋（否則為 None）。
    """
    ok: bool
    message: str
    feedback: HITLFeedback | None = None


def feedback_labels() -> list[str]:
    """回傳 HITL 回饋允許的四種標籤，供頁面產生按鈕（R20.1）。"""
    return list(FEEDBACK_LABELS)


def submit_hitl_feedback(entity_id, verdict_ref, label,
                         store=None, actor="inspector") -> FeedbackResult:
    """提交一筆 HITL 審核回饋，關聯機構與判定，並驗證標籤（R20.1）。

    委派 `src.audit` 的 FeedbackStore.submit_feedback 進行標籤驗證與寫入
    （四種允許標籤：確為異常/誤報/資料問題/需進一步稽查），本函式僅做
    呈現無關的組裝與錯誤轉譯，不自行判斷業務規則（單一事實來源）。

    參數：
      entity_id：受評機構識別碼（park_id 或名稱）。
      verdict_ref：所回饋之判定參照（如風險判定 ref）。
      label：四種允許標籤之一。
      store：audit.FeedbackStore 實例；未提供時使用模組層級便利入口。
      actor：提交回饋的操作者（供稽核軌跡）。

    回傳：
      FeedbackResult。標籤或關聯無效時 ok=False 並附錯誤訊息（不丟出例外）。
    """
    entity_id = "" if entity_id is None else str(entity_id).strip()
    verdict_ref = "" if verdict_ref is None else str(verdict_ref).strip()
    label = "" if label is None else str(label).strip()

    fb = HITLFeedback(entity_id=entity_id, verdict_ref=verdict_ref, label=label)
    try:
        if store is not None:
            recorded = store.submit_feedback(fb, actor=actor)
        else:
            recorded = audit.submit_feedback(fb, actor=actor)
    except ValueError as exc:
        return FeedbackResult(ok=False, message=str(exc), feedback=None)

    return FeedbackResult(
        ok=True,
        message=f"已記錄回饋「{label}」，並關聯至機構 {entity_id} 之判定。",
        feedback=recorded,
    )


# ==========================================================================
# R5.13：工作台資料載入失敗 — 顯示訊息 + 重新載入（不覆寫既有已顯示資料）
# ==========================================================================
@dataclass
class WorkspaceData:
    """工作台資料載入結果（呈現無關）（R5.13）。

    - ok：本次載入是否成功。
    - row：載入到的機構資料（成功時）。
    - message：供頁面顯示的訊息（失敗時為載入失敗說明）。
    - stale：目前持有的資料是否為既有（上一次成功）而非本次載入。
    """
    ok: bool
    row: dict | None = None
    message: str = ""
    stale: bool = False


LOAD_FAILURE_MESSAGE = "工作台資料載入失敗，請按「重新載入」再試一次。"


def load_workspace_data(loader, existing=None) -> WorkspaceData:
    """載入工作台資料；失敗時保留既有資料且不覆寫（R5.13）。

    以呼叫端提供的 `loader`（無參數 callable，回傳機構資料 dict/Series）
    嘗試載入。成功則回傳新資料；失敗（丟出例外或回傳空）則回傳載入失敗訊息
    並「保留」既有已顯示資料（existing），供頁面提供「重新載入」而不清空畫面。

    參數：
      loader：無參數 callable，回傳機構資料；失敗可丟出任意例外。
      existing：目前已顯示的機構資料（dict/Series），載入失敗時沿用。

    回傳：
      WorkspaceData。成功 ok=True 帶新資料；失敗 ok=False，若有既有資料則
      row=existing 且 stale=True（不覆寫），否則 row=None。
    """
    prev = _to_dict(existing) if existing is not None else None
    try:
        loaded = loader()
    except Exception as exc:  # noqa: BLE001 — 任一載入例外皆轉為友善訊息
        msg = f"{LOAD_FAILURE_MESSAGE}（原因：{exc}）"
        return WorkspaceData(ok=False, row=prev, message=msg,
                             stale=prev is not None)

    if loaded is None or (hasattr(loaded, "__len__") and len(loaded) == 0):
        return WorkspaceData(ok=False, row=prev, message=LOAD_FAILURE_MESSAGE,
                             stale=prev is not None)

    return WorkspaceData(ok=True, row=_to_dict(loaded), message="", stale=False)


# ==========================================================================
# R5.14：來源連結無法開啟 — 顯示提示，其餘內容維持可操作
# ==========================================================================
@dataclass
class SourceLink:
    """單一資料來源的可點擊連結狀態（R5.11, R5.14）。

    - label：來源顯示文字（資料集＋主管機關）。
    - url：來源連結（無或無法開啟時為 None）。
    - accessible：連結是否可存取；False 時頁面顯示無法存取提示。
    - notice：無法存取時的提示文字（可空）。
    """
    label: str
    url: str | None
    accessible: bool = True
    notice: str = ""


def _looks_openable(url) -> bool:
    """判斷連結是否為可開啟的 http(s) 連結（不做網路請求，純格式檢查）。"""
    if not url or not isinstance(url, str):
        return False
    u = url.strip().lower()
    return u.startswith("http://") or u.startswith("https://")


def source_link(source, reachable=None) -> SourceLink:
    """由 SourceRef 組裝可點擊來源連結，並標示是否可存取（R5.11, R5.14）。

    當來源無連結或連結無法開啟時，回傳 accessible=False 與提示文字，
    頁面據此顯示「該來源無法存取」提示，而其餘工作台內容維持可正常操作
    （本函式不丟出例外、不影響其他來源）。

    參數：
      source：SourceRef（可為 None）。
      reachable：可選的外部連通性判定（bool）；提供時覆蓋純格式檢查，
                 供頁面在已知連結失效時明確標示無法存取。

    回傳：
      SourceLink。
    """
    if source is None:
        return SourceLink(label="（無來源）", url=None, accessible=False,
                          notice="此分析結果尚未提供原始資料來源連結。")

    label = f"{source.dataset}（{source.authority}）"
    url = getattr(source, "url", None)

    if reachable is None:
        accessible = _looks_openable(url)
    else:
        accessible = bool(reachable) and _looks_openable(url)

    notice = "" if accessible else "此來源連結目前無法開啟，其餘內容仍可正常操作。"
    return SourceLink(label=label, url=(url if accessible else None),
                      accessible=accessible, notice=notice)


def category_source_links(categories, reachability=None) -> list[SourceLink]:
    """為五類分析各類別組裝來源連結狀態（R5.11, R5.14）。

    單一來源無法開啟不影響其餘類別（各自獨立回傳），落實「其餘內容維持
    可操作」。

    參數：
      categories：five_category_analysis 回傳的 CategoryAnalysis 清單。
      reachability：可選 dict[str, bool]，以類別名稱對應該來源是否可連通。

    回傳：
      list[SourceLink]，順序對齊輸入類別。
    """
    reach = dict(reachability or {})
    links: list[SourceLink] = []
    for cat in (categories or []):
        r = reach.get(getattr(cat, "category", None))
        links.append(source_link(getattr(cat, "source", None), reachable=r))
    return links
