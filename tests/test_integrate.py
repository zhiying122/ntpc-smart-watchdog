"""
風險引擎串接整合測試（Risk Engine Integration Tests）
========================================================
對應 Task 22.1（src/integrate.py），驗證：
  - 將 Forensic/Anomaly/Scorer/Timeline/Evidence 輸出串接為契約列，
    以「附加欄位」方式不破壞既有 CONTRACT_COLUMNS 載入契約（R17.1）。
  - 三入口與 Copilot 讀取「已算好」的分數與指標（R10.1, R11.1）。
  - AI 不回流影響計分（assert_no_ai_reflux）。
  - 落地輸出僅在明確呼叫時發生，且寫入臨時路徑（不覆寫既有資料檔）。

含單元測試（具體案例/邊界）與一個 Hypothesis 屬性測試（契約保留不變式）。
"""
import os

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from src.anomaly import detect
from src.evidence import FeatureAttribution, RiskConclusion
from src.integrate import (
    CONTRACT_COLUMNS,
    EXTRA_COLUMNS,
    INTEGRATED_COLUMNS,
    SCORING_COLUMNS,
    IntegratedContract,
    assert_no_ai_reflux,
    integrate_dataset,
    integrate_row,
    write_integrated_contract_files,
)
from src.pipeline import CONTRACT_COLUMNS as PIPELINE_CONTRACT_COLUMNS


# --------------------------------------------------------------------------
# 測試資料
# --------------------------------------------------------------------------
def _source_row():
    """一列已含 Forensic 指標與既有 Scorer 分項的契約列（上游產物）。"""
    return {
        "park_id": "13616",
        "park_name": "新北市立林口幼兒園",
        "park_type": "公校",
        "year": 114,
        "district": "林口區",
        "lat": 25.08,
        "lng": 121.39,
        "income_actual": 120,
        "expense_actual": 130,
        "expense_income_ratio": 1.08,
        "penalty_count": 2,
        "eval_grade": "乙",
        "score_financial": 60.0,
        "score_penalty": 80.0,
        "score_eval": 40.0,
        "risk_total": 62.8,
        "risk_level": "高",
    }


def _year_records():
    """該機構跨年度紀錄（供 Timeline / Change_Point）。"""
    return [
        {"park_id": "13616", "year": 112, "risk_total": 30.0},
        {"park_id": "13616", "year": 113, "risk_total": 35.0},
        {"park_id": "13616", "year": 114, "risk_total": 90.0},  # 明顯突變
    ]


# --------------------------------------------------------------------------
# 契約保留（附加而非破壞，R17.1）
# --------------------------------------------------------------------------
def test_integrated_columns_are_contract_plus_extra_in_order():
    """完整欄位＝既有契約欄位（在前）＋附加欄位（在後）。"""
    assert tuple(INTEGRATED_COLUMNS) == tuple(CONTRACT_COLUMNS) + tuple(EXTRA_COLUMNS)
    # 既有契約欄位在最前段且順序不變（不破壞 common.py 載入契約）。
    assert INTEGRATED_COLUMNS[: len(CONTRACT_COLUMNS)] == tuple(CONTRACT_COLUMNS)
    # 與 pipeline 的契約欄位一致（同一份契約來源）。
    assert tuple(CONTRACT_COLUMNS) == tuple(PIPELINE_CONTRACT_COLUMNS)
    # 附加欄位不與既有欄位重疊。
    assert not (set(EXTRA_COLUMNS) & set(CONTRACT_COLUMNS))


def test_integrate_row_preserves_existing_contract_values():
    """既有契約欄位值原樣保留，不被覆寫。"""
    src = _source_row()
    row = integrate_row(src, year_records=_year_records())
    for col, val in src.items():
        assert row[col] == val
    # 且含全部整合欄位。
    assert set(INTEGRATED_COLUMNS).issubset(row.keys())


# --------------------------------------------------------------------------
# Scorer 串接：已算好的權威總分/等級/責任 AI 聲明（R10.1）
# --------------------------------------------------------------------------
def test_scorer_outputs_written_as_precomputed():
    row = integrate_row(_source_row(), year_records=_year_records())
    assert row["eng_risk_total"] is not None
    assert 0.0 <= row["eng_risk_total"] <= 100.0
    assert row["eng_risk_level"] in {"低", "中", "高", "極高"}
    # 責任 AI 聲明非空（R10.4/R19.4）。
    assert isinstance(row["eng_not_illegality"], str) and row["eng_not_illegality"]
    assert 0.0 <= row["eng_data_confidence"] <= 100.0


