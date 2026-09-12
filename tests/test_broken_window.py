"""
破窗效應累犯加權分數測試（Broken Window Score, R25）
======================================================
驗證 src/broken_window.py：
  - 公式、上限與確定性（Property 44）。
  - 時效單調性與缺值排除（Property 45）。
  - 嚴重度分級、頻率放大、評估窗等單元行為。

對應 tasks.md 4.5 / 4.6 / 4.7。
"""
from datetime import date

from hypothesis import given, settings
from hypothesis import strategies as st

from src.broken_window import (
    SEVERITY_WEIGHTS,
    Violation,
    broken_window_score,
)

AS_OF = date(2026, 9, 12)


def _v(months_ago, severity="moderate", desc="x"):
    """建立一筆發生於 months_ago 個月前的違規。"""
    d = date(2026, 9, 12)
    total_months = d.year * 12 + (d.month - 1) - months_ago
    y, m = divmod(total_months, 12)
    return Violation(occurred_on=date(y, m + 1, 1), severity=severity, description=desc)


def test_no_violations_scores_zero():
    """無違規 → 分數 0（R25.4）。"""
    r = broken_window_score([], AS_OF)
    assert r.score == 0.0
    assert r.n_counted == 0


def test_severity_weights_correct():
    """嚴重度權重 minor=3/moderate=6/major=12（R25.2）。"""
    assert SEVERITY_WEIGHTS == {"minor": 3, "moderate": 6, "major": 12}


def test_recent_scores_higher_than_old():
    """時效衰減：同嚴重度，近期違規貢獻高於久遠（R25.3）。"""
    recent = broken_window_score([_v(1, "major")], AS_OF)
    old = broken_window_score([_v(30, "major")], AS_OF)
    assert recent.score > old.score


def test_frequency_amplifier_increases_with_count():
    """頻率放大：多筆違規分數高於單筆同類（R25.4）。"""
    one = broken_window_score([_v(1, "moderate")], AS_OF)
    three = broken_window_score([_v(1, "moderate"), _v(2, "moderate"), _v(3, "moderate")], AS_OF)
    assert three.score > one.score
    assert three.frequency_amplifier == round(1 + 0.15 * 2, 4)


def test_missing_date_or_type_excluded():
    """缺日期或類型 → 待人工確認並排除計算，不中斷其餘（R25.8）。"""
    vs = [
        _v(1, "major", "valid"),
        Violation(occurred_on=None, severity="major", description="no-date"),
        Violation(occurred_on=date(2026, 1, 1), severity=None, category=None, description="no-type"),
    ]
    r = broken_window_score(vs, AS_OF)
    assert r.n_counted == 1
    assert len(r.pending_manual) == 2


def test_window_excludes_old_violations():
    """評估窗：超出 window_months 的違規被排除（R25.5）。"""
    r = broken_window_score([_v(50, "major")], AS_OF, window_months=36)
    assert r.n_counted == 0
    assert r.score == 0.0


def test_category_maps_to_severity():
    """未給 severity 時由 category 推得嚴重度。"""
    v = Violation(occurred_on=date(2026, 8, 1), category="安全", description="設施安全")
    r = broken_window_score([v], AS_OF)
    assert r.n_counted == 1
    assert r.details[0].severity == "major"


# Feature: smart-watchdog-platform, Property 44: 破窗效應累犯加權—公式、上限與確定性
@settings(max_examples=100)
@given(
    n=st.integers(min_value=0, max_value=15),
    sev=st.sampled_from(["minor", "moderate", "major"]),
    half_life=st.integers(min_value=6, max_value=36),
)
def test_property_44_formula_cap_determinism(n, sev, half_life):
    """分數 = min(100, freq_amp × Σ(severity × decay))；0 筆→0；確定性；0–100。"""
    vs = [_v(months_ago=i, severity=sev, desc=f"v{i}") for i in range(n)]
    r1 = broken_window_score(vs, AS_OF, half_life_months=half_life)
    r2 = broken_window_score(vs, AS_OF, half_life_months=half_life)

    # 確定性
    assert r1.score == r2.score
    # 範圍
    assert 0.0 <= r1.score <= 100.0
    # 0 筆 → 0
    if n == 0:
        assert r1.score == 0.0
    # 公式一致性（重算比對）
    if r1.n_counted > 0:
        expected_raw = r1.frequency_amplifier * sum(d.contribution for d in r1.details)
        assert r1.score == round(min(100.0, expected_raw), 1)


# Feature: smart-watchdog-platform, Property 45: 破窗—時效單調性與缺值排除
@settings(max_examples=100)
@given(
    months_a=st.integers(min_value=0, max_value=35),
    gap=st.integers(min_value=1, max_value=30),
    sev=st.sampled_from(["minor", "moderate", "major"]),
)
def test_property_45_time_monotonicity_and_exclusion(months_a, gap, sev):
    """同嚴重度，較近期者貢獻不小於較久遠者（時效衰減單調）。"""
    recent = broken_window_score([_v(months_a, sev)], AS_OF, window_months=999)
    older = broken_window_score([_v(months_a + gap, sev)], AS_OF, window_months=999)
    assert recent.score >= older.score

    # 缺日期紀錄被排除、不中斷其餘
    mixed = broken_window_score(
        [_v(months_a, sev), Violation(occurred_on=None, severity=sev)],
        AS_OF, window_months=999,
    )
    assert len(mixed.pending_manual) == 1
    assert mixed.n_counted == 1
