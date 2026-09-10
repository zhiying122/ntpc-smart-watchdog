"""
KPI 計算器單元測試（KPI Calculator, R23）
=========================================================================
驗證 src/kpi.py：
  - 計算 R23.1 列舉的全部九項 KPI，每項附非空定義與數值（R23.2）。
  - 具真實標籤時據實計算 Recall@K / Precision@K / FPR / Detection Rate。
  - 缺乏真實標籤時標示「示範估算」並說明依據（R23.3）。
  - 所有比率型 KPI 皆落於 [0, 1]（Property 42 前導；R23.1）。

對應 Task 15.3「實作 KPI 計算器」（Requirements 23.1, 23.2, 23.3）。
屬性測試（Property 42）另見 Task 15.5。
"""
import pytest

from src.kpi import (
    DEMO_ESTIMATE_LABEL,
    KPI_DEFINITIONS,
    KpiCalculator,
    KpiInputs,
    KpiMetric,
    compute_kpi_map,
    compute_kpis,
)

# R23.1 要求的九項 KPI key。
EXPECTED_KEYS = {
    "risk_detection_rate",
    "recall_at_k",
    "precision_at_k",
    "fpr",
    "investigation_time_reduction",
    "data_integration_coverage",
    "explainability_coverage",
    "source_traceability",
    "inspection_resource_efficiency",
}


# --------------------------------------------------------------------------
# R23.1：計算全部 KPI
# --------------------------------------------------------------------------
def test_computes_all_nine_kpis():
    """compute 回傳 R23.1 列舉的全部九項 KPI。"""
    metrics = compute_kpis(KpiInputs())
    assert len(metrics) == 9
    assert {m.key for m in metrics} == EXPECTED_KEYS


def test_compute_map_indexed_by_key():
    """compute_map 以 key 為索引回傳，且涵蓋全部 KPI。"""
    m = compute_kpi_map(KpiInputs())
    assert set(m.keys()) == EXPECTED_KEYS
    assert all(isinstance(v, KpiMetric) for v in m.values())


# --------------------------------------------------------------------------
# R23.2：每項 KPI 附定義與數值
# --------------------------------------------------------------------------
def test_every_kpi_has_definition_and_value():
    """每一 KPI 皆附非空定義與有限數值（R23.2）。"""
    for m in compute_kpis(KpiInputs()):
        assert m.definition.strip(), f"{m.key} 缺定義"
        assert isinstance(m.value, float)
        assert m.value == m.value  # 非 NaN


def test_definitions_match_registry():
    """回傳的定義與 KPI_DEFINITIONS 一致。"""
    for m in compute_kpis(KpiInputs()):
        assert m.definition == KPI_DEFINITIONS[m.key]


# --------------------------------------------------------------------------
# R23.3：缺真實標籤標示「示範估算」
# --------------------------------------------------------------------------
def test_missing_labels_marked_as_demo_estimate():
    """無真實標籤時，標籤型 KPI 標為示範估算並帶標示文字（R23.3）。"""
    m = compute_kpi_map(KpiInputs(has_ground_truth=False))
    for key in ("risk_detection_rate", "recall_at_k", "precision_at_k", "fpr"):
        assert m[key].is_estimate is True
        assert m[key].label == DEMO_ESTIMATE_LABEL
        assert m[key].basis.strip()


def test_ground_truth_confusion_not_estimate():
    """提供混淆矩陣時，FPR / Detection Rate 據實計算且非示範估算。"""
    inputs = KpiInputs(
        has_ground_truth=True,
        true_positives=8,
        false_positives=2,
        false_negatives=2,
        true_negatives=88,
    )
    m = compute_kpi_map(inputs)
    # Detection Rate = TP / (TP + FN) = 8 / 10 = 0.8
    assert m["risk_detection_rate"].is_estimate is False
    assert m["risk_detection_rate"].value == pytest.approx(0.8)
    # FPR = FP / (FP + TN) = 2 / 90
    assert m["fpr"].is_estimate is False
    assert m["fpr"].value == pytest.approx(2 / 90)


def test_coverage_kpis_not_estimate_with_real_denominator():
    """覆蓋率型 KPI 由系統實際統計，非示範估算。"""
    inputs = KpiInputs(
        total_institutions=20,
        integrated_institutions=15,
        explained_conclusions=18,
        total_conclusions=20,
        traceable_signals=40,
        total_signals=50,
    )
    m = compute_kpi_map(inputs)
    assert m["data_integration_coverage"].is_estimate is False
    assert m["data_integration_coverage"].value == pytest.approx(0.75)
    assert m["explainability_coverage"].value == pytest.approx(0.9)
    assert m["source_traceability"].value == pytest.approx(0.8)


