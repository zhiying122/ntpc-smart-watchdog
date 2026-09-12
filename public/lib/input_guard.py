"""
使用者輸入品質守門（Input Quality Guard）— 純邏輯
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網「機構回應／申訴」表單
的送出前檢查。本模組不 import streamlit，純函式易於單元測試。

目的：這是會被機構與主管機關看到的正式說明管道，需擋下：
  1. 不雅字眼／攻擊性用語（維持公共平台的基本禮節）。
  2. 明顯亂填（純符號、單字重複灌水、無意義過短內容）。
偵測到即回傳警告，讓頁面阻擋送出並提示使用者修正——不是替使用者審查意見，
而是確保送出的內容是「可被處理的正式說明」。

責任 AI：本守門僅做基本品質與禮節檢查，不對意見立場作審查；正當的批評、
負面回饋只要用語得體、內容具體，皆可正常送出。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# 不雅字詞清單（基本，涵蓋常見中文粗俗字與英文髒話字根）
# ---------------------------------------------------------------------------
# 說明：此清單為「明顯不雅／攻擊性」用語的基本防線，非窮舉；以子字串比對。
# 刻意保守，避免誤傷正當用語（如「幹部」「妹妹」等不列入或以更精確規則處理）。
_PROFANITY: tuple[str, ...] = (
    "幹你", "幹妳", "幹您", "去死", "白痴", "白癡", "智障", "北七", "低能",
    "廢物", "垃圾人", "王八", "混蛋", "婊", "賤", "靠北", "靠腰", "他媽的",
    "你媽", "妳媽", "娘炮", "神經病", "有病", "腦殘", "faaggot", "fuck", "shit",
    "bitch", "asshole", "dick", "cunt",
)

#: 明顯需要精確比對（避免誤傷）的粗俗單字，用「詞邊界式」規則另行處理。
_PROFANITY_TIGHT: tuple[str, ...] = ("幹", "屌", "雞掰", "機掰", "gan")

#: 內容最短長度（去除空白後）；過短視為無意義填答。
_MIN_MEANINGFUL_LEN = 8


@dataclass(frozen=True)
class GuardResult:
    """輸入檢查結果。

    - ok=True：可送出。
    - ok=False：不可送出，reasons 列出所有命中的問題（供頁面逐條提示）。
    - severity：'block'（阻擋送出）。目前所有命中皆為 block。
    """
    ok: bool
    reasons: list[str] = field(default_factory=list)
    severity: str = "block"


def _norm(text: str) -> str:
    return (text or "").strip()


def contains_profanity(text: str) -> bool:
    """是否含不雅／攻擊性用語（基本清單，子字串比對）。"""
    t = (text or "").lower()
    if any(w in t for w in _PROFANITY):
        return True
    # 精確粗俗字：前後非中文字母時才算（降低「幹部/幹勁」等誤判）。
    for w in _PROFANITY_TIGHT:
        for mobj in re.finditer(re.escape(w), t):
            # 「幹」出現在「幹部/幹勁/幹事/主幹」等詞中不算；孤立或接攻擊性語境才算。
            tail = t[mobj.end(): mobj.end() + 1]
            if w == "幹" and tail in ("部", "勁", "事", "練", "線", "道"):
                continue
            return True
    return False


def is_gibberish(text: str) -> bool:
    """是否為明顯亂填：純符號/數字、單一字元重複灌水、無中英數實質內容。"""
    t = _norm(text)
    if not t:
        return True
    # 去空白後的實質字元。
    compact = re.sub(r"\s+", "", t)
    if not compact:
        return True
    # 完全沒有中文字、也沒有英文字母 → 視為純符號/亂碼。
    if not re.search(r"[\u4e00-\u9fffA-Za-z]", compact):
        return True
    # 單一字元重複佔比過高（如「啊啊啊啊啊啊」「aaaaaaa」）。
    most = max((compact.count(c) for c in set(compact)), default=0)
    if len(compact) >= 4 and most / len(compact) >= 0.8:
        return True
    # 不同字元種類太少（如「哈哈哈哈」只 1 種）。
    if len(compact) >= 6 and len(set(compact)) <= 2:
        return True
    return False


def check_appeal_text(text: str, *, min_len: int = _MIN_MEANINGFUL_LEN) -> GuardResult:
    """檢查申訴／說明內容是否可送出。

    規則（任一命中即阻擋，並附具體理由）：
      - 空白或過短（去空白後 < min_len）→ 內容過短。
      - 明顯亂填（純符號/重複灌水）→ 疑似無效內容。
      - 含不雅／攻擊性用語 → 請以得體用語重新表述。

    正當、具體、用語得體的負面回饋不受影響，可正常送出。
    """
    reasons: list[str] = []
    t = _norm(text)
    compact = re.sub(r"\s+", "", t)

    if len(compact) < min_len:
        reasons.append(f"內容過短：請具體說明您要澄清或補充的事項（至少 {min_len} 個字）。")
    elif is_gibberish(t):
        reasons.append("內容似乎是無意義或重複的字元，請以完整句子具體說明。")

    if contains_profanity(t):
        reasons.append("內容含不雅或攻擊性用語，請以得體、就事論事的方式重新表述。")

    return GuardResult(ok=not reasons, reasons=reasons)


def check_name(text: str) -> GuardResult:
    """檢查聯絡人／職稱欄：不可含不雅用語；可留空（留空不阻擋）。"""
    t = _norm(text)
    if not t:
        return GuardResult(ok=True)
    reasons: list[str] = []
    if contains_profanity(t):
        reasons.append("聯絡人／職稱含不雅用語，請修正。")
    if is_gibberish(t):
        reasons.append("聯絡人／職稱似乎是無意義字元，請填寫真實稱謂。")
    return GuardResult(ok=not reasons, reasons=reasons)
