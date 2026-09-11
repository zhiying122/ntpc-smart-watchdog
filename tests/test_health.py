"""系統健康檢查 src/health.py 的單元測試。"""
import os
import time

import pandas as pd
import pytest

from src import health


# ---------------------------------------------------------------------------
# 契約資料檔檢查
# ---------------------------------------------------------------------------
def test_contract_missing_is_error(monkeypatch):
    monkeypatch.setattr(health, "LATEST_CSV", "/no/such/file.csv")
    item = health.check_contract_data()
    assert item.status == health.ERROR


def test_contract_fresh_is_ok(tmp_path, monkeypatch):
    f = tmp_path / "latest.csv"
    f.write_text("x", encoding="utf-8")
    monkeypatch.setattr(health, "LATEST_CSV", str(f))
    item = health.check_contract_data()
    assert item.status == health.OK


def test_contract_stale_is_warn(tmp_path, monkeypatch):
    f = tmp_path / "latest.csv"
    f.write_text("x", encoding="utf-8")
    old = time.time() - (health.DATA_STALE_WARN_DAYS + 10) * 86400
    os.utime(str(f), (old, old))
    monkeypatch.setattr(health, "LATEST_CSV", str(f))
    item = health.check_contract_data()
    assert item.status == health.WARN


# ---------------------------------------------------------------------------
# 快取檢查
# ---------------------------------------------------------------------------
def test_cache_missing_is_warn(monkeypatch):
    item = health.check_cache("/no/such/cache.json", "測試")
    assert item.status == health.WARN
    assert "尚無本地快取" in item.detail


def test_cache_fresh_is_ok(tmp_path):
    f = tmp_path / "c.json"
    f.write_text("{}", encoding="utf-8")
    item = health.check_cache(str(f), "測試")
    assert item.status == health.OK


# ---------------------------------------------------------------------------
# 資料完整性
# ---------------------------------------------------------------------------
def test_integrity_ok():
    df = pd.DataFrame({"park_id": [1], "park_name": ["a"],
                       "risk_total": [50], "risk_level": ["中"]})
    assert health.check_data_integrity(df).status == health.OK


def test_integrity_missing_columns_is_error():
    df = pd.DataFrame({"park_id": [1]})
    assert health.check_data_integrity(df).status == health.ERROR


def test_integrity_empty_is_error():
    df = pd.DataFrame({"park_id": [], "park_name": [],
                       "risk_total": [], "risk_level": []})
    assert health.check_data_integrity(df).status == health.ERROR


# ---------------------------------------------------------------------------
# 核心模組 import 健檢
# ---------------------------------------------------------------------------
def test_core_modules_all_load():
    items = health.check_core_modules()
    assert len(items) == len(health._CORE_MODULES)
    # 所有核心模組應可載入。
    assert all(i.status == health.OK for i in items), \
        [i.name for i in items if i.status != health.OK]


# ---------------------------------------------------------------------------
# 整體報告
# ---------------------------------------------------------------------------
def test_run_health_check_structure():
    df = pd.DataFrame({"park_id": [1], "park_name": ["a"],
                       "risk_total": [50], "risk_level": ["中"]})
    report = health.run_health_check(df)
    assert len(report.items) >= 5
    counts = report.counts()
    assert sum(counts.values()) == len(report.items)
    assert report.overall in (health.OK, health.WARN, health.ERROR)


def test_overall_reflects_worst():
    r = health.HealthReport(items=[
        health.HealthItem("a", health.OK, "ok"),
        health.HealthItem("b", health.WARN, "warn"),
    ])
    assert r.overall == health.WARN
    r.items.append(health.HealthItem("c", health.ERROR, "err"))
    assert r.overall == health.ERROR
