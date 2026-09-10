"""
NLP 文字分析與風險分類體系（NLP_Engine）
==========================================
小小守護員 Smart Watchdog Platform — 將非結構化文字（裁罰／評鑑／公告）轉為
可用的風險訊號。對應 design.md「6. NLP_Engine」與 requirements.md「Requirement 9」。

核心原則（對齊專案護城河）：
- 本引擎屬「輿情／文本訊號」層，產出**可解釋**的分類與抽取結果，供風險分數的
  NLP 分項與稽查員判讀使用；AI 不參與計分，分類採規則式關鍵詞比對（白盒、可攤開）。
- 依 Risk_Taxonomy 歸類為 收費／人事／照顧／安全／行政／財務／其他（R9.5）。
- 文本無法對應任一既定分類時 → 歸為「其他」並**保留原始文本供人工判讀**（R9.6）。

本模組為淨新增，且僅依賴標準函式庫，不引入額外執行期相依，維持既有基線可攜性。
`NLPResult` 型別定義於本模組（與其他共用型別 src/models.py 分離，因其為 NLP 專用契約）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Risk_Taxonomy 風險分類體系（R9.5, R9.6）
# --------------------------------------------------------------------------
# 七大分類；「其他」為預設收容分類（無法歸類時使用）。
CATEGORY_FEE = "收費"
CATEGORY_PERSONNEL = "人事"
CATEGORY_CARE = "照顧"
CATEGORY_SAFETY = "安全"
CATEGORY_ADMIN = "行政"
CATEGORY_FINANCE = "財務"
CATEGORY_OTHER = "其他"

RISK_TAXONOMY: tuple[str, ...] = (
    CATEGORY_FEE,
    CATEGORY_PERSONNEL,
    CATEGORY_CARE,
    CATEGORY_SAFETY,
    CATEGORY_ADMIN,
    CATEGORY_FINANCE,
    CATEGORY_OTHER,
)

# 每個分類的關鍵詞集合（規則式、可解釋）。順序即為判定優先序：
# 命中越靠前的分類優先，多個分類同時命中時取命中關鍵詞數最多者，平手取優先序。
# 「其他」不含關鍵詞，作為預設收容分類（R9.6）。
_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    CATEGORY_SAFETY: (
        "安全", "意外", "受傷", "跌倒", "燙傷", "食物中毒", "消防", "逃生",
        "遊具", "娃娃車", "交通車", "接送", "校車", "危險", "傷害", "災害",
    ),
    CATEGORY_CARE: (
        "照顧", "照護", "體罰", "虐待", "不當管教", "疏忽", "餵食", "午睡",
        "衛生", "保育", "情緒", "身心", "餐點", "營養", "生病", "疾病",
    ),
    CATEGORY_FEE: (
        "收費", "費用", "超收", "退費", "註冊費", "月費", "代辦費", "雜費",
        "溢收", "學費", "價格", "繳費", "收退費",
    ),
    CATEGORY_PERSONNEL: (
        "人事", "教師", "教保員", "師資", "員額", "聘用", "資格", "無照",
        "師生比", "人力", "勞動", "薪資", "加班", "離職", "人員", "任用",
    ),
    CATEGORY_FINANCE: (
        "財務", "財報", "決算", "預算", "帳目", "會計", "經費", "補助款",
        "挪用", "核銷", "發票", "款項", "收支", "盈餘", "短絀", "審計",
    ),
    CATEGORY_ADMIN: (
        "行政", "立案", "登記", "變更", "備查", "文件", "申報", "程序",
        "公告", "評鑑", "設立", "許可", "證照", "違規", "改善", "限期",
    ),
}

# 違規/嚴重度關鍵詞 → 嚴重度分數（1 低、2 中、3 高）。可攤開解釋。
_SEVERITY_KEYWORDS: dict[str, int] = {
    # 高嚴重度
    "廢止": 3, "撤銷": 3, "停辦": 3, "停止招生": 3, "移送": 3, "刑事": 3,
    "虐待": 3, "食物中毒": 3, "重大": 3, "死亡": 3, "勒令": 3,
    # 中嚴重度
    "裁罰": 2, "罰鍰": 2, "處分": 2, "違反": 2, "超收": 2, "體罰": 2,
    "限期改善": 2, "缺失": 2, "查獲": 2, "違法": 2, "違規": 2,
    # 低嚴重度
    "提醒": 1, "建議": 1, "輔導": 1, "注意": 1, "改進": 1, "缺漏": 1,
}

_SEVERITY_LABEL = {1: "低", 2: "中", 3: "高"}

# 事件時間軸抽取：民國年月日與西元年月日的簡易樣式。
_DATE_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 民國年：如 112年5月3日 / 112年5月 / 112/5/3
    re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月(?:\s*(\d{1,2})\s*日)?"),
    # 西元年：如 2023年5月3日 / 2023-05-03 / 2023/5/3
    re.compile(r"(\d{4})[/\-年]\s*(\d{1,2})[/\-月]\s*(\d{1,2})?\s*日?"),
)


# --------------------------------------------------------------------------
# NLPResult — NLP 分析結果契約（R9.1–R9.6）
# --------------------------------------------------------------------------
@dataclass
class NLPResult:
    """單一文本的結構化 NLP 分析結果。

    欄位對應驗收準則：
    - category：Risk_Taxonomy 之一（收費/人事/照顧/安全/行政/財務/其他）（R9.5）。
    - doc_type：來源文件類型（裁罰/評鑑/公告等），由呼叫端提供。
    - violation_type：辨識出的違規類型（可為 None 表示未辨識）（R9.2）。
    - severity / severity_label：嚴重程度（1/2/3 對應 低/中/高）（R9.2）。
    - keywords / topics：抽取的關鍵字與主題（R9.3）。
    - summary：事件摘要（R9.4）。
    - timeline：事件時間軸，元素為（日期字串, 事件片段）（R9.4）。
    - unclassified：True 表示無法對應任一既定分類，歸「其他」（R9.6）。
    - raw_text：原始文本；無法歸類時**必為非空**以供人工判讀（R9.6）。

    Validates: Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
    """
    category: str
    doc_type: str
    raw_text: str
    violation_type: str | None = None
    severity: int = 0                              # 0 表示未偵測到嚴重度訊號
    severity_label: str = "未判定"
    keywords: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    summary: str = ""
    timeline: list[tuple[str, str]] = field(default_factory=list)
    unclassified: bool = False


# --------------------------------------------------------------------------
# 主要 API
# --------------------------------------------------------------------------
def analyze_text(text: str, doc_type: str = "unknown") -> NLPResult:
    """分析文本並產出 NLPResult。

    步驟（全部可解釋）：
      1. 分類（R9.1, R9.5）：規則式關鍵詞比對至 Risk_Taxonomy。
      2. 違規類型與嚴重度（R9.2）。
      3. 關鍵字／主題抽取（R9.3）。
      4. 事件摘要與時間軸（R9.4）。
      5. 無法歸類 → 「其他」並保留原文（R9.6）。

    Args:
        text: 待分析文本（裁罰／評鑑／公告等）。
        doc_type: 來源文件類型標籤，僅記錄於結果，不影響分類邏輯。

    Returns:
        NLPResult：分類結果恆為 Risk_Taxonomy 之一。
    """
    safe_text = text if isinstance(text, str) else ("" if text is None else str(text))

    category, matched_keywords, unclassified = _classify(safe_text)
    violation_type, severity = _detect_violation(safe_text)
    keywords = _extract_keywords(safe_text, matched_keywords)
    topics = _extract_topics(category, matched_keywords)
    timeline = _extract_timeline(safe_text)
    summary = _summarize(safe_text)

    # R9.6：無法歸類時保留原始文本供人工判讀（原文非空時 raw_text 必非空）。
    return NLPResult(
        category=category,
        doc_type=doc_type,
        raw_text=safe_text,
        violation_type=violation_type,
        severity=severity,
        severity_label=_SEVERITY_LABEL.get(severity, "未判定"),
        keywords=keywords,
        topics=topics,
        summary=summary,
        timeline=timeline,
        unclassified=unclassified,
    )


# --------------------------------------------------------------------------
# 內部輔助函式（皆為純函式，便於測試）
# --------------------------------------------------------------------------
def _classify(text: str) -> tuple[str, list[str], bool]:
    """規則式分類至 Risk_Taxonomy。

    Returns:
        (category, matched_keywords, unclassified)
        - category 恆為 RISK_TAXONOMY 之一。
        - 無任何關鍵詞命中 → ('其他', [], True)（R9.6）。
    """
    best_category = CATEGORY_OTHER
    best_hits: list[str] = []

    for category, keywords in _CATEGORY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw in text]
        if not hits:
            continue
        # 取命中關鍵詞數最多者；平手時保留先出現（dict 插入序即優先序）的分類。
        if len(hits) > len(best_hits):
            best_category = category
            best_hits = hits

    if not best_hits:
        # 無法對應任一既定分類 → 「其他」並標記 unclassified（R9.6）。
        return CATEGORY_OTHER, [], True

    return best_category, best_hits, False


def _detect_violation(text: str) -> tuple[str | None, int]:
    """辨識違規類型與嚴重程度（R9.2）。

    - severity 取所有命中嚴重度關鍵詞的最大值（最嚴重者主導）。
    - violation_type 取觸發該最大嚴重度的關鍵詞；無命中則 (None, 0)。
    """
    max_severity = 0
    violation_type: str | None = None
    for keyword, level in _SEVERITY_KEYWORDS.items():
        if keyword in text and level > max_severity:
            max_severity = level
            violation_type = keyword
    return violation_type, max_severity


def _extract_keywords(text: str, matched_keywords: list[str]) -> list[str]:
    """抽取關鍵字（R9.3）：分類命中詞 + 命中的嚴重度關鍵詞，去重且保序。"""
    found: list[str] = list(matched_keywords)
    for keyword in _SEVERITY_KEYWORDS:
        if keyword in text:
            found.append(keyword)
    # 去重保序
    seen: set[str] = set()
    unique: list[str] = []
    for kw in found:
        if kw not in seen:
            seen.add(kw)
            unique.append(kw)
    return unique


def _extract_topics(category: str, matched_keywords: list[str]) -> list[str]:
    """主題分析（R9.3）：以分類為主主題，命中關鍵詞為次主題。"""
    topics: list[str] = [category]
    for kw in matched_keywords:
        if kw not in topics:
            topics.append(kw)
    return topics


def _extract_timeline(text: str) -> list[tuple[str, str]]:
    """抽取事件時間軸（R9.4）：找出日期字樣並附鄰近文本片段。

    回傳依日期於文本中出現順序排列的 (日期字串, 事件片段) 清單。
    """
    events: list[tuple[int, str, str]] = []
    for pattern in _DATE_PATTERNS:
        for m in pattern.finditer(text):
            date_str = m.group(0).strip()
            start = m.start()
            end = m.end()
            # 取日期後方最多 40 字作為事件片段（若無則取前方）。
            snippet = text[end:end + 40].strip()
            if not snippet:
                snippet = text[max(0, start - 40):start].strip()
            events.append((start, date_str, snippet))

    # 依出現位置排序，去除重疊的重複日期字串。
    events.sort(key=lambda e: e[0])
    seen_dates: set[str] = set()
    timeline: list[tuple[str, str]] = []
    for _, date_str, snippet in events:
        if date_str in seen_dates:
            continue
        seen_dates.add(date_str)
        timeline.append((date_str, snippet))
    return timeline


def _summarize(text: str, max_len: int = 80) -> str:
    """產出事件摘要（R9.4）：取首個語句（以句號/換行斷句），超長截斷。"""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ""
    # 以中文句號、驚嘆號、問號或換行為斷句依據。
    parts = re.split(r"[。！？\n]", normalized)
    first = next((p.strip() for p in parts if p.strip()), normalized)
    if len(first) > max_len:
        return first[:max_len] + "…"
    return first
