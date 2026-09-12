"""
裁罰-機構實體比對（Penalty-to-Institution Matcher, R17.2 / R17.3 / R17.4）
============================================================================
小小守護員 Smart Watchdog Platform — 將動態抓取的裁罰紀錄（多以「行為人／
負責人」個人姓名為鍵）比對到具體教保機構，並以**信心分級**輸出，絕不把
不確定的比對當成確定事實。

為什麼需要信心分級（責任 AI，關鍵）：
--------------------------------------------------------------------------
裁罰 JSON 的鍵多為個人姓名（行為人 777 筆、負責人 2061 筆），而非機構名。
把「張三」對到「XX 幼兒園」須靠機構的 `owner`（負責人）欄位比對，此比對
**本質不確定**（同名、負責人異動、資料時點不同皆可能錯配）。政府系統最忌
把不確定比對當事實去影響風險分、冤枉機構。故本模組：

  - 只輸出「比對結果 + 信心等級 + 依據」，不直接改任何機構的風險分。
  - 三級信心：
      HIGH   — 裁罰對象名稱 == 機構名稱（正規化後相等），或負責人姓名與
               機構 owner 完全相符且該姓名在母體中唯一。
      MEDIUM — 負責人姓名與機構 owner 完全相符，但該姓名對應多間機構
               （無法唯一判定）。
      LOW    — 僅部分相符 / 疑似，僅供人工參考。
  - 每一筆比對保留可追溯依據（來源裁罰 id、比對方法、依據字串）。
  - 提供 aggregate：僅將 HIGH 信心比對計入「機構確認裁罰數」，MEDIUM/LOW
    另計為「待人工確認」，供風險引擎選擇性、可追溯地採用。

沿用 `src/entity_resolver.normalize_name` 之名稱正規化（單一事實來源）。
本模組為純函式、不 import streamlit，可離線測試。
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from src.entity_resolver import normalize_name

# 信心等級常數
HIGH = "high"
MEDIUM = "medium"
LOW = "low"


@dataclass
class PenaltyMatch:
    """單筆裁罰對機構的比對結果（含信心與可追溯依據）。

    - penalty_id：來源裁罰紀錄 id（可追溯）。
    - subject：裁罰對象名稱（行為人/負責人姓名或機構名）。
    - subject_type：對象別（行為人/負責人/其他）。
    - park_id：比對到的機構識別碼。
    - park_name：比對到的機構名稱。
    - confidence：HIGH / MEDIUM / LOW。
    - method：比對方法（name_exact / owner_unique / owner_ambiguous / partial）。
    - evidence：人類可讀依據字串。
    - date / law / punishment：裁罰內容（供顯示）。
    """
    penalty_id: str
    subject: str
    subject_type: str
    park_id: str
    park_name: str
    confidence: str
    method: str
    evidence: str
    date: str = ""
    law: str = ""
    punishment: str = ""


@dataclass
class MatchSummary:
    """單一機構的裁罰比對彙總（供風險引擎選擇性採用）。

    - park_id / park_name：機構識別。
    - confirmed_count：HIGH 信心比對數（建議計入）。
    - pending_count：MEDIUM + LOW 比對數（待人工確認，不建議直接計分）。
    - matches：該機構所有比對明細（含各信心等級）。
    """
    park_id: str
    park_name: str
    confirmed_count: int = 0
    pending_count: int = 0
    matches: list[PenaltyMatch] = field(default_factory=list)


# --------------------------------------------------------------------------
# 內部：建立比對索引
# --------------------------------------------------------------------------
def _index_institutions(institutions: Iterable) -> tuple[dict, dict]:
    """建立 (正規化機構名→[inst], 正規化owner→[inst]) 兩個索引。

    institutions 元素需具屬性 park_id / park_name / owner（如
    live_source.NormalizedInstitution），或為含同名鍵的 dict。
    """
    by_name: dict[str, list] = defaultdict(list)
    by_owner: dict[str, list] = defaultdict(list)
    for inst in institutions:
        name = _attr(inst, "park_name")
        owner = _attr(inst, "owner")
        nname = normalize_name(name)
        nowner = normalize_name(owner)
        if nname:
            by_name[nname].append(inst)
        if nowner:
            by_owner[nowner].append(inst)
    return by_name, by_owner


def _attr(obj, key: str) -> str:
    """相容 dataclass 物件與 dict 的屬性取值。"""
    if isinstance(obj, dict):
        return str(obj.get(key) or "")
    return str(getattr(obj, key, "") or "")


# --------------------------------------------------------------------------
# 主流程：比對
# --------------------------------------------------------------------------
def match_penalties(penalties: Iterable, institutions: Iterable) -> list[PenaltyMatch]:
    """將裁罰紀錄比對到機構，輸出含信心等級的比對清單（R17.2–R17.4）。

    penalties 元素需具屬性 subject / subject_type / date / law / punishment /
    record_id（如 live_source.PenaltyRecord）或含同名鍵的 dict。

    比對規則（依信心由高至低）：
      1. 裁罰對象正規化名稱 == 某機構正規化名稱 → HIGH（name_exact）。
      2. 裁罰對象正規化名稱 == 某機構 owner，且該 owner 唯一對應一間機構
         → HIGH（owner_unique）。
      3. 同上但 owner 對應多間機構 → 對每間輸出 MEDIUM（owner_ambiguous）。
      4. 其餘 → 不輸出（避免臆測）。低信心 partial 比對保留為未來擴充點，
         預設不啟用，以免產生大量雜訊。

    不會直接修改任何機構風險分；僅輸出可追溯的比對結果。
    """
    by_name, by_owner = _index_institutions(institutions)
    results: list[PenaltyMatch] = []

    # 去重（資料正確性 / 責任 AI）：來源裁罰資料常含重複紀錄（相同 record_id，
    # 或 id 缺漏時以 對象+日期+法條+處分 判定重複）。若不去重，同一裁罰會被
    # 重複計入機構的 confirmed_count，虛增風險分。這裡在比對前先去重。
    _deduped = []
    _seen_pen: set = set()
    for pen in penalties:
        _rid = _attr(pen, "record_id").strip()
        # 來源資料中 id 為受處分對象 UUID，同一對象常有多筆不同日期/處分（如罰鍰、降收、停招）。
        # 以 對象+日期+法條+處分 判定重複；若皆空則以 record_id 判定。
        _content = "|".join([
            _attr(pen, "subject"), _attr(pen, "date"),
            _attr(pen, "law"), _attr(pen, "punishment"),
        ])
        _has_details = any([_attr(pen, "date"), _attr(pen, "law"), _attr(pen, "punishment")])
        _key = _content if _has_details else (_rid or _content)
        if _key in _seen_pen:
            continue
        _seen_pen.add(_key)
        _deduped.append(pen)

    for pen in _deduped:
        subject = _attr(pen, "subject")
        nsubject = normalize_name(subject)
        if not nsubject:
            continue

        pid = _attr(pen, "record_id")
        stype = _attr(pen, "subject_type")
        pdate = _attr(pen, "date")
        plaw = _attr(pen, "law")
        ppun = _attr(pen, "punishment")

        # 規則 1：對象名稱直接等於機構名稱 → HIGH。
        if nsubject in by_name:
            for inst in by_name[nsubject]:
                results.append(PenaltyMatch(
                    penalty_id=pid, subject=subject, subject_type=stype,
                    park_id=_attr(inst, "park_id"), park_name=_attr(inst, "park_name"),
                    confidence=HIGH, method="name_exact",
                    evidence=f"裁罰對象名稱與機構名稱正規化後相符：'{subject}'",
                    date=pdate, law=plaw, punishment=ppun,
                ))
            continue

        # 規則 2/3：對象名稱等於某機構 owner。
        if nsubject in by_owner:
            matched = by_owner[nsubject]
            unique = len(matched) == 1
            for inst in matched:
                results.append(PenaltyMatch(
                    penalty_id=pid, subject=subject, subject_type=stype,
                    park_id=_attr(inst, "park_id"), park_name=_attr(inst, "park_name"),
                    confidence=HIGH if unique else MEDIUM,
                    method="owner_unique" if unique else "owner_ambiguous",
                    evidence=(
                        f"裁罰對象（{stype}）'{subject}' 與機構負責人相符"
                        + ("，且該負責人唯一對應此機構。"
                           if unique else
                           f"，但該負責人對應 {len(matched)} 間機構，無法唯一判定，待人工確認。")
                    ),
                    date=pdate, law=plaw, punishment=ppun,
                ))
            continue

        # 其餘：不臆測，不輸出。

    return results


def summarize_by_institution(matches: Iterable[PenaltyMatch]) -> dict[str, MatchSummary]:
    """將比對清單彙總到各機構，區分「確認（HIGH）」與「待確認（MEDIUM/LOW）」。

    回傳 {park_id: MatchSummary}。confirmed_count 僅計 HIGH 信心比對，供風險
    引擎選擇性、可追溯地採用；MEDIUM/LOW 一律計入 pending，不建議直接計分。
    """
    summaries: dict[str, MatchSummary] = {}
    for m in matches:
        s = summaries.get(m.park_id)
        if s is None:
            s = MatchSummary(park_id=m.park_id, park_name=m.park_name)
            summaries[m.park_id] = s
        s.matches.append(m)
        if m.confidence == HIGH:
            s.confirmed_count += 1
        else:
            s.pending_count += 1
    return summaries


def confirmed_penalty_counts(matches: Iterable[PenaltyMatch]) -> dict[str, int]:
    """回傳 {park_id: 確認裁罰數（僅 HIGH 信心）}。

    此為風險引擎可安全採用的裁罰標籤來源——只採用高信心比對，避免以不確定
    比對推高機構風險（責任 AI）。
    """
    counts: dict[str, int] = defaultdict(int)
    for m in matches:
        if m.confidence == HIGH:
            counts[m.park_id] += 1
    return dict(counts)
