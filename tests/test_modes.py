"""
三模式路由與存取控制單元測試（User-Mode Routing, R1.1, R1.6, R1.7）
======================================================================
驗證 app/lib/modes.py：
  - 已驗證使用者依類型唯一對應 Gov_Console / Inspector_Workspace / Parent_Portal（R1.1）。
  - 三模式功能集合兩兩互斥、不重疊（R1.6）。
  - 未驗證或無法對應之身分 → 存取拒絕，且輸出不含任何分數/等級資訊（R1.7）。

對應 Task 18.1「實作三模式路由與存取控制」。
屬性測試（Property 1/3/4）另見 Task 18.3。

本模組位於 app/lib/（非 src 套件），且 app/ 無 __init__.py，故以檔案路徑載入，
避免更動既有 app/ 套件結構。
"""
import importlib.util
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MODES_PATH = os.path.join(_ROOT, "app", "lib", "modes.py")

_spec = importlib.util.spec_from_file_location("app_lib_modes", _MODES_PATH)
modes = importlib.util.module_from_spec(_spec)
# 註冊至 sys.modules，使 dataclass 於解析 `from __future__ import annotations`
# 的字串型別註解時能找到自身模組命名空間。
sys.modules[_spec.name] = modes
_spec.loader.exec_module(modes)

Mode = modes.Mode
UserType = modes.UserType
VALID_MODES = modes.VALID_MODES


# ---------------------------------------------------------------------------
# R1.1 — 使用者類型唯一對應模式
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "user_type, expected",
    [
        (UserType.GOV_USER, Mode.GOV_CONSOLE),
        (UserType.INSPECTOR, Mode.INSPECTOR_WORKSPACE),
        (UserType.PARENT_USER, Mode.PARENT_PORTAL),
    ],
)
def test_authenticated_user_routes_to_expected_mode(user_type, expected):
    d = modes.resolve_mode(user_type)
    assert d.authorized is True
    assert d.mode is expected
    assert d.message is None


def test_string_user_type_is_accepted():
    """接受字串型別（大小寫/空白不敏感）。"""
    d = modes.resolve_mode("  Gov_User  ")
    assert d.authorized is True
    assert d.mode is Mode.GOV_CONSOLE


def test_resolved_mode_is_one_of_three_valid_modes():
    for ut in UserType:
        d = modes.resolve_mode(ut)
        assert d.mode in VALID_MODES


def test_authorized_features_match_mode_feature_set():
    d = modes.resolve_mode(UserType.INSPECTOR)
    assert d.features == modes.features_for(Mode.INSPECTOR_WORKSPACE)
    assert len(d.features) > 0


# ---------------------------------------------------------------------------
# R1.6 — 功能集合互斥、不重疊
# ---------------------------------------------------------------------------
def test_feature_sets_are_pairwise_disjoint():
    # 不得拋出例外；模組匯入時亦已執行此檢查。
    modes.assert_features_disjoint()


def test_union_size_equals_sum_of_sets():
    total = sum(len(modes.features_for(m)) for m in VALID_MODES)
    assert len(modes.all_features()) == total


def test_every_feature_belongs_to_exactly_one_mode():
    for feat in modes.all_features():
        owning = [m for m in VALID_MODES if feat in modes.features_for(m)]
        assert len(owning) == 1
        assert modes.feature_mode(feat) is owning[0]


def test_unknown_feature_has_no_mode():
    assert modes.feature_mode("nonexistent_feature") is None


# ---------------------------------------------------------------------------
# R1.7 — 未授權存取拒絕且不揭露分數/等級
# ---------------------------------------------------------------------------
def test_unauthenticated_is_denied():
    d = modes.resolve_mode(UserType.GOV_USER, authenticated=False)
    assert d.authorized is False
    assert d.mode is Mode.DENIED


def test_unknown_user_type_is_denied():
    for bad in [None, "hacker", "", 123, object()]:
        d = modes.resolve_mode(bad)
        assert d.authorized is False, f"expected denial for {bad!r}"
        assert d.mode is Mode.DENIED


