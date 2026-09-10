"""
資料可信度評分單元測試（Confidence_Scorer, R18.1）
=======================================================
驗證 src/confidence.py 的 `confidence(record) -> DataConfidence`：
  - 輸出 0–100 分（含端點）與可攤開的 factors 明細。
  - factors 加總等於 score（白盒可加性）。
  - 支援 FinancialRecord、dict 與缺值紀錄。
  - 時效、完整度、來源、招生、明細各因子行為正確。

對應 Task 4.2「實作資料可信度分數」（Requirements 18.1）。
屬性測試（Property 37）另見 Task 4.4。
"""
from datetime import date, timedelta

import pytest

from src.confidence import FACTOR_WEIGHTS, confidence
from src.models import DataConfidence, FinancialRecord, SourceRef


def _full_record(last_updated: date | None = None) -> FinancialRecord:
    """所有因子皆滿分的完整紀錄。"""
    return FinancialRecord(
        park_id="p-full",
        park_name="完整示範幼兒園",
        year=113,
        income_actual=1000.0,
        expense_actual=900.0,
        tuition_actual=800.0,
        surplus=100.0,
        income_last_year=950.0,
        expense_last_year=880.0,
        enrollment=30,
        detail_amounts=list(range(1, 12)),  # 11 筆 >= 目標 10
        source_ref=SourceRef(
            dataset="公校決算",
            authority="教育局",
            url="https://example.gov.tw/x",
            last_updated=last_updated or date.today(),
        ),
    )


def test_returns_data_confidence_type():
    """回傳型別為共用型別 DataConfidence。"""
    dc = confidence(_full_record())
    assert isinstance(dc, DataConfidence)


def test_full_record_scores_100():
    """所有因子滿分的完整紀錄 → 100 分。"""
    dc = confidence(_full_record())
    assert dc.score == 100.0


def test_empty_record_scores_0():
    """完全缺值的紀錄 → 0 分，且各因子皆為 0。"""
    empty = FinancialRecord(park_id="p-empty", park_name="空園", year=112)
    dc = confidence(empty)
    assert dc.score == 0.0
    assert all(v == 0.0 for v in dc.factors.values())


def test_score_within_range():
    """分數落於 0–100 含端點。"""
    dc = confidence(_full_record())
    assert 0.0 <= dc.score <= 100.0


def test_factors_sum_equals_score():
    """factors 明細加總等於總分（白盒可加性）。"""
    dc = confidence(_full_record())
    assert round(sum(dc.factors.values()), 4) == dc.score


def test_factors_keys_match_weights():
    """factors 涵蓋所有已定義的權重因子。"""
    dc = confidence(_full_record())
    assert set(dc.factors.keys()) == set(FACTOR_WEIGHTS.keys())


def test_entity_id_from_park_id():
    """entity_id 優先取 park_id。"""
    dc = confidence(_full_record())
    assert dc.entity_id == "p-full"


def test_entity_id_from_dict_entity_id_key():
    """dict 無 park_id 時退回 entity_id 欄位。"""
    dc = confidence({"entity_id": "d-1", "income_actual": 1.0})
    assert dc.entity_id == "d-1"


def test_entity_id_unknown_when_no_identifier():
    """無任何識別欄位時回傳 'unknown'。"""
    dc = confidence({"income_actual": 1.0})
    assert dc.entity_id == "unknown"


def test_missing_source_zeroes_traceability_and_freshness():
    """無 source_ref → 來源與時效因子皆為 0。"""
    rec = FinancialRecord(
        park_id="p", park_name="n", year=113,
        income_actual=1.0, expense_actual=1.0, tuition_actual=1.0,
        surplus=0.0, income_last_year=1.0, expense_last_year=1.0,
        enrollment=10, detail_amounts=list(range(1, 12)),
        source_ref=None,
    )
    dc = confidence(rec)
    assert dc.factors["source_traceable"] == 0.0
    assert dc.factors["freshness"] == 0.0


def test_stale_source_lowers_freshness():
    """來源逾 730 天 → 時效因子為 0；新來源 → 時效滿分。"""
    fresh = confidence(_full_record(last_updated=date.today()))
    stale = confidence(_full_record(last_updated=date.today() - timedelta(days=800)))
    assert fresh.factors["freshness"] == FACTOR_WEIGHTS["freshness"] * 100.0
    assert stale.factors["freshness"] == 0.0
    assert stale.score < fresh.score


def test_freshness_linear_midpoint():
    """時效介於 180–730 天間線性遞減（中點約半分）。"""
    mid_days = (180 + 730) // 2
    dc = confidence(_full_record(last_updated=date.today() - timedelta(days=mid_days)))
    max_contrib = FACTOR_WEIGHTS["freshness"] * 100.0
    assert 0.0 < dc.factors["freshness"] < max_contrib


def test_zero_enrollment_scores_zero_enrollment_factor():
    """招生人數為 0 → 招生因子為 0（不可作為每名幼兒指標分母）。"""
    rec = FinancialRecord(park_id="p", park_name="n", year=113, enrollment=0)
    dc = confidence(rec)
    assert dc.factors["enrollment"] == 0.0


def test_partial_detail_amounts_scaled():
    """明細筆數不足目標 → detail_granularity 按比例計分。"""
    rec = FinancialRecord(
        park_id="p", park_name="n", year=113,
        detail_amounts=[1, 2, 3, 4, 5],  # 5/10
    )
    dc = confidence(rec)
    max_contrib = FACTOR_WEIGHTS["detail_granularity"] * 100.0
    assert dc.factors["detail_granularity"] == pytest.approx(max_contrib * 0.5, abs=1e-6)


def test_dict_input_supported():
    """支援 dict 輸入（非 dataclass）。"""
    dc = confidence({
        "park_id": "d-2",
        "income_actual": 1.0,
        "expense_actual": 1.0,
        "enrollment": 10,
    })
    assert dc.entity_id == "d-2"
    assert 0.0 < dc.score < 100.0


def test_source_with_empty_fields_partial_traceability():
    """有 source_ref 但 dataset/url 皆空 → 來源因子給部分分。"""
    rec = FinancialRecord(
        park_id="p", park_name="n", year=113,
        source_ref=SourceRef(dataset="", authority="教育局", url=None),
    )
    dc = confidence(rec)
    assert 0.0 < dc.factors["source_traceable"] < FACTOR_WEIGHTS["source_traceable"] * 100.0
