"""
稽核軌跡與人在迴路回饋（Audit_Logger + HITL_Feedback, R20, R21）
====================================================================
小小守護員 Smart Watchdog Platform — 治理層（Governance）子系統。

本模組提供兩件事，對應 design.md「14. Audit_Logger + HITL_Feedback」：

    def log(actor, action, target, ts) -> AuditEntry
        \"\"\"關鍵操作（判定/分派/模擬/回饋）僅可新增不可竄改 (R21.1, R21.2)。\"\"\"
    def query_audit(filter) -> list[AuditEntry]
        \"\"\"依時間順序回傳 (R21.3)。\"\"\"
    def submit_feedback(fb) -> HITLFeedback
        \"\"\"確為異常/誤報/資料問題/需進一步稽查；關聯機構與判定 (R20)。\"\"\"

設計原則
--------
- Append-only（僅可新增，不可竄改，R21.2）：`AuditLog` 對外只暴露「新增」與
  「查詢」兩種操作，沒有任何更新或刪除既有紀錄的 API。內部以私有 list 保存，
  查詢時回傳「複本」，呼叫端即使改動回傳的 list 也不會影響已寫入的軌跡。
  單筆 `AuditEntry` 本身為 `frozen=True` dataclass（見 src/models.py），
  落實「單筆紀錄不可竄改」的語意。
- 時間排序（R21.3）：查詢一律依 `ts` 由舊到新（穩定排序）回傳。
- 誠實不虛構：回饋標籤限定於需求列舉的四種，非法標籤直接拒絕。

本模組僅依賴標準函式庫與 `src.models` 的共用型別 `AuditEntry` /
`HITLFeedback`，不引入額外執行期相依，維持既有基線的可攜性。

責任 AI：稽核軌跡與回饋屬「人工判斷紀錄」，供模型改進與問責使用；
回饋標籤（如「誤報」）不改寫既有風險分數，僅作為後續改進流程輸入。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .models import AuditEntry, HITLFeedback

# --------------------------------------------------------------------------
# HITL 回饋允許的判定標籤（R20.1）
# --------------------------------------------------------------------------
# 稽查員審核回饋的四種選項，需與 Inspector_Workspace 按鈕一致。
CONFIRMED_ANOMALY = "確為異常"
FALSE_POSITIVE = "誤報"
DATA_ISSUE = "資料問題"
NEEDS_FURTHER_AUDIT = "需進一步稽查"

FEEDBACK_LABELS: tuple[str, ...] = (
    CONFIRMED_ANOMALY,
    FALSE_POSITIVE,
    DATA_ISSUE,
    NEEDS_FURTHER_AUDIT,
)


# --------------------------------------------------------------------------
# 稽核軌跡查詢條件（AuditFilter, R21.3）
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class AuditFilter:
    """稽核軌跡查詢條件（全部為選用；未指定者不過濾）。

    - actor：僅回傳指定操作者的紀錄。
    - action：僅回傳指定操作類型的紀錄（判定/分派/模擬/回饋）。
    - target：僅回傳指定對象的紀錄。
    - start / end：時間區間（含端點）；用於複查特定期間的操作。

    Validates: Requirements 21.3
    """
    actor: str | None = None
    action: str | None = None
    target: str | None = None
    start: datetime | None = None
    end: datetime | None = None

    def matches(self, entry: AuditEntry) -> bool:
        """判斷單筆稽核紀錄是否符合本查詢條件。"""
        if self.actor is not None and entry.actor != self.actor:
            return False
        if self.action is not None and entry.action != self.action:
            return False
        if self.target is not None and entry.target != self.target:
            return False
        if self.start is not None and entry.ts < self.start:
            return False
        if self.end is not None and entry.ts > self.end:
            return False
        return True


# --------------------------------------------------------------------------
# 稽核軌跡記錄器（Audit_Logger, R21）
# --------------------------------------------------------------------------
class AuditLog:
    """Append-only 稽核軌跡記錄器（R21.1, R21.2, R21.3）。

    僅暴露「新增（log）」與「查詢（query_audit）」；不提供更新或刪除
    既有紀錄的方法，以落實「僅可新增不可竄改」（R21.2）。

    查詢回傳的是排序後的複本 list，呼叫端對回傳結果的任何改動都不會
    影響內部已寫入的軌跡（R21.2）。

    Validates: Requirements 21.1, 21.2, 21.3
    """

    def __init__(self, entries: Iterable[AuditEntry] | None = None) -> None:
        # 以私有 list 保存；不對外暴露可變參照。
        self._entries: list[AuditEntry] = list(entries) if entries else []

    def log(
        self,
        actor: str,
        action: str,
        target: str,
        ts: datetime | None = None,
    ) -> AuditEntry:
        """記錄一筆關鍵操作（操作者、操作類型、對象、時間）（R21.1）。

        參數
        ------
        actor : str
            操作者（如稽查員帳號、系統模組）。不可為空字串。
        action : str
            操作類型（判定/分派/模擬/回饋等）。不可為空字串。
        target : str
            操作對象（如機構 park_id、判定 ref）。不可為空字串。
        ts : datetime | None
            操作時間；未提供時以當下 UTC 時間填入（測試可注入固定值）。

        回傳
        ------
        AuditEntry
            新增的稽核紀錄（frozen，不可竄改）。

        例外
        ------
        ValueError
            當 actor / action / target 為空字串時。

        不變式
        ------
        - 新增後 len 只增不減。
        - 既有紀錄不被修改或移除。

        Validates: Requirements 21.1, 21.2
        """
        if not actor or not str(actor).strip():
            raise ValueError("actor 不可為空")
        if not action or not str(action).strip():
            raise ValueError("action 不可為空")
        if not target or not str(target).strip():
            raise ValueError("target 不可為空")

        entry = AuditEntry(
            actor=str(actor),
            action=str(action),
            target=str(target),
            ts=ts if ts is not None else datetime.now(timezone.utc),
        )
        self._entries.append(entry)
        return entry

    def query_audit(self, filter: AuditFilter | None = None) -> list[AuditEntry]:
        """依時間順序（由舊到新）回傳符合條件的稽核紀錄（R21.3）。

        參數
        ------
        filter : AuditFilter | None
            查詢條件；未提供時回傳全部紀錄。

        回傳
        ------
        list[AuditEntry]
            依 `ts` 由舊到新穩定排序的紀錄「複本」。對回傳結果的改動
            不會影響內部軌跡（R21.2）。

        Validates: Requirements 21.3
        """
        if filter is None:
            matched = list(self._entries)
        else:
            matched = [e for e in self._entries if filter.matches(e)]
        # 依時間由舊到新穩定排序（相同 ts 維持寫入順序）。
        matched.sort(key=lambda e: e.ts)
        return matched

    def __len__(self) -> int:
        return len(self._entries)


# --------------------------------------------------------------------------
# 人在迴路回饋收集器（HITL_Feedback, R20）
# --------------------------------------------------------------------------
class FeedbackStore:
    """審核回饋收集器：記錄稽查員回饋並關聯機構與判定（R20）。

    每筆回饋亦寫入所繫的稽核軌跡（若提供 audit_log），落實「回饋屬關鍵操作」
    需被稽核（R21.1）。累積回饋可供模型改進流程取用（R20.3）。

    Validates: Requirements 20.1, 20.2, 20.3
    """

    def __init__(self, audit_log: AuditLog | None = None) -> None:
        self._feedback: list[HITLFeedback] = []
        self._audit_log = audit_log

    def submit_feedback(
        self,
        fb: HITLFeedback,
        actor: str = "inspector",
        ts: datetime | None = None,
    ) -> HITLFeedback:
        """提交一筆審核回饋，並關聯至對應機構與判定（R20.1, R20.2）。

        參數
        ------
        fb : HITLFeedback
            審核回饋，含 entity_id（機構）、verdict_ref（判定）與 label。
            label 必須為四種允許標籤之一（確為異常/誤報/資料問題/需進一步稽查）。
        actor : str
            提交回饋的操作者（用於稽核軌跡）。
        ts : datetime | None
            提交時間（供稽核軌跡；測試可注入）。

        回傳
        ------
        HITLFeedback
            已記錄的回饋（原物件）。

        例外
        ------
        ValueError
            當 label 不在允許清單、或 entity_id / verdict_ref 為空時。

        Validates: Requirements 20.1, 20.2
        """
        if fb.label not in FEEDBACK_LABELS:
            raise ValueError(
                f"回饋標籤無效：{fb.label!r}；允許值為 {FEEDBACK_LABELS}"
            )
        if not fb.entity_id or not str(fb.entity_id).strip():
            raise ValueError("回饋必須關聯機構（entity_id 不可為空）")
        if not fb.verdict_ref or not str(fb.verdict_ref).strip():
            raise ValueError("回饋必須關聯判定（verdict_ref 不可為空）")

        self._feedback.append(fb)

        # 回饋本身是關鍵操作，寫入稽核軌跡（R21.1）。
        if self._audit_log is not None:
            self._audit_log.log(
                actor=actor,
                action="feedback",
                target=f"{fb.entity_id}:{fb.verdict_ref}",
                ts=ts,
            )
        return fb

    def all_feedback(self) -> list[HITLFeedback]:
        """回傳累積回饋的複本，供模型改進流程使用（R20.3）。"""
        return list(self._feedback)

    def feedback_for_entity(self, entity_id: str) -> list[HITLFeedback]:
        """回傳指定機構的所有回饋（複本）。"""
        return [fb for fb in self._feedback if fb.entity_id == entity_id]

    def __len__(self) -> int:
        return len(self._feedback)


# --------------------------------------------------------------------------
# 模組層級便利函式（以共享的預設實例操作）
# --------------------------------------------------------------------------
# 提供簡潔的 log / query_audit / submit_feedback 便利入口，對應 design.md
# 的自由函式簽名；內部委派給共享的預設 AuditLog / FeedbackStore 實例。
_DEFAULT_AUDIT_LOG = AuditLog()
_DEFAULT_FEEDBACK_STORE = FeedbackStore(audit_log=_DEFAULT_AUDIT_LOG)


def log(actor: str, action: str, target: str, ts: datetime | None = None) -> AuditEntry:
    """便利入口：於預設稽核軌跡新增一筆紀錄（R21.1, R21.2）。"""
    return _DEFAULT_AUDIT_LOG.log(actor, action, target, ts)


def query_audit(filter: AuditFilter | None = None) -> list[AuditEntry]:
    """便利入口：依時間順序查詢預設稽核軌跡（R21.3）。"""
    return _DEFAULT_AUDIT_LOG.query_audit(filter)


def submit_feedback(
    fb: HITLFeedback, actor: str = "inspector", ts: datetime | None = None
) -> HITLFeedback:
    """便利入口：向預設回饋收集器提交一筆審核回饋（R20.1, R20.2）。"""
    return _DEFAULT_FEEDBACK_STORE.submit_feedback(fb, actor=actor, ts=ts)
