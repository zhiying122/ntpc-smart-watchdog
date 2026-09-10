"""
NLP_Engine 單元測試（Task 10.1）
==================================
驗證 src/nlp_engine.py 的文本分類、違規/嚴重度辨識、關鍵字/主題抽取、
事件摘要與時間軸，以及 Risk_Taxonomy 歸類與無法歸類保留原文的行為。

對應 Requirements 9.1, 9.2, 9.3, 9.4, 9.5, 9.6。
（Property 27 屬性測試由 Task 10.2 實作，本檔僅具體案例單元測試。）
"""
from src.nlp_engine import (
    CATEGORY_ADMIN,
    CATEGORY_CARE,
    CATEGORY_FEE,
    CATEGORY_FINANCE,
    CATEGORY_OTHER,
    CATEGORY_PERSONNEL,
    CATEGORY_SAFETY,
    NLPResult,
    RISK_TAXONOMY,
    analyze_text,
)


# --------------------------------------------------------------------------
# R9.1 / R9.5：分類至 Risk_Taxonomy
# --------------------------------------------------------------------------
def test_result_type_and_category_in_taxonomy():
    """analyze_text 回傳 NLPResult，且分類恆為 Risk_Taxonomy 之一（R9.1, R9.5）。"""
    r = analyze_text("該園超收註冊費。", "裁罰")
    assert isinstance(r, NLPResult)
    assert r.category in RISK_TAXONOMY


def test_classify_fee():
    """收費相關文本歸類為『收費』（R9.5）。"""
    r = analyze_text("查獲業者超收註冊費與月費，違反收退費規定。", "裁罰")
    assert r.category == CATEGORY_FEE


def test_classify_safety():
    """安全事故文本歸類為『安全』（R9.5）。"""
    r = analyze_text("幼童搭乘娃娃車發生交通意外導致受傷，消防到場處理。", "公告")
    assert r.category == CATEGORY_SAFETY


def test_classify_care():
    """照顧/管教文本歸類為『照顧』（R9.5）。"""
    r = analyze_text("教保員對幼童不當管教並有體罰情事，涉及照護疏忽。", "評鑑")
    assert r.category == CATEGORY_CARE


def test_classify_personnel():
    """人事/師資文本歸類為『人事』（R9.5）。"""
    r = analyze_text("查獲聘用無照教師，師生比不符員額規定。", "裁罰")
    assert r.category == CATEGORY_PERSONNEL


def test_classify_finance():
    """財務/帳目文本歸類為『財務』（R9.5）。"""
    r = analyze_text("決算書帳目異常，補助款疑遭挪用，會計核銷有缺失。", "評鑑")
    assert r.category == CATEGORY_FINANCE


def test_classify_admin():
    """行政/立案文本歸類為『行政』（R9.5）。"""
    r = analyze_text("園所未依規定辦理立案變更登記，文件申報程序不全。", "公告")
    assert r.category == CATEGORY_ADMIN


# --------------------------------------------------------------------------
# R9.6：無法歸類 → 「其他」並保留原文
# --------------------------------------------------------------------------
def test_unclassifiable_falls_back_to_other_and_keeps_raw_text():
    """無關鍵詞命中的文本歸為『其他』且保留原始文本（R9.6）。"""
    raw = "今天天氣晴朗適合戶外教學。"
    r = analyze_text(raw, "公告")
    assert r.category == CATEGORY_OTHER
    assert r.unclassified is True
    assert r.raw_text == raw
    assert r.raw_text.strip() != ""


def test_empty_text_classified_as_other():
    """空字串安全處理，歸為『其他』不拋例外（R9.6）。"""
    r = analyze_text("", "unknown")
    assert r.category == CATEGORY_OTHER
    assert r.unclassified is True


def test_none_text_is_safe():
    """None 輸入不拋例外，轉為空字串並歸『其他』。"""
    r = analyze_text(None, "unknown")  # type: ignore[arg-type]
    assert r.category == CATEGORY_OTHER


# --------------------------------------------------------------------------
# R9.2：違規類型與嚴重度
# --------------------------------------------------------------------------
def test_severity_high_for_serious_violation():
    """『廢止立案』等嚴重違規判為高嚴重度（R9.2）。"""
    r = analyze_text("因重大缺失遭廢止立案並移送法辦。", "裁罰")
    assert r.severity == 3
    assert r.severity_label == "高"
    assert r.violation_type is not None


def test_severity_medium_for_fine():
    """『罰鍰/裁罰』判為中嚴重度（R9.2）。"""
    r = analyze_text("違反規定經裁罰罰鍰並限期改善。", "裁罰")
    assert r.severity == 2
    assert r.severity_label == "中"


def test_severity_zero_when_no_signal():
    """無嚴重度訊號時 severity 為 0、標籤為未判定。"""
    r = analyze_text("園方舉辦親子日活動。", "公告")
    assert r.severity == 0
    assert r.severity_label == "未判定"
    assert r.violation_type is None


# --------------------------------------------------------------------------
# R9.3：關鍵字與主題
# --------------------------------------------------------------------------
def test_keywords_extracted_and_deduped():
    """抽取關鍵字，含分類命中詞與嚴重度詞且去重（R9.3）。"""
    r = analyze_text("超收註冊費，違反收費規定，遭裁罰。", "裁罰")
    assert "收費" in r.keywords
    assert "超收" in r.keywords
    # 去重：無重複元素
    assert len(r.keywords) == len(set(r.keywords))


def test_topics_lead_with_category():
    """主題以分類為首（R9.3）。"""
    r = analyze_text("超收註冊費。", "裁罰")
    assert r.topics[0] == r.category


# --------------------------------------------------------------------------
# R9.4：事件摘要與時間軸
# --------------------------------------------------------------------------
def test_timeline_extracts_roc_date():
    """抽取民國年月日事件時間軸（R9.4）。"""
    r = analyze_text("112年5月3日該園發生食物中毒事件。", "公告")
    assert len(r.timeline) >= 1
    dates = [d for d, _ in r.timeline]
    assert any("112年5月3日" in d for d in dates)


def test_timeline_ordered_by_appearance():
    """多個日期依出現順序排列（R9.4）。"""
    r = analyze_text("112年1月1日提出申請；112年6月1日限期改善。", "裁罰")
    dates = [d for d, _ in r.timeline]
    assert dates == sorted(dates, key=lambda d: r.raw_text.index(d))


def test_summary_is_first_sentence():
    """事件摘要取首句（R9.4）。"""
    r = analyze_text("該園違反收費規定。後續已完成改善。", "裁罰")
    assert r.summary == "該園違反收費規定"


def test_summary_truncates_long_text():
    """過長首句被截斷並附省略號（R9.4）。"""
    long_sentence = "違規" * 100
    r = analyze_text(long_sentence, "裁罰")
    assert r.summary.endswith("…")
    assert len(r.summary) <= 81  # max_len(80) + 省略號
