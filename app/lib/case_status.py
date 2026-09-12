"""
案件狀態（Case Lifecycle）— 輕量持久化
============================================================
把「稽查決策」變成可流轉、可記住、可跨頁共用的狀態，讓系統從「分析報表」
升級為「稽查作戰工作流」。呈現無關（純邏輯 + JSON 持久化），供各頁面共用。

狀態流：
    pending（待研判） → dispatch（建議派查） → investigating（調查中）
                     → closed_confirmed（結案·屬實） / closed_dismissed（結案·不成立）

決策動作 → 目標狀態：
    建議派查   -> dispatch
    存疑待補   -> investigating
    不成立結案 -> closed_dismissed
    結案·屬實 -> closed_confirmed

持久化：data/derived/case_status.json（單一檔案，無需資料庫；競賽環境足夠）。
所有寫入附時間戳與操作者，供稽核軌跡（與 HITL 回饋互補：此處記「決策狀態」，
HITL 記「模型回饋標籤」）。
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STORE_PATH = os.path.join(ROOT, "data", "derived", "case_status.json")

# 狀態鍵 → (中文標籤, 語意層 risk key 用於配色)
STATUS_META: dict[str, tuple[str, str]] = {
    "pending": ("待研判", "medium"),
    "dispatch": ("建議派查", "high"),
    "investigating": ("調查中", "low"),
    "closed_confirmed": ("結案·屬實", "critical"),
    "closed_dismissed": ("結案·不成立", "normal"),
}

# 決策按鈕標籤 → 目標狀態
DECISION_TO_STATUS: dict[str, str] = {
    "建議派查": "dispatch",
    "存疑待補": "investigating",
    "不成立結案": "closed_dismissed",
    "結案·屬實": "closed_confirmed",
}

# 案件頁決策條要呈現的三顆主要按鈕（行動優先）
PRIMARY_DECISIONS: tuple[str, ...] = ("建議派查", "存疑待補", "不成立結案")

# 視為「已完成稽查/處置」的終態（供派工台「排除已稽查」使用）
CLOSED_STATUSES: frozenset[str] = frozenset({"closed_confirmed", "closed_dismissed"})
# 視為「已納入處置流程」的狀態（收件匣判斷是否仍待研判）
ACTIVE_STATUSES: frozenset[str] = frozenset({"dispatch", "investigating"})


@dataclass
class CaseRecord:
    """單一機構的案件狀態紀錄。"""
    entity_id: str
    status: str = "pending"
    updated_at: str = ""
    actor: str = ""
    note: str = ""
    history: list[dict] = field(default_factory=list)

    def status_label(self) -> str:
        return STATUS_META.get(self.status, (self.status, "medium"))[0]

    def status_risk_key(self) -> str:
        return STATUS_META.get(self.status, (self.status, "medium"))[1]

    def is_closed(self) -> bool:
        return self.status in CLOSED_STATUSES

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "status": self.status,
            "updated_at": self.updated_at,
            "actor": self.actor,
            "note": self.note,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CaseRecord":
        return cls(
            entity_id=str(d.get("entity_id", "")),
            status=str(d.get("status", "pending")),
            updated_at=str(d.get("updated_at", "")),
            actor=str(d.get("actor", "")),
            note=str(d.get("note", "")),
            history=list(d.get("history", [])),
        )


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime())


def _load_raw(path: str | None = None) -> dict:
    p = path or _STORE_PATH
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        # 檔案毀損不應阻擋系統啟動；退化為空狀態。
        return {}


def _save_raw(data: dict, path: str | None = None) -> None:
    p = path or _STORE_PATH
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load_all(path: str | None = None) -> dict[str, CaseRecord]:
    """載入所有案件狀態，回傳 {entity_id: CaseRecord}。"""
    raw = _load_raw(path)
    out: dict[str, CaseRecord] = {}
    for eid, rec in raw.items():
        if isinstance(rec, dict):
            out[str(eid)] = CaseRecord.from_dict({**rec, "entity_id": eid})
    return out


def get_status(entity_id, path: str | None = None) -> CaseRecord:
    """取得單一機構的狀態；不存在時回傳預設 pending 紀錄（不寫檔）。"""
    eid = "" if entity_id is None else str(entity_id).strip()
    all_rec = load_all(path)
    return all_rec.get(eid, CaseRecord(entity_id=eid, status="pending"))


def set_status(entity_id, decision_or_status, actor="inspector",
               note="", path: str | None = None) -> CaseRecord:
    """設定機構案件狀態並持久化，附時間戳與稽核歷史。

    decision_or_status 可為決策標籤（如「建議派查」）或狀態鍵（如 "dispatch"）。
    無效值會拋出 ValueError（呼叫端負責處理）。
    """
    eid = "" if entity_id is None else str(entity_id).strip()
    if not eid:
        raise ValueError("entity_id 不可為空")

    key = str(decision_or_status).strip()
    if key in DECISION_TO_STATUS:
        status = DECISION_TO_STATUS[key]
        decision_label = key
    elif key in STATUS_META:
        status = key
        decision_label = STATUS_META[key][0]
    else:
        raise ValueError(f"未知的決策或狀態：{key}")

    raw = _load_raw(path)
    prev = raw.get(eid, {})
    history = list(prev.get("history", []))
    history.append({
        "status": status,
        "decision": decision_label,
        "at": _now(),
        "actor": actor,
        "note": note,
    })
    rec = CaseRecord(
        entity_id=eid, status=status, updated_at=_now(),
        actor=actor, note=note, history=history,
    )
    raw[eid] = rec.to_dict()
    _save_raw(raw, path)
    return rec


def summary(path: str | None = None) -> dict[str, int]:
    """回傳各狀態的機構計數（供主頁收件匣、KPI 使用）。"""
    counts = {k: 0 for k in STATUS_META}
    for rec in load_all(path).values():
        counts[rec.status] = counts.get(rec.status, 0) + 1
    return counts


def closed_entity_ids(path: str | None = None) -> set[str]:
    """回傳已結案（屬實/不成立）的機構 id 集合，供派工台排除已稽查。"""
    return {eid for eid, rec in load_all(path).items() if rec.is_closed()}
