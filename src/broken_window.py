"""
破窗效應累犯加權分數（Broken Window Score, R25）
=====================================================
小小守護員 Smart Watchdog Platform — 裁罰分項的組成之一（創意 2：把犯罪學的
破窗理論與再犯風險時效衰減搬進教保稽查）。

核心思想（可辯護、可攤開）：
  機構重大違法事件多為「頻繁、近期、未改善的輕微違規」長期累積的後果。純看
  違規「次數」會低估這種惡化趨勢。破窗效應累犯加權以三個可解釋因子將違規紀錄
  轉為 0–100 分：
    1. 嚴重度權重（severity）：輕微=3 / 中度=6 / 重大=12（R25.2）。
    2. 時效衰減（time decay）：0.5^(距今月數 / 半衰期 H)，近期違規權重高於久遠
       （R25.3）。半衰期 H 預設 18 個月（範圍 6–36）。
    3. 頻率放大（frequency amplifier）：1 + 0.15 ×(窗內違規筆數 − 1)（R25.4）。

  Broken_Window_Score = min(100, 頻率放大 × Σ_i severity(v_i) × decay(t_i))

學理依據（內容已改寫以符合授權限制）：
  - 破窗理論（Wilson & Kelling；Keizer et al., Science 2008）：輕微失序訊號
    誘發更嚴重失序與擴散。
  - 動態再犯風險（Yukhnenko et al., Oxford）：近期急性事件較陳年紀錄更具預測力，
    支撐時效衰減設計。

責任 AI：本分數僅為稽查優先序參考，風險不等於違法。缺類型/日期之違規紀錄標記
待人工確認並排除於計算之外（R25.8），不中斷其餘紀錄；相同輸入恆得相同分數
（確定性，R25.9）。

對應：requirements.md R25、design.md「1b. Broken_Window_Score」、tasks.md 4.5。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# --------------------------------------------------------------------------
# 嚴重度分級（R25.2）：違規類型 → 嚴重度等級 → 權重。
# 與 penalty_nlp 的五類（收費/人力/安全/教保/行政）對映到三級嚴重度。
# --------------------------------------------------------------------------
SEVERITY_WEIGHTS = {"minor": 3, "moderate": 6, "major": 12}

# penalty_nlp 五大類別 → 破窗三級嚴重度（對映表，供 NLP 違規類型辨識對接）。
CATEGORY_TO_SEVERITY = {
    "安全": "major",     # 照顧與安全疑慮 → 重大
    "收費": "moderate",  # 收費違規 → 中度
    "人力": "moderate",  # 進用未具資格人員 → 中度
    "教保": "moderate",  # 教保服務品質 → 中度
    "行政": "minor",     # 資料未依規公開 → 輕微
    "未分類": "minor",
}

# 預設參數（R25.3, R25.5）。
DEFAULT_HALF_LIFE_MONTHS = 18
HALF_LIFE_MIN, HALF_LIFE_MAX = 6, 36
DEFAULT_WINDOW_MONTHS = 36
FREQ_AMPLIFIER_PER_EXTRA = 0.15  # 每多一筆違規的頻率放大增量（R25.4）


@dataclass
class Violation:
    """單一違規紀錄（破窗計算的輸入單位）。

    - occurred_on：違規發生日期（date）；缺值 → 標記待人工確認並排除（R25.8）。
    - severity：三級嚴重度 'minor'/'moderate'/'major'；缺值時可由 category 推得。
    - category：penalty_nlp 五類（收費/人力/安全/教保/行政）；用於推 severity。
    - description：原始事由文字（供貢獻明細追溯）。
    """
    occurred_on: date | None = None
    severity: str | None = None
    category: str | None = None
    description: str = ""


@dataclass
class ContributionDetail:
    """單筆違規對破窗分數的貢獻明細（可攤開解釋，R25.6）。"""
    description: str
    severity: str
    severity_weight: int
    months_since: float
    time_decay: float
    contribution: float          # severity_weight × time_decay（未乘頻率放大）


@dataclass
class BrokenWindowResult:
    """破窗效應累犯加權結果（R25.1, R25.6）。"""
    score: float                 # 0–100
    n_counted: int               # 納入計算的違規筆數
    frequency_amplifier: float
    details: list[ContributionDetail] = field(default_factory=list)
    pending_manual: list[str] = field(default_factory=list)  # 缺類型/日期被排除者（R25.8）


def _months_between(earlier: date, later: date) -> float:
    """回傳 later 相對 earlier 的月數（近似，以 30.44 天/月）。負值截為 0。"""
    days = (later - earlier).days
    return max(0.0, days / 30.4375)


def _resolve_severity(v: Violation) -> str | None:
    """解析違規的三級嚴重度：優先用顯式 severity，否則由 category 推得。"""
    if v.severity in SEVERITY_WEIGHTS:
        return v.severity
    if v.category and v.category in CATEGORY_TO_SEVERITY:
        return CATEGORY_TO_SEVERITY[v.category]
    return None


def broken_window_score(
    violations: list[Violation],
    as_of: date,
    half_life_months: int = DEFAULT_HALF_LIFE_MONTHS,
    window_months: int = DEFAULT_WINDOW_MONTHS,
) -> BrokenWindowResult:
    """計算破窗效應累犯加權分數（R25.1–R25.6, R25.8, R25.9）。

    公式（R25.1）：
        score = min(100, frequency_amplifier(n) × Σ_i severity_weight(v_i) × time_decay(t_i))
      - severity_weight：minor=3 / moderate=6 / major=12（R25.2）。
      - time_decay(t) = 0.5 ^ (months_since / half_life)，half_life 夾於 6–36（R25.3）。
      - frequency_amplifier(n) = 1 + 0.15 ×(n − 1)，n=窗內納入計算的違規筆數；
        n=0 → 分數 0（R25.4）。

    參數：
      violations       ：違規紀錄清單。
      as_of            ：評估基準日（計算距今月數與評估窗）。
      half_life_months ：時效半衰期（6–36，超出範圍自動夾至邊界）（R25.3）。
      window_months    ：評估窗（近 N 個月，預設 36，可設定）（R25.5）。

    回傳：
      BrokenWindowResult。缺類型或發生日期之紀錄列入 pending_manual 並排除計算
      （R25.8），不中斷其餘；相同輸入恆得相同結果（確定性，R25.9）。
    """
    # 半衰期夾至合法範圍（R25.3）。
    h = max(HALF_LIFE_MIN, min(int(half_life_months), HALF_LIFE_MAX))

    details: list[ContributionDetail] = []
    pending: list[str] = []

    for v in violations:
        severity = _resolve_severity(v)
        # 缺類型/嚴重度或缺日期 → 待人工確認、排除計算（R25.8）。
        if severity is None or v.occurred_on is None:
            pending.append(v.description or "(未標示事由)")
            continue

        months_since = _months_between(v.occurred_on, as_of)
        # 評估窗：超出窗（近 window_months 個月）者排除（R25.5）。
        if months_since > window_months:
            continue

        weight = SEVERITY_WEIGHTS[severity]
        decay = 0.5 ** (months_since / h)
        contribution = weight * decay
        details.append(ContributionDetail(
            description=v.description or f"({severity})",
            severity=severity,
            severity_weight=weight,
            months_since=round(months_since, 2),
            time_decay=round(decay, 4),
            contribution=round(contribution, 4),
        ))

    n = len(details)
    if n == 0:
        # 無納入計算之違規 → 分數 0（R25.4）。
        return BrokenWindowResult(
            score=0.0, n_counted=0, frequency_amplifier=0.0,
            details=[], pending_manual=pending,
        )

    freq_amp = 1 + FREQ_AMPLIFIER_PER_EXTRA * (n - 1)
    raw = freq_amp * sum(d.contribution for d in details)
    score = round(min(100.0, raw), 1)

    return BrokenWindowResult(
        score=score,
        n_counted=n,
        frequency_amplifier=round(freq_amp, 4),
        details=details,
        pending_manual=pending,
    )