def test_denied_result_exposes_no_features():
    d = modes.resolve_mode(None)
    assert d.features == frozenset()


def test_denied_result_discloses_no_score_or_level():
    """存取遭拒的輸出不得含任何足以還原分數/等級的欄位或內容。"""
    d = modes.resolve_mode(None)
    # 拒絕物件的完整字串（含 message）不得洩漏任何分數/等級關鍵字。
    blob = repr(d).lower()
    for banned in ("risk_total", "risk_level", "score", "分數", "等級", "極高"):
        assert banned not in blob
    assert d.message is not None  # 有存取遭拒提示


def test_denied_mode_is_not_a_valid_mode():
    assert Mode.DENIED not in VALID_MODES


# ===========================================================================
# Task 18.2 — 家長入口欄位白名單投影 public_view（R1.5, R6.6）
# ===========================================================================
# 家長入口的公開投影不得洩漏任何內部風險分數、等級或其衍生排序（Property 2）。
# 以下先以單元測試涵蓋具體案例與邊界，再以屬性測試（Property 2）驗證泛化不變式。

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

public_view = modes.public_view


# 禁止外洩的欄位（分數/等級/衍生排序），任何形式皆不得出現在投影輸出。
_FORBIDDEN_SAMPLE_KEYS = [
    "risk_total",
    "risk_level",
    "risk_level_abs",
    "risk_score",
    "risk_rank",
    "risk_percentile",
    "score_financial",
    "score_penalty",
    "score_evaluation",
    "score_sentiment",
    "score",
    "financial_score",
    "rank",
    "ranking",
    "percentile",
    "priority_rank",
    "sort_key",
]


def _is_leaky_key(key: str) -> bool:
    """測試端獨立判定：某鍵是否屬於分數/等級/衍生排序（不得外洩）。"""
    k = str(key).strip().lower()
    if k in {
        "risk_total", "risk_level", "risk_level_abs", "risk_score",
        "rank", "ranking", "percentile", "priority", "order",
        "sort_key", "sort_order",
    }:
        return True
    return (
        k.startswith("score_")
        or k.endswith("_score")
        or k == "score"
        or k.startswith("risk_")
        or k.endswith("_risk")
        or "rank" in k
        or "percentile" in k
    )


# ---------------------------------------------------------------------------
# 單元測試：具體案例
# ---------------------------------------------------------------------------
def test_public_view_keeps_whitelisted_public_fields():
    record = {
        "park_name": "示範幼兒園",
        "ownership": "私立",
        "address": "新北市板橋區",
        "district": "板橋區",
        "tuition_info": {"monthly": 12000},
        "public_eval": "通過",
        "public_penalty": [],
    }
    out = public_view(record)
    assert out["park_name"] == "示範幼兒園"
    assert out["ownership"] == "私立"
    assert out["tuition_info"] == {"monthly": 12000}
    assert out["public_eval"] == "通過"
    assert out["public_penalty"] == []


def test_public_view_removes_risk_total_level_and_scores():
    record = {
        "park_name": "示範幼兒園",
        "ownership": "公立",
        "risk_total": 87.3,
        "risk_level": "高",
        "risk_level_abs": "critical",
        "score_financial": 40.0,
        "score_penalty": 30.0,
        "score_evaluation": 10.0,
        "score_sentiment": 7.3,
    }
    out = public_view(record)
    assert out == {"park_name": "示範幼兒園", "ownership": "公立"}
    for banned in ("risk_total", "risk_level", "risk_level_abs"):
        assert banned not in out
    assert not any(k.startswith("score_") for k in out)


def test_public_view_removes_derived_ranking_columns():
    record = {
        "park_name": "A 園",
        "rank": 1,
        "ranking": 1,
        "risk_rank": 1,
        "risk_percentile": 0.99,
        "percentile": 0.99,
        "priority_rank": 3,
        "sort_key": "z",
    }
    out = public_view(record)
    assert out == {"park_name": "A 園"}


def test_public_view_case_and_whitespace_insensitive_on_forbidden_keys():
    record = {
        "park_name": "B 園",
        "  Risk_Total  ": 55.0,
        "SCORE_Financial": 20.0,
        "Risk_Level": "中",
    }
    out = public_view(record)
    assert out == {"park_name": "B 園"}


