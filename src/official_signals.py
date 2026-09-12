"""
官方公開信號（Official Public Signals）
======================================
以「全國教保資訊網 / 新北市幼兒教育資源網」的官方公開資料——
裁罰紀錄與評鑑等第——作為機構關注信號的來源。

設計原則（對齊 spec）：
- 這是真實、官方、可追溯的公開資料，公信力高於社群評論，
  且完全免費、免金鑰、無爬蟲法遵風險。
- 依 Risk_Taxonomy（收費/人事/照顧/安全/行政/財務/其他）為每筆裁罰歸類，
  並依破窗效應嚴重度概念（輕微/中度/重大）標記嚴重度。
- 每一筆信號皆附來源標示，供 Evidence_Chain 追溯（R11、R9.8）。
- 責任邊界：本模組僅「呈現官方已公開的事實」，不作違法/舞弊認定（R19）。

輸出為結構化 dict，供 UI 呈現與後續（選用）納入輿情分項使用。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 資料來源標示（供 Evidence_Chain）
SOURCE_PENALTY = "全國教保資訊網－裁罰紀錄"
SOURCE_EVAL = "全國教保資訊網－評鑑結果"

# 嚴重度分級（對齊 R25 破窗效應嚴重度概念：輕微/中度/重大）
SEVERITY_MINOR = "輕微"
SEVERITY_MODERATE = "中度"
SEVERITY_MAJOR = "重大"

# 情緒/關注傾向標籤（沿用既有頁面的三態，讓 UI 一致）
SENTIMENT_NEG = "neg"   # 負向關注（有裁罰、評鑑待改進）
SENTIMENT_NEU = "neu"   # 中性（一般）
SENTIMENT_POS = "pos"   # 正向（評鑑優良、無裁罰）

# 裁罰事由關鍵字 → (Risk_Taxonomy 類別, 嚴重度)
# 依教保機構常見違規態樣歸類；找不到對應時歸「其他/中度」。
_PENALTY_RULES: list[tuple[tuple[str, ...], str, str]] = [
    (("超收", "收費", "退費"), "收費", SEVERITY_MINOR),
    (("師生比", "人員資格", "資格不符", "未具資格"), "人事", SEVERITY_MODERATE),
    (("設施", "安全", "設備"), "安全", SEVERITY_MODERATE),
    (("照顧", "虐", "體罰", "餐點", "衛生"), "照顧", SEVERITY_MAJOR),
    (("財務", "申報", "決算", "帳"), "財務", SEVERITY_MODERATE),
    (("隱匿", "規避", "拒絕稽查", "未配合"), "行政", SEVERITY_MAJOR),
    (("公開", "公告", "資訊"), "行政", SEVERITY_MINOR),
]

# 評鑑等第 → (關注傾向, 說明)
_EVAL_RULES: dict[str, tuple[str, str]] = {
    "優": (SENTIMENT_POS, "評鑑優良，無明顯待改進事項"),
    "良": (SENTIMENT_NEU, "評鑑良好，屬一般水準"),
    "乙": (SENTIMENT_NEG, "評鑑列乙等，存在待改進事項"),
    "待改進": (SENTIMENT_NEG, "評鑑列待改進，須追蹤缺失改善"),
}


@dataclass
class OfficialSignal:
    """單一官方公開信號（裁罰或評鑑），供 UI 呈現與證據鏈追溯。"""
    text: str            # 呈現用描述
    sentiment: str       # pos / neu / neg（關注傾向）
    category: str        # Risk_Taxonomy 類別
    severity: str        # 輕微 / 中度 / 重大 / 一般
    source: str          # 官方資料來源標示（Evidence_Chain）
    signal_type: str     # "penalty" | "eval"


@dataclass
class OfficialSignalReport:
    """單一機構的官方公開信號彙整。"""
    park_name: str
    signals: list[OfficialSignal] = field(default_factory=list)
    penalty_count: int = 0
    eval_grade: str | None = None

    @property
    def negative_count(self) -> int:
        return sum(1 for s in self.signals if s.sentiment == SENTIMENT_NEG)

    @property
    def total_count(self) -> int:
        return len(self.signals)

    @property
    def negative_ratio(self) -> float:
        return self.negative_count / self.total_count if self.total_count else 0.0


def classify_penalty(reason: str) -> tuple[str, str]:
    """依裁罰事由歸類 Risk_Taxonomy 類別與嚴重度（R9.5）。

    無法對應任一既定分類時歸為「其他」/中度（R9.6 精神）。
    """
    text = (reason or "").strip()
    if not text:
        return ("其他", SEVERITY_MODERATE)
    for keywords, category, severity in _PENALTY_RULES:
        if any(kw in text for kw in keywords):
            return (category, severity)
    return ("其他", SEVERITY_MODERATE)


def _to_int(value) -> int:
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _clean_str(value) -> str:
    """安全轉字串：None、pandas NaN、字串 'nan' 皆視為空字串。"""
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan" or text == "":
        return ""
    return text


def build_report(row: dict) -> OfficialSignalReport:
    """將契約檔一列（dict）轉為官方公開信號彙整。

    讀取 park_name / penalty_count / penalty_reason / eval_grade 等既有欄位，
    產出結構化信號清單，每筆附來源標示供追溯。
    """
    park_name = _clean_str(row.get("park_name"))
    penalty_count = _to_int(row.get("penalty_count"))
    reason = _clean_str(row.get("penalty_reason"))
    grade = _clean_str(row.get("eval_grade")) or None

    report = OfficialSignalReport(
        park_name=park_name,
        penalty_count=penalty_count,
        eval_grade=grade,
    )

    # 裁罰信號
    if penalty_count > 0 and reason:
        category, severity = classify_penalty(reason)
        report.signals.append(OfficialSignal(
            text=f"裁罰紀錄：{reason}（共 {penalty_count} 次）",
            sentiment=SENTIMENT_NEG,
            category=category,
            severity=severity,
            source=SOURCE_PENALTY,
            signal_type="penalty",
        ))
    elif penalty_count == 0:
        report.signals.append(OfficialSignal(
            text="裁罰紀錄：近期無裁罰",
            sentiment=SENTIMENT_POS,
            category="行政",
            severity="一般",
            source=SOURCE_PENALTY,
            signal_type="penalty",
        ))

    # 評鑑信號
    if grade:
        sentiment, note = _EVAL_RULES.get(grade, (SENTIMENT_NEU, f"評鑑等第：{grade}"))
        report.signals.append(OfficialSignal(
            text=f"評鑑結果：{grade} 等——{note}",
            sentiment=sentiment,
            category="行政",
            severity="一般",
            source=SOURCE_EVAL,
            signal_type="eval",
        ))

    return report