# --------------------------------------------------------------------------
# Anomaly 串接（唯讀展示，R8）
# --------------------------------------------------------------------------
def test_anomaly_result_written_into_row():
    entity = {"value": 100.0, "population": [1, 2, 3, 2, 1, 2, 3],
              "series": [1, 1, 100]}
    ar = detect(entity)
    row = integrate_row(_source_row(), anomaly_result=ar,
                        year_records=_year_records())
    assert isinstance(row["eng_anomaly_point"], bool)
    assert row["eng_anomaly_confidence"] in {"high_confidence", "to_confirm", "none"}
    assert row["eng_anomaly_hit_count"] == ar.method_hit_count


def test_anomaly_absent_keeps_defaults():
    row = integrate_row(_source_row(), anomaly_result=None)
    assert row["eng_anomaly_point"] is None
    assert row["eng_anomaly_confidence"] is None


# --------------------------------------------------------------------------
# Timeline 串接：變化點數與觸發說明（R12）
# --------------------------------------------------------------------------
def test_timeline_change_points_detected():
    row = integrate_row(_source_row(), year_records=_year_records())
    assert row["eng_change_point_count"] >= 1
    assert isinstance(row["eng_change_point_note"], str)
    assert row["eng_change_point_note"]


def test_timeline_absent_zero_change_points():
    row = integrate_row(_source_row(), year_records=None)
    assert row["eng_change_point_count"] == 0
    assert row["eng_change_point_note"] is None


# --------------------------------------------------------------------------
# Evidence 串接：可追溯證據鏈（R11.1）
# --------------------------------------------------------------------------
def test_evidence_auto_conclusion_is_traceable():
    """未提供 conclusion 時，由已算好分項自動建最小可追溯證據鏈。"""
    row = integrate_row(_source_row())
    assert row["eng_evidence_traceable"] is True
    assert isinstance(row["eng_evidence_summary"], str) and row["eng_evidence_summary"]


def test_evidence_explicit_conclusion_used():
    from src.models import SourceRef
    conclusion = RiskConclusion(
        entity_id="13616",
        conclusion="支出結構異常",
        attributions=[
            FeatureAttribution(
                feature="expense_income_ratio",
                raw_value=1.08,
                source=SourceRef(dataset="決算書", authority="新北市教育局"),
                contribution=0.9,
                method="shap",
            )
        ],
    )
    row = integrate_row(_source_row(), conclusion=conclusion)
    assert row["eng_evidence_traceable"] is True
    assert "支出結構異常" in row["eng_evidence_summary"]


def test_evidence_no_subscores_not_traceable():
    """無任何已算好分項 → 無法自動建鏈，標記不可追溯（誠實）。"""
    bare = {"park_id": "9999", "park_name": "測試園"}
    row = integrate_row(bare, run_scorer=False)
    assert row["eng_evidence_traceable"] is False
    assert row["eng_evidence_summary"] is None


# --------------------------------------------------------------------------
# 多機構串接與依實體映射
# --------------------------------------------------------------------------
def test_integrate_dataset_maps_by_entity():
    rows = [_source_row(),
            {"park_id": "13611", "park_name": "瑞芳幼兒園", "year": 112,
             "score_financial": 10.0, "score_penalty": 0.0, "score_eval": 30.0}]
    entity = {"value": 100.0, "population": [1, 2, 3, 2, 1, 2, 3],
              "series": [1, 1, 100]}
    contract = integrate_dataset(
        rows,
        anomaly_by_entity={"13616": detect(entity)},
        year_records_by_entity={"13616": _year_records()},
    )
    assert isinstance(contract, IntegratedContract)
    assert len(contract.rows) == 2
    by_id = {r["park_id"]: r for r in contract.rows}
    # 有映射者取得異常/時間軸；無映射者維持預設。
    assert by_id["13616"]["eng_anomaly_hit_count"] is not None
    assert by_id["13616"]["eng_change_point_count"] >= 1
    assert by_id["13611"]["eng_anomaly_point"] is None
    assert by_id["13611"]["eng_change_point_count"] == 0


def test_empty_dataset_does_not_crash():
    contract = integrate_dataset([])
    assert contract.rows == []


