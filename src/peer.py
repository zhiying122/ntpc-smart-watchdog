"""
同儕群組與同儕統計量（Peer Group & Peer Comparison, R13）
==========================================================
小小守護員 Smart Watchdog Platform — 同儕比較子系統。

對應 design.md「Components and Interfaces / 4. Peer_Group」與 Data Models，
落實需求 R13：
  - R13.1：依機構類型（park_type）、規模（size_band）、區域（district）劃分同儕群組。
  - R13.2：計算機構相對同儕群組的中位數、百分位、z-score 與穩健偏差。
  - R13.3：標示機構在同儕群組中的相對位置。
  - R13.4：同儕群組樣本數低於可靠比較門檻時，標示為樣本不足（insufficient）。

設計原則（對齊 project-vision 白盒可解釋）：所有統計量皆為明確、可解釋的
規則與統計計算，無 AI 參與。百分位採「≤ x 的比例」定義（含機構自身），
落於 0–100；z-score = (x − 群組平均) / 群組標準差；穩健偏差採中位數與
MAD（Median Absolute Deviation）為基礎，抗離群值。

責任 AI：同儕「異常」僅代表相對偏離，不等於違法（見 design.md 責任 AI 原則）。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# 同儕群組可靠比較的最小樣本數門檻（含受評機構自身）。
# 少於此門檻時 peer_stats 標記 insufficient（R13.4）。
MIN_PEER_SAMPLE = 5

# 依機構屬性劃分同儕群組的預設維度（R13.1）。
DEFAULT_PEER_KEYS = ("park_type", "size_band", "district")


# --------------------------------------------------------------------------
# 同儕群組（Peer Group, R13.1）
# --------------------------------------------------------------------------
@dataclass
class PeerGroup:
    """一個同儕群組：依 (park_type, size_band, district) 等維度分群後的成員集合。

    Validates: Requirements 13.1
    """
    key: tuple                                   # 分群鍵（各維度取值組成的 tuple）
    by: tuple[str, ...]                           # 分群所依維度名稱
    members: list[dict] = field(default_factory=list)   # 群組成員（含受評機構自身）

    @property
    def size(self) -> int:
        """群組樣本數（含受評機構自身）。"""
        return len(self.members)


# --------------------------------------------------------------------------
# 同儕統計量（Peer Comparison, R13.2, R13.3, R13.4）
# --------------------------------------------------------------------------
@dataclass
class PeerComparison:
    """機構相對同儕群組的統計量（R13.2）與相對位置（R13.3）。

    - median：群組中位數。
    - percentile：受評機構值在群組中的百分位（0–100，含機構自身）。
    - z_score：(x − 群組平均) / 群組標準差；標準差為 0 時為 0.0。
    - robust_deviation：以中位數與 MAD 為基礎的穩健偏差 (x − median) / (1.4826 * MAD)；
      MAD 為 0 時為 0.0。
    - position：相對位置標籤（低於同儕 / 接近同儕 / 高於同儕）（R13.3）。
    - insufficient：群組樣本數低於門檻時為 True，其餘統計量不可靠（R13.4）。
    - sample_n：實際參與計算的有效樣本數。

    Validates: Requirements 13.2, 13.3, 13.4
    """
    metric: str
    value: float | None
    median: float | None = None
    percentile: float | None = None
    z_score: float | None = None
    robust_deviation: float | None = None
    position: str | None = None
    insufficient: bool = False
    sample_n: int = 0


# --------------------------------------------------------------------------
# 建立同儕群組（R13.1）
# --------------------------------------------------------------------------
def _group_key(record: dict, by: tuple[str, ...]) -> tuple:
    """依 by 維度取出分群鍵。缺值以 None 佔位，確保相同屬性歸為同一群。"""
    return tuple(record.get(dim) for dim in by)


def build_peer_group(
    entity: dict,
    population: list[dict],
    by: tuple[str, ...] = DEFAULT_PEER_KEYS,
) -> PeerGroup:
    """依 by 維度（預設機構類型/規模/區域）將 entity 分到其同儕群組（R13.1）。

    參數：
      entity     ：受評機構（dict，至少含 by 指定的維度欄位）。
      population ：全體機構清單（每筆為 dict）。
      by         ：分群維度名稱 tuple，預設 ("park_type","size_band","district")。

    回傳：
      PeerGroup，members 為 population 中與 entity 分群鍵相同者（含 entity 自身，
      若 entity 亦在 population 中則不重複加入；否則納入 entity 以保證自身在群內）。
    """
    key = _group_key(entity, by)
    members = [rec for rec in population if _group_key(rec, by) == key]

    # 確保受評機構自身在群組內（供百分位含自身計算）。
    if entity not in members:
        members = members + [entity]

    return PeerGroup(key=key, by=tuple(by), members=members)


# --------------------------------------------------------------------------
# 同儕統計量（R13.2, R13.3, R13.4）
# --------------------------------------------------------------------------
def _collect_values(group: PeerGroup, metric: str) -> list[float]:
    """從群組成員收集指定指標的有效數值（排除 None 與非數值）。"""
    values: list[float] = []
    for rec in group.members:
        v = rec.get(metric)
        if v is None:
            continue
        if isinstance(v, bool):  # bool 是 int 子類，明確排除避免誤計
            continue
        if isinstance(v, (int, float)):
            values.append(float(v))
    return values


def _percentile_of(value: float, values: list[float]) -> float:
    """value 在 values 中的百分位（0–100），採「≤ value 的比例」定義（含自身）。"""
    n = len(values)
    if n == 0:
        return 0.0
    count_le = sum(1 for v in values if v <= value)
    return round(count_le / n * 100, 4)


def _relative_position(z_score: float | None) -> str:
    """依 z-score 給出可解釋的相對位置標籤（R13.3）。"""
    if z_score is None:
        return "無法判定"
    if z_score <= -1.0:
        return "低於同儕"
    if z_score >= 1.0:
        return "高於同儕"
    return "接近同儕"


def peer_stats(
    entity: dict,
    group: PeerGroup,
    metric: str = "risk_total",
) -> PeerComparison:
    """計算 entity 於指定 metric 相對 group 的同儕統計量（R13.2, R13.3, R13.4）。

    參數：
      entity ：受評機構（dict）。
      group  ：由 build_peer_group 產生的同儕群組。
      metric ：欲比較的指標欄位名稱，預設 "risk_total"。

    回傳：
      PeerComparison。當群組有效樣本數 < MIN_PEER_SAMPLE 時，
      insufficient=True 且統計量以可得資訊填入但視為不可靠（R13.4）。

    統計定義（R13.2）：
      - median           = 群組中位數
      - percentile       = entity 值在群組中「≤ 該值」的比例 × 100（0–100，含自身）
      - z_score          = (x − mean) / stdev；stdev == 0 時為 0.0
      - robust_deviation = (x − median) / (1.4826 × MAD)；MAD == 0 時為 0.0
    """
    value = entity.get(metric)
    if isinstance(value, bool):
        value = None
    elif isinstance(value, (int, float)):
        value = float(value)
    else:
        value = None

    values = _collect_values(group, metric)
    sample_n = len(values)

    result = PeerComparison(metric=metric, value=value, sample_n=sample_n)

    # 樣本不足：標記後直接回傳（統計量保持 None，視為不可靠）（R13.4）。
    if sample_n < MIN_PEER_SAMPLE:
        result.insufficient = True
        result.position = "樣本不足"
        return result

    # 中位數（R13.2）。
    median = statistics.median(values)
    result.median = round(median, 4)

    # 受評機構無有效值時，仍可回報群組中位數，但個體統計量無法計算。
    if value is None:
        result.position = "無法判定"
        return result

    # 百分位（0–100，含自身）（R13.2, R13.3）。
    result.percentile = _percentile_of(value, values)

    # z-score = (x − mean) / stdev；stdev == 0 → 0.0（R13.2）。
    mean = statistics.fmean(values)
    stdev = statistics.pstdev(values) if sample_n > 1 else 0.0
    result.z_score = round((value - mean) / stdev, 4) if stdev > 0 else 0.0

    # 穩健偏差：以中位數與 MAD（Median Absolute Deviation）為基礎，抗離群（R13.2）。
    abs_dev = [abs(v - median) for v in values]
    mad = statistics.median(abs_dev)
    if mad > 0:
        # 1.4826 為常態分布下 MAD 與標準差的一致性換算係數。
        result.robust_deviation = round((value - median) / (1.4826 * mad), 4)
    else:
        result.robust_deviation = 0.0

    # 相對位置（R13.3）。
    result.position = _relative_position(result.z_score)

    return result
