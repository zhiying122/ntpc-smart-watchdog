"""
What-if 情境模擬（Simulation Engine, R4）
==========================================
小小守護員 Smart Watchdog Platform — 決策層 What-if 情境模擬子系統。

對應 design.md「Components and Interfaces / 11. Simulation_Engine」與
Correctness Properties（Property 14/15/16）。

本檔實作 Task 12.1 之核心：**依配額/權重方案/排除近12月已稽查重排序**，
並保證**不覆寫基準風險分數**與**無效參數被拒絕且不變更既有顯示**，落實需求：
  - R4.1：Gov_User 將稽查配額變更為介於 1–999 的指定值 → 依新配額重新
          產生稽查優先序清單（改變輸出筆數）。
  - R4.2：Gov_User 選擇權重方案（如純財務、費用優先）→ 依所選權重重新
          計算並重新排序機構。
  - R4.3：Gov_User 選擇排除近期已稽查機構 → 從結果中移除近 12 個月內已
          稽查的機構後重新排序。
  - R4.4：模擬結果不覆寫系統的基準風險分數（模擬為唯讀衍生，不回寫）。
  - R4.6：模擬參數無效（配額非 1–999 整數、權重方案不在允許清單內）→ 拒絕
          該次模擬並回傳指出參數無效的訊息，且不變更既有顯示結果。

設計原則（對齊 project-vision 白盒可解釋）：模擬僅以規則與確定性排序完成，
無 AI 參與。權重方案為明確、可攤開的分項權重字典；重排序分數由基準分項
（financial / penalty / eval）依所選權重線性組合而得，與基準總分脫鉤，
確保「模擬不覆寫基準」（R4.4）。

**基準保護（R4.4）核心保證**：`simulate` 絕不修改傳入的 `base`（或其任何
機構項目）的既有欄位；重排序後的模擬分數輸出於全新的 `SimulationResult`
物件中（`sim_score` / `rank`），基準的 `risk_total` 等欄位維持原值不變。

責任 AI：模擬僅為稽查資源之情境推演與排序建議，不代表任何違法認定
（見 design.md 責任 AI 原則）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from src.models import SimParams

# --------------------------------------------------------------------------
# 配額（quota）合法範圍（R4.1, R4.6）。
# --------------------------------------------------------------------------
MIN_QUOTA = 1
MAX_QUOTA = 999

# 「近期已稽查」的時間窗（近 12 個月）（R4.3）。以 365 天近似 12 個月。
RECENT_INSPECTED_DAYS = 365


# --------------------------------------------------------------------------
# 允許的權重方案（R4.2, R4.6）
# --------------------------------------------------------------------------
# 分項與 src/risk_score.py 的 WEIGHTS 對齊（financial / penalty / eval），
# 確保模擬重排序建立於既有白盒分項之上。每一方案為可攤開、可對評審解釋的
# 明確權重字典（合計為 1.0）。
#
#   - "balanced"（預設，均衡）：延續基線 50/34/16。
#   - "financial_only"（純財務）：僅看財務異常分項。
#   - "penalty_priority"（裁罰優先 / 費用優先）：拉高裁罰權重。
#   - "eval_priority"（評鑑優先）：拉高評鑑權重。
ALLOWED_WEIGHT_SCHEMES: dict[str, dict[str, float]] = {
    "balanced": {"financial": 0.50, "penalty": 0.34, "eval": 0.16},
    "financial_only": {"financial": 1.00, "penalty": 0.00, "eval": 0.00},
    "penalty_priority": {"financial": 0.20, "penalty": 0.70, "eval": 0.10},
    "eval_priority": {"financial": 0.20, "penalty": 0.10, "eval": 0.70},
}

# 用於線性組合的基準分項欄位名稱（讀自各機構項目，不修改）。
_COMPONENT_FIELDS = ("financial", "penalty", "eval")


# --------------------------------------------------------------------------
# 輸入資料結構
# --------------------------------------------------------------------------
@dataclass
class BaselineInstitution:
    """基準資料集中的一間機構（模擬輸入）。

    - park_id：機構識別碼，作為確定性 tie-break 的次要鍵。
    - risk_total：基準風險總分（0–100）；模擬**不得覆寫**此值（R4.4）。
    - components：基準分項分數（financial / penalty / eval，各 0–100），
      供依權重方案重新線性組合出模擬分數（R4.2）。
    - last_inspected：最近一次稽查日期；供排除近 12 個月已稽查（R4.3）。
    - attributes：其他屬性（保留擴充）。

    Validates: Requirements 4.1, 4.2, 4.3, 4.4
    """
    park_id: str
    risk_total: float
    components: dict[str, float] = field(default_factory=dict)
    last_inspected: date | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


# `base` 為基準資料集：一組基準機構。以獨立型別別名表達語意（RiskDataset）。
RiskDataset = list[BaselineInstitution]


# --------------------------------------------------------------------------
# 輸出資料結構（新型別，本檔定義）
# --------------------------------------------------------------------------
@dataclass
class SimRankItem:
    """模擬重排序後的一筆結果。

    - park_id：機構識別碼。
    - sim_score：依所選權重方案重新計算的模擬分數（0–100），與基準總分脫鉤。
    - rank：於模擬清單中的名次（1 起算）。
    - reason：含模擬分數與權重方案的可解釋理由。

    Validates: Requirements 4.1, 4.2
    """
    park_id: str
    sim_score: float
    rank: int
    reason: str


@dataclass
class SimulationResult:
    """What-if 情境模擬輸出（R4）。

    - ranked：依模擬分數重排序、至多 quota 筆的結果（R4.1, R4.2）。
    - rejected：參數無效時為 True，此時 ranked 為空且 base 不受影響（R4.6）。
    - message：說明訊息（拒絕原因，或排除/截斷等資訊）。
    - weight_scheme：本次採用的權重方案名稱（供追溯/顯示）。
    - excluded_recent_count：因近 12 個月已稽查而排除的機構數（R4.3）。

    Validates: Requirements 4.1, 4.2, 4.3, 4.6
    """
    ranked: list[SimRankItem] = field(default_factory=list)
    rejected: bool = False
    message: str | None = None
    weight_scheme: str | None = None
    excluded_recent_count: int = 0


# --------------------------------------------------------------------------
# 參數驗證（R4.6）
# --------------------------------------------------------------------------
def is_valid_quota(quota: Any) -> bool:
    """判定配額是否為介於 MIN_QUOTA..MAX_QUOTA 的整數（R4.1, R4.6）。

    嚴格語意：
      - 必須為 int 型別（排除 float，如 5.0）。
      - 明確排除 bool（Python 中 bool 為 int 子類，True/False 不應視為配額）。
      - 必須落於 [MIN_QUOTA, MAX_QUOTA] 閉區間內。
    """
    if isinstance(quota, bool):
        return False
    if not isinstance(quota, int):
        return False
    return MIN_QUOTA <= quota <= MAX_QUOTA


def is_valid_weight_scheme(scheme: Any) -> bool:
    """判定權重方案是否在允許清單內（R4.2, R4.6）。"""
    return isinstance(scheme, str) and scheme in ALLOWED_WEIGHT_SCHEMES


def _rejection_message(params: SimParams) -> str:
    """產生參數無效的拒絕訊息（R4.6）。內容明確指出何者無效與允許範圍。"""
    problems: list[str] = []
    if not is_valid_quota(params.quota):
        problems.append(
            f"配額 quota 無效：需為介於 {MIN_QUOTA} 至 {MAX_QUOTA} 的整數，"
            f"但收到 {params.quota!r}"
        )
    if not is_valid_weight_scheme(params.weight_scheme):
        allowed = "、".join(sorted(ALLOWED_WEIGHT_SCHEMES))
        problems.append(
            f"權重方案 weight_scheme 無效：需為允許清單之一（{allowed}），"
            f"但收到 {params.weight_scheme!r}"
        )
    detail = "；".join(problems)
    return f"模擬參數無效，已拒絕本次模擬且不變更既有顯示結果（R4.6）。{detail}。"


# --------------------------------------------------------------------------
# 分數重算與排序
# --------------------------------------------------------------------------
def _component_value(inst: BaselineInstitution, key: str) -> float:
    """安全取出基準分項值（缺值以 0 中性處理），不修改機構物件。"""
    val = inst.components.get(key)
    if val is None:
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def _sim_score(inst: BaselineInstitution, weights: dict[str, float]) -> float:
    """依所選權重方案將基準分項線性組合為模擬分數（0–100）（R4.2）。

    模擬分數與基準總分（risk_total）脫鉤，僅由分項與權重決定，
    因此重排序不需、也不會改動基準分數（R4.4）。
    """
    total = sum(weights.get(k, 0.0) * _component_value(inst, k)
                for k in _COMPONENT_FIELDS)
    # 夾在 0–100，並四捨五入至小數點後 1 位（與白盒分數輸出精度一致）。
    return round(max(0.0, min(100.0, total)), 1)


def _is_recently_inspected(inst: BaselineInstitution, now: date) -> bool:
    """判定機構是否於近 12 個月內已稽查（R4.3）。無稽查日期則否。"""
    if inst.last_inspected is None:
        return False
    cutoff = now - timedelta(days=RECENT_INSPECTED_DAYS)
    return inst.last_inspected >= cutoff


def _sort_key(item: tuple[BaselineInstitution, float]) -> tuple[float, str]:
    """確定性排序鍵：模擬分數由高至低、相同時 park_id 由小至大。

    以 (-sim_score, park_id) 作為鍵，保證相同輸入永遠得到相同順序。
    """
    inst, sim = item
    return (-sim, str(inst.park_id))


def _build_reason(sim: float, scheme: str) -> str:
    """產生含模擬分數與權重方案的可解釋理由。"""
    return (
        f"模擬重排序：依權重方案「{scheme}」重新計算模擬分數 {sim:g}，"
        f"依模擬分數由高至低、相同時機構識別碼由小至大確定性排序。"
        f"（此為情境推演，不覆寫基準風險分數）"
    )


# --------------------------------------------------------------------------
# 模擬主函式（R4.1, R4.2, R4.3, R4.4, R4.6）
# --------------------------------------------------------------------------
def simulate(
    base: RiskDataset,
    params: SimParams,
    now: date | None = None,
) -> SimulationResult:
    """依配額/權重方案/排除近12月已稽查重排序；不覆寫基準分數（R4.1–R4.6）。

    行為：
      - 參數驗證（R4.6）：配額非 1–999 整數或權重方案不在允許清單 → 拒絕，
        回傳 rejected=True 與說明訊息，且**不變更既有顯示**（不修改 base）。
      - 權重方案（R4.2）：以所選方案將基準分項線性組合為模擬分數並重排序。
      - 排除近期已稽查（R4.3）：exclude_recent_inspected=True 時，移除近 12
        個月（RECENT_INSPECTED_DAYS 天）內已稽查的機構後重排序。
      - 配額（R4.1）：輸出至多 quota 筆（改變配額即改變輸出筆數）。
      - 基準保護（R4.4）：全程唯讀 base，模擬分數輸出於全新結果物件，
        基準風險分數維持不變。

    參數：
      - base：基準資料集（一組 BaselineInstitution）。
      - params：模擬參數（quota / weight_scheme / exclude_recent_inspected）。
      - now：判定「近 12 個月」的參考日期；預設為今日（供測試注入）。

    Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.6
    """
    # 0) 參數驗證（R4.6）：無效即拒絕，不修改 base、不產生排序結果。
    if not is_valid_quota(params.quota) or not is_valid_weight_scheme(
        params.weight_scheme
    ):
        return SimulationResult(
            ranked=[],
            rejected=True,
            message=_rejection_message(params),
            weight_scheme=None,
            excluded_recent_count=0,
        )

    ref_now = now or date.today()
    weights = ALLOWED_WEIGHT_SCHEMES[params.weight_scheme]

    # 1) 排除近 12 個月已稽查（R4.3）。全程唯讀，不修改任何機構物件。
    excluded_recent_count = 0
    candidates: list[BaselineInstitution] = []
    for inst in base:
        if params.exclude_recent_inspected and _is_recently_inspected(inst, ref_now):
            excluded_recent_count += 1
            continue
        candidates.append(inst)

    # 2) 依權重方案重算模擬分數（R4.2）。模擬分數為衍生值，與基準總分脫鉤。
    scored = [(inst, _sim_score(inst, weights)) for inst in candidates]

    # 3) 確定性排序：模擬分數由高至低、相同時 park_id 由小至大。
    scored.sort(key=_sort_key)

    # 4) 依配額截斷輸出至多 quota 筆（R4.1）。
    chosen = scored[: params.quota]

    ranked = [
        SimRankItem(
            park_id=str(inst.park_id),
            sim_score=sim,
            rank=i + 1,
            reason=_build_reason(sim, params.weight_scheme),
        )
        for i, (inst, sim) in enumerate(chosen)
    ]

    # 5) 組裝說明訊息（非拒絕情境下的資訊性訊息）。
    parts: list[str] = [
        f"權重方案「{params.weight_scheme}」，配額 {params.quota}，"
        f"輸出 {len(ranked)} 筆。"
    ]
    if params.exclude_recent_inspected:
        parts.append(f"已排除近 12 個月已稽查機構 {excluded_recent_count} 間。")
    message = "".join(parts)

    return SimulationResult(
        ranked=ranked,
        rejected=False,
        message=message,
        weight_scheme=params.weight_scheme,
        excluded_recent_count=excluded_recent_count,
    )
