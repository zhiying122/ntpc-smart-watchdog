"""
家長信任中心公開揭露與時效標記單元測試（Parent_Portal）
========================================================
驗證 `app/lib/parent_portal.py` 的呈現無關核心邏輯（Task 21.1）：

  - 風險欄位移除：risk_total / risk_level / score_* 一律不外洩（R1.5, R6.6）。
  - 無官方資料 → 「查無公開資料」，不以推估／預設／空白替代（R6.3）。
  - 來源 >365 天 → 「資料可能過時」；恰 365 天不過時（R6.4，Property 34 邊界）。
  - 每欄位附官方來源連結與最後更新時間（R6.1, R6.2）。
  - 不含任何違法／舞弊／高風險標記（R6.7, R6.8）。

聚焦具體範例與邊界；Property 34 屬性測試由 Task 21.2 另行實作。
"""
import os
import sys
from datetime import date, timedelta

# 讓 `from lib import parent_portal` 可用（app 目錄加入 sys.path）。
_APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

from lib import parent_portal as pp  # noqa: E402
from src.models import PublicInstitutionView, SourceRef  # noqa: E402


# ---------------------------------------------------------------------------
# 風險欄位移除（R1.5, R6.6）
# ---------------------------------------------------------------------------
def test_is_risk_field_exact_and_prefix():
    assert pp.is_risk_field("risk_total")
    assert pp.is_risk_field("risk_level")
    assert pp.is_risk_field("risk_level_abs")
    assert pp.is_risk_field("score_financial")
    assert pp.is_risk_field("score_penalty")
    assert pp.is_risk_field("SCORE_Eval")          # 大小寫不敏感
    assert not pp.is_risk_field("park_name")
    assert not pp.is_risk_field("district")
    assert not pp.is_risk_field("eval_grade")      # 評鑑等第屬公開資料，非內部分數


def test_strip_risk_fields_removes_all_internal_risk_columns():
    record = {
        "park_name": "測試幼兒園",
        "district": "板橋區",
        "park_type": "公校",
        "eval_grade": "甲",
        "risk_total": 87.5,
        "risk_level": "高",
        "risk_level_abs": "中",
        "score_financial": 40.0,
        "score_penalty": 30.0,
        "score_eval": 17.0,
    }
    safe = pp.strip_risk_fields(record)
    assert "park_name" in safe and "district" in safe and "eval_grade" in safe
    for forbidden in ("risk_total", "risk_level", "risk_level_abs",
                      "score_financial", "score_penalty", "score_eval"):
        assert forbidden not in safe
    # 不修改原輸入
    assert "risk_total" in record


def test_build_public_view_never_exposes_risk_fields():
    record = {
        "park_name": "光明幼兒園",
        "park_type": "非營利",
        "eval_grade": "優",
        "risk_total": 99.9,
        "risk_level": "極高",
        "score_financial": 50.0,
    }
    view = pp.build_public_view(record)
    # dataclass 欄位不得含任何風險鍵
    d = view.__dict__
    for k in d:
        assert not pp.is_risk_field(k)
    assert view.park_name == "光明幼兒園"
    assert view.ownership == "非營利"
    assert view.public_eval == "優"


# ---------------------------------------------------------------------------
# 無官方資料 → 「查無公開資料」（R6.3）
# ---------------------------------------------------------------------------
def test_missing_data_shows_no_public_data_label_not_blank():
    f = pp.build_field("tuition_info", "收費資訊", None, None)
    assert f.has_data is False
    assert f.value is None
    assert f.display_value == pp.NO_PUBLIC_DATA_LABEL
    assert f.display_value != ""            # 不以空白替代
    assert f.source is None
    assert f.stale is False


def test_empty_string_and_empty_collection_treated_as_no_data():
    for empty in ("", "   ", [], {}, ()):
        f = pp.build_field("k", "欄位", empty, None)
        assert f.has_data is False
        assert f.display_value == pp.NO_PUBLIC_DATA_LABEL


def test_present_value_is_kept_verbatim_not_defaulted():
    src = SourceRef(dataset="收費公告", authority="教育局", url="https://x.gov.tw",
                    last_updated=date.today())
    f = pp.build_field("tuition_info", "收費資訊", {"月費": 8000}, src)
    assert f.has_data is True
    assert f.value == {"月費": 8000}
    assert f.display_value == {"月費": 8000}
    assert f.source_url == "https://x.gov.tw"
    assert f.source_last_updated == date.today()


