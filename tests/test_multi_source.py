"""
多來源風險交叉驗證單元測試（Multi-Source Cross-Validation）
================================================================
驗證 src.multi_source 的五層資料模型、事實/輿情分離、司法階段區分、
輿情微弱訊號偵測、交叉驗證等級判定與責任 AI 邊界（不定罪）。

責任 AI 核心：AI 可以發現訊號，但不能直接定罪。
"""
from hypothesis import given, settings
from hypothesis import strategies as st

from src.multi_source import (LAYER_JUDICIAL, LAYER_NEWS, LAYER_OFFICIAL,
                              LAYER_PETITION, LAYER_SOCIAL, TIER_EVENT,
                              TIER_FACT, TIER_SENTIMENT, CrossValidationReport,
                              build_report, collector_registry,
                              detect_weak_signals, social_neg_ratio_for)


def _item(layer, text, scope="specific", match="測試幼兒園", **extra):
    d = {"layer": layer, "text": text, "scope": scope, "park_name_match": match}
    d.update(extra)
    return d


# --------------------------------------------------------------------------
# 輿情微弱訊號偵測（R9.7, R9.11）
# --------------------------------------------------------------------------
def test_weak_signal_detects_teacher_turnover():
    """『老師一直換』→ 命中『師資頻繁更換』。"""
    r = detect_weak_signals("這間園老師一直換，師資很不穩定")
    assert "師資頻繁更換" in r.categories
    assert r.no_signal is False
    assert r.sentiment == "neg"


def test_weak_signal_detects_multiple_categories():
    """一段文本可命中多類微弱訊號。"""
    r = detect_weak_signals("孩子不想上學，而且監視器都調不到畫面")
    assert "幼兒抗拒上學" in r.categories
    assert "監視設備異常" in r.categories


def test_weak_signal_no_signal_when_neutral():
    """中性文本 → no_signal=True，不產生風險訊號（R9.11）。"""
    r = detect_weak_signals("今天天氣很好，孩子開心地玩遊戲")
    assert r.no_signal is True
    assert r.categories == []


def test_weak_signal_keeps_snippet_for_traceability():
    """保留來源文本片段供證據鏈追溯（R9.8）。"""
    r = detect_weak_signals("園方拒絕溝通，態度差")
    assert r.snippet != ""


# --------------------------------------------------------------------------
# 事實 vs 輿情分層（tier）與司法階段區分
# --------------------------------------------------------------------------
def test_official_layer_is_fact():
    """官方裁罰 → 事實層（可進正式計分）。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_OFFICIAL, "教育局裁罰：收費違規", sentiment="neg")])
    assert rep.signals[0].tier == TIER_FACT


def test_news_layer_is_event_not_fact():
    """新聞 → 事件層（非違法認定）。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_NEWS, "媒體報導疑似不當管教")])
    assert rep.signals[0].tier == TIER_EVENT


def test_social_layer_is_sentiment():
    """社群評論 → 輿情層。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_SOCIAL, "Google 評論：老師態度很差", platform="google_review")])
    assert rep.signals[0].tier == TIER_SENTIMENT


def test_judicial_conviction_is_fact_but_indictment_is_event():
    """判決確定=事實；起訴/偵查中=事件（被起訴≠被判決有罪）。"""
    convicted = build_report("測試幼兒園", items=[
        _item(LAYER_JUDICIAL, "行政處分確定", judicial_stage="處分確定", sentiment="neg")])
    indicted = build_report("測試幼兒園", items=[
        _item(LAYER_JUDICIAL, "遭起訴，審理中", judicial_stage="起訴")])
    assert convicted.signals[0].tier == TIER_FACT
    assert indicted.signals[0].tier == TIER_EVENT


# --------------------------------------------------------------------------
# 交叉驗證等級（多來源集中才提高關注，非定罪）
# --------------------------------------------------------------------------
def test_cross_validation_corroborated_needs_three_layers_and_fact():
    """≥3 類來源且含事實層 → corroborated。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_OFFICIAL, "裁罰：收費違規", sentiment="neg"),   # fact
        _item(LAYER_NEWS, "媒體報導收費爭議"),                       # event
        _item(LAYER_SOCIAL, "Google：老師態度很差，不願溝通",
              platform="google_review"),                            # sentiment
    ])
    assert rep.distinct_layer_count == 3
    assert rep.cross_validation_level() == "corroborated"
    assert "優先" in rep.attention_notice()


