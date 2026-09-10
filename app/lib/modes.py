"""
三模式路由與存取控制（User-Mode Routing & Access Control）
============================================================
小小守護員 Smart Watchdog Platform — 依使用者類型將已驗證使用者路由至
三種且僅三種決策模式之一：政府指揮中心（Gov_Console）、稽查員調查工作台
（Inspector_Workspace）、家長信任中心（Parent_Portal）。

未通過身分驗證，或使用者類型無法對應至三種模式之任一者，一律回傳「存取拒絕」
（access denied），且輸出**不揭露任何機構風險分數或風險等級資訊**。

本模組只負責「路由決策」與「功能集合定義」（R1.1, R1.6, R1.7），不含任何
Streamlit 呈現邏輯，亦不含分數計算。家長入口的欄位白名單投影 `public_view()`
由後續任務 18.2 於呈現層實作（R1.5, R6.6），本模組僅定義其模式歸屬。

責任 AI（Responsible AI）：風險（risk）不等於違法（illegality）。存取遭拒時
本模組保證輸出中不含任何足以還原機構風險分數或等級的欄位。

對應 design.md「使用者模式與存取控制（R1, R19）」章節與 Property 1/3/4。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


# ---------------------------------------------------------------------------
# 使用者類型與模式定義
# ---------------------------------------------------------------------------
class UserType(str, Enum):
    """已定義的使用者角色（對應 requirements Glossary）。

    其餘任何未列於此的類型，於路由時皆視為「無法對應」而遭拒。
    """
    GOV_USER = "gov_user"           # 政府管理者／決策者
    INSPECTOR = "inspector"          # 稽查員
    PARENT_USER = "parent_user"      # 家長／一般民眾


class Mode(str, Enum):
    """三種且僅三種使用者模式（R1.1）。

    DENIED 非「第四種模式」，而是「未進入任一模式」的存取拒絕結果（R1.7）。
    """
    GOV_CONSOLE = "Gov_Console"              # 政府指揮中心
    INSPECTOR_WORKSPACE = "Inspector_Workspace"  # 稽查員調查工作台
    PARENT_PORTAL = "Parent_Portal"          # 家長信任中心
    DENIED = "Access_Denied"                 # 存取拒絕（非模式）


#: 三種正式模式（不含 DENIED），供功能集合互斥性檢查與外部列舉使用。
VALID_MODES: tuple[Mode, ...] = (
    Mode.GOV_CONSOLE,
    Mode.INSPECTOR_WORKSPACE,
    Mode.PARENT_PORTAL,
)


# ---------------------------------------------------------------------------
# 使用者類型 → 模式的唯一對映（R1.1）
# ---------------------------------------------------------------------------
# 每一使用者類型恰對應一種模式；任一使用者在同一時間僅對應其中一種模式。
_USER_TYPE_TO_MODE: dict[UserType, Mode] = {
    UserType.GOV_USER: Mode.GOV_CONSOLE,
    UserType.INSPECTOR: Mode.INSPECTOR_WORKSPACE,
    UserType.PARENT_USER: Mode.PARENT_PORTAL,
}


# ---------------------------------------------------------------------------
# 三模式功能集合（互斥、不重疊，R1.6）
# ---------------------------------------------------------------------------
# 每一功能項目以穩定字串鍵表示，且恰屬於三種模式集合之一；任兩集合交集為空。
# 分派最佳化與 What-if 模擬屬「政府決策」職能 → Gov_Console。
# 單一機構深入調查、證據鏈、AI Copilot、HITL 回饋屬「稽查」職能 → Inspector_Workspace。
# 公開透明欄位查詢屬「家長」職能 → Parent_Portal。
_MODE_FEATURES: dict[Mode, frozenset[str]] = {
    Mode.GOV_CONSOLE: frozenset({
        "district_risk_overview",      # 全轄區風險總覽
        "high_risk_kpi_counts",        # 高/中/低/新增異常 KPI 計數
        "risk_map",                    # Leaflet 風險地圖
        "district_risk_ranking",       # 行政區風險排名
        "high_risk_institution_list",  # 高風險機構排名清單（前 20）
        "risk_trend_three_years",      # 近三年風險趨勢
        "risk_hotspots",               # 風險熱點
        "allocation_optimizer",        # 智慧稽查分派最佳化
        "whatif_simulation",           # What-if 情境模擬
        "operational_kpi_dashboard",   # 營運 KPI 儀表板
    }),
    Mode.INSPECTOR_WORKSPACE: frozenset({
        "single_institution_investigation",  # 單一機構深入調查檢視
        "risk_breakdown_radar",               # 風險分項雷達圖
        "risk_timeline",                      # 風險時間軸
        "category_analysis",                  # 財務/收費/營運/法規/NLP 分析
        "peer_comparison",                    # 同儕比較
        "anomaly_detection_view",             # 異常偵測結果
        "evidence_chain",                     # 證據鏈
        "feature_attribution",                # 前 5 特徵歸因
        "investigation_checklist",            # 調查檢核清單
        "ai_copilot",                         # AI 稽查助手
        "hitl_feedback",                      # 人在迴路審核回饋
    }),
    Mode.PARENT_PORTAL: frozenset({
        "public_institution_lookup",   # 機構公開資訊查詢
        "public_basic_info",           # 基本資訊/公私立別
        "public_tuition_info",         # 公開收費資訊
        "public_evaluation",           # 公開評鑑結果
        "public_penalty_record",       # 公開裁罰紀錄
        "public_source_freshness",     # 來源連結與時效標記
    }),
}


# ---------------------------------------------------------------------------
# 路由結果
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RoutingDecision:
    """單次路由決策結果（R1.1, R1.7）。

    - authorized 為 True 時 mode ∈ VALID_MODES 且 features 為該模式功能集合。
    - authorized 為 False 時 mode == Mode.DENIED、features 為空、且附拒絕提示訊息。

    不變式（責任 AI，R1.7）：本物件不含任何機構風險分數或等級欄位；
    存取遭拒時 features 為空集合，不揭露任何模式功能或資料。

    Validates: Requirements 1.1, 1.6, 1.7
    """
    mode: Mode
    authorized: bool
    features: frozenset[str] = field(default_factory=frozenset)
    message: str | None = None


# 存取遭拒時對使用者顯示的固定提示（不含任何分數/等級/機構資料）。
ACCESS_DENIED_MESSAGE = (
    "存取遭拒：您的身分未通過驗證或無法對應任一使用者模式，"
    "無法進入政府指揮中心、稽查員調查工作台或家長信任中心。"
)


# ---------------------------------------------------------------------------
# 型別正規化
# ---------------------------------------------------------------------------
def _coerce_user_type(user_type: object) -> UserType | None:
    """將輸入正規化為已知 UserType，無法對應時回傳 None。

    接受 UserType 實例或其字串值（大小寫與前後空白不敏感）。
    任何其他輸入（None、未知字串、其他型別）皆視為無法對應。
    """
    if isinstance(user_type, UserType):
        return user_type
    if isinstance(user_type, str):
        key = user_type.strip().lower()
        for member in UserType:
            if member.value == key:
                return member
    return None


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------
def features_for(mode: Mode) -> frozenset[str]:
    """回傳指定模式的功能集合；DENIED 或未知模式回傳空集合。"""
    return _MODE_FEATURES.get(mode, frozenset())


def resolve_mode(user_type: object, *, authenticated: bool = True) -> RoutingDecision:
    """依使用者類型與驗證狀態解析其對應模式（核心路由，R1.1, R1.7）。

    參數
    ----
    user_type:
        使用者類型，接受 `UserType` 或其字串值。
    authenticated:
        是否已通過身分驗證。False 代表未驗證。

    回傳
    ----
    RoutingDecision:
        - 已驗證且類型可對應 → authorized=True，mode 為三模式之一，
          features 為該模式功能集合。
        - 未驗證，或類型無法對應 → authorized=False，mode=Mode.DENIED，
          features 為空，message 為存取遭拒提示，且不含任何分數/等級資訊（R1.7）。

    Validates: Requirements 1.1, 1.7
    """
    if not authenticated:
        return _denied()

    coerced = _coerce_user_type(user_type)
    if coerced is None:
        return _denied()

    mode = _USER_TYPE_TO_MODE.get(coerced)
    if mode is None or mode not in VALID_MODES:
        return _denied()

    return RoutingDecision(
        mode=mode,
        authorized=True,
        features=features_for(mode),
        message=None,
    )


def _denied() -> RoutingDecision:
    """建構存取拒絕結果：不揭露任何模式功能、分數或等級（R1.7）。"""
    return RoutingDecision(
        mode=Mode.DENIED,
        authorized=False,
        features=frozenset(),
        message=ACCESS_DENIED_MESSAGE,
    )


def all_features() -> frozenset[str]:
    """三模式全部功能項目的聯集（供互斥性檢查與導覽建構）。"""
    result: frozenset[str] = frozenset()
    for feats in _MODE_FEATURES.values():
        result |= feats
    return result


def feature_mode(feature: str) -> Mode | None:
    """回傳某功能項目所屬的唯一模式；不屬任一模式時回傳 None（R1.6）。"""
    for mode, feats in _MODE_FEATURES.items():
        if feature in feats:
            return mode
    return None


def assert_features_disjoint() -> None:
    """驗證三模式功能集合兩兩互斥且不重疊（R1.6）。

    功能集合為模組內常數，此檢查於匯入時自動執行，確保任一功能項目恰屬
    三模式其中之一，不得同時出現於兩種以上模式。若違反則於匯入期即失敗，
    避免錯誤設定流入執行期。

    Validates: Requirements 1.6
    """
    modes = list(_MODE_FEATURES)
    for i in range(len(modes)):
        for j in range(i + 1, len(modes)):
            overlap = _MODE_FEATURES[modes[i]] & _MODE_FEATURES[modes[j]]
            if overlap:
                raise ValueError(
                    f"功能集合互斥性違反：{modes[i].value} 與 {modes[j].value} "
                    f"重疊於 {sorted(overlap)}"
                )
    # 聯集大小應等於各集合大小總和（無重複）。
    total = sum(len(f) for f in _MODE_FEATURES.values())
    if len(all_features()) != total:
        raise ValueError("功能集合互斥性違反：存在跨模式重複功能項目")


# ---------------------------------------------------------------------------
# 家長入口欄位白名單投影（public_view，R1.5, R6.6）
# ---------------------------------------------------------------------------
# 家長信任中心僅得呈現「公開透明欄位」；任何內部風險分數、風險等級或其衍生排序
# 皆不得外洩，且不得留下任何足以還原上述值的欄位（Property 2）。
#
# 設計採「白名單投影 + 黑名單防禦」雙保險：
#   1) 先以白名單挑出允許欄位（PUBLIC_WHITELIST_FIELDS）；
#   2) 再以黑名單規則（_is_forbidden_key）過濾，確保即便白名單欄位命名疏漏、
#      或上游資料混入分數/排序欄位，亦不會滲漏。
# 黑名單優先於白名單：同時命中時一律移除（責任 AI，寧可少給不可外洩）。

#: 家長入口允許呈現的公開透明欄位白名單（對應 PublicInstitutionView 與 R6.1/6.2/6.4）。
#: 僅含機構識別與公開事實欄位；不含任何分數/等級/排序衍生欄位。
PUBLIC_WHITELIST_FIELDS: frozenset[str] = frozenset({
    "park_id",           # 機構識別碼（非分數衍生）
    "park_name",         # 機構名稱
    "ownership",         # 公私立別
    "address",           # 地址
    "district",          # 行政區
    "tuition_info",      # 公開收費資訊
    "public_eval",       # 公開評鑑結果
    "public_penalty",    # 公開裁罰紀錄
    "field_sources",     # 每欄位官方來源與最後更新時間（R6.2）
    "stale_flags",       # 每欄位是否可能過時（>365 天，R6.4）
})

#: 明確禁止的欄位鍵（精確比對，經正規化後）。涵蓋總分、等級與其絕對值變體。
_FORBIDDEN_EXACT_KEYS: frozenset[str] = frozenset({
    "risk_total",
    "risk_level",
    "risk_level_abs",
    "risk_score",
    "risk_rank",
    "risk_percentile",
    "rank",
    "ranking",
    "percentile",
    "priority",
    "priority_rank",
    "order",
    "sort_key",
    "sort_order",
})

#: 禁止欄位的樣式（子字串/前綴），用於捕捉 score_*、risk_* 與各種衍生排序欄位。
#: 經正規化（小寫、去空白）後比對。
_FORBIDDEN_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^score_"),        # 所有 score_* 分項
    re.compile(r"_score$"),        # 任何以 _score 結尾（如 financial_score）
    re.compile(r"^score$"),        # 單獨 score
    re.compile(r"^risk_"),         # 所有 risk_* 內部風險欄位
    re.compile(r"_risk$"),         # 任何以 _risk 結尾
    re.compile(r"rank"),           # 排名/排序衍生（rank, ranking, risk_rank...）
    re.compile(r"percentile"),     # 百分位（相對分級衍生，R10.6）
)


def _normalize_key(key: object) -> str:
    """將欄位鍵正規化為小寫、去前後空白的字串，供黑名單比對。"""
    return str(key).strip().lower()


def _is_forbidden_key(key: object) -> bool:
    """判定某欄位鍵是否為禁止外洩之分數/等級/衍生排序欄位（黑名單）。

    禁止條件（任一成立即為 True）：
      - 正規化後精確命中 `_FORBIDDEN_EXACT_KEYS`；或
      - 正規化後符合 `_FORBIDDEN_PATTERNS` 任一樣式（score_*、risk_*、rank、percentile 等）。
    """
    norm = _normalize_key(key)
    if norm in _FORBIDDEN_EXACT_KEYS:
        return True
    return any(pat.search(norm) for pat in _FORBIDDEN_PATTERNS)


def public_view(record: Mapping[str, Any] | Any) -> dict[str, Any]:
    """家長入口欄位白名單投影（R1.5, R6.6）。

    將單筆機構紀錄投影為僅含公開透明欄位的字典，移除 `risk_total`、`risk_level`、
    `risk_level_abs`、所有 `score_*` 欄位及其衍生排序欄位（rank/percentile 等），
    確保家長入口無法呈現或還原任何內部風險分數與等級。

    參數
    ----
    record:
        單筆機構紀錄。可為 dict（欄位鍵值對）或具 `__dict__` 的物件
        （如 dataclass 實例），後者以其屬性作為欄位來源。

    回傳
    ----
    dict[str, Any]:
        僅含白名單且未命中黑名單之欄位。輸出保證不含任何 `risk_total`、
        `risk_level`、`risk_level_abs`、`score_*` 或衍生排序欄位（Property 2）。

    設計不變式（責任 AI，R1.7/R6.6）：黑名單優先於白名單——凡命中禁止規則之
    欄位一律移除，即使其名稱誤列於白名單亦然，避免任何分數/等級外洩。

    Validates: Requirements 1.5, 6.6
    """
    items = _record_items(record)
    projected: dict[str, Any] = {}
    for key, value in items:
        # 黑名單優先：禁止欄位無論是否在白名單內，一律排除。
        if _is_forbidden_key(key):
            continue
        norm = _normalize_key(key)
        if norm in _WHITELIST_NORMALIZED:
            projected[str(key)] = value
    return projected


#: 白名單的正規化形式，供 public_view 以正規化鍵比對（大小寫/空白不敏感）。
_WHITELIST_NORMALIZED: frozenset[str] = frozenset(
    _normalize_key(f) for f in PUBLIC_WHITELIST_FIELDS
)


def _record_items(record: Mapping[str, Any] | Any) -> list[tuple[str, Any]]:
    """由 dict 或物件擷取欄位鍵值對，供 public_view 投影使用。

    - Mapping（如 dict）：直接取其 items。
    - 其他物件（如 dataclass 實例）：取其 `__dict__`。
    - 無法擷取欄位者：回傳空清單（投影結果為空字典，等同「無公開欄位」）。
    """
    if isinstance(record, Mapping):
        return list(record.items())
    data = getattr(record, "__dict__", None)
    if isinstance(data, Mapping):
        return list(data.items())
    return []


# 匯入時即驗證功能集合互斥性，讓錯誤設定盡早暴露（fail fast）。
assert_features_disjoint()
