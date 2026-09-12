"""
公眾查詢網核心純邏輯單元測試（Public Trust Center）
========================================================
驗證 `public/lib/` 之呈現無關核心邏輯（不依賴網路）：

  - geocode：Haversine 距離、地址解析、距離格式化。
  - ntpc_districts：新北市 29 區座標表與行政區比對。
  - parent_map：家長版關注度分級/柔和色階/標記（刻意不用後台「風險」詞彙）。
  - sentiment_watch：規則式主題分類/情緒判斷/趨勢偵測/家長友善分級。
  - sentiment_score：輿情關注指數診斷式白盒公式（分項加權、與後台風險分區隔）。
  - input_guard：申訴輸入品質守門（不雅字/亂填偵測，不誤傷正當回饋）。
  - evaluation_cycle：評鑑分年分區輪替狀態判定（官方用語，非 nan）。
  - news_crawler：新聞標題解析與精準比對（避免同名/同地區張冠李戴）。

聚焦具體範例與責任 AI 不變式（家長端不使用「風險」字眼、不作指控）。
"""
import os
import sys
from datetime import date

# 讓 `from lib import ...` 指向 public/lib。
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PUBLIC = os.path.join(_ROOT, "public")
for _p in (_PUBLIC, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import geocode as geo  # noqa: E402
from lib import ntpc_districts as nd  # noqa: E402
from lib import parent_map as pmap  # noqa: E402
from lib import sentiment_watch as sw  # noqa: E402
from lib import sentiment_score as ss  # noqa: E402
from lib import input_guard as ig  # noqa: E402
from lib import evaluation_cycle as evc  # noqa: E402
from lib import news_crawler as nc  # noqa: E402


REF = date(2026, 9, 12)


# ===========================================================================
# geocode：距離與地址解析（純數學/純字串，無網路）
# ===========================================================================
def test_haversine_same_point_is_zero():
    assert geo.haversine_km(25.0, 121.0, 25.0, 121.0) == 0.0


def test_haversine_known_distance_reasonable():
    # 台北車站 ~ 板橋車站 約 8km 上下，容許誤差。
    d = geo.haversine_km(25.0478, 121.5170, 25.0143, 121.4636)
    assert 4.0 < d < 9.0


def test_format_distance_meters_and_km():
    assert "公尺" in geo.format_distance(0.5)
    assert "公里" in geo.format_distance(2.0)


def test_parse_address_extracts_road_and_house():
    p = geo.parse_address("新北市新莊區瓊林路90號")
    assert p.county == "新北市"
    assert p.district == "新莊區"
    assert p.road == "瓊林路"
    assert p.house_no == "90"


def test_parse_address_road_with_section():
    p = geo.parse_address("新北市板橋區文化路一段188號")
    assert p.district == "板橋區"
    assert p.road == "文化路一段"
    assert p.house_no == "188"


def test_parse_address_district_only():
    p = geo.parse_address("新北市新莊區")
    assert p.district == "新莊區"
    assert p.house_no == ""


# ===========================================================================
# ntpc_districts：29 區座標與比對
# ===========================================================================
def test_all_29_districts_present():
    assert len(nd.NTPC_DISTRICTS) == 29


def test_find_district_full_and_short_name():
    assert nd.find_district_in_text("我住新莊區") == "新莊區"
    assert nd.find_district_in_text("板橋文化路") == "板橋區"  # 去「區」短名亦可命中


def test_find_district_none_when_absent():
    assert nd.find_district_in_text("台北市大安區") is None


def test_district_center_returns_coords():
    c = nd.district_center("板橋區")
    assert c is not None and 24.9 < c[0] < 25.1


# ===========================================================================
# parent_map：家長版分級（刻意不用後台「風險」詞彙）
# ===========================================================================
def test_parent_levels_use_attention_wording_not_risk():
    # 家長版四級標籤皆為描述性，不含「風險」字眼（責任 AI）。
    for lvl in (pmap.LEVEL_CALM, pmap.LEVEL_ACTIVE, pmap.LEVEL_WATCH, pmap.LEVEL_NONE):
        label = pmap.level_label(lvl)
        assert "風險" not in label
    assert pmap.level_label(pmap.LEVEL_WATCH) == "值得留意"


def test_watch_color_is_amber_not_alarm_red():
    # 最高等級用暖琥珀（非警報紅 #D64545/後台高風險色）。
    assert pmap.color_for_level(pmap.LEVEL_WATCH) == "#D99A4E"


def test_build_marker_reads_public_fields():
    row = {"park_id": "X1", "park_name": "測試幼兒園", "park_type": "非營利",
           "district": "板橋區", "lat": 25.01, "lng": 121.46}
    m = pmap.build_marker(row, attention_level=pmap.LEVEL_ACTIVE, distance_km=1.2)
    assert m.has_coords and m.name == "測試幼兒園"
    assert m.attention_level == pmap.LEVEL_ACTIVE
    assert m.distance_km == 1.2


def test_build_marker_missing_coords():
    m = pmap.build_marker({"park_name": "無座標園"})
    assert not m.has_coords


# ===========================================================================
# sentiment_watch：規則式分類/情緒/趨勢/分級
# ===========================================================================
def test_classify_topics_hits_fee():
    assert "fee" in sw.classify_topics("這間的收費與退費有疑問")


def test_classify_sentiment_neg_pos_neu():
    assert sw.classify_sentiment("態度很差又亂收費") == "neg"
    assert sw.classify_sentiment("老師很用心環境乾淨推薦") == "pos"
    assert sw.classify_sentiment("今天天氣普通") == "neu"


def test_empty_items_summary_is_none_level():
    s = sw.summarize_attention([], reference=REF)
    assert s.level == sw.LEVEL_NONE
    assert s.total_items == 0


def test_summary_advice_has_no_accusation():
    # 值得留意的建議語不得含指控字眼（責任 AI）。
    recs = [
        {"source_type": "forum", "title": "收費爭議討論", "excerpt": "有家長抱怨收費爭議退費困難",
         "url": "http://x", "published": (REF.replace(month=8)).isoformat()},
        {"source_type": "review", "title": "收費問題", "excerpt": "覺得收費貴又亂",
         "url": "http://x", "published": (REF.replace(month=8, day=20)).isoformat()},
        {"source_type": "news", "title": "收費討論", "excerpt": "家長反映收費問題不滿",
         "url": "http://x", "published": (REF.replace(month=9, day=1)).isoformat()},
    ]
    items = sw.load_items_from_records(recs)
    s = sw.summarize_attention(items, reference=REF)
    for bad in ("虐童", "涉嫌", "疑似", "違法認定"):
        assert bad not in s.advice


# ===========================================================================
# sentiment_score：輿情關注指數（診斷式白盒，與後台風險分區隔）
# ===========================================================================
def test_index_zero_when_no_items():
    idx = ss.compute_index([], reference=REF)
    assert idx.total == 0.0
    assert idx.band == sw.LEVEL_NONE


def test_index_weights_sum_to_one():
    w = ss._weights()
    assert abs(sum(w.values()) - 1.0) < 1e-9


def test_index_contributions_sum_close_to_total():
    recs = [
        {"source_type": "news", "title": "安全事件討論", "excerpt": "家長擔心安全受傷問題",
         "url": "http://x", "published": (REF.replace(month=8, day=i)).isoformat()}
        for i in range(1, 6)
    ]
    items = sw.load_items_from_records(recs)
    idx = ss.compute_index(items, reference=REF)
    assert 0 <= idx.total <= 100
    assert abs(sum(idx.contributions.values()) - idx.total) <= 1.0


def test_index_disclaimer_separates_from_risk_score():
    idx = ss.compute_index([], reference=REF)
    # 免責聲明須明言與稽查系統風險分數無關（責任 AI 區隔）。
    assert "風險分數" in idx.disclaimer or "風險" in idx.disclaimer


# ===========================================================================
# input_guard：申訴輸入守門
# ===========================================================================
def test_guard_blocks_profanity():
    r = ig.check_appeal_text("你們這些白痴亂寫一通根本亂搞")
    assert not r.ok


def test_guard_blocks_gibberish():
    assert not ig.check_appeal_text("!!!!!@@@@####").ok
    assert not ig.check_appeal_text("啊啊啊啊啊啊啊啊").ok


def test_guard_blocks_too_short():
    assert not ig.check_appeal_text("沒事").ok


def test_guard_allows_legitimate_negative_feedback():
    # 得體、具體的負面回饋應可送出（不審查立場）。
    r = ig.check_appeal_text("我對貴園近一年的師資流動有疑慮，希望能公開說明教師異動情形。")
    assert r.ok


def test_guard_does_not_flag_ganbu():
    # 「幹部」不應被誤判為不雅。
    assert ig.check_appeal_text("幹部會議已討論並將對外說明收費調整的原因與依據。").ok


# ===========================================================================
# evaluation_cycle：分年分區輪替狀態（官方用語，非 nan）
# ===========================================================================
def test_eval_status_with_grade():
    status, text = evc.evaluation_status("林口區", "乙")
    assert status == evc.STATUS_EVALUATED
    assert "乙" in text


def test_eval_status_scheduled_district():
    status, text = evc.evaluation_status("樹林區", None)
    assert status == evc.STATUS_PENDING
    assert "114" in text  # 樹林排入 114 學年度


def test_eval_status_unscheduled_district():
    status, text = evc.evaluation_status("新莊區", None)
    assert status == evc.STATUS_PENDING
    assert "尚未排入本輪" in text


def test_eval_status_never_returns_nan():
    _, text = evc.evaluation_status("新莊區", float("nan"))
    assert "nan" not in text.lower()


# ===========================================================================
# news_crawler：標題解析與精準比對（避免張冠李戴）
# ===========================================================================
def test_clean_title_splits_source():
    title, src = nc._clean_title("某某幼兒園收費說明 - 中央社")
    assert title == "某某幼兒園收費說明"
    assert src == "中央社"


def test_name_core_strips_prefix_suffix():
    assert nc.name_core("新北市立林口幼兒園") == "林口"
    assert nc.name_core("新北市新莊非營利幼兒園") == "新莊非營利"


def test_title_match_distinctive_core():
    # 具鑑別度核心詞：標題含核心詞即相關。
    assert nc._title_matches("新莊非營利幼兒園辦活動", "新莊非營利", "新莊區", "新北市新莊非營利幼兒園")


def test_title_match_generic_core_requires_full_name():
    # 地區泛稱（林口）：僅「林口幼兒園」不足以確認，需完整全名，避免張冠李戴。
    assert not nc._title_matches("林口幼兒園驚傳虐童", "林口", "林口區", "新北市立林口幼兒園")
    assert nc._title_matches("新北市立林口幼兒園辦親子活動", "林口", "林口區", "新北市立林口幼兒園")


def test_build_query_binds_core_and_district():
    q = nc.build_query("新北市新莊非營利幼兒園", "新莊區")
    assert "新莊非營利" in q and "新莊區" in q and "幼兒園" in q


def test_build_query_appends_extra_keyword():
    """build_query 帶關鍵字時應附加於查詢末（多組查詢用）。"""
    q = nc.build_query("新北市新莊非營利幼兒園", "新莊區", extra="收費")
    assert "新莊非營利" in q and "新莊區" in q and "幼兒園" in q and "收費" in q
    # 無關鍵字時向後相容，不應多出空白關鍵字。
    q0 = nc.build_query("新北市新莊非營利幼兒園", "新莊區")
    assert q0.endswith("幼兒園")


def test_dedupe_removes_same_url_across_sources():
    """跨來源去重：同 URL 只保留一則，並依發布日新到舊排序。"""
    recs = [
        {"url": "http://a", "title": "甲", "published": "2026-08-01",
         "source_platform": "google_news"},
        {"url": "http://a", "title": "甲(重複)", "published": "2026-08-01",
         "source_platform": "bing_news"},
        {"url": "http://b", "title": "乙", "published": "2026-09-01",
         "source_platform": "bing_news"},
    ]
    out = nc._dedupe(recs)
    assert len(out) == 2                      # 同 URL 去重
    assert out[0]["url"] == "http://b"        # 較新者在前


def test_dedupe_merges_same_news_across_sources_different_urls():
    """同一則新聞跨來源（URL 各異、標題有標點差異）應合併為一則，
    且保留媒體原站連結（家長點到原文，非聚合器轉址）。"""
    recs = [
        {"url": "https://news.google.com/rss/a", "title": "某幼兒園事件 家長怒",
         "published": "2026-09-01", "source_platform": "google_news"},
        {"url": "https://www.bing.com/news/b", "title": "某幼兒園事件，家長怒",
         "published": "2026-09-01", "source_platform": "bing_news"},
        {"url": "https://news.ltn.com.tw/c", "title": "某幼兒園事件 家長怒",
         "published": "2026-09-01", "source_platform": "media_rss"},
    ]
    out = nc._dedupe(recs)
    assert len(out) == 1                                # 三來源同則合併
    assert out[0]["source_platform"] == "media_rss"     # 保留原站連結
    assert "ltn.com.tw" in out[0]["url"]


def test_dedupe_falls_back_to_title_date_when_no_url():
    """URL 缺失時以「標題+日期」為去重鍵。"""
    recs = [
        {"url": "", "title": "同標題", "published": "2026-09-01"},
        {"url": "", "title": "同標題", "published": "2026-09-01"},
        {"url": "", "title": "同標題", "published": "2026-08-01"},
    ]
    out = nc._dedupe(recs)
    assert len(out) == 2                      # 標題同但日期不同者視為兩則


def test_fetch_all_news_aggregates_and_dedupes(monkeypatch):
    """多來源聚合：多組 Google News + Bing 的結果合併並去重（不觸網）。"""
    calls = {"n": 0}

    def _fake_rss(endpoint, query, park_name, district, *, platform,
                  timeout, limit, reference):
        calls["n"] += 1
        # 每次回傳同一則（同 URL），驗證跨查詢/跨來源去重成一則。
        return [{
            "source_type": "news", "source_platform": platform,
            "source_name": "測試媒體", "title": "某幼兒園新聞",
            "excerpt": "某幼兒園新聞", "url": "http://same",
            "published": "2026-09-01",
            "matched": True,
        }]

    monkeypatch.setattr(nc, "_fetch_rss", _fake_rss)
    # 媒體 RSS 直連也 mock 掉，避免測試觸網（回空即可）。
    monkeypatch.setattr(nc, "_fetch_media_rss", lambda *a, **k: [])
    out = nc.fetch_all_news("新北市新莊非營利幼兒園", "新莊區", reference=REF)
    assert calls["n"] >= 2                     # 至少多組查詢 + Bing 都被呼叫
    assert len(out) == 1                       # 同 URL 去重成一則


def test_fetch_all_news_empty_when_no_core():
    """園名無可辨識核心詞時回空清單，不觸網。"""
    assert nc.fetch_all_news("", "") == []


def test_media_rss_filters_to_matching_park(monkeypatch):
    """台灣媒體全站 RSS 直連：只保留標題確實對應本園者（精準比對）。"""
    fake = (
        '<?xml version="1.0"?><rss><channel>'
        '<item><title>新莊非營利幼兒園辦親子活動</title><link>http://m/1</link>'
        '<pubDate>Wed, 10 Sep 2026 08:00:00 +0800</pubDate></item>'
        '<item><title>某小學運動會登場</title><link>http://m/2</link>'
        '<pubDate>Wed, 10 Sep 2026 09:00:00 +0800</pubDate></item>'
        '</channel></rss>'
    )

    class _R:
        text = fake
        def raise_for_status(self):  # noqa: D401
            pass

    monkeypatch.setattr(nc.requests, "get", lambda *a, **k: _R())
    recs = nc._fetch_media_rss("自由時報", "http://x",
                               "新北市新莊非營利幼兒園", "新莊區",
                               timeout=5, reference=REF)
    assert len(recs) == 1                          # 只命中對應本園那則
    assert recs[0]["source_platform"] == "media_rss"
    assert recs[0]["source_name"] == "自由時報"
    assert recs[0]["matched"] is True


def test_media_rss_network_error_returns_empty(monkeypatch):
    """媒體 RSS 連線錯誤回空清單，不拋例外、不影響其他來源。"""
    def _boom(*a, **k):
        raise nc.requests.RequestException("連線失敗")

    monkeypatch.setattr(nc.requests, "get", _boom)
    assert nc._fetch_media_rss("自由時報", "http://x", "某某幼兒園", "板橋區",
                               timeout=5, reference=REF) == []
