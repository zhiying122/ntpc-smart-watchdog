"""
異常偵測單元測試（Anomaly Detector Unit Tests, R8）
=====================================================
驗證 `src/anomaly.py` 的 `detect()` 對點／情境／集體三類異常的多方法輸出行為：
  - 每方法 flag == (score >= threshold)（R8.1, R8.2；對應 Property 25）。
  - 三類異常各輸出 (bool, score)（R8.1）。
  - 樣本不足時標記 insufficient_sample 並跳過，不中斷其餘方法（R8.5）。
  - 保留既有 Isolation Forest 與 IQR 精神（R8.6）。
"""
import pytest

from src import anomaly
from src.models import (
    AnomalyMethodResult,
    AnomalyResult,
    ConsolidatedAnomaly,
    MethodNote,
)


def test_detect_returns_three_anomaly_types():
    """detect 對 point/contextual/collective 各輸出 (bool, score)（R8.1）。"""
    entity = {"value": 100.0, "population": [1, 2, 3, 4, 5], "series": [1, 2, 3, 100]}
    result = anomaly.detect(entity)
    assert isinstance(result, AnomalyResult)
    for pair in (result.point, result.contextual, result.collective):
        assert isinstance(pair, tuple) and len(pair) == 2
        assert isinstance(pair[0], bool)
        assert isinstance(pair[1], float)
        assert 0.0 <= pair[1] <= 100.0


def test_flag_consistent_with_threshold_for_applicable_methods():
    """適用方法的 flag 恆等於 (score >= threshold)（Property 25 / R8.2）。"""
    entity = {"value": 500.0, "population": [1, 2, 3, 4, 5, 6],
              "series": [10, 10, 10, 500]}
    result = anomaly.detect(entity)
    for m in result.methods:
        if m.applicable:
            assert m.flag == (m.score >= m.threshold)
        else:
            # 樣本不足方法 flag 恆為 False（不參與命中）。
            assert m.flag is False


def test_clear_point_outlier_is_flagged_by_zscore():
    """明顯離群的目標值應被 z-score 判為異常（point flag）。"""
    entity = {"value": 1000.0, "population": [10, 11, 9, 10, 12, 8, 11]}
    result = anomaly.detect(entity, methods=["zscore", "robust"])
    zscore = next(m for m in result.methods if m.method == "zscore")
    assert zscore.applicable
    assert zscore.flag is True
    assert result.point[0] is True


def test_normal_value_not_flagged():
    """接近母體中心的目標值不應被判為點異常。"""
    entity = {"value": 10.0, "population": [10, 11, 9, 10, 12, 8, 11, 10]}
    result = anomaly.detect(entity, methods=["zscore", "robust"])
    zscore = next(m for m in result.methods if m.method == "zscore")
    assert zscore.flag is False


def test_insufficient_sample_marked_and_skipped():
    """樣本不足時標記 insufficient_sample、applicable=False，不中斷其餘方法（R8.5）。"""
    # population 僅 1 筆 → zscore/robust/lof/clustering/iforest 樣本不足；
    # series 有 2 筆 → timeseries 仍可運作。
    entity = {"value": 5.0, "population": [5.0], "series": [10, 30]}
    result = anomaly.detect(entity)
    zscore = next(m for m in result.methods if m.method == "zscore")
    assert zscore.applicable is False
    assert zscore.note.get("skipped") == "insufficient_sample"
    # timeseries 有足夠樣本仍應運作（不被其他方法樣本不足中斷）。
    ts = next(m for m in result.methods if m.method == "timeseries")
    assert ts.applicable is True


def test_timeseries_contextual_anomaly_on_sudden_change():
    """跨年度序列突變應觸發情境（contextual）異常。"""
    entity = {"series": [100, 100, 100, 300]}
    result = anomaly.detect(entity, methods=["timeseries"])
    ts = next(m for m in result.methods if m.method == "timeseries")
    assert ts.applicable is True
    assert ts.flag is True
    assert result.contextual[0] is True


def test_unknown_method_ignored():
    """未知方法名稱被忽略，不產生結果也不拋例外。"""
    entity = {"value": 10.0, "population": [1, 2, 3, 4, 5]}
    result = anomaly.detect(entity, methods=["zscore", "nonexistent_method"])
    assert [m.method for m in result.methods] == ["zscore"]


def test_method_hit_count_and_confidence_label():
    """>=2 適用方法命中 → high_confidence 並正確計數命中方法。"""
    entity = {"value": 1000.0,
              "population": [10, 11, 9, 10, 12, 8, 11, 10, 9, 11],
              "series": [10, 10, 10, 1000]}
    result = anomaly.detect(entity)
    hits = [m for m in result.methods if m.applicable and m.flag]
    assert result.method_hit_count == len(hits)
    if result.method_hit_count >= 2:
        assert result.confidence_label == "high_confidence"
    else:
        assert result.confidence_label == "to_confirm"