# --------------------------------------------------------------------------
# Recall@K / Precision@K 定義一致性
# --------------------------------------------------------------------------
def test_recall_and_precision_at_k_match_definition():
    """依排序標籤驗證 Recall@K 與 Precision@K 公式（R23.1）。"""
    # 排名前 5 中有 3 個真實異常；全體 4 個真實異常。
    labels = [True, True, False, True, False, False, True, False]
    inputs = KpiInputs(ranked_labels=labels, k=5, has_ground_truth=True)
    m = compute_kpi_map(inputs)
    # 前 5：True,True,False,True,False -> 命中 3
    # Precision@5 = 3 / 5 = 0.6
    assert m["precision_at_k"].value == pytest.approx(0.6)
    # 全體真實異常 = 4；Recall@5 = 3 / 4 = 0.75
    assert m["recall_at_k"].value == pytest.approx(0.75)


def test_k_defaults_to_sequence_length():
    """未提供 K 時預設為序列長度。"""
    labels = [True, False, True, False]
    m = compute_kpi_map(KpiInputs(ranked_labels=labels, has_ground_truth=True))
    # K=4，前 4 命中 2；Precision = 2/4 = 0.5，Recall = 2/2 = 1.0
    assert m["precision_at_k"].value == pytest.approx(0.5)
    assert m["recall_at_k"].value == pytest.approx(1.0)


def test_k_clamped_to_sequence_length():
    """K 超過序列長度時被夾擠至長度，不越界。"""
    labels = [True, True]
    m = compute_kpi_map(KpiInputs(ranked_labels=labels, k=99, has_ground_truth=True))
    assert 0.0 <= m["precision_at_k"].value <= 1.0
    assert m["precision_at_k"].value == pytest.approx(1.0)


# --------------------------------------------------------------------------
# 稽查時間縮減率 / 資源效率
# --------------------------------------------------------------------------
def test_investigation_time_reduction_computed():
    """有實測耗時時計算縮減率 = 1 - 系統/基準。"""
    inputs = KpiInputs(
        baseline_minutes_per_case=100.0,
        system_minutes_per_case=40.0,
    )
    m = compute_kpi_map(inputs)
    assert m["investigation_time_reduction"].is_estimate is False
    assert m["investigation_time_reduction"].value == pytest.approx(0.6)


def test_investigation_time_reduction_estimate_when_missing():
    """缺實測基準時標為示範估算。"""
    m = compute_kpi_map(KpiInputs())
    assert m["investigation_time_reduction"].is_estimate is True
    assert m["investigation_time_reduction"].label == DEMO_ESTIMATE_LABEL


def test_inspection_resource_efficiency():
    """已稽查命中比例計算正確。"""
    inputs = KpiInputs(has_ground_truth=True, inspected_count=10, hits_found=7)
    m = compute_kpi_map(inputs)
    assert m["inspection_resource_efficiency"].value == pytest.approx(0.7)
    assert m["inspection_resource_efficiency"].is_estimate is False


# --------------------------------------------------------------------------
# 值域保證與邊界（Property 42 前導；R23.1）
# --------------------------------------------------------------------------
def test_all_ratio_kpis_within_unit_interval():
    """所有比率型 KPI 皆落於 [0, 1]（值域保證）。"""
    inputs = KpiInputs(
        ranked_labels=[True, False, True],
        k=2,
        has_ground_truth=True,
        true_positives=3,
        false_positives=1,
        false_negatives=1,
        true_negatives=5,
        total_institutions=10,
        integrated_institutions=8,
        explained_conclusions=9,
        total_conclusions=10,
        traceable_signals=20,
        total_signals=25,
        baseline_minutes_per_case=120.0,
        system_minutes_per_case=30.0,
        inspected_count=6,
        hits_found=4,
    )
    for m in compute_kpis(inputs):
        if m.is_ratio:
            assert 0.0 <= m.value <= 1.0, f"{m.key} 越界: {m.value}"


def test_zero_denominators_are_safe():
    """所有分母為 0 時，比率型 KPI 回傳 0.0，不拋例外、不越界。"""
    metrics = compute_kpis(KpiInputs())
    for m in metrics:
        assert 0.0 <= m.value <= 1.0
        assert m.value == m.value  # 非 NaN


def test_system_slower_than_baseline_clamped_to_zero():
    """系統比基準慢時縮減率不為負，夾擠至 0。"""
    inputs = KpiInputs(
        baseline_minutes_per_case=30.0,
        system_minutes_per_case=90.0,
    )
    m = compute_kpi_map(inputs)
    assert m["investigation_time_reduction"].value == 0.0
