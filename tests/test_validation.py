"""
風險分數 × 官方裁罰標籤　驗證模組測試（src/validation.py）
==========================================================
驗證「以裁罰為高風險標籤、檢驗分數鑑別力」的核心邏輯正確且穩健：
  - 高分組裁罰率高於對照組時，方向一致且 lift/相關為正。
  - 缺欄位、無裁罰、空資料等邊界安全處理，不拋例外。
  - 責任 AI 聲明恆非空。
"""
import pandas as pd

from src.validation import (
    validate_against_penalties,
    _point_biserial,
    NOT_ILLEGALITY_NOTICE,
)


def _df(rows):
    return pd.DataFrame(rows)


def test_high_group_higher_penalty_rate_direction_consistent():
    """高分組裁罰率明顯高於對照組 → 方向一致、lift>1、r>0。"""
    rows = []
    # 高風險 4 間：3 間有裁罰
    for i, pen in enumerate([2, 1, 3, 0]):
        rows.append({"park_name": f"高{i}", "risk_total": 80 - i,
                     "risk_level": "高", "penalty_count": pen})
    # 對照組 6 間：僅 1 間有裁罰
    for i, pen in enumerate([0, 0, 0, 0, 1, 0]):
        rows.append({"park_name": f"低{i}", "risk_total": 20 + i,
                     "risk_level": "低", "penalty_count": pen})

    r = validate_against_penalties(_df(rows))
    assert r.direction_consistent is True
    assert r.high.penalty_rate > r.control.penalty_rate
    assert r.lift is not None and r.lift > 1
    assert r.point_biserial_r is not None and r.point_biserial_r > 0
    assert r.not_illegality_notice  # 非空
    assert r.high.n == 4 and r.control.n == 6


def test_no_penalty_records_reports_gracefully():
    """全體無裁罰 → n_penalized=0、不拋例外、結論說明無標籤可驗證。"""
    rows = [{"park_name": f"P{i}", "risk_total": 50, "risk_level": "中",
             "penalty_count": 0} for i in range(5)]
    r = validate_against_penalties(_df(rows))
    assert r.n_penalized == 0
    assert "無" in r.interpretation
    assert r.not_illegality_notice


def test_missing_column_safe():
    """缺 penalty_count 欄位 → 中性結果、不拋例外。"""
    rows = [{"park_name": "A", "risk_total": 70, "risk_level": "高"}]
    r = validate_against_penalties(_df(rows))
    assert r.n_total == 0
    assert r.direction_consistent is False
    assert r.not_illegality_notice


def test_penalty_count_nan_treated_as_zero():
    """penalty_count 為 NaN → 視為 0（未被裁罰），不污染統計。"""
    rows = [
        {"park_name": "高0", "risk_total": 80, "risk_level": "高", "penalty_count": 2},
        {"park_name": "高1", "risk_total": 75, "risk_level": "高",
         "penalty_count": float("nan")},
        {"park_name": "低0", "risk_total": 20, "risk_level": "低",
         "penalty_count": float("nan")},
    ]
    r = validate_against_penalties(_df(rows))
    # 高分組 2 間，其中 1 間有裁罰 → 50%
    assert r.high.penalty_rate == 0.5
    # 對照組 1 間，NaN→0 → 0%
    assert r.control.penalty_rate == 0.0


def test_point_biserial_bounds_and_no_variance():
    """點二系列相關落於 [-1,1]；標籤無變異回 None。"""
    assert _point_biserial([1, 2, 3, 4], [0, 0, 0, 0]) is None  # 全 0
    assert _point_biserial([1, 2, 3, 4], [1, 1, 1, 1]) is None  # 全 1
    r = _point_biserial([10, 20, 30, 40], [0, 0, 1, 1])
    assert r is not None and -1.0 <= r <= 1.0 and r > 0


def test_notice_constant_non_empty():
    assert isinstance(NOT_ILLEGALITY_NOTICE, str) and NOT_ILLEGALITY_NOTICE.strip()
