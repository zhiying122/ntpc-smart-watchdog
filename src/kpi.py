"""
關鍵績效指標計算器（KPI Calculator, R23）
====================================================================
小小守護員 Smart Watchdog Platform — 決策工具層（Decision Tools）子系統。

本模組對應 design.md「決策工具｜R3, R4, R23｜... + KPI」，提供一組營運 KPI，
讓政府決策者衡量系統對稽查效能的實際貢獻（R23 User Story）。

需要計算的 KPI（R23.1）
------------------------
- 風險偵測率（Risk Detection Rate）
- Recall@K
- Precision@K
- FPR（False Positive Rate，偽陽性率）
- 稽查時間縮減率（Investigation Time Reduction）
- 資料整合覆蓋率（Data Integration Coverage）
- 可解釋性覆蓋率（Explainability Coverage）
- 來源可追溯率（Source Traceability）
- 稽查資源效率（Inspection Resource Efficiency）

設計原則
--------
- 每一 KPI 皆附「定義（definition）」與「數值（value）」（R23.2）。
- 誠實揭露（R23.3）：凡因缺乏真實標籤（ground-truth labels）而無法可靠計算的
  KPI，一律標示 `is_estimate=True`（「示範估算」）並在 `basis` 說明其依據，
  絕不宣稱擁有真實標籤（呼應 R22.3 誠實原則）。
- 範圍保證（Property 42, R23.1）：所有比率型 KPI 皆落於 [0, 1]；
  Precision@K 與 Recall@K 與其定義一致（介於 0 至 1）。以夾擠（clamp）
  與安全除法保護分母為 0 的邊界，避免 NaN／越界。

本模組僅依賴標準函式庫，不引入額外執行期相依，維持既有基線的可攜性。

責任 AI：KPI 為系統效能的量化描述，非對任一機構「違法」之認定；
「示範估算」標示確保在缺乏真實標籤時不誇大宣稱。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

# --------------------------------------------------------------------------
# 「示範估算」標示文字（R23.3）
# --------------------------------------------------------------------------
# 當某 KPI 缺乏真實標籤而無法可靠計算時，於呈現層顯示此標示。
DEMO_ESTIMATE_LABEL = "示範估算"


# --------------------------------------------------------------------------
# 數值安全工具
# --------------------------------------------------------------------------
def _safe_ratio(numerator: float, denominator: float) -> float:
    """安全除法：分母為 0（或負）時回傳 0.0，避免 ZeroDivisionError／NaN。

    比率型 KPI 的分母恆為「非負計數」，故分母 <= 0 視為無可計算樣本，
    回傳 0.0 為中性且落於 [0, 1] 的合法值。
    """
    if denominator is None or denominator <= 0:
        return 0.0
    return float(numerator) / float(denominator)


def _clamp01(value: float) -> float:
    """將數值夾擠至 [0, 1] 範圍（比率型 KPI 的值域保證，Property 42）。"""
    if value != value:  # NaN 防護
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)


# --------------------------------------------------------------------------
# 單一 KPI 結果（附定義與數值, R23.2）
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class KpiMetric:
    """單一 KPI 的計算結果，附定義與數值（R23.2, R23.3）。

    屬性
    ------
    key : str
        KPI 識別鍵（如 "recall_at_k"）。
    name : str
        KPI 顯示名稱（如 "Recall@K"）。
    value : float
        當前數值。比率型 KPI 落於 [0, 1]（Property 42）。
    definition : str
        KPI 的定義說明（非空字串，R23.2）。
    is_ratio : bool
        是否為比率型 KPI（值域 [0, 1]）；用於範圍檢核。
    is_estimate : bool
        是否為「示範估算」（因缺乏真實標籤而無法可靠計算，R23.3）。
    basis : str
        數值計算依據；示範估算時說明替代標註策略。
    label : str
        呈現用標示；示範估算時為 DEMO_ESTIMATE_LABEL，否則為空字串。

    Validates: Requirements 23.1, 23.2, 23.3
    """
    key: str
    name: str
    value: float
    definition: str
    is_ratio: bool = True
    is_estimate: bool = False
    basis: str = ""

    @property
    def label(self) -> str:
        """呈現層標示：示範估算時回傳「示範估算」，否則空字串。"""
        return DEMO_ESTIMATE_LABEL if self.is_estimate else ""


# --------------------------------------------------------------------------
# KPI 計算輸入
# --------------------------------------------------------------------------
@dataclass
class KpiInputs:
    """KPI 計算所需的輸入資料（全部為選用，缺者以誠實估算處理）。

    標籤相關（缺真實標籤時將標為示範估算, R23.3）
    ------------------------------------------------
    ranked_labels : Sequence[bool] | None
        依風險分數由高至低排序後，各機構之「真實為異常」標籤序列。
        `None` 表示無真實標籤 → 相關 KPI 標為示範估算。
    k : int | None
        Top-K 的 K 值；未提供時預設為序列長度。
    has_ground_truth : bool
        是否具備真實標籤。False → Recall/Precision/FPR/Detection 皆為示範估算。

    混淆矩陣（具真實標籤時可直接提供）
    ------------------------------------
    true_positives / false_positives / false_negatives / true_negatives : int | None
        若提供，用於精確計算 FPR、Precision、Recall、Detection Rate。

    覆蓋率相關（可由系統實際狀態統計，通常具真實分母）
    ----------------------------------------------------
    total_institutions : int
        母體機構總數（覆蓋率分母）。
    integrated_institutions : int
        已整合多來源資料的機構數（資料整合覆蓋率分子）。
    explained_conclusions : int
        具可解釋分項／特徵歸因的風險結論數（可解釋性覆蓋率分子）。
    total_conclusions : int
        風險結論總數（可解釋性覆蓋率分母）。
    traceable_signals : int
        可回溯至官方來源的訊號數（來源可追溯率分子）。
    total_signals : int
        訊號總數（來源可追溯率分母）。

    效率相關（示範估算, 缺實測基準時）
    ------------------------------------
    baseline_minutes_per_case : float | None
        傳統人工每案稽查耗時（分鐘）。
    system_minutes_per_case : float | None
        導入系統後每案耗時（分鐘）。
    inspected_count : int
        已稽查機構數（資源效率分母）。
    hits_found : int
        已稽查中命中（確為異常）數（資源效率分子）。
    """
    # 標籤 / 混淆矩陣
    ranked_labels: Sequence[bool] | None = None
    k: int | None = None
    has_ground_truth: bool = False
    true_positives: int | None = None
    false_positives: int | None = None
    false_negatives: int | None = None
    true_negatives: int | None = None

    # 覆蓋率
    total_institutions: int = 0
    integrated_institutions: int = 0
    explained_conclusions: int = 0
    total_conclusions: int = 0
    traceable_signals: int = 0
    total_signals: int = 0

    # 效率
    baseline_minutes_per_case: float | None = None
    system_minutes_per_case: float | None = None
    inspected_count: int = 0
    hits_found: int = 0


# --------------------------------------------------------------------------
# KPI 定義（供呈現層顯示, R23.2）
# --------------------------------------------------------------------------
KPI_DEFINITIONS: dict[str, str] = {
    "risk_detection_rate": (
        "風險偵測率（Recall / Detection Rate）＝命中真實異常 ÷ 全部真實異常。"
        "以進入 Top-K 優先稽查名單者為「被偵測」；當 K 涵蓋全部機構時，即為"
        "整體召回。分母是「真實異常數」，不是全體機構數。此指標與 Recall@K "
        "同定義（K 相同時數值相等），兩者非彼此矛盾。"
    ),
    "recall_at_k": (
        "Recall@K＝Top-K 名單命中真實異常 ÷ 全部真實異常。分母同為「真實異常"
        "數」。K 越大涵蓋越廣、Recall 越高；K 涵蓋全部真實異常時 Recall=100%，"
        "此時的 100% 反映名單夠長，非模型無誤判（誤判看 Precision@K／FPR）。"
    ),
    "precision_at_k": (
        "Precision@K＝Top-K 名單命中真實異常 ÷ K。分母是「名單長度 K」（與 "
        "Recall 分母不同）。衡量優先稽查名單的準確度：名單中真的有問題的比例。"
    ),
    "fpr": (
        "FPR（偽陽性率）：在所有真實非異常機構中，被系統誤標為高風險的比例；"
        "計算式為 FP / (FP + TN)。"
    ),
    "investigation_time_reduction": (
        "稽查時間縮減率（Investigation Time Reduction）：導入系統後每案稽查"
        "耗時相較傳統人工的縮減比例；計算式為 1 - 系統耗時 / 基準耗時。"
    ),
    "data_integration_coverage": (
        "資料整合覆蓋率（Data Integration Coverage）：已完成多來源資料整合"
        "的機構數，除以母體機構總數。"
    ),
    "explainability_coverage": (
        "可解釋性覆蓋率（Explainability Coverage）：具備可解釋分項與特徵歸因"
        "的風險結論數，除以風險結論總數。"
    ),
    "source_traceability": (
        "來源可追溯率（Source Traceability）：可回溯至官方來源的訊號數，"
        "除以訊號總數；衡量證據鏈的完整度。"
    ),
    "inspection_resource_efficiency": (
        "稽查資源效率（Inspection Resource Efficiency）：已稽查機構中命中"
        "（確為異常）的比例；衡量投入稽查人力的產出效益。"
    ),
}


# --------------------------------------------------------------------------
# KPI 計算器（KPI Calculator, R23）
# --------------------------------------------------------------------------
class KpiCalculator:
    """依輸入資料計算全部 R23.1 KPI，附定義與數值（R23.2, R23.3）。

    計算原則
    --------
    - 具真實標籤（has_ground_truth=True 或提供混淆矩陣）時，據實計算
      Detection Rate / Recall@K / Precision@K / FPR，並以真實依據標示。
    - 缺乏真實標籤時，仍回傳可展示數值（依替代標註策略估算），但一律
      標示 `is_estimate=True`（「示範估算」）並於 basis 說明依據（R23.3）。
    - 覆蓋率與可追溯率由系統實際狀態統計，通常具真實分母，非示範估算；
      但分母為 0 時以安全除法回傳 0.0。
    - 所有比率型 KPI 皆夾擠至 [0, 1]（Property 42, R23.1）。

    Validates: Requirements 23.1, 23.2, 23.3
    """

    def compute(self, inputs: KpiInputs) -> list[KpiMetric]:
        """計算全部 KPI，回傳 KpiMetric 清單（順序對齊 R23.1 列舉順序）。"""
        return [
            self._risk_detection_rate(inputs),
            self._recall_at_k(inputs),
            self._precision_at_k(inputs),
            self._fpr(inputs),
            self._investigation_time_reduction(inputs),
            self._data_integration_coverage(inputs),
            self._explainability_coverage(inputs),
            self._source_traceability(inputs),
            self._inspection_resource_efficiency(inputs),
        ]

    def compute_map(self, inputs: KpiInputs) -> dict[str, KpiMetric]:
        """計算全部 KPI，回傳以 key 為索引的字典（便於呈現層取用）。"""
        return {m.key: m for m in self.compute(inputs)}

    # ----- 標籤依賴型 KPI（缺真實標籤 → 示範估算, R23.3） -----

    def _has_confusion(self, inputs: KpiInputs) -> bool:
        """是否提供了可用的混淆矩陣（四格皆非 None）。"""
        return (
            inputs.true_positives is not None
            and inputs.false_positives is not None
            and inputs.false_negatives is not None
            and inputs.true_negatives is not None
        )

    def _label_based(self, inputs: KpiInputs) -> bool:
        """標籤型 KPI 是否可據真實標籤計算（否則標為示範估算）。"""
        return inputs.has_ground_truth or self._has_confusion(inputs)

    def _risk_detection_rate(self, inputs: KpiInputs) -> KpiMetric:
        """風險偵測率 = TP / (TP + FN)（真實異常中被偵測到的比例，即整體召回）。

        無混淆矩陣、僅有排序弱標籤時：以「進入 Top-K 優先稽查名單」近似為
        「被系統判為高風險（偵測）」，分子＝Top-K 名單命中的真實異常數、
        分母＝全部真實異常數。此定義與 Recall@K 一致（同分子同分母）；
        當 K 涵蓋全部機構時，兩者皆等於整體召回。定義文字已載明此關係，
        避免與 Recall@K 被誤讀為方向矛盾的兩個指標。
        """
        based = self._label_based(inputs)
        if self._has_confusion(inputs):
            tp = inputs.true_positives or 0
            fn = inputs.false_negatives or 0
            value = _safe_ratio(tp, tp + fn)
            basis = f"據混淆矩陣 TP={tp}, FN={fn} 計算。"
        elif inputs.ranked_labels is not None:
            labels = list(inputs.ranked_labels)
            n = len(labels)
            k = self._effective_k(inputs, n)
            total_positives = sum(1 for x in labels if x)
            hits_in_topk = sum(1 for x in labels[:k] if x)
            value = _safe_ratio(hits_in_topk, total_positives)
            basis = (
                f"以 Top-K 名單為偵測近似：K={k}，名單命中真實異常 "
                f"{hits_in_topk} / 全部真實異常 {total_positives}"
                f"（與 Recall@K 同定義；分母為真實異常數，非全體機構數）。"
            )
        else:
            value = 0.0
            basis = "缺乏真實標籤，暫以替代標註策略（弱監督／歷史裁罰）估算。"
        return KpiMetric(
            key="risk_detection_rate",
            name="風險偵測率 (Risk Detection Rate)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["risk_detection_rate"],
            is_ratio=True,
            is_estimate=not based,
            basis=basis,
        )

    def _effective_k(self, inputs: KpiInputs, n: int) -> int:
        """決定有效 K：未提供時取序列長度；夾擠至 [0, n]。"""
        if inputs.k is None:
            return n
        return max(0, min(int(inputs.k), n))

    def _recall_at_k(self, inputs: KpiInputs) -> KpiMetric:
        """Recall@K = (前 K 命中之真實異常數) / (全部真實異常數)。"""
        based = self._label_based(inputs)
        value = 0.0
        basis = "缺乏真實標籤，依替代標註策略（歷史裁罰為弱標籤）估算。"
        if inputs.ranked_labels is not None:
            labels = list(inputs.ranked_labels)
            n = len(labels)
            k = self._effective_k(inputs, n)
            total_positives = sum(1 for x in labels if x)
            hits_in_topk = sum(1 for x in labels[:k] if x)
            value = _safe_ratio(hits_in_topk, total_positives)
            basis = (
                f"K={k}，前 K 命中 {hits_in_topk} / 全部真實異常 {total_positives}"
                f"（分母＝真實異常數）。"
            )
        return KpiMetric(
            key="recall_at_k",
            name="Recall@K",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["recall_at_k"],
            is_ratio=True,
            is_estimate=not based,
            basis=basis,
        )

    def _precision_at_k(self, inputs: KpiInputs) -> KpiMetric:
        """Precision@K = (前 K 命中之真實異常數) / K。"""
        based = self._label_based(inputs)
        value = 0.0
        basis = "缺乏真實標籤，依替代標註策略（歷史裁罰為弱標籤）估算。"
        if inputs.ranked_labels is not None:
            labels = list(inputs.ranked_labels)
            n = len(labels)
            k = self._effective_k(inputs, n)
            hits_in_topk = sum(1 for x in labels[:k] if x)
            value = _safe_ratio(hits_in_topk, k)
            basis = f"K={k}，前 K 命中 {hits_in_topk} / K={k}（分母＝名單長度 K）。"
        return KpiMetric(
            key="precision_at_k",
            name="Precision@K",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["precision_at_k"],
            is_ratio=True,
            is_estimate=not based,
            basis=basis,
        )

    def _fpr(self, inputs: KpiInputs) -> KpiMetric:
        """FPR = FP / (FP + TN)（真實非異常中被誤標的比例）。"""
        based = self._has_confusion(inputs)
        if based:
            fp = inputs.false_positives or 0
            tn = inputs.true_negatives or 0
            value = _safe_ratio(fp, fp + tn)
            basis = f"據混淆矩陣 FP={fp}, TN={tn} 計算。"
        else:
            value = 0.0
            basis = "缺乏真實標籤（無 TN／FP 可分），以示範估算呈現。"
        return KpiMetric(
            key="fpr",
            name="偽陽性率 (FPR)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["fpr"],
            is_ratio=True,
            is_estimate=not based,
            basis=basis,
        )

    # ----- 覆蓋率型 KPI（系統實際統計, 通常具真實分母） -----

    def _investigation_time_reduction(self, inputs: KpiInputs) -> KpiMetric:
        """稽查時間縮減率 = 1 - 系統耗時 / 基準耗時。"""
        has_measure = (
            inputs.baseline_minutes_per_case is not None
            and inputs.system_minutes_per_case is not None
            and inputs.baseline_minutes_per_case > 0
        )
        if has_measure:
            ratio = _safe_ratio(
                float(inputs.system_minutes_per_case),
                float(inputs.baseline_minutes_per_case),
            )
            value = 1.0 - ratio
            basis = (
                f"基準 {inputs.baseline_minutes_per_case} 分/案，"
                f"系統 {inputs.system_minutes_per_case} 分/案。"
            )
            is_estimate = False
        else:
            value = 0.0
            basis = "缺乏實測稽查耗時基準，以示範估算呈現。"
            is_estimate = True
        return KpiMetric(
            key="investigation_time_reduction",
            name="稽查時間縮減率 (Investigation Time Reduction)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["investigation_time_reduction"],
            is_ratio=True,
            is_estimate=is_estimate,
            basis=basis,
        )

    def _data_integration_coverage(self, inputs: KpiInputs) -> KpiMetric:
        """資料整合覆蓋率 = 已整合機構數 / 母體機構總數。"""
        value = _safe_ratio(inputs.integrated_institutions, inputs.total_institutions)
        return KpiMetric(
            key="data_integration_coverage",
            name="資料整合覆蓋率 (Data Integration Coverage)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["data_integration_coverage"],
            is_ratio=True,
            is_estimate=False,
            basis=(
                f"已整合 {inputs.integrated_institutions} / "
                f"母體 {inputs.total_institutions} 間。"
            ),
        )

    def _explainability_coverage(self, inputs: KpiInputs) -> KpiMetric:
        """可解釋性覆蓋率 = 具可解釋結論數 / 風險結論總數。"""
        value = _safe_ratio(inputs.explained_conclusions, inputs.total_conclusions)
        return KpiMetric(
            key="explainability_coverage",
            name="可解釋性覆蓋率 (Explainability Coverage)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["explainability_coverage"],
            is_ratio=True,
            is_estimate=False,
            basis=(
                f"可解釋結論 {inputs.explained_conclusions} / "
                f"結論總數 {inputs.total_conclusions}。"
            ),
        )

    def _source_traceability(self, inputs: KpiInputs) -> KpiMetric:
        """來源可追溯率 = 可回溯訊號數 / 訊號總數。"""
        value = _safe_ratio(inputs.traceable_signals, inputs.total_signals)
        return KpiMetric(
            key="source_traceability",
            name="來源可追溯率 (Source Traceability)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["source_traceability"],
            is_ratio=True,
            is_estimate=False,
            basis=(
                f"可回溯訊號 {inputs.traceable_signals} / "
                f"訊號總數 {inputs.total_signals}。"
            ),
        )

    def _inspection_resource_efficiency(self, inputs: KpiInputs) -> KpiMetric:
        """稽查資源效率 = 已稽查命中數 / 已稽查機構數。"""
        based = self._label_based(inputs) or inputs.inspected_count > 0
        value = _safe_ratio(inputs.hits_found, inputs.inspected_count)
        if inputs.inspected_count > 0 and self._label_based(inputs):
            basis = f"已稽查命中 {inputs.hits_found} / 已稽查 {inputs.inspected_count}。"
            is_estimate = False
        else:
            basis = "缺乏真實稽查結果標籤，以示範估算呈現。"
            is_estimate = True
        return KpiMetric(
            key="inspection_resource_efficiency",
            name="稽查資源效率 (Inspection Resource Efficiency)",
            value=_clamp01(value),
            definition=KPI_DEFINITIONS["inspection_resource_efficiency"],
            is_ratio=True,
            is_estimate=is_estimate,
            basis=basis,
        )


# --------------------------------------------------------------------------
# 模組層級便利函式
# --------------------------------------------------------------------------
_DEFAULT_CALCULATOR = KpiCalculator()


def compute_kpis(inputs: KpiInputs) -> list[KpiMetric]:
    """便利入口：以預設計算器計算全部 KPI（R23.1, R23.2, R23.3）。"""
    return _DEFAULT_CALCULATOR.compute(inputs)


def compute_kpi_map(inputs: KpiInputs) -> dict[str, KpiMetric]:
    """便利入口：以預設計算器計算全部 KPI 並回傳字典。"""
    return _DEFAULT_CALCULATOR.compute_map(inputs)
