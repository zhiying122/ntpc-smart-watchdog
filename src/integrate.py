"""
風險引擎輸出串接（Risk Engine Integration, Task 22.1）
========================================================
小小守護員 Smart Watchdog Platform — 將五大風險引擎的輸出串接成單一「已算好」
的契約資料，供三入口（Gov_Console / Inspector_Workspace / Parent_Portal）
與 AI Copilot 直接讀取。

⚠️ 實作狀態（務必先讀）：本模組為 **design.md / Task 22.1 規格對齊實作**，
展示「五引擎輸出 → 附加欄位 → 契約檔」的端到端串接架構，但**目前未接入 live
資料主幹**。現行 live 契約檔（kindergartens_latest.csv / kindergartens.csv）
**實際由 `src/risk_score.py` 的 `main()` 產生**（流程見 scripts/rebuild_all.py）。
真正的資料流請追 scripts/rebuild_all.py 與 src/risk_score.py；本模組保留供
規格對齊與未來規模化擴充。

對應需求：
  - R17.1：整合財務／裁罰／評鑑／收費／地理資料的資料管線（本模組串接其上游
    產物，形成端到端資料流 RAW → Pipeline → Forensic/Anomaly → Scorer →
    Timeline/Evidence → 契約檔）。
  - R10.1：Risk_Scorer 融合各分項輸出 0–100 風險分（本模組把 Scorer 產出的
    total/level/各分項貢獻寫入契約列，讓三入口讀「已算好」的分數）。
  - R11.1：為每一風險結論建立證據鏈（本模組把 Evidence 產出的可追溯摘要
    附加到契約列，供 Inspector_Workspace 展示、可回溯官方來源）。

設計原則（對齊 project-vision 白盒可解釋 + design.md 資料流）：
  1. **附加而非破壞**：輸出欄位以既有 CONTRACT_COLUMNS 為基礎，本模組新增的
     欄位（EXTRA_COLUMNS）一律「附加」在既有欄位之後。既有 app/lib/common.py
     以 `pandas.read_csv` 載入契約檔，多出的欄位不影響既有欄位的讀取，故載入
     契約不被破壞。
  2. **單向資料流、AI 不回流**：本模組只把「規則／統計」算出的分數與指標寫入
     契約。AI 層（src/ai_report.py）僅「讀取」契約中的已算好分數（如 risk_total、
     score_*），絕不參與計分，也不把 AI 產物寫回計分欄位（維持可解釋白盒）。
     `assert_no_ai_reflux()` 以斷言保護此不變式。
  3. **安全（不破壞既有資料檔）**：`import` 本模組不會有任何寫檔副作用；
     `integrate_dataset()` 只回傳記憶體物件；落地必須明確呼叫
     `write_integrated_contract_files()` 並由呼叫端指定輸出路徑。預設不覆寫
     data/processed 下供 UI 載入的既有檔。

本模組僅依賴標準函式庫與既有 src 模組；pandas 為選用相依，僅在 `from_dataframe`
輔助入口使用，維持既有基線可攜性。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from src import risk_score
from src.evidence import (
    FeatureAttribution,
    RiskConclusion,
    build_evidence_chain,
)
from src.pipeline import CONTRACT_COLUMNS, _write_csv
from src.timeline import build_timeline, detect_change_points

# --------------------------------------------------------------------------
# 附加欄位（一律加在既有 CONTRACT_COLUMNS 之後，維持既有載入契約）
# --------------------------------------------------------------------------
# 這些欄位由本模組串接各引擎輸出後寫入，供三入口與 Copilot「讀取已算好」的值。
# 命名以 eng_* 前綴標示為「風險引擎附加輸出」，避免與既有契約欄位衝突。
EXTRA_COLUMNS: tuple[str, ...] = (
    # --- Scorer（R10.1）：以白盒 score() 產出的權威總分/等級/責任 AI 聲明 ---
    "eng_risk_total",        # 0–100 白盒總分（與 score_* 分項可加性一致）
    "eng_risk_level",        # 低/中/高/極高
    "eng_not_illegality",    # 「風險不等於違法」非空聲明（R10.4/R19.4）
    "eng_data_confidence",   # 資料可信度（0–100，併同顯示，不參與計分 R18.3）
    # --- Anomaly（R8）：三類異常整合旗標與一致性標示（唯讀展示） ---
    "eng_anomaly_point",       # 點異常 flag
    "eng_anomaly_contextual",  # 情境異常 flag
    "eng_anomaly_collective",  # 集體異常 flag
    "eng_anomaly_confidence",  # high_confidence / to_confirm / none
    "eng_anomaly_hit_count",   # 命中方法數
    # --- Timeline（R12）：跨年度變化點數與最新觸發說明（唯讀展示） ---
    "eng_change_point_count",  # 偵測到的變化點數
    "eng_change_point_note",   # 最新一個變化點的觸發指標說明（R12.4）
    # --- Evidence（R11.1）：證據鏈是否完整可追溯 + 摘要（唯讀展示） ---
    "eng_evidence_traceable",  # 證據鏈是否完整可追溯（bool）
    "eng_evidence_summary",    # 證據鏈摘要（結論 + 環數，供 Inspector 展示）
)

# 完整輸出欄位順序＝既有契約欄位 + 附加欄位（附加在後，不破壞既有載入契約）。
INTEGRATED_COLUMNS: tuple[str, ...] = tuple(CONTRACT_COLUMNS) + EXTRA_COLUMNS

# AI 絕不可回寫的「計分欄位」白名單（用於 assert_no_ai_reflux 保護）。
# 這些欄位只能由規則／統計引擎（Scorer/Forensic）產出（維持白盒、AI 不回流）。
SCORING_COLUMNS: frozenset[str] = frozenset({
    "score_financial", "score_penalty", "score_eval",
    "risk_total", "risk_level", "risk_level_abs",
    "eng_risk_total", "eng_risk_level",
})


# --------------------------------------------------------------------------
# 輸出資料模型
# --------------------------------------------------------------------------
@dataclass
class IntegratedContract:
    """串接後的契約資料集（記憶體物件，不落地）。

    - rows：每列為 dict，含既有契約欄位 + 附加引擎欄位（EXTRA_COLUMNS）。
    - columns：完整欄位順序（INTEGRATED_COLUMNS）。

    Validates: Requirements 10.1, 11.1, 17.1
    """
    rows: list[dict] = field(default_factory=list)
    columns: tuple[str, ...] = INTEGRATED_COLUMNS


# --------------------------------------------------------------------------
# 輔助：安全取值
# --------------------------------------------------------------------------
def _get(row: Mapping | Any, key: str, default: Any = None) -> Any:
    """從 dict 或具屬性物件安全取值。"""
    if isinstance(row, Mapping):
        return row.get(key, default)
    if hasattr(row, "get"):
        try:
            return row.get(key, default)
        except TypeError:
            pass
    return getattr(row, key, default)


def _is_missing(v: Any) -> bool:
    """None / NaN / 空字串視為缺值。"""
    if v is None or v == "":
        return True
    try:
        return bool(v != v)  # NaN
    except Exception:
        return False


def _to_float(v: Any) -> float | None:
    if _is_missing(v):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f


def _blank_integrated_row() -> dict:
    """建立一列，含全部欄位（既有契約 + 附加），預設 None（中性空值）。"""
    return {col: None for col in INTEGRATED_COLUMNS}


# --------------------------------------------------------------------------
# 各引擎串接（每個引擎的輸出 → 附加欄位）
# --------------------------------------------------------------------------
def _apply_scorer(out: dict, source_row: Mapping | Any) -> None:
    """以白盒 Scorer（src.risk_score.score）算出權威總分/等級並寫入附加欄位。

    Scorer 沿用既有分項評分（score_financial/score_penalty/score_eval 或其來源
    欄位），輸出 RiskBreakdown（可加性、責任 AI 聲明、資料可信度），確保三入口
    讀到「已算好」且可解釋的分數（R10.1）。缺分項以中性值處理，不放大風險。
    """
    confidence = _get(source_row, "data_confidence")
    breakdown = risk_score.score(source_row, confidence=confidence)
    out["eng_risk_total"] = breakdown.total
    out["eng_risk_level"] = breakdown.level
    out["eng_not_illegality"] = breakdown.not_illegality_notice
    out["eng_data_confidence"] = breakdown.data_confidence


def _apply_anomaly(out: dict, anomaly_result: Any) -> None:
    """把 Anomaly 三類整合結果寫入附加欄位（唯讀展示，不參與計分）。

    anomaly_result 需為 src.anomaly.detect 產出的 AnomalyResult（或相容物件）。
    None 時保持欄位為預設（None），不中斷串接（R8.5 精神：不因缺席而中斷）。
    """
    if anomaly_result is None:
        return
    point = getattr(anomaly_result, "point", (False, 0.0))
    contextual = getattr(anomaly_result, "contextual", (False, 0.0))
    collective = getattr(anomaly_result, "collective", (False, 0.0))
    out["eng_anomaly_point"] = bool(point[0])
    out["eng_anomaly_contextual"] = bool(contextual[0])
    out["eng_anomaly_collective"] = bool(collective[0])
    out["eng_anomaly_confidence"] = getattr(
        anomaly_result, "confidence_label", "to_confirm"
    )
    out["eng_anomaly_hit_count"] = int(
        getattr(anomaly_result, "method_hit_count", 0)
    )


def _apply_timeline(out: dict, year_records: Iterable[Mapping] | None,
                    metric: str = "risk_total") -> None:
    """建立跨年度時間軸與變化點，把數量與最新觸發說明寫入附加欄位（R12）。

    year_records 為該機構跨年度紀錄（每筆含 year 與 metric 欄位）；None/空時
    變化點數為 0、說明為 None（唯讀展示，不影響計分）。
    """
    if not year_records:
        out["eng_change_point_count"] = 0
        return
    records = list(year_records)
    timeline = build_timeline(records, metric=metric)
    series = [p.value for p in timeline.points]
    change_points = detect_change_points(series, metric=metric)
    out["eng_change_point_count"] = len(change_points)
    if change_points:
        # 取時間上最新（index 最大）的變化點觸發說明（R12.4）。
        latest_cp = max(change_points, key=lambda cp: cp.index)
        out["eng_change_point_note"] = latest_cp.trigger


def _apply_evidence(out: dict, conclusion: Any) -> None:
    """把證據鏈可追溯性與摘要寫入附加欄位（R11.1）。

    conclusion 可為：
      - src.evidence.RiskConclusion（直接建鏈）。
      - None：由本列已算好的分項自動組出一個「風險摘要結論」以建立最小證據鏈，
        確保三入口顯示風險結論時皆能附上可追溯的證據鏈（R11.1）。
    """
    if conclusion is None:
        conclusion = _auto_conclusion(out)
    if conclusion is None:
        out["eng_evidence_traceable"] = False
        return
    chain = build_evidence_chain(conclusion)
    out["eng_evidence_traceable"] = chain.is_fully_traceable()
    out["eng_evidence_summary"] = (
        f"{chain.conclusion}（證據環 {len(chain.links)} 條）"
    )


def _auto_conclusion(out: dict) -> RiskConclusion | None:
    """由本列已算好的分項貢獻自動組出最小風險結論與特徵歸因（R11.1）。

    僅使用「已算好」的分項分數作為特徵歸因來源（不觸發任何 AI），確保證據鏈
    的每一環都可回溯至原始分項值。無任何可用分項時回傳 None。
    """
    entity_id = str(out.get("park_id") or out.get("park_name") or "")
    total = _to_float(out.get("eng_risk_total"))
    if total is None:
        total = _to_float(out.get("risk_total"))

    attributions: list[FeatureAttribution] = []
    for feature in ("score_financial", "score_penalty", "score_eval"):
        val = _to_float(out.get(feature))
        if val is None:
            continue
        attributions.append(
            FeatureAttribution(
                feature=feature,
                raw_value=val,
                contribution=val,
                method="rule",
            )
        )

    if not attributions:
        return None

    total_text = f"{total:.1f}" if total is not None else "N/A"
    return RiskConclusion(
        entity_id=entity_id,
        conclusion=f"風險綜合評估（總分 {total_text}）",
        attributions=attributions,
    )


# --------------------------------------------------------------------------
# 主串接：把單一機構的引擎輸出串接為一列附加欄位
# --------------------------------------------------------------------------
def integrate_row(
    source_row: Mapping | Any,
    *,
    anomaly_result: Any = None,
    year_records: Iterable[Mapping] | None = None,
    conclusion: Any = None,
    timeline_metric: str = "risk_total",
    run_scorer: bool = True,
) -> dict:
    """串接單一機構的 Forensic/Scorer/Anomaly/Timeline/Evidence 輸出為一列。

    輸出列＝既有契約欄位（由 source_row 帶入，保留 Forensic/既有 Scorer 的
    score_*/risk_* 等值）＋ 附加引擎欄位（EXTRA_COLUMNS）。

    參數
    ----
    source_row : Mapping | 物件
        單一機構的契約列（通常來自 build()/pipeline 的輸出），至少含
        既有契約欄位。既有欄位原樣保留（不覆寫），確保載入契約不破壞。
    anomaly_result : AnomalyResult | None
        src.anomaly.detect 的輸出；None 則附加異常欄位保持預設。
    year_records : Iterable[Mapping] | None
        該機構跨年度紀錄（供 Timeline/Change_Point）；None 則變化點數為 0。
    conclusion : RiskConclusion | None
        供 Evidence 建鏈的結論；None 則由已算好分項自動組出最小結論。
    timeline_metric : str
        時間軸取值欄位，預設 "risk_total"。
    run_scorer : bool
        是否以白盒 Scorer 重算權威 eng_risk_total/level（預設 True）。
        既有 score_*/risk_* 欄位不受影響（仍原樣保留）。

    回傳
    ----
    dict：含 INTEGRATED_COLUMNS 全部欄位的一列。
    """
    out = _blank_integrated_row()

    # 1) 既有契約欄位原樣帶入（保留 Forensic 指標與既有 Scorer 分項/總分）。
    for col in CONTRACT_COLUMNS:
        val = _get(source_row, col)
        if not _is_missing(val):
            out[col] = val

    # 2) Scorer（R10.1）：以白盒 score() 產出權威總分/等級/聲明/可信度。
    if run_scorer:
        _apply_scorer(out, source_row)

    # 3) Anomaly（R8）：三類整合旗標（唯讀展示）。
    _apply_anomaly(out, anomaly_result)

    # 4) Timeline（R12）：變化點數與最新觸發說明。
    _apply_timeline(out, year_records, metric=timeline_metric)

    # 5) Evidence（R11.1）：證據鏈可追溯性與摘要。
    _apply_evidence(out, conclusion)

    return out


def integrate_dataset(
    source_rows: Iterable[Mapping | Any],
    *,
    anomaly_by_entity: Mapping[str, Any] | None = None,
    year_records_by_entity: Mapping[str, Iterable[Mapping]] | None = None,
    conclusion_by_entity: Mapping[str, Any] | None = None,
    timeline_metric: str = "risk_total",
    run_scorer: bool = True,
) -> IntegratedContract:
    """串接多機構的引擎輸出為契約資料集（記憶體物件，不落地）。

    以每列的 park_id（缺則 park_name）作為實體鍵，對應 anomaly / year_records /
    conclusion 三個「依實體」的輸入映射。任一映射缺席時，該引擎欄位以預設處理，
    不中斷整體串接（誠實揭露：無資料即空值）。

    安全：本函式不寫任何檔案，只回傳 IntegratedContract。落地請明確呼叫
    write_integrated_contract_files()。

    Validates: Requirements 10.1, 11.1, 17.1
    """
    anomaly_by_entity = anomaly_by_entity or {}
    year_records_by_entity = year_records_by_entity or {}
    conclusion_by_entity = conclusion_by_entity or {}

    rows: list[dict] = []
    for source_row in source_rows:
        key = str(
            _get(source_row, "park_id") or _get(source_row, "park_name") or ""
        )
        row = integrate_row(
            source_row,
            anomaly_result=anomaly_by_entity.get(key),
            year_records=year_records_by_entity.get(key),
            conclusion=conclusion_by_entity.get(key),
            timeline_metric=timeline_metric,
            run_scorer=run_scorer,
        )
        rows.append(row)

    return IntegratedContract(rows=rows, columns=INTEGRATED_COLUMNS)


# --------------------------------------------------------------------------
# AI 不回流保護（維持白盒、單向資料流）
# --------------------------------------------------------------------------
def assert_no_ai_reflux(
    before_row: Mapping | Any,
    after_row: Mapping | Any,
) -> None:
    """斷言 AI 層互動前後，任何計分欄位（SCORING_COLUMNS）皆未被改動。

    用途：在「AI Copilot 讀取契約 → 產生回答」的流程外圍呼叫，保證 AI 只讀不寫、
    不回流影響計分（R10 白盒可解釋、單向資料流）。若任一計分欄位被更動則拋出
    AssertionError，及早捕捉違反不變式的程式路徑。
    """
    for col in SCORING_COLUMNS:
        b = _get(before_row, col)
        a = _get(after_row, col)
        # NaN 視為相等（皆為缺值）。
        if _is_missing(b) and _is_missing(a):
            continue
        assert b == a, (
            f"AI 回流偵測：計分欄位 '{col}' 於 AI 互動後被更動 "
            f"({b!r} -> {a!r})，違反 AI 不影響計分之不變式。"
        )


# --------------------------------------------------------------------------
# 落地輸出（明確呼叫；預設不覆寫既有資料檔）
# --------------------------------------------------------------------------
def write_integrated_contract_files(
    contract: IntegratedContract,
    latest_path: str,
    full_path: str,
) -> None:
    """將串接後的契約資料集寫出至契約檔（附加欄位，維持既有載入契約）。

    安全設計（與 src.pipeline.write_contract_files 一致）：本函式須由呼叫端
    明確指定輸出路徑；`import` 或 `integrate_dataset` 皆不會自動落地，避免無意
    覆寫 data/processed 下供 UI 載入的既有檔。

    欄位順序為 INTEGRATED_COLUMNS（既有契約欄位在前、附加欄位在後），因此
    app/lib/common.py 以 pandas.read_csv 載入時，既有欄位位置與名稱不變，
    載入契約不被破壞；多出的附加欄位僅供三入口與 Copilot 額外讀取。

    參數
    ----
    contract    : integrate_dataset 的輸出。
    latest_path : kindergartens_latest.csv 目標路徑（每園一列）。
    full_path   : kindergartens.csv 目標路徑（每園每年一列）。

    註：latest/full 皆以相同欄位契約輸出；呼叫端負責提供對應的每園一列 /
    每園每年一列資料（可分別建立兩份 IntegratedContract 後各自寫出）。
    """
    _write_csv(latest_path, contract.rows, contract.columns)
    _write_csv(full_path, contract.rows, contract.columns)


# --------------------------------------------------------------------------
# 選用輔助：DataFrame 入口（pandas 為選用相依）
# --------------------------------------------------------------------------
def from_dataframe(df, **kwargs) -> IntegratedContract:
    """由 pandas.DataFrame（如 risk_score.build 的輸出）建立串接契約。

    僅在明確呼叫時 import pandas，維持既有基線可攜性。每列轉為 dict 後交由
    integrate_dataset 串接。df 內既有的 score_*/risk_* 欄位會原樣保留於輸出，
    白盒 Scorer 另以 eng_risk_* 欄位提供權威總分（兩者一致、可對照）。
    """
    records = df.to_dict(orient="records")
    return integrate_dataset(records, **kwargs)