def test_cross_validation_converging_two_layers_no_fact():
    """2 類來源、無事實層 → converging（訊號集中，需人工確認）。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_NEWS, "媒體報導爭議"),
        _item(LAYER_SOCIAL, "PTT 討論：師資一直換", platform="ptt"),
    ])
    assert rep.cross_validation_level() == "converging"
    assert "違法" in rep.attention_notice()  # 敘事含「不等於違法」責任聲明


def test_cross_validation_single_source():
    """單一來源 → single_source。"""
    rep = build_report("測試幼兒園", items=[
        _item(LAYER_SOCIAL, "Dcard 一篇討論", platform="dcard")])
    assert rep.cross_validation_level() == "single_source"


def test_cross_validation_none_when_no_signal():
    """無任何訊號 → none。"""
    rep = build_report("查無此園", items=[
        _item(LAYER_NEWS, "與本園無關", match="別間園")])
    assert rep.cross_validation_level() == "none"


# --------------------------------------------------------------------------
# 社群負面比例（僅社群層計入 neg_ratio；事實/事件不灌入輿情）
# --------------------------------------------------------------------------
def test_neg_ratio_only_from_social_layer():
    """neg_ratio 只由社群層計算；官方/新聞不影響輿情比例。"""
    items = [
        _item(LAYER_OFFICIAL, "裁罰：收費違規", sentiment="neg"),
        _item(LAYER_NEWS, "媒體報導"),
        _item(LAYER_SOCIAL, "Google：態度差不溝通", platform="google_review"),
        _item(LAYER_SOCIAL, "Google：環境整潔老師用心", platform="google_review",
              sentiment="pos"),
    ]
    ratio = social_neg_ratio_for("測試幼兒園", items=items)
    # 兩筆社群：1 負 1 正 → 0.5
    assert ratio == 0.5


def test_neg_ratio_none_when_no_social():
    """無社群訊號 → None（讓 score_sentiment 中性處理，不放大）。"""
    items = [_item(LAYER_OFFICIAL, "裁罰：收費違規", sentiment="neg")]
    assert social_neg_ratio_for("測試幼兒園", items=items) is None


def test_sector_scope_applies_to_all():
    """sector 範圍套用於所有機構（產業背景訊號）。"""
    items = [_item(LAYER_NEWS, "產業層級違規統計", scope="sector", match="")]
    rep = build_report("任何一間園", items=items)
    assert len(rep.signals) == 1


# --------------------------------------------------------------------------
# 抓取能力誠實揭露：FB/IG/Google 不宣稱可即時抓取
# --------------------------------------------------------------------------
def test_collector_registry_honest_about_capabilities():
    """PTT/新聞/司法可即時抓取；FB/IG/Google 標為 adapter（不誇稱可爬）。"""
    reg = {c.source: c for c in collector_registry()}
    live = [c for c in reg.values() if c.live_capable]
    adapter = [c for c in reg.values() if not c.live_capable]
    assert any("PTT" in c.source for c in live)
    assert any("Facebook" in c.source for c in adapter)
    assert any("Instagram" in c.source for c in adapter)
    assert any("Google" in c.source for c in adapter)


# --------------------------------------------------------------------------
# 屬性測試：tier 恆為三態、等級對應層數、確定性
# Feature: smart-watchdog-platform, Property (multi-source tier/level invariants)
# --------------------------------------------------------------------------
_layers = st.sampled_from([LAYER_OFFICIAL, LAYER_JUDICIAL, LAYER_NEWS,
                           LAYER_PETITION, LAYER_SOCIAL])


@settings(max_examples=120)
@given(items=st.lists(
    st.builds(lambda ly, t: {"layer": ly, "text": t or "訊號",
                             "scope": "specific", "park_name_match": "園"},
              _layers, st.text(min_size=0, max_size=20)),
    min_size=0, max_size=8))
def test_property_multi_source_invariants(items):
    """Feature: smart-watchdog-platform, Property: multi-source invariants。

    對任意訊號集合：每筆 tier ∈ {fact,event,sentiment}；交叉驗證等級與
    不同來源層數一致；neg_ratio ∈ [0,1]；且組裝為確定性。"""
    r1 = build_report("園", items=items)
    r2 = build_report("園", items=items)
    for s in r1.signals:
        assert s.tier in (TIER_FACT, TIER_EVENT, TIER_SENTIMENT)
    n = r1.distinct_layer_count
    lvl = r1.cross_validation_level()
    if n == 0:
        assert lvl == "none"
    elif n == 1:
        assert lvl == "single_source"
    else:
        assert lvl in ("converging", "corroborated")
    assert 0.0 <= r1.negative_sentiment_ratio <= 1.0
    # 確定性
    assert r1.cross_validation_level() == r2.cross_validation_level()
    assert isinstance(r1, CrossValidationReport)
