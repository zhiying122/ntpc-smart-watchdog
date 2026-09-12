"""
RBAC 資料授權層單元測試（app/lib/permissions.py）
====================================================
核心原則：權限在資料層擋，不是 UI 藏。

驗證：
  - authorize_dataframe 對家長角色回傳的 DataFrame **不含** risk_total /
    risk_level / risk_level_abs / 任何 score_* / 排序衍生欄位。
  - 政府 / 稽查員保留完整欄位。
  - get_allowed_fields 三角色正確。
  - get_role_navigation 三角色頁面集合正確，且家長只含家長頁。

本模組位於 app/lib/（非 src 套件，無 __init__.py），沿用 tests/test_modes.py
的 importlib file-path 載入方式，避免更動既有 app/ 套件結構。permissions.py
為純邏輯（不 import streamlit），故測試不需 Streamlit runtime。
"""
import importlib.util
import os
import sys

import pandas as pd
import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PERM_PATH = os.path.join(_ROOT, "app", "lib", "permissions.py")

# 確保 src 可被 permissions -> modes（若走 src 路徑）解析；並將 app/lib 加入路徑
# 以支援 permissions 內部的 modes 載入。
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_spec = importlib.util.spec_from_file_location("app_lib_permissions", _PERM_PATH)
perm = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = perm
_spec.loader.exec_module(perm)

GOV = perm.ROLE_GOV
INSPECTOR = perm.ROLE_INSPECTOR
PARENT = perm.ROLE_PARENT


# 模擬真實 CSV 欄位（含所有內部風險/鑑識欄位）。
def _sample_df():
    return pd.DataFrame({
        "park_id": ["P001", "P002"],
        "park_name": ["示範幼兒園", "測試幼兒園"],
        "park_type": ["公立", "非營利"],
        "district": ["板橋區", "新莊區"],
        "address": ["新北市板橋區", "新北市新莊區"],
        "tuition_actual": [12000, 15000],
        "eval_grade": ["優", "良"],
        "year": [113, 113],
        # 以下為家長絕不可見的內部欄位
        "risk_total": [92.0, 45.0],
        "risk_level": ["高", "中"],
        "risk_level_abs": ["critical", "medium"],
        "score_financial": [40.0, 20.0],
        "score_penalty": [30.0, 10.0],
        "score_eval": [16.0, 8.0],
        "benford_score": [0.8, 0.2],
        "beneish_score": [1.2, 0.5],
        "iforest_score": [0.9, 0.1],
        "penalty_count": [3, 0],
    })


# 明確禁止家長看到的欄位。
_FORBIDDEN = [
    "risk_total", "risk_level", "risk_level_abs",
    "score_financial", "score_penalty", "score_eval",
    "benford_score", "beneish_score", "iforest_score",
]


# ---------------------------------------------------------------------------
# authorize_dataframe — 家長角色實際移除風險欄位
# ---------------------------------------------------------------------------
def test_authorize_dataframe_parent_drops_all_risk_fields():
    df = _sample_df()
    out = perm.authorize_dataframe(df, PARENT)
    for col in _FORBIDDEN:
        assert col not in out.columns, f"家長 df 不得含 {col}"
    # 亦不得含任何 score_* 或 risk_*
    for col in out.columns:
        assert not str(col).startswith("score_")
        assert not str(col).startswith("risk_")


def test_authorize_dataframe_parent_keeps_only_public_fields():
    df = _sample_df()
    out = perm.authorize_dataframe(df, PARENT)
    # 家長公開欄位：含裁罰「事實」欄位（次數/原因/類別）——裁罰紀錄為公開揭露
    # 資訊，家長本得知悉；但不含任何內部風險分數（score_penalty 仍被擋除）。
    expected_public = {"park_id", "park_name", "park_type", "district",
                       "address", "tuition_actual", "eval_grade", "year",
                       "penalty_count"}
    assert set(out.columns) == expected_public
    # 確認裁罰「評分」（風險分項）仍不外洩，只給裁罰「事實」。
    assert "score_penalty" not in out.columns


def test_authorize_dataframe_parent_does_not_mutate_original():
    df = _sample_df()
    original_cols = list(df.columns)
    perm.authorize_dataframe(df, PARENT)
    assert list(df.columns) == original_cols  # 原始 df 不被修改


def test_authorize_dataframe_parent_result_is_real_projection_not_hidden():
    """關鍵：家長 df 根本不含 risk_total 這一欄（不是保留再隱藏）。"""
    df = _sample_df()
    out = perm.authorize_dataframe(df, PARENT)
    # 嘗試存取 risk_total 應該 KeyError（欄位根本不存在）。
    with pytest.raises(KeyError):
        _ = out["risk_total"]


