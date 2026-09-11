"""
主動預警層（Proactive Alert / Watchlist）— 事前主動示警
========================================================================
小小守護員 Smart Watchdog Platform — 對齊題目核心「縮短預警時間：從事後
被動稽查提前為事前主動示警」。

設計理念（重要）：
--------------------------------------------------------------------
本系統的風險分數是「相對稽查優先序」設計（同儕比較 + 百分位分級，見
docs/methodology.md），而非絕對造假分。實務上全體分數集中在中低區間
（例如公校普遍相對規矩），因此**預警門檻不可寫死絕對數字**（如 80/75），
否則資料集若無任何園達 80 分，預警系統將一間都抓不到而失效。

正解：以**相對基準**定義預警等級——結合「百分位」與「同儕標準差」兩種
統計基準，任何資料分布下都能穩定篩出「相對最需關注」與「接近門檻、需
提前追蹤」的機構。此即審計界同儕比較（peer benchmarking，PCAOB AS 2305
分析程序）的延伸。

兩級預警：
  - 紅色警報 (CRITICAL_ALERT)：相對最高風險群（預設 Top 15%）。
    建議行動：立即納入本期稽查名單、優先派員查核。
  - 橘色預警 (WATCHLIST)：尚未達高風險、但已接近門檻的「預警緩衝區」
    （預設 Top 15%–30%）。建議行動：納入主動追蹤，資料更新時重新評估，
    避免其惡化跨過紅線才被動發現。這一層正是「事前示警」的關鍵。

規模化說明（供簡報／評審問答）：
--------------------------------------------------------------------
本層以「純函式 + 現有快照資料」實作，Demo 穩定不依賴外部網路。架構上預留
`evaluate()` 作為單次評估入口，可由排程器（cron / EventBridge）或資料管線
在每次資料更新後呼叫，即構成「隨資料更新自動重新預警」的即時預警系統，
無需改動本層邏輯——即現有設計即為可規模化到即時資料源的預警引擎。

本模組為純邏輯（僅依賴 pandas / numpy），不 import streamlit，可離線測試。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 預警等級常數
# ---------------------------------------------------------------------------
CRITICAL_ALERT = "紅色警報"   # 相對最高風險：建議立即派查
WATCHLIST = "橘色預警"        # 接近門檻的緩衝區：建議主動追蹤（事前示警核心）
NORMAL = "正常"               # 未達預警

#: 預警等級的顏色映射（對齊 UI 設計準則的語意色，非裝飾用途）。
ALERT_COLOR: dict[str, str] = {
    CRITICAL_ALERT: "#C0392B",  # red = critical
    WATCHLIST: "#E67E22",       # orange = warning
    NORMAL: "#2E7D32",          # green = normal
}


@dataclass
class AlertConfig:
    """預警門檻設定（相對基準；可調，簡報時可展示調整效果）。

    critical_pct : float
        紅色警報的百分位門檻（0–1）。預設 0.85 = 相對 Top 15%（對齊
        risk_score.risk_level_percentile 的高風險門檻，兩者一致）。
    watch_pct : float
        橘色預警的百分位門檻（0–1）。預設 0.70 = Top 30%；落在
        watch_pct（含）與 critical_pct（不含）之間者為橘色預警緩衝區。
    sigma_k : float
        同儕標準差輔助門檻：分數 ≥ 同儕平均 + sigma_k × 標準差 者，
        即使百分位未達也升級為紅色警報（抓「絕對意義上明顯偏離同儕」者）。
        預設 1.5。設為 None 可停用此輔助規則。
    """
    critical_pct: float = 0.85
    watch_pct: float = 0.70
    sigma_k: float | None = 1.5

    def __post_init__(self) -> None:
        if not (0.0 < self.watch_pct < self.critical_pct < 1.0):
            raise ValueError(
                "門檻須滿足 0 < watch_pct < critical_pct < 1，"
                f"目前 watch_pct={self.watch_pct}, critical_pct={self.critical_pct}"
            )
        if self.sigma_k is not None and self.sigma_k < 0:
            raise ValueError("sigma_k 不可為負")


@dataclass
class Alert:
    """單一機構的預警結果。"""
    park_id: Any
    park_name: str
    risk_total: float
    level: str                      # CRITICAL_ALERT / WATCHLIST / NORMAL
    percentile: float               # 該園在全體中的百分位（0–1）
    peer_z: float | None            # 相對同儕的 z-score（無法計算時為 None）
    reasons: list[str] = field(default_factory=list)   # 觸發此預警的原因
    recommended_action: str = ""    # 建議稽查行動
    color: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "park_id": self.park_id,
            "park_name": self.park_name,
            "risk_total": self.risk_total,
            "level": self.level,
            "percentile": round(self.percentile, 4),
            "peer_z": None if self.peer_z is None else round(self.peer_z, 3),
            "reasons": list(self.reasons),
            "recommended_action": self.recommended_action,
            "color": self.color,
        }


# ---------------------------------------------------------------------------
# 觸發原因彙整（可解釋：每筆預警都說明「為什麼被示警」）
# ---------------------------------------------------------------------------
# 欄位 → (人類可讀名稱, 觸發判斷函式)。用既有 kindergartens_latest.csv 欄位。
def _collect_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []

    def _num(col):
        v = row.get(col)
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    ratio = _num("expense_income_ratio")
    if ratio is not None and ratio > 1.0:
        over = (ratio - 1.0) * 100
        reasons.append(f"收支比 {ratio:.2f}（支出超過收入 {over:.1f}%，入不敷出）")

    pen = _num("penalty_count")
    if pen is not None and pen >= 1:
        reasons.append(f"裁罰紀錄 {int(pen)} 次")

    mad = _num("benford_mad")
    if mad is not None and mad >= 0.04:
        reasons.append(f"班佛偏離度 {mad:.3f}（數字分布偏離常態，偏高）")

    yoy = _num("expense_yoy_pct")
    if yoy is not None and abs(yoy) >= 30:
        direction = "增" if yoy > 0 else "減"
        reasons.append(f"支出年{direction} {abs(yoy):.0f}%（跨年度突變）")

    sf = _num("score_financial")
    if sf is not None and sf >= 50:
        reasons.append(f"財務異常分 {sf:.0f}（鑑識會計多層方法偏高）")

    grade = row.get("eval_grade")
    if isinstance(grade, str) and grade in ("乙", "待改進"):
        reasons.append(f"評鑑結果「{grade}」")

    return reasons


def _action_for(level: str, reasons: list[str]) -> str:
    if level == CRITICAL_ALERT:
        base = "建議本期立即納入稽查名單、優先派員查核"
    elif level == WATCHLIST:
        base = "建議納入主動追蹤清單，資料更新時重新評估（尚未達高風險但接近門檻）"
    else:
        base = "維持例行監測"
    if reasons:
        return f"{base}；重點查核方向：{reasons[0]}"
    return base


# ---------------------------------------------------------------------------
# 核心：單次預警評估（可由排程 / 資料管線重複呼叫 → 即時預警系統）
# ---------------------------------------------------------------------------
def evaluate(df: pd.DataFrame, config: AlertConfig | None = None,
             score_col: str = "risk_total",
             group_col: str = "park_type") -> list[Alert]:
    """對整批機構做一次預警評估，回傳每園的 Alert（依風險由高至低排序）。

    相對基準：
      - 百分位：以全體分數分布計算每園百分位。
      - 同儕 z-score：以同儕群組（預設同 park_type）平均與標準差計算；
        群組樣本 < 3 或標準差為 0 時 peer_z 為 None（不套用 sigma 規則）。

    升級規則：
      1. 百分位 ≥ critical_pct → 紅色警報。
      2. watch_pct ≤ 百分位 < critical_pct → 橘色預警。
      3. （輔助）peer_z ≥ sigma_k → 直接升級為紅色警報（明顯偏離同儕）。
    """
    if config is None:
        config = AlertConfig()
    if df is None or len(df) == 0:
        return []
    if score_col not in df.columns:
        raise KeyError(f"資料缺少分數欄位：{score_col}")

    work = df.copy()
    scores = pd.to_numeric(work[score_col], errors="coerce")
    percentiles = scores.rank(pct=True)

    # 同儕 z-score（依群組；群組不可用時退回全體）。
    peer_z = pd.Series(np.nan, index=work.index, dtype="float")
    if group_col in work.columns:
        groups = work.groupby(group_col).groups
    else:
        groups = {"__all__": work.index}
    for _g, idx in groups.items():
        sub = scores.loc[idx]
        if len(sub) >= 3 and sub.std(ddof=0) > 0:
            peer_z.loc[idx] = (sub - sub.mean()) / sub.std(ddof=0)

    alerts: list[Alert] = []
    for i in work.index:
        pct = float(percentiles.loc[i]) if not pd.isna(percentiles.loc[i]) else 0.0
        z = peer_z.loc[i]
        z_val = None if pd.isna(z) else float(z)
        score = float(scores.loc[i]) if not pd.isna(scores.loc[i]) else 0.0

        # 分級：百分位為主，同儕 z-score 為輔助升級規則。
        if pct >= config.critical_pct:
            level = CRITICAL_ALERT
        elif pct >= config.watch_pct:
            level = WATCHLIST
        else:
            level = NORMAL
        if (config.sigma_k is not None and z_val is not None
                and z_val >= config.sigma_k):
            level = CRITICAL_ALERT

        reasons = _collect_reasons(work.loc[i])
        alerts.append(Alert(
            park_id=work.loc[i].get("park_id"),
            park_name=str(work.loc[i].get("park_name", "")),
            risk_total=round(score, 1),
            level=level,
            percentile=pct,
            peer_z=z_val,
            reasons=reasons,
            recommended_action=_action_for(level, reasons),
            color=ALERT_COLOR[level],
        ))

    alerts.sort(key=lambda a: a.risk_total, reverse=True)
    return alerts


def active_alerts(df: pd.DataFrame, config: AlertConfig | None = None,
                  **kwargs) -> list[Alert]:
    """只回傳達預警（紅色警報 + 橘色預警）的機構，供戰情室「主動示警」面板使用。"""
    return [a for a in evaluate(df, config, **kwargs) if a.level != NORMAL]


def alert_summary(df: pd.DataFrame, config: AlertConfig | None = None,
                  **kwargs) -> dict[str, int]:
    """回傳各預警等級的計數（供 KPI 帶顯示）。"""
    result = {CRITICAL_ALERT: 0, WATCHLIST: 0, NORMAL: 0}
    for a in evaluate(df, config, **kwargs):
        result[a.level] += 1
    return result


def alerts_to_dataframe(alerts: list[Alert]) -> pd.DataFrame:
    """將 Alert 清單轉為 DataFrame（供表格顯示 / CSV 下載）。"""
    if not alerts:
        return pd.DataFrame(columns=[
            "park_id", "park_name", "risk_total", "level",
            "percentile", "peer_z", "reasons", "recommended_action",
        ])
    rows = []
    for a in alerts:
        d = a.to_dict()
        d["reasons"] = "；".join(d["reasons"]) if d["reasons"] else "—"
        d.pop("color", None)
        rows.append(d)
    return pd.DataFrame(rows)
