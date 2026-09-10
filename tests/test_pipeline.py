"""
資料整合管線單元測試（Data Pipeline Unit Tests）
==================================================
對應 Task 14.1（src/pipeline.py），驗證 run_pipeline 整合財務/裁罰/評鑑/
收費/地理五類資料並維持既有契約欄位（R17.1）。
"""
import os

from src.pipeline import (
    CONTRACT_COLUMNS,
    DataSources,
    IntegratedDataset,
    run_pipeline,
    write_contract_files,
)


def _sources():
    return DataSources(
        financial=[
            {"park_id": "13616", "park_name": "新北市立林口幼兒園", "park_type": "公校",
             "year": 112, "income_actual": 100, "expense_actual": 90},
            {"park_id": "13616", "park_name": "林口幼兒園", "park_type": "公校",
             "year": 114, "income_actual": 120, "expense_actual": 110},
            {"park_id": "13611", "park_name": "新北市立瑞芳幼兒園", "park_type": "公校",
             "year": 112, "income_actual": 50, "expense_actual": 70},
        ],
        penalty=[
            {"park_name": "新北市立林口幼兒園", "penalty_count": 2,
             "penalty_reason": "超收幼生", "eval_grade": "乙"},
        ],
        evaluation=[
            {"park_name": "瑞芳幼兒園", "eval_grade": "甲"},
        ],
        fee=[
            {"park_name": "林口幼兒園", "tuition_actual": 2500},
        ],
        geo=[
            {"park_name": "新北市立林口幼兒園", "district": "林口區",
             "lat": 25.08, "lng": 121.39},
        ],
    )


# --------------------------------------------------------------------------
# 整合輸出結構（R17.1）
# --------------------------------------------------------------------------
def test_run_pipeline_returns_integrated_dataset():
    ds = run_pipeline(_sources())
    assert isinstance(ds, IntegratedDataset)
    # 兩間機構（13616 跨兩年、13611 一年）。
    assert len(ds.entities) == 2
    # per_year：13616 兩列 + 13611 一列 = 3。
    assert len(ds.per_year_rows) == 3
    # latest：每園一列 = 2。
    assert len(ds.latest_rows) == 2


def test_latest_row_takes_newest_year():
    """latest 列取最新年度的財務值（R17.1）。"""
    ds = run_pipeline(_sources())
    latest = {r["park_id"]: r for r in ds.latest_rows}
    assert latest["13616"]["year"] == 114
    assert latest["13616"]["income_actual"] == 120


def test_auxiliary_sources_merged_into_latest():
    """裁罰/評鑑/收費/地理併入 latest 列（R17.1）。"""
    ds = run_pipeline(_sources())
    latest = {r["park_id"]: r for r in ds.latest_rows}
    lk = latest["13616"]
    assert lk["penalty_count"] == 2
    assert lk["district"] == "林口區"
    assert lk["lat"] == 25.08
    assert lk["tuition_actual"] == 2500
    # 評鑑併入瑞芳。
    assert latest["13611"]["eval_grade"] == "甲"


def test_contract_columns_preserved_on_every_row():
    """所有輸出列皆含既有契約欄位，計分欄位保留 None 由後續階段填入。"""
    ds = run_pipeline(_sources())
    for row in ds.latest_rows + ds.per_year_rows:
        assert set(CONTRACT_COLUMNS).issubset(row.keys())
        # 管線不計分，score_*/risk_* 應為 None。
        assert row["risk_total"] is None
        assert row["score_financial"] is None


def test_empty_sources_do_not_crash():
    """全空來源安全回傳空資料集（不中斷）。"""
    ds = run_pipeline(DataSources())
    assert ds.latest_rows == []
    assert ds.per_year_rows == []
    assert ds.entities == []


# --------------------------------------------------------------------------
# 落地輸出（不覆寫既有檔；寫入臨時路徑驗證欄位契約）
# --------------------------------------------------------------------------
def test_write_contract_files_uses_contract_header(tmp_path):
    ds = run_pipeline(_sources())
    latest_path = os.path.join(tmp_path, "kindergartens_latest.csv")
    full_path = os.path.join(tmp_path, "kindergartens.csv")
    write_contract_files(ds, latest_path, full_path)

    with open(latest_path, encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert tuple(header) == CONTRACT_COLUMNS
    assert os.path.exists(full_path)