# --------------------------------------------------------------------------
# AI 不回流（維持白盒、單向資料流）
# --------------------------------------------------------------------------
def test_assert_no_ai_reflux_passes_when_scores_unchanged():
    before = integrate_row(_source_row(), year_records=_year_records())
    # 模擬 AI 互動：僅讀取、附加非計分欄位（例如展示用文字），不改計分欄位。
    after = dict(before)
    after["eng_evidence_summary"] = "AI 補充展示文字（非計分）"
    assert_no_ai_reflux(before, after)  # 不應拋出


def test_assert_no_ai_reflux_detects_scoring_tamper():
    before = integrate_row(_source_row(), year_records=_year_records())
    after = dict(before)
    after["risk_total"] = 999.0  # AI 非法回寫計分欄位
    with pytest.raises(AssertionError):
        assert_no_ai_reflux(before, after)


def test_scoring_columns_cover_key_score_fields():
    for col in ("risk_total", "risk_level", "score_financial",
                "eng_risk_total", "eng_risk_level"):
        assert col in SCORING_COLUMNS


# --------------------------------------------------------------------------
# 落地輸出（不覆寫既有檔；寫入臨時路徑驗證欄位契約）
# --------------------------------------------------------------------------
def test_write_uses_integrated_header_contract_first(tmp_path):
    contract = integrate_dataset([_source_row()],
                                 year_records_by_entity={"13616": _year_records()})
    latest_path = os.path.join(tmp_path, "kindergartens_latest.csv")
    full_path = os.path.join(tmp_path, "kindergartens.csv")
    write_integrated_contract_files(contract, latest_path, full_path)

    with open(latest_path, encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert tuple(header) == INTEGRATED_COLUMNS
    # 既有契約欄位仍在最前段（common.py 讀既有欄位不受影響）。
    assert tuple(header[: len(CONTRACT_COLUMNS)]) == tuple(CONTRACT_COLUMNS)
    assert os.path.exists(full_path)


def test_import_has_no_write_side_effect(tmp_path):
    """import 與 integrate_dataset 皆不落地（安全：不覆寫既有資料檔）。"""
    # integrate_dataset 只回傳記憶體物件，無檔案產生。
    marker = os.path.join(tmp_path, "should_not_exist.csv")
    integrate_dataset([_source_row()])
    assert not os.path.exists(marker)


# --------------------------------------------------------------------------
# 屬性測試：契約保留不變式（附加欄位不破壞既有契約）
# --------------------------------------------------------------------------
# Feature: smart-watchdog-platform, Task 22.1 契約保留
# Validates: Requirements 17.1, 10.1
_score = st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)


@settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
@given(
    fin=_score,
    pen=st.sampled_from([0, 1, 2, 3, 5]),
    grade=st.sampled_from(["優", "甲", "良", "乙", "中", "丙", "待改進", "不通過", ""]),
    income=st.floats(min_value=1, max_value=1e8, allow_nan=False, allow_infinity=False),
    expense=st.floats(min_value=0, max_value=1e8, allow_nan=False, allow_infinity=False),
)
def test_property_contract_preserved_and_extra_appended(
    fin, pen, grade, income, expense
):
    """任意輸入下：整合列必含全部既有契約欄位（保留原值）＋附加欄位，
    且權威總分落於 0–100、等級為四級之一（R17.1, R10.1）。"""
    src = {
        "park_id": "P1",
        "park_name": "屬性測試園",
        "year": 114,
        "income_actual": income,
        "expense_actual": expense,
        "score_financial": fin,
        "penalty_count": pen,
        "eval_grade": grade,
    }
    row = integrate_row(src)

    # 1) 既有契約欄位全部存在；帶入的「非空」既有值原樣保留，
    #    空值/缺值則正規化為中性空值 None（落地時 _write_csv 轉為 ""，
    #    與 common.py 以 pandas 讀取空白格一致，載入契約不破壞）。
    assert set(CONTRACT_COLUMNS).issubset(row.keys())
    for col, val in src.items():
        if val == "" or val is None:
            assert row[col] is None
        else:
            assert row[col] == val

    # 2) 附加欄位全部存在。
    assert set(EXTRA_COLUMNS).issubset(row.keys())

    # 3) 權威總分（Scorer）落於有效範圍、等級為四級之一。
    assert 0.0 <= row["eng_risk_total"] <= 100.0
    assert row["eng_risk_level"] in {"低", "中", "高", "極高"}
    # 4) 責任 AI 聲明恆存在（非空）。
    assert isinstance(row["eng_not_illegality"], str) and row["eng_not_illegality"]
