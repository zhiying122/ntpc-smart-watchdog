"""
動態資料連接器 src/live_source.py 的單元測試。

策略：不依賴網路（用 monkeypatch 注入假資料與模擬失敗），確保測試穩定、
可離線在 CI 執行。真實來源可用性另以手動整合驗證（已於開發時實測）。
"""
import json
import os

import pytest

from src import live_source as ls


# ---------------------------------------------------------------------------
# 假資料（貼近真實結構）
# ---------------------------------------------------------------------------
def _fake_geojson():
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.5, 25.0]},
                "properties": {
                    "id": "abc-1", "title": "新北市立測試幼兒園", "type": "公立",
                    "city": "新北市", "town": "板橋區", "address": "測試路1號",
                    "owner": "王小明", "count_approved": "120", "monthly": 5000,
                    "penalty": "無",
                },
            },
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [121.0, 24.0]},
                "properties": {
                    "id": "xyz-2", "title": "台北市某幼兒園", "type": "私立",
                    "city": "臺北市", "town": "大安區", "address": "他縣路2號",
                    "owner": "李大華", "count_approved": "80", "monthly": 12000,
                    "penalty": "有",
                },
            },
        ],
    }


def _fake_punish():
    return {
        "行為人：張三": [
            {"date": "2025/01/01", "law": "第33條", "punishment": "罰鍰：60,000元",
             "id": "p1"},
        ],
        "負責人：新北市立測試幼兒園": [
            {"date": "2024/06/15", "law": "第30條", "punishment": "罰鍰：30,000元",
             "id": "p2"},
        ],
        "無冒號鍵": [
            {"date": "2023/03/03", "law": "第10條", "punishment": "警告", "id": "p3"},
        ],
    }


# ---------------------------------------------------------------------------
# 解析：機構 GeoJSON
# ---------------------------------------------------------------------------
def test_parse_preschools_filters_by_city():
    res = ls.parse_preschools(_fake_geojson(), city="新北市")
    assert len(res) == 1  # 只留新北市
    inst = res[0]
    assert inst.park_name == "新北市立測試幼兒園"
    assert inst.district == "板橋區"
    assert inst.count_approved == 120
    assert inst.monthly == 5000.0
    assert inst.lat == 25.0 and inst.lng == 121.5  # GeoJSON 為 [lng, lat]
    assert inst.owner == "王小明"


def test_parse_preschools_empty_or_malformed():
    assert ls.parse_preschools(None) == []
    assert ls.parse_preschools({}) == []
    assert ls.parse_preschools({"features": [None, 123, "x"]}) == []


def test_parse_preschools_missing_fields_safe():
    gj = {"features": [{"properties": {"city": "新北市"}}]}  # 幾乎全缺
    res = ls.parse_preschools(gj)
    assert len(res) == 1
    assert res[0].count_approved is None
    assert res[0].monthly is None
    assert res[0].lat is None and res[0].lng is None


# ---------------------------------------------------------------------------
# 解析：裁罰
# ---------------------------------------------------------------------------
def test_parse_penalties_subject_type_and_count():
    res = ls.parse_penalties(_fake_punish())
    assert len(res) == 3
    by_type = {r.subject_type for r in res}
    assert "行為人" in by_type and "負責人" in by_type and "其他" in by_type
    zhangsan = next(r for r in res if r.subject == "張三")
    assert zhangsan.punishment == "罰鍰：60,000元"
    assert zhangsan.record_id == "p1"


def test_parse_penalties_malformed():
    assert ls.parse_penalties(None) == []
    assert ls.parse_penalties({"k": "not-a-list"}) == []
    assert ls.parse_penalties({"k": [None, 1]}) == []


# ---------------------------------------------------------------------------
# 抓取 + 快取 + 離線備援
# ---------------------------------------------------------------------------
def test_fetch_json_live_success_writes_cache(tmp_path, monkeypatch):
    cache = str(tmp_path / "c.json")
    monkeypatch.setattr(ls, "_http_get_json", lambda url, timeout=30: {"ok": 1})
    fr = ls.fetch_json("http://x", cache)
    assert fr.is_live is True
    assert fr.ok and fr.data == {"ok": 1}
    assert fr.used_fallback is False
    assert os.path.exists(cache)  # 已寫快取


def test_fetch_json_falls_back_to_cache_on_failure(tmp_path, monkeypatch):
    cache = str(tmp_path / "c.json")
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump({"cached": True}, fh)

    def _boom(url, timeout=30):
        raise TimeoutError("網路逾時")

    monkeypatch.setattr(ls, "_http_get_json", _boom)
    fr = ls.fetch_json("http://x", cache)
    assert fr.is_live is False
    assert fr.used_fallback is True
    assert fr.data == {"cached": True}
    assert fr.error is not None  # 有錯誤說明


def test_fetch_json_no_cache_no_network(tmp_path, monkeypatch):
    cache = str(tmp_path / "missing.json")

    def _boom(url, timeout=30):
        raise ConnectionError("無網路")

    monkeypatch.setattr(ls, "_http_get_json", _boom)
    fr = ls.fetch_json("http://x", cache)
    assert fr.ok is False
    assert fr.data is None
    assert fr.used_fallback is True


def test_fetch_json_prefer_cache(tmp_path, monkeypatch):
    cache = str(tmp_path / "c.json")
    with open(cache, "w", encoding="utf-8") as fh:
        json.dump({"cached": True}, fh)
    # prefer_cache=True 時不應觸網。
    monkeypatch.setattr(ls, "_http_get_json",
                        lambda *a, **k: pytest.fail("不應觸網"))
    fr = ls.fetch_json("http://x", cache, prefer_cache=True)
    assert fr.data == {"cached": True}
    assert fr.is_live is False


# ---------------------------------------------------------------------------
# 完整載入 + 狀態旗標
# ---------------------------------------------------------------------------
def test_load_live_dataset_all_live(monkeypatch):
    def _fake_fetch(url, cache, timeout=30, prefer_cache=False):
        data = _fake_geojson() if "preschool" in url else _fake_punish()
        return ls.FetchResult(data=data, is_live=True, fetched_at="now",
                              source_url=url)

    monkeypatch.setattr(ls, "fetch_json", _fake_fetch)
    ds = ls.load_live_dataset()
    assert ds.is_live is True
    assert len(ds.institutions) == 1  # 只有新北
    assert len(ds.penalties) == 3


def test_load_live_dataset_fallback_marks_not_live(monkeypatch):
    def _fake_fetch(url, cache, timeout=30, prefer_cache=False):
        data = _fake_geojson() if "preschool" in url else _fake_punish()
        live = "preschool" not in url  # 機構源用備援
        return ls.FetchResult(data=data, is_live=live, used_fallback=not live,
                              source_url=url)

    monkeypatch.setattr(ls, "fetch_json", _fake_fetch)
    ds = ls.load_live_dataset()
    assert ds.is_live is False  # 任一備援即非全即時


def test_attribution_present():
    res = ls.parse_preschools(_fake_geojson())
    assert "全國教保資訊網" in res[0].source_attribution
    pens = ls.parse_penalties(_fake_punish())
    assert "g0v" in pens[0].source_attribution
