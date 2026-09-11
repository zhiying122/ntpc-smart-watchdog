"""
A+ RBAC 角色權限架構 —「你能看什麼」（Data-layer Authorization）
====================================================================
小小守護員 Smart Watchdog Platform — 以角色為中心的資料授權層（RBAC）。

核心原則：**權限在資料層擋，不是 UI 藏**。
不該給某角色看的欄位，是在資料層被「投影掉」（實際從 DataFrame 移除），
而不是保留後在前端隱藏。家長角色取得的 DataFrame 本身就不含 risk_total，
並非前端把分數算出來再藏起來。

本模組為**純邏輯**：不 import streamlit（可離線單元測試）。
沿用既有 `app/lib/modes.py` 的三種角色（UserType）與 `public_view` 黑名單防禦，
不重寫其邏輯，只在其之上建構「角色 → 可見資料 / 可見頁面」的 RBAC 對映。

三個 Demo 角色（對應 modes.UserType）：
  - 政府管理者 gov_user    — 全轄區決策視角，看得到所有欄位與風險分。
  - 稽查人員   inspector   — 單一機構鑑識調查，看得到所有欄位（含 risk/score/證據）。
  - 家長       parent_user — 公開透明視角，只看得到公開欄位，**不含任何風險分**。

責任 AI：風險資訊不是越多人看越好，而是由角色、職責與必要性決定誰可以看到。
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# 載入既有 modes.py（app/lib 非套件、無 __init__.py，故以檔案路徑載入）
# ---------------------------------------------------------------------------
# 沿用 tests/test_modes.py 同樣的 importlib file-path 載入方式，確保無論從
# Streamlit（`from lib import modes`）或從測試（file-path 載入）皆能取得同一份
# 角色定義與 public_view 黑名單規則，不重寫其邏輯。
def _load_modes():
    # 優先嘗試一般 import（Streamlit 執行時 lib 在 sys.path 上）。
    try:
        from lib import modes as _m  # type: ignore
        return _m
    except Exception:
        pass
    _here = os.path.dirname(os.path.abspath(__file__))
    _modes_path = os.path.join(_here, "modes.py")
    _spec = importlib.util.spec_from_file_location("app_lib_modes", _modes_path)
    _m = importlib.util.module_from_spec(_spec)
    import sys as _sys
    _sys.modules[_spec.name] = _m
    _spec.loader.exec_module(_m)
    return _m


modes = _load_modes()


# ---------------------------------------------------------------------------
# 角色常數（沿用 modes.UserType 的三種字串值）
# ---------------------------------------------------------------------------
ROLE_GOV = "gov_user"          # 政府管理者
ROLE_INSPECTOR = "inspector"   # 稽查人員
ROLE_PARENT = "parent_user"    # 家長

VALID_ROLES: tuple[str, ...] = (ROLE_GOV, ROLE_INSPECTOR, ROLE_PARENT)

#: 三個 Demo 角色的可讀中文名（政府/企業級介面，不使用 emoji 裝飾）。
ROLE_DISPLAY: dict[str, dict[str, str]] = {
    ROLE_GOV: {"name": "政府管理者", "emoji": ""},
    ROLE_INSPECTOR: {"name": "稽查人員", "emoji": ""},
    ROLE_PARENT: {"name": "家長", "emoji": ""},
}


def role_label(role: str) -> str:
    """回傳角色的中文名（政府/企業級介面不加 emoji）。未知角色回傳原字串。"""
    info = ROLE_DISPLAY.get(role)
    if not info:
        return str(role)
    return info["name"]


def role_name(role: str) -> str:
    """回傳角色的中文名。"""
    info = ROLE_DISPLAY.get(role)
    return info["name"] if info else str(role)


def role_emoji(role: str) -> str:
    """（保留相容）政府/企業級介面不使用 emoji，一律回傳空字串。"""
    return ""


# ===========================================================================
# 資料權限矩陣（Data Permission Matrix）
# ===========================================================================
# 定義各「資料類別」對三角色的可見性（政府/企業級介面，以文字表達不用符號）：
#   FULL    = "完整可見"
#   PARTIAL = "部分可見"  部分/去識別可見
#   NONE    = "不可見"
#
# 可程式查詢（dict），並可產生「可展示表格」供簡報頁（6_governance）使用。
FULL = "完整可見"
PARTIAL = "部分可見"
NONE = "不可見"

#: 資料類別 → {角色: 可見性}。順序即為簡報表格的呈現順序。
DATA_PERMISSION_MATRIX: dict[str, dict[str, str]] = {
    "基本資料": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: FULL},
    "收費資料": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: FULL},
    "公開評鑑": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: FULL},
    "公開裁罰": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: FULL},
    "財務資料": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "Risk Score": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "Anomaly Detail": {ROLE_GOV: PARTIAL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "AI Investigation": {ROLE_GOV: PARTIAL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "稽查優先級": {ROLE_GOV: FULL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "內部查核資料": {ROLE_GOV: PARTIAL, ROLE_INSPECTOR: FULL, ROLE_PARENT: NONE},
    "資源分派": {ROLE_GOV: FULL, ROLE_INSPECTOR: PARTIAL, ROLE_PARENT: NONE},
}


def data_visibility(category: str, role: str) -> str:
    """查詢某「資料類別」對某角色的可見性（完整可見/部分可見/不可見）。未知者回傳不可見。"""
    return DATA_PERMISSION_MATRIX.get(category, {}).get(role, NONE)


def permission_matrix_table() -> pd.DataFrame:
    """回傳可展示的資料權限矩陣表格（供簡報頁 6_governance 使用）。

    欄位：資料類別 × 三角色（以中文名為欄名），值為 完整可見/部分可見/不可見。
    """
    columns = {role: role_label(role) for role in VALID_ROLES}
    rows: list[dict[str, Any]] = []
    for category, vis in DATA_PERMISSION_MATRIX.items():
        row: dict[str, Any] = {"資料類別": category}
        for role in VALID_ROLES:
            row[columns[role]] = vis.get(role, NONE)
        rows.append(row)
    return pd.DataFrame(rows, columns=["資料類別", *columns.values()])


# ===========================================================================
# 欄位級授權：get_allowed_fields / authorize_dataframe
# ===========================================================================
# 家長公開欄位白名單：以實際 CSV 欄位命名為準（park_id/park_name/ownership/
# park_type/district/address/tuition_actual/eval_grade 與公開相關欄位）。
# 此清單**刻意不含** risk_total/risk_level/risk_level_abs/score_*/任何排序衍生欄位。
_PARENT_PUBLIC_FIELDS: frozenset[str] = frozenset({
    "park_id",         # 機構識別碼（非分數衍生）
    "park_name",       # 機構名稱
    "ownership",       # 公私立別（若資料集提供）
    "park_type",       # 機構類型（公立/非營利…）
    "district",        # 行政區
    "address",         # 地址
    "tuition_actual",  # 公開收費（實際）
    "tuition_info",    # 公開收費資訊（契約欄位）
    "eval_grade",      # 公開評鑑等第
    "public_eval",     # 公開評鑑結果（契約欄位）
    "public_penalty",  # 公開裁罰紀錄（契約欄位）
    "year",            # 年度（識別用，非分數）
})


def get_allowed_fields(role: str) -> set[str]:
    """回傳該角色允許看到的 DataFrame 欄位集合（欄位級授權）。

    - 政府（gov_user）：全部欄位 → 回傳完整資料集欄位集合（以「不限制」表示，
      實務上 authorize_dataframe 對政府/稽查員直接回傳完整 df）。此函式回傳
      家長公開欄位 ∪ 完整風險欄位的聯集語意；為明確起見回傳「所有已知欄位」的
      超集標記，見下方 ALL_FIELDS。
    - 稽查員（inspector）：全部欄位（含 risk_total/score_*/anomaly/evidence）。
    - 家長（parent_user）：只有公開欄位白名單，**不含**任何 risk_*/score_*/排序衍生欄位。

    設計說明：政府與稽查員為「全欄位可見」，因此回傳 `ALL_FIELDS` 這個哨兵集合
    （見 authorize_dataframe：對這兩個角色不做欄位刪減）。家長則回傳明確白名單。
    """
    if role == ROLE_PARENT:
        return set(_PARENT_PUBLIC_FIELDS)
    if role in (ROLE_GOV, ROLE_INSPECTOR):
        # 全欄位可見：回傳公開欄位與完整風險欄位的聯集，作為「允許欄位」的明示清單。
        return set(_PARENT_PUBLIC_FIELDS) | set(_FULL_RISK_FIELDS)
    # 未知角色：最保守，只給公開欄位。
    return set(_PARENT_PUBLIC_FIELDS)


#: 完整風險/鑑識欄位（政府與稽查員可見；家長絕不可見）。用於 get_allowed_fields
#: 對 gov/inspector 的「明示允許清單」與測試對照。
_FULL_RISK_FIELDS: frozenset[str] = frozenset({
    "risk_total", "risk_level", "risk_level_abs",
    "score_financial", "score_penalty", "score_eval", "score_sentiment",
    "income_actual", "expense_actual", "surplus", "expense_income_ratio",
    "benford_mad", "benford_sample_n", "benford_score", "benford_chi2",
    "benford_pvalue", "benford_significant",
    "beneish_score", "beneish_egdi", "beneish_tata",
    "iforest_score", "iforest_explain", "expense_yoy_pct",
    "penalty_count", "lat", "lng",
})


def _parent_authorize(df: pd.DataFrame) -> pd.DataFrame:
    """家長角色的 DataFrame 投影：實際「丟掉」所有風險/分數/排序衍生欄位。

    採「白名單 + modes.public_view 黑名單」雙保險：
      1) 先挑出白名單內的欄位；
      2) 再以 modes._is_forbidden_key 黑名單過濾，確保即使白名單命名疏漏或
         上游混入 risk_*/score_*/rank/percentile 欄位也不會外洩。
    回傳的 df 根本不含 risk_total —— 不是保留再隱藏。
    """
    forbidden = getattr(modes, "_is_forbidden_key", None)
    keep: list[str] = []
    for col in df.columns:
        # 黑名單優先：任何禁止欄位一律排除（即使誤列於白名單）。
        if forbidden is not None and forbidden(col):
            continue
        if col in _PARENT_PUBLIC_FIELDS:
            keep.append(col)
    return df.loc[:, keep].copy()


def authorize_dataframe(df: pd.DataFrame, role: str) -> pd.DataFrame:
    """依角色投影 DataFrame（資料層授權，非 UI 隱藏）。

    - 家長（parent_user）：實際移除所有 risk_*/score_*/排序衍生欄位，
      回傳的 df **根本不含** risk_total —— 家長頁拿到的資料本身就沒有分數。
    - 政府（gov_user）/ 稽查員（inspector）：回傳完整 df 的複本（全欄位可見）。
    - 未知/未登入角色：比照家長，採最保守投影（只留公開欄位）。

    參數
    ----
    df : pd.DataFrame
        原始資料（可能含 risk_total/score_* 等內部欄位）。
    role : str
        角色字串（gov_user/inspector/parent_user）。

    回傳
    ----
    pd.DataFrame
        依角色投影後的 DataFrame（複本，不動原始 df）。
    """
    if df is None:
        return df
    if role in (ROLE_GOV, ROLE_INSPECTOR):
        # 全欄位可見：回傳複本，示範仍走過資料授權層這一致流程。
        return df.copy()
    # 家長與未知角色：最保守，實際丟掉風險欄位。
    return _parent_authorize(df)


# ===========================================================================
# 頁面級授權：角色 → 可見頁面（第一層授權，UI 導覽）
# ===========================================================================
# 頁面 key 沿用 common.NAV 與 pages/ 的檔名關鍵字。現有頁面對映到角色的原則
# 依 modes._MODE_FEATURES 的精神分配：
#
#   政府（Gov_Console 職能：全轄區決策、分派、模擬）:
#     主頁（風險總覽）、2_map（風險地圖）、3_ai（AI 決策支援）、
#     4_sentiment（輿情分析）、6_governance（資料治理權限矩陣）
#   稽查員（Inspector_Workspace 職能：單一機構調查、證據、AI Copilot）:
#     1_case（案件調查）、3_ai（AI 決策支援）、4_sentiment（輿情分析）
#   家長（Parent_Portal 職能：公開透明查詢）:
#     5_parent（家長信任中心）—— 且僅此一頁
#
# 說明：3_ai / 4_sentiment 同時服務政府與稽查員（決策支援 + 分析），
# 因此在兩者的導覽中皆出現；家長只看得到家長頁。
# 說明（系統切分）：本 app 為「公務後台」，僅服務政府與稽查兩種公務角色。
# 家長端已切分為獨立的「公眾查詢網」（public/ 獨立進入點、無登入、獨立網域），
# 因此公務後台的導覽不含家長頁；家長角色在此不對應任何頁面（導覽為空）。
# ROLE_PARENT 常數與 authorize_dataframe 的去識別化投影仍保留，供公眾查詢網
# 於資料層取用「移除所有風險欄位後」的公開資料。
_ROLE_PAGES: dict[str, tuple[str, ...]] = {
    ROLE_GOV: ("主頁", "2_map", "5_dispatch", "7_integration", "3_ai",
               "4_sentiment", "6_governance", "8_health"),
    ROLE_INSPECTOR: ("1_case", "3_ai", "4_sentiment"),
    ROLE_PARENT: (),  # 家長端已切離為獨立公眾查詢網，公務後台不提供家長頁
}


def get_role_navigation(role: str) -> list[str]:
    """回傳該角色可見的頁面 key 清單（第一層授權，供側欄導覽過濾）。

    key 對應 common.NAV 的 key 與 pages/ 檔名關鍵字（主頁/1_case/2_map/
    3_ai/4_sentiment/5_parent/6_governance）。未知/未登入角色回傳空清單
    （側欄不顯示任何導覽）。
    """
    return list(_ROLE_PAGES.get(role, ()))


# ===========================================================================
# 權限摘要：供 UI 與簡報引用
# ===========================================================================
def visible_data_categories(role: str) -> list[str]:
    """回傳該角色「可見（完整可見 或 部分可見）」的資料類別清單。"""
    result: list[str] = []
    for category, vis in DATA_PERMISSION_MATRIX.items():
        if vis.get(role, NONE) in (FULL, PARTIAL):
            result.append(category)
    return result


def get_role_permissions(role: str) -> dict[str, Any]:
    """回傳該角色的權限摘要（可見資料類別、可見頁面），供 UI 與簡報引用。

    回傳結構：
        {
          "role": <role>,
          "name": <中文名>,
          "emoji": <emoji>,
          "label": "<emoji> <中文名>",
          "visible_categories": [ ... 可見資料類別 ... ],
          "hidden_categories": [ ... 不可見資料類別 ... ],
          "navigation": [ ... 可見頁面 key ... ],
          "allowed_fields": { ... 允許欄位集合（家長為白名單；政府/稽查員為全欄位）},
          "full_access": bool,   # 是否全欄位可見（政府/稽查員 True）
        }
    """
    visible = visible_data_categories(role)
    hidden = [c for c in DATA_PERMISSION_MATRIX if c not in visible]
    return {
        "role": role,
        "name": role_name(role),
        "emoji": role_emoji(role),
        "label": role_label(role),
        "visible_categories": visible,
        "hidden_categories": hidden,
        "navigation": get_role_navigation(role),
        "allowed_fields": get_allowed_fields(role),
        "full_access": role in (ROLE_GOV, ROLE_INSPECTOR),
    }
