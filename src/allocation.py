"""
智慧稽查分派最佳化（Allocation Optimizer, R3）
================================================
小小守護員 Smart Watchdog Platform — 決策層分派最佳化子系統。

對應 design.md「Components and Interfaces / 10. Allocation_Optimizer」與
Data Models（AllocationItem / AllocationResult）。

本檔實作 Task 11.1 之核心：**風險覆蓋最大化**與**確定性 tie-break**，
並於 Task 11.2 擴充**限制過濾、輸出上限與邊界處理**（N 驗證、fewer_than_n、
無合格說明、已稽查排除、區域限制），落實需求：
  - R3.1：接受機構清單、稽查員人數 N、區域限制、已稽查清單與優先政策，
          輸出一組稽查機構集合。
  - R3.2：以「在所有限制條件下，使所選機構風險分數總和達到可行解中的最大值」
          為最佳化目標；風險覆蓋 = 所選機構風險分數之總和。
  - R3.3：多組風險分數總和相同的最佳解時，依（風險分數由高至低、風險分數
          相同時機構識別碼由小至大）順序選取，使相同輸入永遠產生相同輸出。
  - R3.4：將已稽查清單中的機構排除於本次輸出之外。
  - R3.5：設定區域限制時，輸出的每一機構皆滿足該區域限制。
  - R3.6：輸出機構數量不超過 N，且在限制下選取盡可能多但至多 N 間。
  - R3.7：合格機構數少於 N → 輸出全部合格機構並標示 fewer_than_n。
  - R3.8：無合格機構 → 回傳空集合並附說明無合格原因的訊息。
  - R3.9：N 非介於 1 至 1000 的整數 → 拒絕請求、不產生集合、回傳錯誤訊息。
  - R3.10：為每一入選機構提供含風險分數的可解釋分派理由。

設計原則（對齊 project-vision 白盒可解釋）：最佳化以規則與確定性排序完成，
無 AI 參與。目標函數為「所選機構風險分數之總和」，且選取基數上限為 N。
在此線性可加、無容量以外耦合限制的目標下，**貪婪選取風險分數最高的合格
機構**即為最佳解；相同風險分數時以機構識別碼（park_id）由小至大作為
確定性 tie-break，保證相同輸入永遠得到相同輸出。

擴充性（Task 11.2 後續）：本模組將限制過濾（區域限制、已稽查排除）、
N 驗證、輸出上限與邊界處理（合格 < N、無合格、N 無效）分離為可插拔的
輔助函式與資料結構（RegionFilter / Policy），使 Task 11.2 可在不改動核心
排序邏輯的前提下擴充。Task 11.1 聚焦 R3.1–R3.3 的核心排序與最大化語意。

責任 AI：分派僅為稽查資源建議排序，不代表任何違法認定
（見 design.md 責任 AI 原則）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from src.models import AllocationItem, AllocationResult

# N（稽查員人數）合法範圍（R3.9）。Task 11.1 定義常數供 Task 11.2 驗證使用。
MIN_INSPECTORS = 1
MAX_INSPECTORS = 1000


# --------------------------------------------------------------------------
# N 驗證（R3.9）
# --------------------------------------------------------------------------
def _invalid_n_message(n: Any) -> str:
    """產生 N 無效的錯誤訊息（R3.9）。內容明確指出 N 無效與合法範圍。"""
    return (
        f"稽查員人數 N 無效：需為介於 {MIN_INSPECTORS} 至 {MAX_INSPECTORS} 的整數，"
        f"但收到 {n!r}。已拒絕本次分派請求，未產生稽查集合。"
    )


def is_valid_n(n: Any) -> bool:
    """判定 N 是否為介於 MIN_INSPECTORS..MAX_INSPECTORS 的整數（R3.9）。

    嚴格語意：
      - 必須為 int 型別（排除 float，如 2.5 或 2.0）。
      - 明確排除 bool（Python 中 bool 為 int 子類，True/False 不應視為有效人數）。
      - 必須落於 [MIN_INSPECTORS, MAX_INSPECTORS] 閉區間內。
    """
    if isinstance(n, bool):
        return False
    if not isinstance(n, int):
        return False
    return MIN_INSPECTORS <= n <= MAX_INSPECTORS


# --------------------------------------------------------------------------
# 輸入資料結構（可擴充；Task 11.2 將擴充過濾語意）
# --------------------------------------------------------------------------
@dataclass
class Institution:
    """一間候選稽查機構。

    - park_id：機構識別碼，作為確定性 tie-break 的次要鍵（R3.3）。
    - risk_score：風險分數（0–100），為風險覆蓋最大化的目標值（R3.2）。
    - district：所屬行政區，供區域限制過濾（R3.5，Task 11.2 使用）。
    - attributes：其他屬性（保留擴充，供政策/區域限制引用）。

    Validates: Requirements 3.1
    """
    park_id: str
    risk_score: float
    district: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class RegionFilter:
    """區域限制（R3.5）。

    Task 11.1 僅定義結構並提供預設「不限制」行為；實際過濾語意與邊界
    （無合格機構等）由 Task 11.2 完整實作。

    - allowed_districts：允許的行政區集合；None 代表不限制區域。

    Validates: Requirements 3.1
    """
    allowed_districts: set[str] | None = None

    def allows(self, inst: Institution) -> bool:
        """判定機構是否滿足區域限制（無限制時恆為 True）。"""
        if self.allowed_districts is None:
            return True
        return inst.district in self.allowed_districts


@dataclass
class Policy:
    """優先政策（R3.1）。

    Task 11.1 以「風險分數總和最大化」為預設目標；policy 保留擴充點，
    未來可攜帶權重方案或優先規則。score_key 允許自政策取出用於排序/
    最大化的分數（預設即機構 risk_score）。

    Validates: Requirements 3.1
    """
    name: str = "risk_coverage_max"
    score_key: Callable[[Institution], float] | None = None

    def score_of(self, inst: Institution) -> float:
        """取得用於最大化與排序的分數（預設為機構 risk_score）。"""
        if self.score_key is not None:
            return self.score_key(inst)
        return inst.risk_score


# --------------------------------------------------------------------------
# 確定性排序（R3.3 tie-break）
# --------------------------------------------------------------------------
def _sort_key(inst: Institution, policy: Policy) -> tuple[float, str]:
    """確定性排序鍵：風險分數由高至低、相同時 park_id 由小至大（R3.3）。

    以 (-score, park_id) 作為鍵：Python 穩定升冪排序下，
    -score 較小者（即 score 較大者）在前；score 相同時 park_id 字典序小者在前。
    """
    return (-policy.score_of(inst), str(inst.park_id))


def deterministic_order(
    institutions: Iterable[Institution], policy: Policy | None = None
) -> list[Institution]:
    """回傳依 (風險分 desc, park_id asc) 排序的機構清單（R3.3）。

    相同輸入永遠回傳相同順序，為分派確定性的基礎。
    """
    pol = policy or Policy()
    return sorted(institutions, key=lambda x: _sort_key(x, pol))


def _no_eligible_message(
    institutions: list[Institution],
    region_filter: RegionFilter,
    inspected: set[str],
) -> str:
    """產生「無合格機構」說明訊息（R3.8）。

    依候選為空、全數已稽查、區域限制過濾殆盡等成因，給出可解釋的說明，
    協助使用者理解為何回傳空集合。
    """
    total = len(institutions)
    if total == 0:
        return "無符合條件之合格機構可供分派：候選機構清單為空。"

    excluded_inspected = sum(
        1 for inst in institutions if str(inst.park_id) in inspected
    )
    excluded_region = sum(
        1
        for inst in institutions
        if str(inst.park_id) not in inspected and not region_filter.allows(inst)
    )

    causes: list[str] = []
    if excluded_inspected:
        causes.append(f"已稽查排除 {excluded_inspected} 間（R3.4）")
    if excluded_region:
        causes.append(f"不符區域限制排除 {excluded_region} 間（R3.5）")
    cause_text = "；".join(causes) if causes else "所有候選機構均不符合限制條件"

    return (
        f"無符合條件之合格機構可供分派：候選共 {total} 間，"
        f"經限制過濾後無合格機構（{cause_text}）。"
    )


def _build_reason(inst: Institution, policy: Policy) -> str:
    """產生含風險分數的分派理由（R3.10）。

    註：R3.10（分派理由完整）之完整邊界由 Task 11.2 涵蓋；此處提供核心
    非空理由字串，內容包含機構風險分數，供 R3.1–R3.3 輸出使用。
    """
    score = policy.score_of(inst)
    return (
        f"入選稽查名單：機構 {inst.park_id} 風險分數 {score:g}，"
        f"依風險覆蓋最大化（風險分數總和最大）與確定性排序"
        f"（風險分數由高至低、相同時機構識別碼由小至大）入選。"
    )


# --------------------------------------------------------------------------
# 分派最佳化主函式（R3.1, R3.2, R3.3）
# --------------------------------------------------------------------------
def optimize(
    institutions: list[Institution],
    n: int,
    region_filter: RegionFilter | None = None,
    inspected: set[str] | None = None,
    policy: Policy | None = None,
) -> AllocationResult:
    """在限制下最大化所選機構風險分數總和，並以確定性順序選取（R3.1–R3.3）。

    目標（R3.2）：所選機構風險分數之總和達到可行解中的最大值。目標函數為
    線性可加且僅受選取基數上限 N 約束，故對「合格機構」依風險分數由高至低
    貪婪選取前 N 間即為最佳解——所選集合的風險分數總和不小於任何相同基數的
    其他合格選集。

    確定性（R3.3）：候選機構先以 (風險分數 desc, park_id asc) 排序，因此在
    多組風險分數總和相同的最佳解之間，永遠以相同順序選取，使相同輸入永遠
    產生相同輸出。

    參數：
      - institutions：候選機構清單。
      - n：稽查員人數（選取基數上限）。
      - region_filter：區域限制（R3.5）；預設不限制。
      - inspected：已稽查機構 park_id 集合（R3.4）；預設為空。
      - policy：優先政策（R3.1）；預設以 risk_score 最大化。

    邊界與限制處理（Task 11.2 完整實作）：
      - N 有效性驗證（R3.9）：N 非介於 1..1000 的整數（含 float、bool、
        None、超出範圍）→ 拒絕請求、不產生集合、回傳指出 N 無效的錯誤訊息。
      - 已稽查排除（R3.4）：inspected 中的機構不得出現於輸出。
      - 區域限制（R3.5）：輸出的每一機構皆須滿足 region_filter。
      - 輸出上限與盡量多（R3.6）：輸出數量 ≤ N，且在限制下盡可能多。
      - 合格 < N（R3.7）：輸出全部合格機構並標示 fewer_than_n=True。
      - 無合格（R3.8）：回傳空集合並附說明無合格原因的訊息。
      - 分派理由（R3.10）：每機構附含風險分數的可解釋理由。

    Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10
    """
    # 0) N 有效性驗證（R3.9）：先於任何過濾/選取，無效即拒絕且不產生集合。
    if not is_valid_n(n):
        return AllocationResult(
            selected=[],
            fewer_than_n=False,
            message=_invalid_n_message(n),
        )

    pol = policy or Policy()
    rf = region_filter or RegionFilter()
    already = inspected or set()

    # 1) 過濾出合格機構：排除已稽查（R3.4）、滿足區域限制（R3.5）。
    eligible = [
        inst
        for inst in institutions
        if str(inst.park_id) not in already and rf.allows(inst)
    ]

    # 2) 無合格機構（R3.8）：回傳空集合並附說明無合格原因的訊息。
    if not eligible:
        return AllocationResult(
            selected=[],
            fewer_than_n=False,
            message=_no_eligible_message(institutions, rf, already),
        )

    # 3) 確定性排序：風險分數由高至低、相同時 park_id 由小至大（R3.3）。
    ordered = deterministic_order(eligible, pol)

    # 4) 貪婪選取前 min(N, 合格數) 間 → 風險分數總和最大（R3.2, R3.6）。
    #    N 已驗證為 1..1000 的正整數，直接作為選取基數上限。
    chosen = ordered[:n]

    # 5) 產出含風險分數的分派理由（R3.10）。
    selected = [
        AllocationItem(
            park_id=str(inst.park_id),
            risk_score=pol.score_of(inst),
            reason=_build_reason(inst, pol),
        )
        for inst in chosen
    ]

    # 6) 合格機構數少於 N → 標示 fewer_than_n（R3.7）。
    fewer_than_n = len(eligible) < n
    message = None
    if fewer_than_n:
        message = (
            f"合格機構共 {len(eligible)} 間，少於請求的稽查員人數 N={n}，"
            f"已輸出全部合格機構。"
        )

    return AllocationResult(
        selected=selected,
        fewer_than_n=fewer_than_n,
        message=message,
    )
