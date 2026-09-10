"""
風險時間軸與變化點偵測（Risk Timeline & Change-Point Detection, R12, R5.3）
=============================================================================
小小守護員 Smart Watchdog Platform — 跨年度風險時間軸子系統。

對應 design.md「Components and Interfaces / 5. Timeline + Change_Point」與
Data Models，落實需求：
  - R12.1 / R5.3：為每個機構產生跨年度的風險時間軸，涵蓋「所有可取得年度」，
    且依年度「由舊到新」排序。
  - R12.2：在時間軸上標記「統計上顯著」的變化點（Change_Point）。
  - R12.3：當某年度的指標相對歷史序列達到變化點判定條件時，於時間軸標示該變化點。
  - R12.4：為每個標示的變化點提供對應的「觸發指標說明」。

設計原則（對齊 project-vision 白盒可解釋）：變化點偵測全程以明確、可解釋的
規則與統計計算完成（穩健 z-score + YoY 比例雙判準），無 AI 參與。每一個
被標記的變化點皆附帶人類可讀的觸發指標說明字串（R12.4），使稽查員能理解
「為什麼這個時點被標為情勢突變」。

責任 AI：風險時間軸與變化點僅代表「數值層面的趨勢變化」，不等於違法認定
（見 design.md 責任 AI 原則）。
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# 變化點判定參數（可解釋、可調整）
# --------------------------------------------------------------------------
# 變化點偵測所需的最小序列長度：至少需要「先前歷史 + 當前點」才能判定相對變化。
# 少於此長度時無足夠歷史基準，不產生變化點（R12.3 需相對歷史序列）。
MIN_SERIES_LENGTH = 3

# 穩健 z-score 判定門檻：當前值相對「先前歷史」的穩健標準分數絕對值
# 達到此門檻，視為統計上顯著（R12.2）。3.5 為 Iglewicz–Hoaglin 常用之
# 穩健離群判定門檻（以中位數與 MAD 為基礎，抗離群）。
DEFAULT_Z_THRESHOLD = 3.5

# YoY 比例判定門檻：當前值相對「前一年度值」的年增率絕對值達到此門檻，
# 視為突變（與 forensic.sudden_change 語意一致，預設 0.30）。此為輔助判準，
# 使得序列過短、MAD 為 0 等統計退化情境仍能捕捉明顯的年度突變。
DEFAULT_YOY_THRESHOLD = 0.30

# 常態分布下 MAD 與標準差的一致性換算係數（供穩健 z-score 使用）。
_MAD_SCALE = 1.4826


# --------------------------------------------------------------------------
# 資料模型（Data Models）
# --------------------------------------------------------------------------
@dataclass
class TimelinePoint:
    """時間軸上的單一年度資料點。

    - year：年度（例如 112/113/114）。
    - value：該年度的風險指標值（風險總分或任一鑑識指標值）。
    - metric：該值所對應的指標名稱（供顯示與追溯）。

    Validates: Requirements 12.1, 5.3
    """
    year: int
    value: float | None
    metric: str = "risk_total"


@dataclass
class RiskTimeline:
    """一間機構的跨年度風險時間軸（R12.1, R5.3）。

    不變式：
      - points 依 year「由舊到新」非遞減排序（R5.3, R12.1）。
      - points 涵蓋輸入中「所有可取得年度」，不遺漏（R12.1）。

    Validates: Requirements 12.1, 5.3
    """
    entity_id: str
    metric: str = "risk_total"
    points: list[TimelinePoint] = field(default_factory=list)
    # 變化點（由 detect_change_points 產出後可掛載於此，供介面呈現）。
    change_points: list["ChangePoint"] = field(default_factory=list)

    @property
    def years(self) -> list[int]:
        """時間軸涵蓋的年度（由舊到新）。"""
        return [p.year for p in self.points]


@dataclass
class ChangePoint:
    """時間序列中統計上顯著的變化點（R12.2, R12.3, R12.4）。

    - index：變化點在輸入序列中的索引位置（0-based，指向發生突變的當前點）。
    - value：變化點當前值。
    - previous_value：緊鄰前一點的值（供年增率與方向說明）。
    - z_score：當前值相對先前歷史的穩健標準分數（統計顯著性依據，R12.2）。
    - yoy_rate：相對前一點的年增率（(當前 − 前值) / |前值|）；前值為 0/None 時為 None。
    - direction：變化方向（'上升' / '下降'）。
    - trigger：非空的「觸發指標說明」，說明為何此點被標記為變化點（R12.4）。

    Validates: Requirements 12.2, 12.3, 12.4
    """
    index: int
    value: float
    previous_value: float | None
    z_score: float | None
    yoy_rate: float | None
    direction: str
    trigger: str


# --------------------------------------------------------------------------
# 時間軸建構（R12.1, R5.3）
# --------------------------------------------------------------------------
def _coerce_number(v) -> float | None:
    """將值轉為 float；None、布林與非數值回傳 None（不列入數值計算）。"""
    if v is None:
        return None
    if isinstance(v, bool):  # bool 是 int 子類，明確排除避免誤計
        return None
    if isinstance(v, (int, float)):
        return float(v)
    return None


def build_timeline(
    entity_years: list[dict],
    metric: str = "risk_total",
    entity_id: str = "",
) -> RiskTimeline:
    """由機構的多年度紀錄建構風險時間軸（R12.1, R5.3）。

    參數：
      entity_years：多年度紀錄清單，每筆為 dict，至少含年度欄位（"year"）與
                    指標欄位（由 metric 指定）。年度欄位亦接受 "年度"、"fiscal_year"
                    作為別名，以相容既有資料。
      metric      ：作為時間軸值的指標欄位名稱，預設 "risk_total"。
      entity_id   ：機構識別碼；未提供時嘗試由紀錄的 "park_id"/"entity_id" 推得。

    回傳：
      RiskTimeline，其 points：
        - 涵蓋所有「可取得年度」（能解析出年度的紀錄皆納入）（R12.1）。
        - 依年度由舊到新（非遞減）排序（R5.3, R12.1）。
      指標值缺失或非數值者，該點 value 為 None（仍保留該年度，確保覆蓋完整）。

    穩健性：無法解析年度的紀錄被略過，不中斷其餘年度；重複年度皆保留
    （由舊到新排序後仍相鄰），不擅自合併，交由上層決定。
    """
    def _year_of(rec: dict) -> int | None:
        for key in ("year", "年度", "fiscal_year"):
            if key in rec:
                y = rec.get(key)
                if isinstance(y, bool):
                    continue
                if isinstance(y, (int, float)):
                    return int(y)
                if isinstance(y, str) and y.strip().lstrip("-").isdigit():
                    return int(y.strip())
        return None

    # 推得 entity_id（若未指定）。
    resolved_id = entity_id
    if not resolved_id:
        for rec in entity_years:
            for key in ("park_id", "entity_id"):
                if rec.get(key):
                    resolved_id = str(rec.get(key))
                    break
            if resolved_id:
                break

    points: list[TimelinePoint] = []
    for rec in entity_years:
        year = _year_of(rec)
        if year is None:
            continue  # 無法解析年度：略過，不中斷其餘（穩健性）
        value = _coerce_number(rec.get(metric))
        points.append(TimelinePoint(year=year, value=value, metric=metric))

    # 依年度由舊到新排序（R5.3, R12.1）。年度相同者維持原輸入相對順序（stable sort）。
    points.sort(key=lambda p: p.year)

    return RiskTimeline(entity_id=resolved_id, metric=metric, points=points)


# --------------------------------------------------------------------------
# 變化點偵測（R12.2, R12.3, R12.4）
# --------------------------------------------------------------------------
def _robust_zscore(current: float, history: list[float]) -> float | None:
    """當前值相對「先前歷史」的穩健 z-score（以中位數與 MAD 為基礎，抗離群）。

    定義：z = (current − median(history)) / (1.4826 × MAD(history))。
    當 history 為空回傳 None；當 MAD 為 0（歷史完全一致）時，若 current 與
    中位數不同則回傳 None（改由 YoY 判準捕捉），相同則回傳 0.0。
    """
    if not history:
        return None
    median = statistics.median(history)
    abs_dev = [abs(v - median) for v in history]
    mad = statistics.median(abs_dev)
    if mad <= 0:
        return 0.0 if current == median else None
    return (current - median) / (_MAD_SCALE * mad)


def _yoy_rate(current: float, previous: float | None) -> float | None:
    """年增率 (current − previous) / |previous|；previous 為 0/None 時回傳 None。"""
    if previous is None or previous == 0:
        return None
    return (current - previous) / abs(previous)


def detect_change_points(
    series: list[float] | list[float | None],
    metric: str = "risk_total",
    z_threshold: float = DEFAULT_Z_THRESHOLD,
    yoy_threshold: float = DEFAULT_YOY_THRESHOLD,
) -> list[ChangePoint]:
    """偵測時間序列中統計上顯著的變化點，每點附觸發指標說明（R12.2–R12.4）。

    判定規則（雙判準，任一成立即標記為變化點；皆為明確、可解釋的統計規則）：
      1. 穩健 z-score 判準：當前值相對「其之前所有歷史值」的穩健 z-score
         絕對值 ≥ z_threshold（預設 3.5）視為統計顯著（R12.2）。
      2. YoY 突變判準：當前值相對「前一點值」的年增率絕對值 ≥ yoy_threshold
         （預設 0.30）視為年度突變。此判準補足序列過短或 MAD 退化的情境。

    參數：
      series       ：時間序列值（建議由 build_timeline 依年度由舊到新產出後取 value）。
                     其中 None 代表該年度值缺失，會被略過（不作為當前點判定，
                     但已存在的歷史值仍納入基準）。
      metric       ：觸發指標名稱，用於組出人類可讀的觸發說明（R12.4）。
      z_threshold  ：穩健 z-score 顯著門檻（> 0）。
      yoy_threshold：YoY 突變門檻（≥ 0，與 forensic.sudden_change 語意一致）。

    回傳：
      list[ChangePoint]，依 index（時間先後）由小到大排序。每個 ChangePoint 的
      index 對應到「原始 series」中的索引位置；trigger 為非空說明字串（R12.4）。

    穩健性：序列長度不足（有效點 < MIN_SERIES_LENGTH）時回傳空清單（無足夠歷史
    基準以判定相對變化，R12.3）；不拋出例外。
    """
    # 收集有效（非 None、數值）點及其原始索引。
    valid: list[tuple[int, float]] = []
    for i, v in enumerate(series):
        num = _coerce_number(v)
        if num is not None:
            valid.append((i, num))

    if len(valid) < MIN_SERIES_LENGTH:
        return []

    change_points: list[ChangePoint] = []
    history: list[float] = []
    prev_value: float | None = None

    for pos, (orig_index, value) in enumerate(valid):
        # 第一個有效點作為基準起點，無先前歷史，不判定。
        if pos == 0:
            history.append(value)
            prev_value = value
            continue

        z = _robust_zscore(value, history)
        yoy = _yoy_rate(value, prev_value)

        z_hit = z is not None and abs(z) >= z_threshold
        yoy_hit = yoy is not None and abs(yoy) >= yoy_threshold

        if z_hit or yoy_hit:
            direction = "上升" if value >= (prev_value if prev_value is not None else value) else "下降"
            trigger = _build_trigger(
                metric=metric,
                value=value,
                prev_value=prev_value,
                z=z,
                yoy=yoy,
                z_hit=z_hit,
                yoy_hit=yoy_hit,
                z_threshold=z_threshold,
                yoy_threshold=yoy_threshold,
                direction=direction,
            )
            change_points.append(
                ChangePoint(
                    index=orig_index,
                    value=round(value, 4),
                    previous_value=(round(prev_value, 4) if prev_value is not None else None),
                    z_score=(round(z, 4) if z is not None else None),
                    yoy_rate=(round(yoy, 4) if yoy is not None else None),
                    direction=direction,
                    trigger=trigger,
                )
            )

        # 將當前點納入歷史，供後續點作為基準。
        history.append(value)
        prev_value = value

    return change_points


def _build_trigger(
    metric: str,
    value: float,
    prev_value: float | None,
    z: float | None,
    yoy: float | None,
    z_hit: bool,
    yoy_hit: bool,
    z_threshold: float,
    yoy_threshold: float,
    direction: str,
) -> str:
    """組出非空、人類可讀的觸發指標說明（R12.4）。

    說明內容包含：觸發的指標名稱、變化方向、以及達標的統計判準與數值，
    使稽查員能理解此變化點「為何被標記」及「由哪個指標觸發」。
    """
    reasons: list[str] = []
    if z_hit and z is not None:
        reasons.append(f"穩健 z-score {z:.2f}（門檻 {z_threshold:.2f}）")
    if yoy_hit and yoy is not None:
        reasons.append(f"年增率 {yoy * 100:.1f}%（門檻 {yoy_threshold * 100:.1f}%）")

    prev_desc = f"{prev_value:.4g}" if prev_value is not None else "無前值"
    reason_desc = "、".join(reasons) if reasons else "統計顯著變化"
    return (
        f"指標「{metric}」{direction}：由 {prev_desc} 變為 {value:.4g}，"
        f"觸發判準：{reason_desc}。"
    )