def test_empty_entity_does_not_crash():
    """完全缺資料的 entity 不拋例外，所有方法標記樣本不足。"""
    result = anomaly.detect({})
    assert isinstance(result, AnomalyResult)
    assert all(not m.applicable for m in result.methods)
    assert result.point == (False, 0.0)
    assert result.contextual == (False, 0.0)
    assert result.collective == (False, 0.0)


def test_all_methods_present_by_default():
    """預設執行全部七種方法。"""
    entity = {"value": 10.0, "population": [1, 2, 3, 4, 5, 6, 7, 8]}
    result = anomaly.detect(entity)
    assert {m.method for m in result.methods} == set(anomaly.ALL_METHODS)


# --------------------------------------------------------------------------
# method_applicability 適用性說明（R8.3）
# --------------------------------------------------------------------------
def test_method_applicability_returns_note_for_all_methods():
    """每一內建方法皆能取得非空的適用性說明（R8.3）。"""
    for m in anomaly.ALL_METHODS:
        note = anomaly.method_applicability(m)
        assert isinstance(note, MethodNote)
        assert note.method == m
        assert note.anomaly_type in ("point", "contextual", "collective")
        assert note.assumption != ""
        assert note.limitation != ""


def test_method_applicability_matches_detect_note():
    """適用性說明與 detect() 產出的 note 一致。"""
    entity = {"value": 10.0, "population": [1, 2, 3, 4, 5, 6]}
    result = anomaly.detect(entity, methods=["zscore"])
    detect_note = next(m for m in result.methods if m.method == "zscore").note
    note = anomaly.method_applicability("zscore")
    assert note.anomaly_type == detect_note["anomaly_type"]
    assert note.assumption == detect_note["assumption"]
    assert note.limitation == detect_note["limitation"]


def test_method_applicability_unknown_raises():
    """未知方法名稱應拋 ValueError。"""
    with pytest.raises(ValueError):
        anomaly.method_applicability("nonexistent_method")


# --------------------------------------------------------------------------
# consolidate 一致性整合（R8.4）
# --------------------------------------------------------------------------
def _mr(method: str, flag: bool, applicable: bool = True) -> AnomalyMethodResult:
    return AnomalyMethodResult(
        method=method, score=80.0 if flag else 10.0, flag=flag,
        threshold=60.0, applicable=applicable,
    )


def test_consolidate_two_or_more_hits_high_confidence():
    """>=2 方法命中 → high_confidence 並記命中數與方法名（R8.4）。"""
    results = [_mr("zscore", True), _mr("robust", True), _mr("lof", False)]
    c = anomaly.consolidate(results)
    assert isinstance(c, ConsolidatedAnomaly)
    assert c.confidence_label == "high_confidence"
    assert c.hit_count == 2
    assert set(c.hit_methods) == {"zscore", "robust"}


def test_consolidate_single_hit_to_confirm():
    """單一方法命中 → to_confirm（R8.4）。"""
    results = [_mr("zscore", True), _mr("robust", False)]
    c = anomaly.consolidate(results)
    assert c.confidence_label == "to_confirm"
    assert c.hit_count == 1
    assert c.hit_methods == ["zscore"]


def test_consolidate_no_hits_none():
    """無方法命中 → none。"""
    results = [_mr("zscore", False), _mr("robust", False)]
    c = anomaly.consolidate(results)
    assert c.confidence_label == "none"
    assert c.hit_count == 0
    assert c.hit_methods == []


def test_consolidate_ignores_insufficient_sample_flags():
    """樣本不足（applicable=False）之方法不計入命中（R8.5）。"""
    # 即使 flag 被設為 True，但 applicable=False 不應計入。
    results = [
        _mr("zscore", True, applicable=False),
        _mr("robust", True, applicable=False),
        _mr("lof", True, applicable=True),
    ]
    c = anomaly.consolidate(results)
    assert c.hit_count == 1
    assert c.confidence_label == "to_confirm"
    assert c.hit_methods == ["lof"]


def test_consolidate_hit_count_matches_detect():
    """consolidate 的命中數與 detect 的 method_hit_count 一致。"""
    entity = {"value": 1000.0,
              "population": [10, 11, 9, 10, 12, 8, 11, 10, 9, 11],
              "series": [10, 10, 10, 1000]}
    result = anomaly.detect(entity)
    c = anomaly.consolidate(result.methods)
    assert c.hit_count == result.method_hit_count
