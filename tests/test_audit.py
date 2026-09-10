"""
稽核軌跡與 HITL 回饋單元測試（Audit_Logger + HITL_Feedback, R20, R21）
=========================================================================
驗證 src/audit.py：
  - log(actor, action, target, ts) 為 append-only 且不可竄改。
  - query_audit(filter) 依時間順序（由舊到新）回傳，並支援條件過濾。
  - submit_feedback(fb) 記錄四種允許標籤並關聯機構與判定；非法標籤被拒。
  - 回饋同步寫入稽核軌跡（回饋屬關鍵操作）。

對應 Task 15.2「實作稽核軌跡與 HITL 回饋」
（Requirements 20.1, 20.2, 20.3, 21.1, 21.2, 21.3）。
屬性測試（Property 40, 41）另見 Task 15.4。
"""
from datetime import datetime, timedelta

import pytest

from src.audit import (
    CONFIRMED_ANOMALY,
    DATA_ISSUE,
    FALSE_POSITIVE,
    FEEDBACK_LABELS,
    NEEDS_FURTHER_AUDIT,
    AuditFilter,
    AuditLog,
    FeedbackStore,
)
from src.models import AuditEntry, HITLFeedback


# --------------------------------------------------------------------------
# log / append-only（R21.1, R21.2）
# --------------------------------------------------------------------------
def test_log_records_all_fields():
    """log 記錄操作者、操作類型、對象與時間（R21.1）。"""
    log = AuditLog()
    ts = datetime(2026, 1, 1, 9, 0, 0)
    entry = log.log("inspector-01", "判定", "park-13601", ts)

    assert isinstance(entry, AuditEntry)
    assert entry.actor == "inspector-01"
    assert entry.action == "判定"
    assert entry.target == "park-13601"
    assert entry.ts == ts
    assert len(log) == 1


def test_log_defaults_timestamp_when_omitted():
    """未提供 ts 時自動填入時間戳記。"""
    log = AuditLog()
    entry = log.log("system", "分派", "batch-1")
    assert isinstance(entry.ts, datetime)


def test_log_append_only_len_only_grows():
    """連續 log 後長度只增不減，既有紀錄保留（R21.2）。"""
    log = AuditLog()
    first = log.log("a", "判定", "t1", datetime(2026, 1, 1))
    log.log("b", "模擬", "t2", datetime(2026, 1, 2))
    log.log("c", "回饋", "t3", datetime(2026, 1, 3))

    assert len(log) == 3
    # 最初寫入的紀錄仍在且未被修改
    assert log.query_audit()[0] == first


def test_audit_entry_is_frozen():
    """AuditEntry 為 frozen，單筆紀錄不可竄改（R21.2）。"""
    entry = AuditEntry("a", "判定", "t", datetime(2026, 1, 1))
    with pytest.raises(Exception):
        entry.actor = "hacker"  # type: ignore[misc]


def test_query_result_mutation_does_not_affect_log():
    """改動查詢回傳的 list 不影響內部軌跡（R21.2）。"""
    log = AuditLog()
    log.log("a", "判定", "t1", datetime(2026, 1, 1))
    result = log.query_audit()
    result.clear()
    # 內部紀錄不受影響
    assert len(log) == 1
    assert len(log.query_audit()) == 1


@pytest.mark.parametrize(
    "actor,action,target",
    [("", "判定", "t"), ("a", "", "t"), ("a", "判定", ""), ("  ", "判定", "t")],
)
def test_log_rejects_empty_fields(actor, action, target):
    """空的 actor/action/target 被拒絕。"""
    log = AuditLog()
    with pytest.raises(ValueError):
        log.log(actor, action, target, datetime(2026, 1, 1))


# --------------------------------------------------------------------------
# query_audit：時間排序與過濾（R21.3）
# --------------------------------------------------------------------------
def test_query_audit_returns_time_ordered():
    """query_audit 依時間由舊到新回傳，與寫入順序無關（R21.3）。"""
    log = AuditLog()
    log.log("a", "判定", "t3", datetime(2026, 3, 1))
    log.log("b", "判定", "t1", datetime(2026, 1, 1))
    log.log("c", "判定", "t2", datetime(2026, 2, 1))

    result = log.query_audit()
    ts_list = [e.ts for e in result]
    assert ts_list == sorted(ts_list)
    assert [e.target for e in result] == ["t1", "t2", "t3"]


