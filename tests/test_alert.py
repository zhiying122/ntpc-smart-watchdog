"""主動預警層 src/alert.py 的單元測試。"""
import numpy as np
import pandas as pd
import pytest

from src import alert


def _sample_df():
    return pd.DataFrame({
        "park_id": list(range(1, 11)),
        "park_name": [f"園{i}" for i in range(1, 11)],
        "park_type": ["公立"] * 10,
        "risk_total": [90, 80, 70, 60, 50, 40, 30, 20, 10, 5],
        "expense_income_ratio": [1.5, 1.2, 1.05, 1.0, 0.95, 0.9, 0.9, 0.8, 0.8, 0.7],
        "penalty_count": [2, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        "benford_mad": [0.05, 0.04, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.0],
        "expense_yoy_pct": [40, 10, 5, 0, 0, 0, 0, 0, 0, 0],
        "score_financial": [60, 50, 30, 20, 10, 5, 5, 0, 0, 0],
        "eval_grade": ["乙", "良", "優", "優", "優", "優", "優", "優", "優", "優"],
    })


def test_evaluate_returns_one_alert_per_row_sorted_desc():
    df = _sample_df()
    alerts = alert.evaluate(df)
    assert len(alerts) == len(df)
    scores = [a.risk_total for a in alerts]
    assert scores == sorted(scores, reverse=True)


def test_levels_partition_by_percentile():
    df = _sample_df()
    cfg = alert.AlertConfig(critical_pct=0.85, watch_pct=0.70, sigma_k=None)
    alerts = alert.evaluate(df, cfg)
    levels = {a.park_name: a.level for a in alerts}
    # Top 15% → 紅色；Top 15–30% → 橘色；其餘正常。
    assert levels["園1"] == alert.CRITICAL_ALERT
    assert alert.WATCHLIST in levels.values()
    assert alert.NORMAL in levels.values()


def test_every_alert_has_action():
    for a in alert.evaluate(_sample_df()):
        assert a.recommended_action  # 非空


def test_critical_and_watch_have_reasons_when_signals_exist():
    alerts = {a.park_name: a for a in alert.evaluate(_sample_df())}
    assert alerts["園1"].reasons  # 高風險園應有觸發原因


def test_empty_df_returns_empty():
    assert alert.evaluate(pd.DataFrame()) == []
    assert alert.active_alerts(pd.DataFrame()) == []


def test_single_row_does_not_crash():
    df = pd.DataFrame({
        "park_id": [1], "park_name": ["獨園"], "park_type": ["公立"],
        "risk_total": [50],
    })
    alerts = alert.evaluate(df)
    assert len(alerts) == 1
    assert alerts[0].peer_z is None  # 樣本 < 3，同儕 z 不計算


def test_missing_optional_columns_ok():
    df = pd.DataFrame({
        "park_id": [1, 2, 3, 4],
        "park_name": ["a", "b", "c", "d"],
        "risk_total": [80, 60, 40, 20],
    })
    alerts = alert.evaluate(df)  # 無 park_type / 無各風險欄位也不應爆
    assert len(alerts) == 4


def test_missing_score_column_raises():
    with pytest.raises(KeyError):
        alert.evaluate(pd.DataFrame({"park_name": ["x"]}))


def test_invalid_config_rejected():
    with pytest.raises(ValueError):
        alert.AlertConfig(critical_pct=0.5, watch_pct=0.7)  # watch > critical
    with pytest.raises(ValueError):
        alert.AlertConfig(sigma_k=-1)


def test_sigma_rule_promotes_outlier():
    # 一個遠高於同儕的離群值，即使百分位規則外也應被 sigma 規則升級為紅色。
    df = pd.DataFrame({
        "park_id": list(range(20)),
        "park_name": [f"p{i}" for i in range(20)],
        "park_type": ["公立"] * 20,
        "risk_total": [100] + [10] * 19,  # 一個極端離群
    })
    cfg = alert.AlertConfig(sigma_k=1.5)
    alerts = {a.park_name: a for a in alert.evaluate(df, cfg)}
    assert alerts["p0"].level == alert.CRITICAL_ALERT
    assert alerts["p0"].peer_z >= 1.5


def test_summary_counts_sum_to_total():
    df = _sample_df()
    s = alert.alert_summary(df)
    assert sum(s.values()) == len(df)


def test_alerts_to_dataframe_shape():
    alerts = alert.active_alerts(_sample_df())
    out = alert.alerts_to_dataframe(alerts)
    assert len(out) == len(alerts)
    assert "recommended_action" in out.columns
