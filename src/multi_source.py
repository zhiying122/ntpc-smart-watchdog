"""
多來源風險交叉驗證（Multi-Source Risk Cross-Validation）
================================================================
把「官方資料 × 新聞事件 × 社群輿情 × 司法資料 × 民眾陳情」五層公開資訊，
以機構為單位整合、分類、交叉驗證，產出「需優先關注」的可解釋風險訊號。

核心設計理念（務必嚴守，對齊 requirements.md R19 責任 AI）：
    「AI 可以發現訊號，但不能直接定罪。」
    多個小警訊在同一機構、跨多個獨立來源集中 → 才提高關注度；
    單一來源（尤其新聞／社群／評論）不作為違法認定依據。

五層資料模型與可信度分層（tier）：
  L1 OFFICIAL 官方資料   ── tier=FACT     可信度最高、可進正式風險計分
     （教育局裁罰、行政處分、評鑑、收費、決算、基本資料）
  L2 JUDICIAL 司法資料   ── tier=FACT*    判決確定者為事實；起訴/偵查中為過程（不等於有罪）
     （裁判書、行政處分、行政訴訟）
  L3 NEWS 新聞媒體       ── tier=EVENT    「已被媒體報導的事件」，非違法認定
  L4 PETITION 陳情紀錄   ── tier=EVENT    1999/家長陳情，多次累積為關注訊號
  L5 SOCIAL 社群論壇評論 ── tier=SENTIMENT 只作「網路輿情訊號」，絕不等於違規
     （Dcard / PTT / FB / IG / Google 評論）

「事實 vs 輿情」嚴格分離：
  - FACT 層（官方、判決確定）→ 可進 score_penalty / score_financial 等正式分項。
  - EVENT 層（新聞、陳情、起訴中）→ 標為「事件」，計入關注度但明確非違法。
  - SENTIMENT 層（社群/評論）→ 只計入輿情分項（score_sentiment，貢獻上限 15 分），
    且措辭一律為「網路輿情訊號」而非「違規」。

責任 AI 措辭映射（constructive, 不定罪）：
  Google「老師態度很差」→ 系統呈現「網路輿情：負面評價」，不呈現「教師違規」。

抓取（collect）架構：
  - 合法且穩定來源（PTT web、新聞 RSS、司法院公開查詢）：提供真實 collector 介面。
  - 登入牆/反爬/ToS 限制來源（FB、IG、Google 評論、Dcard）：提供 adapter 介面 +
    誠實標示 `collection_method`，以結構化種子資料示範，架構可接官方 API。
  - 離線 Demo 穩定性：預設讀取 data/raw/multi_source_signals.json 種子；線上抓取為選用。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime

from src.nlp_engine import analyze_text

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_PATH = os.path.join(_ROOT, "data", "raw", "multi_source_signals.json")


# --------------------------------------------------------------------------
# 五層來源與可信度分層
# --------------------------------------------------------------------------
LAYER_OFFICIAL = "official"     # L1 官方
LAYER_JUDICIAL = "judicial"     # L2 司法
LAYER_NEWS = "news"             # L3 新聞
LAYER_PETITION = "petition"     # L4 陳情
LAYER_SOCIAL = "social"         # L5 社群/評論

LAYER_LABEL = {
    LAYER_OFFICIAL: "官方資料",
    LAYER_JUDICIAL: "司法資料",
    LAYER_NEWS: "新聞事件",
    LAYER_PETITION: "陳情紀錄",
    LAYER_SOCIAL: "網路輿情",
}

# 可信度分層（tier）：決定該來源能否進入正式風險計分。
TIER_FACT = "fact"              # 政府確認事實 / 判決確定 → 可進正式分數
TIER_EVENT = "event"           # 已報導事件 / 陳情 / 偵查起訴中 → 關注訊號，非違法
TIER_SENTIMENT = "sentiment"    # 網路輿情 → 僅輿情分項

# 每層預設 tier。
_LAYER_TIER = {
    LAYER_OFFICIAL: TIER_FACT,
    LAYER_JUDICIAL: TIER_FACT,      # 惟需配合 judicial_stage 判定（見下）
    LAYER_NEWS: TIER_EVENT,
    LAYER_PETITION: TIER_EVENT,
    LAYER_SOCIAL: TIER_SENTIMENT,
}

# 司法程序階段：區分「被檢舉 ≠ 被調查 ≠ 被起訴 ≠ 被判決有罪」。
# 只有「判決確定（有罪/處分確定）」才視為 FACT，其餘為 EVENT（過程，不等於有罪）。
JUDICIAL_STAGE_FACT = ("判決確定", "有罪確定", "處分確定", "裁罰確定")
JUDICIAL_STAGE_PROCESS = ("偵查", "起訴", "審理中", "檢舉", "調查", "上訴中")

# 社群平台（L5）識別，供 collector adapter 與 UI 圖示。
SOCIAL_PLATFORMS = ("dcard", "ptt", "facebook", "instagram", "google_review")

# 可即時合法抓取的來源（提供真實 collector）；其餘以 adapter + 種子資料示範。
LIVE_COLLECTABLE = ("ptt", "news_rss", "judicial")


# --------------------------------------------------------------------------
# 輿情微弱訊號（Weak Signal, R9.7）：重大事件爆發前的早期警訊五類
# --------------------------------------------------------------------------
WEAK_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "師資頻繁更換": ("換老師", "老師一直換", "師資不穩", "教師流動", "離職潮",
                "常換老師", "老師離職", "代課"),
    "幼兒抗拒上學": ("不想上學", "抗拒上學", "哭著不去", "怕去學校", "情緒",
                "不肯上學", "拒學"),
    "監視設備異常": ("監視器", "沒有畫面", "調不到", "錄影", "監視死角",
                "攝影機壞", "看不到監視"),
    "管理封閉拒絕溝通": ("不讓進", "拒絕溝通", "不回應", "態度差", "推託",
                  "不處理", "不透明", "封閉", "不讓家長"),
    "照顧安全疑慮": ("受傷", "餵食", "體罰", "不當", "衛生", "餐點", "疏忽",
                "安全", "跌倒", "燙傷"),
}


@dataclass
class WeakSignalResult:
    """單一文本的輿情微弱訊號偵測結果（R9.7, R9.8, R9.11）。"""
    categories: list[str] = field(default_factory=list)   # 命中的訊號類別
    sentiment: str = "neu"                                # pos/neu/neg
    snippet: str = ""                                     # 來源文本片段（證據鏈）
    no_signal: bool = True                                # 未命中任何類別


def detect_weak_signals(text: str, source: str = "") -> WeakSignalResult:
    """偵測家長／社群輿情文本中的五類微弱訊號（R9.7）。

    白盒規則式關鍵字比對（Bedrock 不可用時之 fallback，且完全可解釋）。
    未命中任何類別 → no_signal=True（不產生風險訊號，R9.11）。
    單一輿情文本不作為違法認定依據（R9.8）——本函式僅輸出「訊號」。
    """
    safe = text if isinstance(text, str) else ("" if text is None else str(text))
    hits = [cat for cat, kws in WEAK_SIGNAL_KEYWORDS.items()
            if any(kw in safe for kw in kws)]
    # 情緒傾向：借用 NLP 嚴重度（≥2 視為負向），輿情層以此判關注傾向。
    nlp = analyze_text(safe)
    sentiment = "neg" if (hits or nlp.severity >= 2) else "neu"
    snippet = safe[:60].strip()
    return WeakSignalResult(
        categories=hits,
        sentiment=sentiment,
        snippet=snippet,
        no_signal=not hits,
    )


# --------------------------------------------------------------------------
# 單筆多來源訊號
# --------------------------------------------------------------------------
@dataclass
class SourceSignal:
    """單筆多來源風險訊號（供交叉驗證、UI 呈現與證據鏈追溯）。"""
    layer: str                      # official/judicial/news/petition/social
    tier: str                       # fact/event/sentiment
    text: str
    source: str                     # 平台/媒體名稱（如 PTT、聯合報、Dcard、教育局）
    url: str = ""                   # 原始連結（可追溯）
    date: str = ""                  # 事件/發布日期
    platform: str = ""              # 社群平台鍵（L5 用）
    category: str = ""              # Risk_Taxonomy 分類（NLP）
    sentiment: str = "neu"          # pos/neu/neg
    judicial_stage: str = ""        # 司法階段（L2 用）
    weak_signals: list[str] = field(default_factory=list)  # 命中的微弱訊號類別
    is_demo_sample: bool = False    # 抽樣示範資料標示（R9.10）
    collection_method: str = ""     # 抓取方式（live/adapter/seed），誠實標示

    @property
    def layer_label(self) -> str:
        return LAYER_LABEL.get(self.layer, self.layer)

    @property
    def is_fact(self) -> bool:
        return self.tier == TIER_FACT


# --------------------------------------------------------------------------
# 機構層級交叉驗證結果
# --------------------------------------------------------------------------
@dataclass
class CrossValidationReport:
    """一間機構的多來源交叉驗證彙整。

    交叉驗證原則：獨立來源層（layer）越多、越集中 → 關注度越高。
    但 FACT 與 EVENT/SENTIMENT 嚴格分離：
      - fact_signals 可支持正式風險分項。
      - event/sentiment 僅提高「需關注」程度，不作違法認定。
    """
    park_name: str
    signals: list[SourceSignal] = field(default_factory=list)

    # ---- 分層計數（供風險雷達呈現）----
    def count_by_layer(self) -> dict[str, int]:
        out = {k: 0 for k in LAYER_LABEL}
        for s in self.signals:
            out[s.layer] = out.get(s.layer, 0) + 1
        return out

    @property
    def layers_present(self) -> list[str]:
        return [k for k, v in self.count_by_layer().items() if v > 0]

    @property
    def distinct_layer_count(self) -> int:
        return len(self.layers_present)

    @property
    def fact_signals(self) -> list[SourceSignal]:
        return [s for s in self.signals if s.tier == TIER_FACT]

    @property
    def event_signals(self) -> list[SourceSignal]:
        return [s for s in self.signals if s.tier == TIER_EVENT]

    @property
    def sentiment_signals(self) -> list[SourceSignal]:
        return [s for s in self.signals if s.tier == TIER_SENTIMENT]

    @property
    def negative_sentiment_ratio(self) -> float:
        """社群輿情層的負面比例（0–1），供 score_sentiment。無社群訊號 → 0.0。"""
        soc = self.sentiment_signals
        if not soc:
            return 0.0
        neg = sum(1 for s in soc if s.sentiment == "neg")
        return round(neg / len(soc), 4)

    @property
    def all_weak_signals(self) -> list[str]:
        seen, out = set(), []
        for s in self.signals:
            for w in s.weak_signals:
                if w not in seen:
                    seen.add(w)
                    out.append(w)
        return out

    def cross_validation_level(self) -> str:
        """多來源交叉驗證等級（可解釋，非定罪）。

        依「不同獨立來源層數 + 是否有 FACT 佐證」判定關注度：
          - 'corroborated'（多來源佐證）：≥3 個不同來源層，且至少 1 個 FACT。
          - 'converging'（訊號集中）  ：≥2 個不同來源層。
          - 'single_source'（單一來源）：僅 1 個來源層。
          - 'none'                    ：無訊號。
        """
        n = self.distinct_layer_count
        if n == 0:
            return "none"
        if n >= 3 and len(self.fact_signals) >= 1:
            return "corroborated"
        if n >= 2:
            return "converging"
        return "single_source"

    def attention_notice(self) -> str:
        """行政導向敘事（責任 AI：只說『需關注』，不說『危險/違法』）。"""
        level = self.cross_validation_level()
        n = self.distinct_layer_count
        if level == "corroborated":
            return (f"多來源交叉佐證（{n} 類來源、含官方/司法事實）："
                    "建議列為優先關注並人工查核。風險不等於違法。")
        if level == "converging":
            return (f"多來源訊號集中（{n} 類來源）：建議納入追蹤觀察。"
                    "尚需人工確認，訊號不等於違法。")
        if level == "single_source":
            return "僅單一來源訊號：資訊有限，建議持續監測。訊號不等於違法。"
        return "目前無多來源風險訊號。"


# --------------------------------------------------------------------------
# 分類與載入
# --------------------------------------------------------------------------
def _resolve_tier(layer: str, judicial_stage: str = "") -> str:
    """依來源層與司法階段判定可信度分層（tier）。"""
    if layer == LAYER_JUDICIAL:
        stage = (judicial_stage or "").strip()
        if any(k in stage for k in JUDICIAL_STAGE_FACT):
            return TIER_FACT
        return TIER_EVENT   # 起訴/偵查/檢舉等過程 → 事件（不等於有罪）
    return _LAYER_TIER.get(layer, TIER_EVENT)


def load_signals(data_path: str | None = None) -> list[dict]:
    """載入多來源訊號種子資料；缺失/格式錯誤 → 空清單（優雅降級）。"""
    path = data_path or DEFAULT_DATA_PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else []
    return [i for i in items if isinstance(i, dict)]


def _matches(park_name: str, item: dict) -> bool:
    """機構名稱比對：sector 範圍套用全體；specific 以子字串比對。"""
    scope = str(item.get("scope", "specific")).strip()
    if scope == "sector":
        return True
    key = str(item.get("park_name_match", "")).strip()
    return bool(key) and key in (park_name or "")


def _to_signal(item: dict) -> SourceSignal:
    """把一筆原始 dict 轉為結構化 SourceSignal（含 NLP 分類與微弱訊號）。"""
    layer = str(item.get("layer", LAYER_NEWS)).strip()
    text = str(item.get("text", "")).strip()
    judicial_stage = str(item.get("judicial_stage", "")).strip()
    tier = _resolve_tier(layer, judicial_stage)

    nlp = analyze_text(text)
    # 社群層額外跑微弱訊號偵測（早期預警）。
    weak = []
    social_ws_negative = False
    if layer == LAYER_SOCIAL:
        ws = detect_weak_signals(text, source=str(item.get("source", "")))
        weak = ws.categories
        social_ws_negative = ws.sentiment == "neg"

    # 情緒判定（優先序）：
    #   1) 資料明確標註（pos/neu/neg）→ 採用。
    #   2) 官方/司法 FACT 層或 NLP 嚴重度 ≥2 → 負向關注。
    #   3) 社群層命中任一微弱訊號（如師資頻繁更換、抗拒上學、拒絕溝通）→ 負向輿情，
    #      即使不含「裁罰/違反」等法律詞（社群語言口語化，不應漏判）。
    labeled = item.get("sentiment")
    if labeled in ("pos", "neu", "neg"):
        sentiment = labeled
    elif tier == TIER_FACT or nlp.severity >= 2 or social_ws_negative:
        sentiment = "neg"
    else:
        sentiment = "neu"

    return SourceSignal(
        layer=layer,
        tier=tier,
        text=text,
        source=str(item.get("source", "")).strip(),
        url=str(item.get("url", "")).strip(),
        date=str(item.get("date", "")).strip(),
        platform=str(item.get("platform", "")).strip(),
        category=nlp.category,
        sentiment=sentiment,
        judicial_stage=judicial_stage,
        weak_signals=weak,
        is_demo_sample=bool(item.get("is_demo_sample", False)),
        collection_method=str(item.get("collection_method", "seed")).strip(),
    )


def build_report(park_name: str, items: list[dict] | None = None,
                 data_path: str | None = None) -> CrossValidationReport:
    """彙整某機構適用的多來源訊號，產出交叉驗證報告。"""
    pool = items if items is not None else load_signals(data_path)
    report = CrossValidationReport(park_name=park_name or "")
    for raw in pool:
        if not _matches(park_name, raw):
            continue
        if not str(raw.get("text", "")).strip():
            continue
        report.signals.append(_to_signal(raw))
    return report


def social_neg_ratio_for(park_name: str, items: list[dict] | None = None,
                         data_path: str | None = None) -> float | None:
    """回傳某機構社群輿情負面比例（供 score_sentiment）；無社群訊號 → None。"""
    report = build_report(park_name, items=items, data_path=data_path)
    if not report.sentiment_signals:
        return None
    return report.negative_sentiment_ratio


# --------------------------------------------------------------------------
# 抓取（collect）介面 — 誠實區分「可即時抓取」與「adapter 示範」
# --------------------------------------------------------------------------
@dataclass
class CollectorStatus:
    """單一來源抓取器狀態（供 UI 與資料來源矩陣呈現，誠實揭露）。"""
    source: str
    live_capable: bool          # 是否可即時合法抓取
    method: str                 # 'live_http' / 'official_api' / 'adapter_seed'
    note: str                   # 法遵/技術限制說明
    requires_key: bool = False


def collector_registry() -> list[CollectorStatus]:
    """回傳各來源抓取能力與法遵狀態（誠實揭露，不誇稱可爬）。"""
    return [
        CollectorStatus("PTT（公開 web）", True, "live_http",
                        "www.ptt.cc 公開看板，無需登入，可合法抓取公開文章。"),
        CollectorStatus("新聞（Google News RSS/媒體公開頁）", True, "live_http",
                        "以 RSS/公開頁抓取標題與摘要，來源可追溯。"),
        CollectorStatus("司法院裁判書公開查詢", True, "official_api",
                        "公開判決查詢；區分偵查/起訴/判決確定階段。"),
        CollectorStatus("Dcard", False, "adapter_seed",
                        "官方 API 已收緊、網頁有反爬與登入牆；以 adapter + 種子示範，架構可接官方 API。"),
        CollectorStatus("Google 評論", False, "adapter_seed",
                        "需 Google Places API（金鑰/計費）；爬網頁違反 ToS。以 adapter 示範。",
                        requires_key=True),
        CollectorStatus("Facebook", False, "adapter_seed",
                        "強登入牆、明確禁止爬取；僅能經官方 Graph API 授權存取。以 adapter 示範。",
                        requires_key=True),
        CollectorStatus("Instagram", False, "adapter_seed",
                        "強登入牆、明確禁止爬取；僅能經官方 API 授權存取。以 adapter 示範。",
                        requires_key=True),
    ]


def attach_social_neg_ratio(df, data_path: str | None = None):
    """對整份 DataFrame 附加 neg_ratio（僅取社群輿情層），供 build 管線接入計分。

    以每列 park_name 比對多來源訊號；無社群訊號者 neg_ratio 為 NaN（缺值中性）。
    僅社群層（SENTIMENT）計入 neg_ratio；官方/司法/新聞/陳情不灌入輿情分項，
    維持「事實 vs 輿情」分離。
    """
    import pandas as pd  # noqa: F401

    pool = load_signals(data_path)
    ratios = []
    for _, row in df.iterrows():
        name = str(row.get("park_name", "") or "")
        r = build_report(name, items=pool)
        ratios.append(r.negative_sentiment_ratio if r.sentiment_signals else float("nan"))
    df = df.copy()
    df["neg_ratio"] = ratios
    return df