def test_query_audit_filter_by_actor():
    log = AuditLog()
    log.log("alice", "判定", "t1", datetime(2026, 1, 1))
    log.log("bob", "分派", "t2", datetime(2026, 1, 2))
    log.log("alice", "模擬", "t3", datetime(2026, 1, 3))

    result = log.query_audit(AuditFilter(actor="alice"))
    assert len(result) == 2
    assert all(e.actor == "alice" for e in result)


def test_query_audit_filter_by_action_and_target():
    log = AuditLog()
    log.log("a", "判定", "park-1", datetime(2026, 1, 1))
    log.log("a", "分派", "park-1", datetime(2026, 1, 2))
    log.log("a", "判定", "park-2", datetime(2026, 1, 3))

    result = log.query_audit(AuditFilter(action="判定", target="park-1"))
    assert len(result) == 1
    assert result[0].target == "park-1"
    assert result[0].action == "判定"


def test_query_audit_filter_by_time_range():
    log = AuditLog()
    log.log("a", "判定", "t1", datetime(2026, 1, 1))
    log.log("a", "判定", "t2", datetime(2026, 2, 1))
    log.log("a", "判定", "t3", datetime(2026, 3, 1))

    result = log.query_audit(
        AuditFilter(start=datetime(2026, 1, 15), end=datetime(2026, 2, 15))
    )
    assert [e.target for e in result] == ["t2"]


def test_query_audit_empty_log_returns_empty_list():
    assert AuditLog().query_audit() == []


# --------------------------------------------------------------------------
# submit_feedback（R20.1, R20.2, R20.3）
# --------------------------------------------------------------------------
def test_feedback_labels_are_the_four_options():
    """回饋標籤恰為需求列舉的四種（R20.1）。"""
    assert set(FEEDBACK_LABELS) == {
        CONFIRMED_ANOMALY,
        FALSE_POSITIVE,
        DATA_ISSUE,
        NEEDS_FURTHER_AUDIT,
    }


@pytest.mark.parametrize("label", list(FEEDBACK_LABELS))
def test_submit_feedback_accepts_all_valid_labels(label):
    """四種允許標籤皆可提交並關聯機構與判定（R20.1, R20.2）。"""
    store = FeedbackStore()
    fb = HITLFeedback(entity_id="park-1", verdict_ref="v-1", label=label)
    saved = store.submit_feedback(fb)
    assert saved.label == label
    assert store.feedback_for_entity("park-1") == [fb]


def test_submit_feedback_rejects_invalid_label():
    store = FeedbackStore()
    fb = HITLFeedback(entity_id="park-1", verdict_ref="v-1", label="隨便亂填")
    with pytest.raises(ValueError):
        store.submit_feedback(fb)


@pytest.mark.parametrize("entity_id,verdict_ref", [("", "v-1"), ("park-1", "")])
def test_submit_feedback_requires_entity_and_verdict(entity_id, verdict_ref):
    """回饋必須關聯機構與判定（R20.2）。"""
    store = FeedbackStore()
    fb = HITLFeedback(entity_id=entity_id, verdict_ref=verdict_ref, label=FALSE_POSITIVE)
    with pytest.raises(ValueError):
        store.submit_feedback(fb)


def test_submit_feedback_writes_to_audit_log():
    """回饋屬關鍵操作，同步寫入稽核軌跡（R21.1）。"""
    log = AuditLog()
    store = FeedbackStore(audit_log=log)
    fb = HITLFeedback(entity_id="park-1", verdict_ref="v-1", label=CONFIRMED_ANOMALY)
    store.submit_feedback(fb, actor="inspector-9", ts=datetime(2026, 5, 1))

    audit = log.query_audit(AuditFilter(action="feedback"))
    assert len(audit) == 1
    assert audit[0].actor == "inspector-9"
    assert audit[0].target == "park-1:v-1"


def test_all_feedback_accumulates_for_model_improvement():
    """累積回饋可供模型改進流程使用（R20.3）。"""
    store = FeedbackStore()
    store.submit_feedback(HITLFeedback("park-1", "v-1", CONFIRMED_ANOMALY))
    store.submit_feedback(HITLFeedback("park-2", "v-2", FALSE_POSITIVE))
    assert len(store.all_feedback()) == 2


def test_all_feedback_returns_copy():
    """all_feedback 回傳複本，改動不影響內部狀態。"""
    store = FeedbackStore()
    store.submit_feedback(HITLFeedback("park-1", "v-1", DATA_ISSUE))
    result = store.all_feedback()
    result.clear()
    assert len(store) == 1