# ---------------------------------------------------------------------------
# 時效門檻（R6.4，Property 34 邊界）
# ---------------------------------------------------------------------------
def test_staleness_boundary_365_not_stale_366_stale():
    ref = date(2025, 1, 1)
    assert pp.is_stale(ref - timedelta(days=364), reference=ref) is False
    assert pp.is_stale(ref - timedelta(days=365), reference=ref) is False   # 恰 365 天
    assert pp.is_stale(ref - timedelta(days=366), reference=ref) is True    # 超過
    assert pp.is_stale(ref - timedelta(days=1000), reference=ref) is True


def test_staleness_none_and_future_not_stale():
    ref = date(2025, 1, 1)
    assert pp.is_stale(None, reference=ref) is False           # 無時間資訊
    assert pp.is_stale(ref + timedelta(days=10), reference=ref) is False  # 未來日期


def test_days_since():
    ref = date(2025, 1, 1)
    assert pp.days_since(None, reference=ref) is None
    assert pp.days_since(date(2024, 1, 1), reference=ref) == 366   # 2024 為閏年


def test_stale_source_field_has_stale_notice():
    ref = date(2025, 1, 1)
    old_src = SourceRef(dataset="舊資料", authority="教育局",
                        url="https://x.gov.tw", last_updated=ref - timedelta(days=400))
    f = pp.build_field("public_eval", "公開評鑑結果", "乙", old_src, reference=ref)
    assert f.has_data is True
    assert f.stale is True
    assert f.stale_notice == pp.STALE_NOTICE_LABEL


def test_fresh_source_field_no_stale_notice():
    ref = date(2025, 1, 1)
    fresh = SourceRef(dataset="新資料", authority="教育局",
                      url="https://x.gov.tw", last_updated=ref - timedelta(days=30))
    f = pp.build_field("public_eval", "公開評鑑結果", "甲", fresh, reference=ref)
    assert f.stale is False
    assert f.stale_notice is None


# ---------------------------------------------------------------------------
# 揭露欄位組裝（R6.1, R6.2）
# ---------------------------------------------------------------------------
def test_build_disclosure_fields_covers_all_required_fields():
    ref = date(2025, 6, 1)
    view = PublicInstitutionView(
        park_name="信義幼兒園",
        ownership="公立",
        tuition_info={"月費": 5000},
        public_eval="優",
        public_penalty=None,   # 無裁罰公開資料
        field_sources={
            "ownership": SourceRef(dataset="基本資料", authority="教育局",
                                   url="https://a.gov.tw", last_updated=ref),
            "tuition_info": SourceRef(dataset="收費公告", authority="教育局",
                                      url="https://b.gov.tw", last_updated=ref),
            "public_eval": SourceRef(dataset="評鑑結果", authority="教育局",
                                     url="https://c.gov.tw",
                                     last_updated=ref - timedelta(days=500)),
        },
    )
    fields = pp.build_disclosure_fields(view, basic_info={"行政區": "信義區"}, reference=ref)
    by_key = {f.key: f for f in fields}

    # 五類揭露欄位齊備（R6.1）
    assert set(by_key) == {"basic_info", "ownership", "tuition_info",
                           "public_eval", "public_penalty"}

    # 有資料欄位附來源連結與更新時間（R6.2）
    assert by_key["ownership"].has_data
    assert by_key["ownership"].source_url == "https://a.gov.tw"
    assert by_key["tuition_info"].source_last_updated == ref

    # 評鑑來源 >365 天 → 資料可能過時（R6.4）
    assert by_key["public_eval"].stale is True
    assert by_key["public_eval"].stale_notice == pp.STALE_NOTICE_LABEL

    # 無裁罰資料 → 查無公開資料（R6.3）
    assert by_key["public_penalty"].has_data is False
    assert by_key["public_penalty"].display_value == pp.NO_PUBLIC_DATA_LABEL


def test_disclosure_fields_carry_no_risk_or_illegality_labels():
    """揭露欄位不得含任何風險分數／等級或違法／舞弊標記（R6.6, R6.7, R6.8）。"""
    view = PublicInstitutionView(park_name="測試園", ownership="公立")
    fields = pp.build_disclosure_fields(view, basic_info={"行政區": "中和區"})
    banned = ("風險", "score", "risk", "違法", "舞弊", "高風險", "不合格")
    for f in fields:
        blob = f"{f.key} {f.label} {f.display_value}"
        for bad in banned:
            assert bad not in blob