def test_public_view_drops_unknown_non_whitelisted_fields():
    """未列於白名單的欄位即便非分數，也不予呈現（白名單投影）。"""
    record = {"park_name": "C 園", "internal_note": "機密", "raw_dump": 123}
    out = public_view(record)
    assert out == {"park_name": "C 園"}


def test_public_view_accepts_dataclass_like_object():
    from src.models import PublicInstitutionView, SourceRef  # noqa: WPS433

    view = PublicInstitutionView(
        park_name="D 園",
        ownership="非營利",
        public_eval="優",
        field_sources={"park_name": SourceRef(dataset="ds", authority="教育局")},
        stale_flags={"public_eval": False},
    )
    out = public_view(view)
    assert out["park_name"] == "D 園"
    assert out["ownership"] == "非營利"
    assert "field_sources" in out
    assert not any(_is_leaky_key(k) for k in out)


def test_public_view_empty_or_unusable_record_returns_empty_dict():
    assert public_view({}) == {}
    assert public_view(object()) == {}


# ---------------------------------------------------------------------------
# Property 2: 家長入口隱藏所有內部風險資訊
# ---------------------------------------------------------------------------
# *For any* 機構紀錄，public_view 輸出不含 risk_total、risk_level、任何 score_*
# 欄位或其衍生排序，且無任何可還原上述值的欄位。
# Validates: Requirements 1.5, 6.6

# 產生器：混合白名單公開欄位與各式禁止欄位，構造任意機構紀錄。
_public_key = st.sampled_from(sorted(modes.PUBLIC_WHITELIST_FIELDS))
_forbidden_key = st.sampled_from(_FORBIDDEN_SAMPLE_KEYS)
_arbitrary_key = st.text(min_size=1, max_size=12)
_any_key = st.one_of(_public_key, _forbidden_key, _arbitrary_key)
_any_value = st.one_of(
    st.integers(), st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=20), st.booleans(), st.none(),
)
_record_strategy = st.dictionaries(keys=_any_key, values=_any_value, max_size=12)


@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(record=_record_strategy)
def test_property2_public_view_hides_all_internal_risk_info(record):
    """Property 2: public_view 輸出不含任何分數/等級/衍生排序欄位。

    **Validates: Requirements 1.5, 6.6**
    """
    out = public_view(record)
    # 輸出中不得含任何足以還原分數/等級的欄位。
    for key in out:
        assert not _is_leaky_key(key), f"leaked forbidden key: {key!r}"
    # 輸出鍵必為白名單子集（正規化比對）。
    for key in out:
        assert str(key).strip().lower() in {
            f.strip().lower() for f in modes.PUBLIC_WHITELIST_FIELDS
        }


@settings(max_examples=200)
@given(
    base=st.fixed_dictionaries({
        "park_name": st.text(min_size=1, max_size=20),
        "ownership": st.sampled_from(["公立", "私立", "非營利"]),
    }),
    risk_total=st.floats(min_value=0, max_value=100),
    risk_level=st.sampled_from(["低", "中", "高", "critical"]),
)
def test_property2_injected_scores_never_survive(base, risk_total, risk_level):
    """即便強制注入 risk_total/risk_level/score_*，投影輸出仍完全不含之。

    **Validates: Requirements 1.5, 6.6**
    """
    record = dict(base)
    record["risk_total"] = risk_total
    record["risk_level"] = risk_level
    record["risk_level_abs"] = risk_level
    record["score_financial"] = risk_total / 2
    record["risk_rank"] = 1
    record["percentile"] = 0.5

    out = public_view(record)
    assert "risk_total" not in out
    assert "risk_level" not in out
    assert "risk_level_abs" not in out
    assert not any(k.startswith("score_") for k in out)
    assert "risk_rank" not in out
    assert "percentile" not in out
    # 白名單公開欄位仍應保留。
    assert out["park_name"] == base["park_name"]
    assert out["ownership"] == base["ownership"]
