"""
輿情關注指數（Public Attention Index）— 診斷式白盒評分
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的輿情總評分。

這是什麼、不是什麼（責任 AI，最重要）：
--------------------------------------------------------------------------
「輿情關注指數（0–100）」**只反映近期網路公開討論的熱度與情緒聲量集中程度**，
分數越高代表「近期網路上關於此機構的公開討論越多、負面聲量越集中、或出現
明顯的討論變化」。它**不是**機構品質評價，**不是**違法/舞弊認定，**也不等於**
公務後台 Fiscalint 的財務風險分數（兩者資料基礎完全不同：一個是網路輿情、
一個是財務鑑識）。因此本指數刻意獨立命名、獨立計算，不與後台風險分混用。

為何是「診斷式白盒」：
--------------------------------------------------------------------------
分數由四個可解釋分項加權而成，每項都能攤開給家長看「這分怎麼來的」：
    指數 = 討論量分 ×0.30 + 負面聲量分 ×0.30 + 趨勢變化分 ×0.25 + 主題敏感分 ×0.15
每一分項皆為 0–100，權重固定且公開，無黑箱模型。分數旁一律附「依據」與
「這不代表什麼」的說明，避免家長誤讀為機構好壞的評分。

資料來源：本指數僅計入「與本機構精確比對成功（matched=True）」的公開項目，
避免同名新聞張冠李戴影響分數。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

# 沿用 sentiment_watch 的型別與趨勢偵測（單一事實來源，不重寫）。
try:
    from lib import sentiment_watch as _sw  # type: ignore
except Exception:  # pragma: no cover
    import sentiment_watch as _sw  # type: ignore

# ---------------------------------------------------------------------------
# 權重（固定、公開；診斷式白盒）
# ---------------------------------------------------------------------------
W_VOLUME = 0.30      # 討論量
W_NEGATIVE = 0.30    # 近期負面聲量比例
W_TREND = 0.25       # 趨勢變化（量暴增 / 負面比例上升）
W_TOPIC = 0.15       # 主題敏感度（安全/收費等家長高度關切主題）

#: 主題敏感度權重（0–1）：安全與收費對家長影響最大，敏感度最高。
_TOPIC_SENSITIVITY: dict[str, float] = {
    "safety": 1.00,     # 安全
    "fee": 0.85,        # 收費
    "teacher": 0.70,    # 師資
    "teaching": 0.55,   # 教學品質
    "admin": 0.45,      # 行政
    "other": 0.30,      # 其他
}

#: 討論量達此則數（近期窗內）即視為「討論量分」滿分基準。
_VOLUME_FULL_AT = 10


@dataclass(frozen=True)
class AttentionIndex:
    """輿情關注指數與其可解釋分解（0–100）。

    - total：0–100 綜合指數（四分項加權，四捨五入至整數）。
    - band：對應的家長友善分級代碼（calm/active/watch/none，與 parent_map 對齊）。
    - contributions：各分項「已乘權重」的貢獻值（加總約等於 total）。
    - subscores：各分項的原始 0–100 分（未乘權重，供攤開檢視）。
    - basis：分數依據文字（則數、時間區間、負面比例、趨勢）。
    - disclaimer：固定的「這不代表什麼」說明（責任 AI）。
    """
    total: float
    band: str
    contributions: dict[str, float] = field(default_factory=dict)
    subscores: dict[str, float] = field(default_factory=dict)
    weights: dict[str, float] = field(default_factory=dict)
    basis: str = ""
    disclaimer: str = (
        "本指數僅反映近期網路公開討論的熱度與情緒聲量，"
        "不代表機構品質、不構成違法或舞弊認定，亦與稽查系統的風險分數無關。"
    )


#: 分項顯示名稱（供 UI 攤開）。
SUBSCORE_LABEL: dict[str, str] = {
    "volume": "討論量",
    "negative": "負面聲量",
    "trend": "趨勢變化",
    "topic": "主題敏感度",
}


def _volume_subscore(recent_total: int) -> float:
    """討論量分（0–100）：近期窗內討論則數對 _VOLUME_FULL_AT 線性封頂。"""
    if recent_total <= 0:
        return 0.0
    return min(100.0, recent_total / _VOLUME_FULL_AT * 100.0)


def _negative_subscore(recent_neg_ratio: float) -> float:
    """負面聲量分（0–100）：近期負面比例直接映射為 0–100。"""
    return max(0.0, min(1.0, recent_neg_ratio)) * 100.0


def _trend_subscore(trend) -> float:
    """趨勢變化分（0–100）：量暴增得 60、負面比例上升得 40，可疊加。"""
    if trend is None:
        return 0.0
    s = 0.0
    if getattr(trend, "surge", False):
        s += 60.0
    if getattr(trend, "neg_ratio_up", False):
        s += 40.0
    return min(100.0, s)


def _topic_subscore(items) -> float:
    """主題敏感分（0–100）：近期項目命中的最高主題敏感度 × 100。

    取「所有近期項目主題敏感度」的最大值（最敏感主題主導），反映家長最關切
    的面向是否被討論；無主題資訊回 0。
    """
    best = 0.0
    for it in items:
        for t in getattr(it, "topics", ()) or ():
            best = max(best, _TOPIC_SENSITIVITY.get(t, _TOPIC_SENSITIVITY["other"]))
    return best * 100.0


def compute_index(items, *, reference: date | None = None,
                  window_days: int = _sw.RECENT_WINDOW_DAYS) -> AttentionIndex:
    """由輿情項目計算輿情關注指數（診斷式白盒，0–100）。

    僅計入傳入的項目（呼叫端應先以 matched=True 過濾，避免同名雜訊）。無項目
    時回傳 total=0、band='none'，並在 basis 說明「尚無公開討論」。

    公式（權重固定、公開）：
        total = 討論量分×0.30 + 負面聲量分×0.30 + 趨勢變化分×0.25 + 主題敏感分×0.15

    band 對齊 sentiment_watch.summarize_attention 的分級語意，確保地圖顏色、
    文字分級與本指數三者一致。
    """
    ref = reference or date.today()

    if not items:
        return AttentionIndex(
            total=0.0, band=_sw.LEVEL_NONE,
            contributions={}, subscores={}, weights=_weights(),
            basis="目前尚未蒐集到與本機構精確對應的公開討論。",
        )

    trend = _sw.detect_trend(items, reference=ref, window_days=window_days)
    summary = _sw.summarize_attention(items, reference=ref, window_days=window_days)

    sub = {
        "volume": round(_volume_subscore(trend.recent_total), 1),
        "negative": round(_negative_subscore(trend.recent_neg_ratio), 1),
        "trend": round(_trend_subscore(trend), 1),
        "topic": round(_topic_subscore(items), 1),
    }
    contrib = {
        "volume": round(sub["volume"] * W_VOLUME, 1),
        "negative": round(sub["negative"] * W_NEGATIVE, 1),
        "trend": round(sub["trend"] * W_TREND, 1),
        "topic": round(sub["topic"] * W_TOPIC, 1),
    }
    total = round(sum(contrib.values()), 0)

    return AttentionIndex(
        total=total,
        band=summary.level,
        contributions=contrib,
        subscores=sub,
        weights=_weights(),
        basis=summary.basis,
    )


def _weights() -> dict[str, float]:
    return {"volume": W_VOLUME, "negative": W_NEGATIVE,
            "trend": W_TREND, "topic": W_TOPIC}


def index_band_label(band: str) -> str:
    """回傳指數分級的家長友善名稱（沿用 parent_map 的用詞語意）。"""
    return {
        _sw.LEVEL_CALM: "平靜期",
        _sw.LEVEL_ACTIVE: "有討論",
        _sw.LEVEL_WATCH: "值得留意",
        _sw.LEVEL_NONE: "尚無公開討論",
    }.get(band, "尚無公開討論")
