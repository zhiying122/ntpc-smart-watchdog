"""裁罰-機構實體比對 src/penalty_match.py 的單元測試。

驗證信心分級的正確性與責任 AI 不變式：不確定比對不得升級為 HIGH。
"""
from dataclasses import dataclass

import pytest

from src import penalty_match as pm


# ---------------------------------------------------------------------------
# 測試替身（貼近 live_source 的型別）
# ---------------------------------------------------------------------------
@dataclass
class FakeInst:
    park_id: str
    park_name: str
    owner: str = ""


@dataclass
class FakePen:
    subject: str
    subject_type: str
    record_id: str
    date: str = ""
    law: str = ""
    punishment: str = ""


def _insts():
    return [
        FakeInst("A", "新北市私立快樂幼兒園", owner="王大明"),
        FakeInst("B", "新北市私立陽光幼兒園", owner="李小華"),
        FakeInst("C", "新北市私立星星幼兒園", owner="李小華"),  # 與 B 同負責人
    ]


# ---------------------------------------------------------------------------
# 名稱直接相符 → HIGH
# ---------------------------------------------------------------------------
def test_name_exact_match_is_high():
    pens = [FakePen("新北市私立快樂幼兒園", "負責人", "p1", punishment="罰鍰")]
    res = pm.match_penalties(pens, _insts())
    assert len(res) == 1
    assert res[0].confidence == pm.HIGH
    assert res[0].method == "name_exact"
    assert res[0].park_id == "A"


# ---------------------------------------------------------------------------
# 負責人唯一相符 → HIGH
# ---------------------------------------------------------------------------
def test_owner_unique_match_is_high():
    pens = [FakePen("王大明", "負責人", "p2")]
    res = pm.match_penalties(pens, _insts())
    assert len(res) == 1
    assert res[0].confidence == pm.HIGH
    assert res[0].method == "owner_unique"
    assert res[0].park_id == "A"


# ---------------------------------------------------------------------------
# 負責人對應多間 → MEDIUM（不得升級為 HIGH）
# ---------------------------------------------------------------------------
def test_owner_ambiguous_match_is_medium():
    pens = [FakePen("李小華", "負責人", "p3")]
    res = pm.match_penalties(pens, _insts())
    assert len(res) == 2  # B 與 C 各一
    assert all(m.confidence == pm.MEDIUM for m in res)
    assert all(m.method == "owner_ambiguous" for m in res)
    assert {m.park_id for m in res} == {"B", "C"}


# ---------------------------------------------------------------------------
# 無法比對 → 不輸出（不臆測）
# ---------------------------------------------------------------------------
def test_no_match_produces_nothing():
    pens = [FakePen("查無此人", "行為人", "p4")]
    res = pm.match_penalties(pens, _insts())
    assert res == []


def test_empty_subject_skipped():
    pens = [FakePen("", "行為人", "p5"), FakePen("   ", "負責人", "p6")]
    res = pm.match_penalties(pens, _insts())
    assert res == []


# ---------------------------------------------------------------------------
# 彙總與確認計數
# ---------------------------------------------------------------------------
def test_summarize_separates_confirmed_and_pending():
    pens = [
        FakePen("王大明", "負責人", "p1"),      # HIGH → A
        FakePen("李小華", "負責人", "p2"),      # MEDIUM → B, C
    ]
    matches = pm.match_penalties(pens, _insts())
    summaries = pm.summarize_by_institution(matches)
    assert summaries["A"].confirmed_count == 1
    assert summaries["A"].pending_count == 0
    assert summaries["B"].confirmed_count == 0
    assert summaries["B"].pending_count == 1


def test_confirmed_counts_only_high():
    pens = [
        FakePen("王大明", "負責人", "p1"),      # HIGH → A
        FakePen("王大明", "負責人", "p1b"),     # HIGH → A（第二筆）
        FakePen("李小華", "負責人", "p2"),      # MEDIUM → 不計入
    ]
    counts = pm.confirmed_penalty_counts(pm.match_penalties(pens, _insts()))
    assert counts.get("A") == 2
    assert "B" not in counts  # MEDIUM 不計入確認數
    assert "C" not in counts


# ---------------------------------------------------------------------------
# 相容 dict 輸入
# ---------------------------------------------------------------------------
def test_accepts_dict_inputs():
    insts = [{"park_id": "A", "park_name": "快樂幼兒園", "owner": "王大明"}]
    pens = [{"subject": "王大明", "subject_type": "負責人", "record_id": "p1"}]
    res = pm.match_penalties(pens, insts)
    assert len(res) == 1 and res[0].confidence == pm.HIGH


# ---------------------------------------------------------------------------
# 責任 AI：每筆比對都有可追溯依據
# ---------------------------------------------------------------------------
def test_every_match_has_evidence():
    pens = [FakePen("王大明", "負責人", "p1"), FakePen("李小華", "負責人", "p2")]
    for m in pm.match_penalties(pens, _insts()):
        assert m.evidence
        assert m.penalty_id