# ---------------------------------------------------------------------------
# authorize_dataframe — 政府 / 稽查員保留完整欄位
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", [GOV, INSPECTOR])
def test_authorize_dataframe_full_access_keeps_all_columns(role):
    df = _sample_df()
    out = perm.authorize_dataframe(df, role)
    assert set(out.columns) == set(df.columns)
    for col in _FORBIDDEN:
        assert col in out.columns


@pytest.mark.parametrize("role", [GOV, INSPECTOR])
def test_authorize_dataframe_full_access_preserves_values(role):
    df = _sample_df()
    out = perm.authorize_dataframe(df, role)
    assert out["risk_total"].tolist() == [92.0, 45.0]
    assert out["park_name"].tolist() == ["示範幼兒園", "測試幼兒園"]


def test_authorize_dataframe_unknown_role_is_conservative():
    """未知角色比照家長，採最保守投影（不得洩漏風險欄位）。"""
    df = _sample_df()
    out = perm.authorize_dataframe(df, "hacker")
    for col in _FORBIDDEN:
        assert col not in out.columns


# ---------------------------------------------------------------------------
# get_allowed_fields — 三角色
# ---------------------------------------------------------------------------
def test_get_allowed_fields_parent_is_public_whitelist_only():
    fields = perm.get_allowed_fields(PARENT)
    for col in _FORBIDDEN:
        assert col not in fields
    assert "park_name" in fields
    assert "tuition_actual" in fields
    assert "eval_grade" in fields


@pytest.mark.parametrize("role", [GOV, INSPECTOR])
def test_get_allowed_fields_full_access_includes_risk_fields(role):
    fields = perm.get_allowed_fields(role)
    assert "risk_total" in fields
    assert "score_financial" in fields
    assert "park_name" in fields


def test_get_allowed_fields_parent_subset_of_full():
    parent_fields = perm.get_allowed_fields(PARENT)
    gov_fields = perm.get_allowed_fields(GOV)
    # 家長允許欄位應為政府允許欄位的子集（政府全欄位可見）。
    assert parent_fields.issubset(gov_fields)


# ---------------------------------------------------------------------------
# get_role_navigation — 三角色頁面集合
# ---------------------------------------------------------------------------
def test_get_role_navigation_gov():
    nav = set(perm.get_role_navigation(GOV))
    assert nav == {"主頁", "2_map", "5_dispatch", "7_integration",
                   "3_ai", "4_sentiment", "6_governance", "9_public_preview",
                   "8_health"}


def test_get_role_navigation_inspector():
    nav = set(perm.get_role_navigation(INSPECTOR))
    assert nav == {"1_case", "3_ai", "4_sentiment"}


def test_get_role_navigation_parent_has_no_backend_page():
    # 系統切分後：家長端為獨立公眾查詢網（public/），公務後台不再提供家長頁，
    # 故家長角色在公務後台的導覽為空。家長端不經公務後台的 RBAC 導覽。
    nav = perm.get_role_navigation(PARENT)
    assert nav == []


def test_get_role_navigation_parent_excludes_all_gov_inspector_pages():
    nav = set(perm.get_role_navigation(PARENT))
    for forbidden_page in {"主頁", "1_case", "2_map", "3_ai", "4_sentiment", "6_governance"}:
        assert forbidden_page not in nav


def test_get_role_navigation_unknown_role_is_empty():
    assert perm.get_role_navigation("hacker") == []


# ---------------------------------------------------------------------------
# 資料權限矩陣 / 摘要
# ---------------------------------------------------------------------------
def test_permission_matrix_parent_cannot_see_risk_score():
    assert perm.data_visibility("Risk Score", PARENT) == perm.NONE
    assert perm.data_visibility("財務資料", PARENT) == perm.NONE


def test_permission_matrix_parent_can_see_public_categories():
    for cat in ("基本資料", "收費資料", "公開評鑑", "公開裁罰"):
        assert perm.data_visibility(cat, PARENT) == perm.FULL


def test_permission_matrix_table_has_all_roles_and_categories():
    table = perm.permission_matrix_table()
    assert len(table) == len(perm.DATA_PERMISSION_MATRIX)
    assert "資料類別" in table.columns
    # 三角色欄名皆存在
    for role in perm.VALID_ROLES:
        assert perm.role_label(role) in table.columns


def test_get_role_permissions_summary_shape():
    for role in perm.VALID_ROLES:
        summary = perm.get_role_permissions(role)
        assert summary["role"] == role
        assert "visible_categories" in summary
        assert "navigation" in summary
        assert "allowed_fields" in summary
    # 家長不可見 Risk Score
    parent_summary = perm.get_role_permissions(PARENT)
    assert "Risk Score" not in parent_summary["visible_categories"]
    assert parent_summary["full_access"] is False
    # 政府全欄位可見
    assert perm.get_role_permissions(GOV)["full_access"] is True
