"""
共用資料模型（Shared Data Models）
=====================================
小小守護員 Smart Watchdog Platform — 各子系統共用的 dataclass 型別。

本模組僅定義「資料契約」（型別與欄位），不含業務邏輯，供風險引擎、
決策層、AI 層、三種使用者介面與治理子系統共同引用，確保跨模組資料形狀一致。

對應 design.md「Data Models」章節。所有型別以標準函式庫 dataclasses 定義，
不引入額外執行期相依，維持既有基線的可攜性。

責任 AI（Responsible AI）：風險（risk）不等於違法（illegality）。本模組中
`RiskBreakdown.not_illegality_notice` 等欄位落實此原則。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


# --------------------------------------------------------------------------
# 來源追溯（Evidence / Source）
# --------------------------------------------------------------------------
@dataclass
class SourceRef:
    """官方來源追溯（供證據鏈與家長入口欄位來源標示）。

    Validates: Requirements 11.4, 6.2, 16.1
    """
    dataset: str                       # 資料集名稱
    authority: str                     # 主管機關
    url: str | None = None             # 來源連結（可為 None）
    last_updated: date | None = None   # 該來源最後更新時間（供時效判定 R6.4）


# --------------------------------------------------------------------------
# 鑑識會計指標（Forensic Metrics, R7）
# --------------------------------------------------------------------------
@dataclass
class Metric:
    """單一鑑識指標。

    - value：小數點後 4 位；不可計算（分母 0/缺值）時為 None。
    - formula：非空的明確公式定義字串（R7.9）。
    - computable：分母為 0 或缺值時為 False（R7.11）。

    Validates: Requirements 7.1, 7.9, 7.11
    """
    name: str
    value: float | None
    formula: str
    computable: bool = True


@dataclass
class ForensicMetrics:
    """一間機構於某年度的鑑識會計指標集合（R7）。

    Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.10
    """
    income_growth: Metric              # 收入成長率
    expense_growth: Metric             # 支出成長率
    personnel_ratio: Metric            # 人事費 / 總支出
    operating_ratio: Metric            # 業務費 / 總支出
    income_per_child: Metric           # 每名幼兒收入
    expense_per_child: Metric          # 每名幼兒支出
    # 支出結構占比：人事/業務/其他，合計介於 0.99–1.01（R7.3）
    expense_structure: dict[str, float] = field(default_factory=dict)
    # 保留既有四層方法輸出（R7.10）
    benford_mad: float | None = None
    benford_chi2: float | None = None
    beneish_score: float = 0.0
    iforest_score: float | None = None


# --------------------------------------------------------------------------
# 異常偵測（Anomaly Detection, R8）
# --------------------------------------------------------------------------
@dataclass
class AnomalyMethodResult:
    """單一偵測方法的結果。

    - flag 為真 若且唯若 score 達到 threshold（R8.1, R8.2）。
    - applicable 為 False 代表樣本不足，該方法被跳過（R8.5）。

    Validates: Requirements 8.1, 8.2, 8.3, 8.5
    """
    method: str
    score: float
    flag: bool
    threshold: float = 0.0
    applicable: bool = True
    # 方法適用性說明：適用異常類型、資料前提、已知限制（R8.3）
    note: dict[str, str] = field(default_factory=dict)


@dataclass
class MethodNote:
    """單一偵測方法的適用性說明（R8.3）。

    至少涵蓋：適用的異常類型、資料前提（假設）與已知限制。
    - anomaly_type：point / contextual / collective。
    - assumption：資料前提（如樣本數下限、分布假設）。
    - limitation：已知限制（方法失效或不可靠的情境）。

    Validates: Requirements 8.3
    """
    method: str
    anomaly_type: str
    assumption: str
    limitation: str


@dataclass
class ConsolidatedAnomaly:
    """多方法一致性整合結果（R8.4）。

    - confidence_label：≥2 種獨立方法命中 → 'high_confidence'；
      單一方法命中 → 'to_confirm'；無方法命中 → 'none'。
    - hit_count：命中（flag=True 且 applicable）的方法數。
    - hit_methods：命中的方法名稱清單（供追溯記錄）。

    Validates: Requirements 8.4
    """
    confidence_label: str                              # 'high_confidence' | 'to_confirm' | 'none'
    hit_count: int = 0
    hit_methods: list[str] = field(default_factory=list)


@dataclass
class AnomalyResult:
    """一間機構的整合異常偵測結果（R8）。

    - point/contextual/collective 各為 (bool flag, score)（R8.1）。
    - confidence_label：≥2 方法命中 → 'high_confidence'；單一 → 'to_confirm'（R8.4）。

    Validates: Requirements 8.1, 8.4
    """
    point: tuple[bool, float]
    contextual: tuple[bool, float]
    collective: tuple[bool, float]
    methods: list[AnomalyMethodResult] = field(default_factory=list)
    confidence_label: str = "to_confirm"   # 'high_confidence' | 'to_confirm'
    method_hit_count: int = 0


# --------------------------------------------------------------------------
# 白盒風險評分（Risk Scoring, R10）
# --------------------------------------------------------------------------
@dataclass
class RiskBreakdown:
    """0–100 白盒風險分數與其可解釋分解（R10, R5.2）。

    不變式：round(sum(contributions.values()), 1) == total（R5.2, R10.3）。
    責任 AI：not_illegality_notice 為非空「風險不等於違法」聲明（R10.4, R19.4）。

    Validates: Requirements 10.1, 10.3, 10.4, 18.3, 19.4
    """
    total: float                                       # 0–100
    level: str                                         # 低/中/高/極高(critical)
    contributions: dict[str, float] = field(default_factory=dict)  # 各分項貢獻
    weights: dict[str, float] = field(default_factory=dict)        # 顯示用權重
    not_illegality_notice: str = "風險不等於違法（Risk does not equal illegality）。"
    data_confidence: float = 100.0                     # 對應資料可信度（R18.3）


# --------------------------------------------------------------------------
# 證據鏈（Evidence Chain, R11）
# --------------------------------------------------------------------------
@dataclass
class EvidenceLink:
    """證據鏈單一環節：結論 → 特徵 → 原始資料值 → 官方來源（R11）。

    Validates: Requirements 11.1, 11.2, 11.3, 11.4
    """
    conclusion: str                    # AI/風險結論
    feature: str                       # 特徵歸因
    raw_value: float | str             # 原始資料值
    source: SourceRef                  # 官方來源


# --------------------------------------------------------------------------
# 分派最佳化（Allocation Optimization, R3）
# --------------------------------------------------------------------------
@dataclass
class AllocationItem:
    """一筆分派結果（一間入選機構）。

    reason 為非空分派理由且內容包含 risk_score（R3.10）。

    Validates: Requirements 3.1, 3.10
    """
    park_id: str
    risk_score: float
    reason: str


@dataclass
class AllocationResult:
    """分派最佳化輸出（R3）。

    - selected：至多 N 間，依確定性順序（R3.3, R3.6）。
    - fewer_than_n：合格機構數少於 N 時為 True（R3.7）。
    - message：無合格機構或 N 無效時的說明（R3.8, R3.9）。

    Validates: Requirements 3.6, 3.7, 3.8, 3.9
    """
    selected: list[AllocationItem] = field(default_factory=list)
    fewer_than_n: bool = False
    message: str | None = None


# --------------------------------------------------------------------------
# What-if 情境模擬（Simulation, R4）
# --------------------------------------------------------------------------
@dataclass
class SimParams:
    """模擬參數（R4）。

    - quota：介於 1–999 的配額（R4.1）。
    - weight_scheme：需在允許清單內（R4.2）。
    - exclude_recent_inspected：排除近 12 個月已稽查（R4.3）。

    Validates: Requirements 4.1, 4.2, 4.3
    """
    quota: int
    weight_scheme: str
    exclude_recent_inspected: bool = False


# --------------------------------------------------------------------------
# 家長信任中心公開檢視（Parent Portal, R6）
# --------------------------------------------------------------------------
@dataclass
class PublicInstitutionView:
    """家長入口欄位白名單投影（R6）。

    僅含公開透明欄位，不含 risk_total/risk_level/score_* 與其衍生排序（R6.6, R1.5）。

    Validates: Requirements 6.1, 6.2, 6.4, 6.6
    """
    park_name: str
    ownership: str                                     # 公私立別
    tuition_info: dict | None = None
    public_eval: str | None = None
    public_penalty: list | None = None
    # 每欄位對應官方來源與最後更新時間（R6.2）
    field_sources: dict[str, SourceRef] = field(default_factory=dict)
    # 每欄位是否「資料可能過時」（>365 天，R6.4）
    stale_flags: dict[str, bool] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 治理：稽核軌跡與人在迴路回饋（Governance, R20, R21）
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditEntry:
    """稽核軌跡紀錄（append-only，不可竄改）（R21）。

    以 frozen=True 落實「單筆紀錄不可竄改」的語意（R21.2）。

    Validates: Requirements 21.1, 21.2
    """
    actor: str
    action: str
    target: str
    ts: datetime


@dataclass
class HITLFeedback:
    """人在迴路（Human-in-the-loop）審核回饋（R20）。

    label 取自：確為異常 / 誤報 / 資料問題 / 需進一步稽查（R20.1）。

    Validates: Requirements 20.1, 20.2
    """
    entity_id: str
    verdict_ref: str
    label: str


# --------------------------------------------------------------------------
# 資料可信度（Data Confidence, R18）
# --------------------------------------------------------------------------
@dataclass
class DataConfidence:
    """單一機構或資料紀錄的資料可信度分數（0–100）（R18）。

    Validates: Requirements 18.1
    """
    entity_id: str
    score: float                                       # 0–100
    factors: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------
# 財務原始物件（Financial Record，解析器產物, R17）
# --------------------------------------------------------------------------
@dataclass
class FinancialRecord:
    """財務原始物件（公校決算 / 非營利園財報解析產物）（R17）。

    detail_amounts 為逐筆明細金額（班佛定律用）。source_ref 供官方來源追溯。

    Validates: Requirements 17.1
    """
    park_id: str
    park_name: str
    year: int                          # 112/113/114
    income_actual: float | None = None
    expense_actual: float | None = None
    tuition_actual: float | None = None
    surplus: float | None = None
    income_last_year: float | None = None
    expense_last_year: float | None = None
    enrollment: int | None = None      # 招生人數
    detail_amounts: list[int] = field(default_factory=list)
    source_ref: SourceRef | None = None
