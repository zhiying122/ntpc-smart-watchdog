"""
公開輿情時間序列觀測（Public Sentiment Time-Series Watch）— 純邏輯
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的「輿情觀測」核心邏輯。
本模組**不 import streamlit**，只把「公開新聞／公開評論」清單做主題分類、
情緒判斷、時間序列聚合與趨勢變化偵測，輸出家長友善的觀測摘要與時間軸。

資料範圍與合規（極重要）：
--------------------------------------------------------------------------
- 僅處理**公開可查詢**之來源：公開新聞報導、公開商家評論頁、公開論壇公開貼文。
- **不**處理需登入才可見的內容（如私密社團）；本模組僅消費呼叫端提供的、
  已確認為公開來源的資料，不含任何爬蟲行為。
- 每一則資料都保留 **原始來源連結與發布時間**，供家長回到原文自行判斷，
  不以 AI 摘要結論取代原文。

用詞規範（責任 AI，直接決定此功能會不會出事）：
--------------------------------------------------------------------------
1. 不使用「風險」字眼，改用描述性的 **「近期關注度」**（平靜期／有討論／
   值得留意），與後台財務鑑識的「風險」明確區隔——資料基礎不同，可信度不同。
2. 分級一定附「依據」：幾則討論、時間區間、資料來源，讓家長自行判斷可信度。
3. 不產生任何指控性語言（禁止「疑似虐童」「涉嫌詐欺」等）；只描述
   「近期出現與 OO 主題相關之公開討論，建議家長可進一步向園所查證」。
4. 情緒／主題採**規則式關鍵字＋簡單情緒詞典**，透明可解釋、Demo 可控，
   不使用黑箱大型模型下判斷。

技術決策：規則式先行（可解釋、可在問答時說清楚），未來可再接 Bedrock 做
更細緻的摘要，但分級與判斷維持規則式白盒。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable

# ---------------------------------------------------------------------------
# 主題分類（規則式關鍵字，透明可解釋）
# ---------------------------------------------------------------------------
#: 主題代碼 → 家長友善名稱。
TOPIC_LABEL: dict[str, str] = {
    "fee": "收費",
    "teacher": "師資",
    "safety": "安全",
    "teaching": "教學品質",
    "admin": "行政",
    "other": "其他",
}

#: 主題關鍵字表（規則式比對，命中即歸類；可命中多個主題）。
_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "fee": ("收費", "學費", "費用", "代辦費", "月費", "超收", "退費", "註冊費", "價格", "漲價"),
    "teacher": ("老師", "師資", "教師", "師生比", "流動", "離職", "代課", "配置", "人力"),
    "safety": ("安全", "受傷", "意外", "食物", "餐點", "衛生", "環境", "設施", "門禁", "接送"),
    "teaching": ("教學", "課程", "教保", "品質", "才藝", "教材", "進度", "活動"),
    "admin": ("行政", "溝通", "態度", "服務", "報名", "招生", "管理", "回覆", "聯絡"),
}

#: 情緒詞典（簡單、透明）。命中負面詞加負分、正面詞加正分，判定 pos/neg/neu。
_NEG_WORDS: tuple[str, ...] = (
    "差", "爛", "糟", "失望", "不滿", "抱怨", "投訴", "問題", "擔心", "後悔",
    "亂", "貴", "超收", "退費", "受傷", "髒", "不安全", "流動大", "離職", "沒回應",
    "態度不好", "難溝通", "扣款", "爭議",
)
_POS_WORDS: tuple[str, ...] = (
    "好", "推薦", "用心", "貼心", "安心", "滿意", "優質", "認真", "友善", "乾淨",
    "專業", "溫暖", "細心", "放心", "喜歡", "進步",
)

#: 家長版關注度等級代碼（與 parent_map.LEVEL_* 對齊，此處為單一事實來源）。
LEVEL_CALM = "calm"
LEVEL_ACTIVE = "active"
LEVEL_WATCH = "watch"
LEVEL_NONE = "none"

#: 「近期」觀測窗（天）：預設近 90 天為近期，與其前一段等長窗做趨勢比較。
RECENT_WINDOW_DAYS = 90


# ---------------------------------------------------------------------------
# 單筆公開輿情項目
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SentimentItem:
    """單筆公開新聞／公開評論（呈現無關）。

    - source_type：'news'（新聞）或 'review'（公開評論）或 'forum'（公開論壇）。
    - title/excerpt：標題與摘錄（原文片段，供顯示；非 AI 生成結論）。
    - url：原始來源連結（家長可回原文查證，必填語意）。
    - published：發布日期。
    - topics：命中的主題代碼清單（規則式分類結果）。
    - sentiment：'pos'/'neg'/'neu'（規則式情緒判斷結果）。
    """
    source_type: str
    title: str
    excerpt: str
    url: str
    published: date
    source_name: str = ""
    topics: tuple[str, ...] = field(default_factory=tuple)
    sentiment: str = "neu"

    @property
    def source_type_label(self) -> str:
        return {
            "news": "新聞報導",
            "review": "Google 評論",
            "forum": "公開論壇",
            "facebook": "Facebook 公開貼文",
            "instagram": "Instagram 公開貼文",
            "blog": "部落格",
        }.get(self.source_type, "公開來源")

    @property
    def sentiment_label(self) -> str:
        return {"pos": "正面", "neg": "負面", "neu": "中性"}.get(self.sentiment, "中性")

    @property
    def topic_labels(self) -> list[str]:
        return [TOPIC_LABEL.get(t, TOPIC_LABEL["other"]) for t in self.topics] or [TOPIC_LABEL["other"]]


# ---------------------------------------------------------------------------
# 規則式主題分類與情緒判斷（白盒，可在 Demo 時逐字解釋）
# ---------------------------------------------------------------------------
def classify_topics(text: str) -> tuple[str, ...]:
    """對文字做規則式主題分類；命中多主題則全數回傳，皆未命中回 ('other',)。"""
    t = text or ""
    hits = [topic for topic, kws in _TOPIC_KEYWORDS.items() if any(k in t for k in kws)]
    return tuple(hits) if hits else ("other",)


def classify_sentiment(text: str) -> str:
    """規則式情緒判斷：比較負面詞與正面詞命中數。

    - 負面命中數 > 正面命中數 → 'neg'
    - 正面命中數 > 負面命中數 → 'pos'
    - 相等（含皆為 0）→ 'neu'
    透明可解釋：判斷依據就是詞典命中計數，無黑箱。
    """
    t = text or ""
    neg = sum(1 for w in _NEG_WORDS if w in t)
    pos = sum(1 for w in _POS_WORDS if w in t)
    if neg > pos:
        return "neg"
    if pos > neg:
        return "pos"
    return "neu"


def enrich_item(raw: dict) -> SentimentItem:
    """由原始 dict 建立 SentimentItem，並套用規則式主題分類與情緒判斷。

    若原始資料已帶 topics/sentiment 則沿用（供人工校正的資料），否則以
    title+excerpt 文字即時分類。發布時間接受 'YYYY-MM-DD' 字串或 date。
    """
    pub = raw.get("published")
    if isinstance(pub, str):
        pub = datetime.strptime(pub, "%Y-%m-%d").date()
    elif isinstance(pub, datetime):
        pub = pub.date()
    elif not isinstance(pub, date):
        pub = date.today()

    text = f"{raw.get('title', '')} {raw.get('excerpt', '')}"
    topics = tuple(raw.get("topics") or classify_topics(text))
    sentiment = raw.get("sentiment") or classify_sentiment(text)

    return SentimentItem(
        source_type=str(raw.get("source_type", "news")),
        title=str(raw.get("title", "")),
        excerpt=str(raw.get("excerpt", "")),
        url=str(raw.get("url", "")),
        published=pub,
        source_name=str(raw.get("source_name", "")),
        topics=topics,
        sentiment=sentiment,
    )


# ---------------------------------------------------------------------------
# 時間序列聚合（月）與趨勢變化偵測
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MonthlyPoint:
    """單月聚合點（供時間軸/長條圖）。"""
    month: str          # 'YYYY-MM'
    total: int
    neg: int
    pos: int
    neu: int

    @property
    def neg_ratio(self) -> float:
        return (self.neg / self.total) if self.total else 0.0


def monthly_series(items: Iterable[SentimentItem]) -> list[MonthlyPoint]:
    """把輿情項目依「年-月」聚合為時間序列（依月份遞增排序）。"""
    buckets: dict[str, dict[str, int]] = {}
    for it in items:
        key = it.published.strftime("%Y-%m")
        b = buckets.setdefault(key, {"total": 0, "neg": 0, "pos": 0, "neu": 0})
        b["total"] += 1
        b[it.sentiment if it.sentiment in ("neg", "pos") else "neu"] += 1
    return [
        MonthlyPoint(month=m, total=b["total"], neg=b["neg"], pos=b["pos"], neu=b["neu"])
        for m, b in sorted(buckets.items())
    ]


@dataclass(frozen=True)
class TrendSignal:
    """趨勢變化偵測結果（比單一則負評更有觀測意義）。

    - surge：近期討論量相較前期是否明顯增加。
    - neg_ratio_up：近期負面比例相較前期是否上升。
    - recent_total / prior_total：兩期討論量。
    - recent_neg_ratio / prior_neg_ratio：兩期負面比例。
    - top_topic：近期最常出現的主題（家長友善名稱）。
    描述性、不含判斷字眼；供上層組裝「依據」文字。
    """
    surge: bool
    neg_ratio_up: bool
    recent_total: int
    prior_total: int
    recent_neg_ratio: float
    prior_neg_ratio: float
    top_topic: str = ""


def detect_trend(
    items: list[SentimentItem],
    *,
    reference: date | None = None,
    window_days: int = RECENT_WINDOW_DAYS,
) -> TrendSignal:
    """比較「近一個觀測窗」與「其前一個等長窗」的討論量與負面比例。

    趨勢轉折（量暴增或負面比例持續上升）比單一則負評更有觀測意義，故分級
    以此為主要依據，避免因單一負評就把機構標成「值得留意」。

    判定：
      - surge：近期討論量 >= 前期的 2 倍，且近期至少 3 則（避免小樣本噪音）。
      - neg_ratio_up：近期負面比例 - 前期負面比例 >= 0.2，且近期至少 3 則。
    """
    ref = reference or date.today()
    recent_start = ref - timedelta(days=window_days)
    prior_start = ref - timedelta(days=2 * window_days)

    recent = [it for it in items if recent_start < it.published <= ref]
    prior = [it for it in items if prior_start < it.published <= recent_start]

    r_total, p_total = len(recent), len(prior)
    r_neg = sum(1 for it in recent if it.sentiment == "neg")
    p_neg = sum(1 for it in prior if it.sentiment == "neg")
    r_ratio = (r_neg / r_total) if r_total else 0.0
    p_ratio = (p_neg / p_total) if p_total else 0.0

    surge = r_total >= 3 and r_total >= 2 * max(p_total, 1)
    neg_ratio_up = r_total >= 3 and (r_ratio - p_ratio) >= 0.2

    # 近期最常見主題（家長友善名稱）。
    topic_counter: dict[str, int] = {}
    for it in recent:
        for t in it.topics:
            topic_counter[t] = topic_counter.get(t, 0) + 1
    top_topic = ""
    if topic_counter:
        top_code = max(topic_counter, key=lambda k: topic_counter[k])
        top_topic = TOPIC_LABEL.get(top_code, TOPIC_LABEL["other"])

    return TrendSignal(
        surge=surge,
        neg_ratio_up=neg_ratio_up,
        recent_total=r_total,
        prior_total=p_total,
        recent_neg_ratio=r_ratio,
        prior_neg_ratio=p_ratio,
        top_topic=top_topic,
    )


# ---------------------------------------------------------------------------
# 家長友善觀測摘要（分級 + 依據，無指控語言）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AttentionSummary:
    """近期關注度分級與其「依據」（家長友善、可回溯）。

    - level：calm / active / watch / none。
    - basis：分級依據文字（幾則討論、時間區間、資料來源），家長可據此判斷可信度。
    - advice：家長友善建議（保留判斷空間，如「建議可向園所查證」），無指控語言。
    - total_items / recent_items：全部與近期則數。
    - date_range：資料涵蓋的時間區間文字。
    - source_types：資料來源型別清單（新聞/公開評論/公開論壇）。
    """
    level: str
    basis: str
    advice: str
    total_items: int
    recent_items: int
    date_range: str
    source_types: list[str] = field(default_factory=list)
    trend: TrendSignal | None = None


def _date_range_text(items: list[SentimentItem]) -> str:
    if not items:
        return "—"
    lo = min(it.published for it in items)
    hi = max(it.published for it in items)
    if lo == hi:
        return lo.isoformat()
    return f"{lo.isoformat()} ～ {hi.isoformat()}"


def summarize_attention(
    items: list[SentimentItem],
    *,
    reference: date | None = None,
    window_days: int = RECENT_WINDOW_DAYS,
) -> AttentionSummary:
    """把公開輿情整合為家長友善的「近期關注度」分級與依據。

    分級規則（白盒、以趨勢為主，避免單一負評放大恐慌）：
      - none：完全沒有資料 → 「尚無公開輿情資料」，不臆測、不留白。
      - watch（值得留意）：偵測到討論量暴增，或負面比例明顯上升（趨勢轉折）。
      - active（有討論）：有一定量的近期討論但未達趨勢轉折門檻。
      - calm（平靜期）：近期幾乎沒有集中討論。

    每個等級都附「依據」（則數、時間區間、來源、趨勢數字）與「建議」
    （保留判斷空間，不指控）。

    Returns:
        AttentionSummary
    """
    if not items:
        return AttentionSummary(
            level=LEVEL_NONE,
            basis="目前尚未蒐集到此機構的公開網路討論。",
            advice="尚無公開輿情資料並非機構有無問題之判斷；建議家長以官方公開資訊與實地參訪為主要參考。",
            total_items=0,
            recent_items=0,
            date_range="—",
            source_types=[],
            trend=None,
        )

    ref = reference or date.today()
    trend = detect_trend(items, reference=ref, window_days=window_days)
    src_types = sorted({it.source_type_label for it in items})
    date_range = _date_range_text(items)

    # 依趨勢與近期量決定等級。
    if trend.surge or trend.neg_ratio_up:
        level = LEVEL_WATCH
    elif trend.recent_total >= 2:
        level = LEVEL_ACTIVE
    else:
        level = LEVEL_CALM

    # 組裝「依據」文字（家長可自行判斷可信度）。
    basis_parts = [
        f"共蒐集 {len(items)} 則公開資料（{'、'.join(src_types)}）",
        f"時間區間 {date_range}",
        f"近 {window_days} 天有 {trend.recent_total} 則討論",
    ]
    if trend.recent_total:
        basis_parts.append(f"其中負面比例約 {trend.recent_neg_ratio*100:.0f}%")
    if level == LEVEL_WATCH:
        reasons = []
        if trend.surge:
            reasons.append(
                f"近期討論量（{trend.recent_total} 則）較前一時段（{trend.prior_total} 則）明顯增加")
        if trend.neg_ratio_up:
            reasons.append(
                f"近期負面比例（約 {trend.recent_neg_ratio*100:.0f}%）較前一時段"
                f"（約 {trend.prior_neg_ratio*100:.0f}%）上升")
        basis_parts.append("；".join(reasons))
    basis = "；".join(basis_parts) + "。"

    # 建議文字（保留判斷空間、不指控）。
    if level == LEVEL_WATCH:
        topic_txt = f"與「{trend.top_topic}」相關之" if trend.top_topic else ""
        advice = (
            f"近期網路上出現較多{topic_txt}公開討論，這是「討論的變化」而非事實認定。"
            "建議家長可將此列為了解重點，主動向園所查證，並回到下方原始連結閱讀原文自行判斷。"
        )
    elif level == LEVEL_ACTIVE:
        advice = (
            "近期有一些公開討論，屬常見範圍。建議家長參考下方原文，"
            "並以實地參訪與官方公開資訊作為主要判斷依據。"
        )
    else:
        advice = (
            "近期沒有明顯集中的公開討論。建議家長仍以實地參訪與官方公開資訊為主要參考。"
        )

    return AttentionSummary(
        level=level,
        basis=basis,
        advice=advice,
        total_items=len(items),
        recent_items=trend.recent_total,
        date_range=date_range,
        source_types=src_types,
        trend=trend,
    )


# ---------------------------------------------------------------------------
# 載入示範資料（由頁面以快取包裝）
# ---------------------------------------------------------------------------
def load_items_from_records(records: Iterable[dict]) -> list[SentimentItem]:
    """把原始 dict 記錄轉為 SentimentItem 清單（套用規則式分類），依時間排序。"""
    items = [enrich_item(r) for r in records]
    return sorted(items, key=lambda it: it.published)
