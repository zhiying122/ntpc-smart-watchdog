"""
測試骨架煙霧測試（Scaffold Smoke Tests）
==========================================
驗證共用型別（src/models.py）與共用產生器（tests/generators.py）可正確匯入並運作。
這是 Task 1「建立測試骨架與共用型別」的最小驗證，確保後續屬性測試有可靠地基。
"""
from datetime import datetime

from hypothesis import given, settings

from src import models
from tests import generators as gen


def test_all_shared_types_importable():
    """所有 design.md 指定的共用型別皆存在且可實例化。"""
    expected = [
        "SourceRef", "Metric", "ForensicMetrics", "AnomalyMethodResult",
        "AnomalyResult", "RiskBreakdown", "EvidenceLink", "AllocationItem",
        "AllocationResult", "SimParams", "PublicInstitutionView",
        "AuditEntry", "HITLFeedback", "DataConfidence", "FinancialRecord",
    ]
    for name in expected:
        assert hasattr(models, name), f"缺少共用型別：{name}"


def test_risk_breakdown_has_responsible_ai_notice():
    """RiskBreakdown 預設帶有非空「風險不等於違法」聲明（R10.4, R19.4）。"""
    rb = models.RiskBreakdown(total=50.0, level="中")
    assert rb.not_illegality_notice.strip() != ""


def test_audit_entry_is_frozen():
    """AuditEntry 為不可竄改（frozen）以落實 append-only 語意（R21.2）。"""
    entry = models.AuditEntry(actor="a", action="score", target="p1",
                              ts=datetime(2026, 9, 12, 10, 0, 0))
    import dataclasses
    try:
        entry.actor = "b"  # type: ignore[misc]
        raised = False
    except dataclasses.FrozenInstanceError:
        raised = True
    assert raised, "AuditEntry 應為 frozen，不可修改欄位"


@settings(max_examples=50)
@given(gen.financial_records())
def test_financial_record_generator_produces_valid_records(rec):
    """財務物件產生器產出合法 FinancialRecord。"""
    assert isinstance(rec, models.FinancialRecord)
    assert rec.year in (112, 113, 114)
    assert isinstance(rec.detail_amounts, list)


@settings(max_examples=50)
@given(gen.institution_names())
def test_institution_name_generator_produces_strings(name):
    """名稱變體產生器產出字串（供實體解析測試）。"""
    assert isinstance(name, str)


@settings(max_examples=50)
@given(gen.valid_inspector_n)
def test_valid_inspector_n_within_range(n):
    """有效稽查員人數落於 1..1000（R3.9 有效邊界）。"""
    assert 1 <= n <= 1000


@settings(max_examples=50)
@given(gen.invalid_inspector_n)
def test_invalid_inspector_n_outside_valid_domain(n):
    """無效稽查員人數不落於 1..1000 整數（R3.9 無效值）。"""
    is_valid_int = isinstance(n, int) and 1 <= n <= 1000
    assert not is_valid_int


@settings(max_examples=50)
@given(gen.sim_params())
def test_sim_params_generator_valid(params):
    """模擬參數產生器產出合法 SimParams（配額 1–999、允許權重）。"""
    assert isinstance(params, models.SimParams)
    assert 1 <= params.quota <= 999
    assert params.weight_scheme in gen.WEIGHT_SCHEMES
