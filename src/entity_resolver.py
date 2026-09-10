"""
實體解析（Entity Resolver, R17.2 / R17.3 / R17.4）
====================================================
小小守護員 Smart Watchdog Platform — 跨資料源、跨年度的機構實體解析。

對應 design.md「Components and Interfaces / 12. Data Pipeline + Entity_Resolver」：

    def resolve_entity(records) -> list[ResolvedEntity]
        \"\"\"跨名稱變體/年度解析為同一實體(R17.2)；
        無法可靠判定 → 標記 pending_manual 不強制合併(R17.3)；
        每合併決策保留可追溯依據(R17.4)。\"\"\"

設計原則（白盒、可解釋、可追溯）：
  - 解析僅用規則與字串正規化，無 AI 參與，符合專案「白盒可解釋」定位。
  - 相同 `park_id`（園所代碼）是最強、最可靠的同一實體證據，優先採用。
  - 無 park_id 時退回「正規化名稱」比對：處理全形/半形、空白、常見機構
    後綴（如「附設」「分班」）與年度後綴等名稱變體（R17.2）。
  - 當名稱相似但無法可靠判定為同一實體時，**不強制合併**，各自成為獨立
    實體並標記 `pending_manual=True`，交由人工判讀（R17.3）。
  - 每一次合併決策皆保留 `MergeDecision`（方法、依據、被併入的來源鍵），
    形成可追溯依據（R17.4）。
  - 冪等性：對同一輸入重複解析，結果（實體識別碼指派）不變（Property 38）。

本模組僅依賴標準函式庫，不引入額外執行期相依，維持既有基線的可攜性。
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# 名稱正規化：處理名稱變體（全形/半形、空白、後綴），供 R17.2 的變體比對
# --------------------------------------------------------------------------
# 常見會造成「同一實體不同寫法」的雜訊後綴／片語。移除後再比對，
# 可將「新北市立林口幼兒園」與「林口幼兒園（新北市立）」等變體視為同源。
# 注意：僅移除「行政區域／年度／裝飾性」雜訊，不移除足以區辨不同機構的核心名稱。
_NOISE_PATTERNS = [
    r"新北市立",
    r"新北市",
    r"市立",
    r"私立",
    r"縣立",
    r"\d{2,3}\s*學年度",   # 110學年度 / 112 學年度
    r"\d{2,3}\s*年度",     # 112年度 / 113 年度
    r"\d{2,3}\s*年",       # 112年
]

# 需要移除的所有空白字元（含全形空白）。
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str | None) -> str:
    """將機構名稱正規化為可比對的標準形式（R17.2 名稱變體）。

    步驟：
      1. None/空 → 空字串。
      2. Unicode NFKC 正規化：全形英數字/標點 → 半形，統一相容字元。
      3. 移除所有空白（含全形空白）。
      4. 移除年度後綴與行政區域裝飾性前綴等雜訊片語。
      5. 移除殘留的括號與標點雜訊。

    此函式為純函式（同輸入必得同輸出），是冪等解析的基礎。
    """
    if not name:
        return ""

    # NFKC：全形 → 半形、相容字元統一（處理全形/半形變體）。
    text = unicodedata.normalize("NFKC", str(name))

    # 移除所有空白（含正規化後的一般空白）。
    text = _WS_RE.sub("", text)

    # 移除年度／行政區域等雜訊片語。
    for pat in _NOISE_PATTERNS:
        text = re.sub(pat, "", text)

    # 移除括號與常見標點雜訊（不影響核心名稱辨識）。
    text = re.sub(r"[()（）\[\]【】,，、.。\-—_]", "", text)

    return text.strip()


# --------------------------------------------------------------------------
# 資料模型：合併決策依據（R17.4）與解析後實體
# --------------------------------------------------------------------------
@dataclass
class MergeDecision:
    """單一筆原始紀錄併入某實體的可追溯依據（R17.4）。

    - method：判定方法（'park_id' | 'normalized_name'）。
    - evidence：人類可讀的依據說明（例如比對到的鍵值）。
    - source_record_key：被併入紀錄的來源鍵（park_id 或原始名稱）。

    Validates: Requirements 17.4
    """
    method: str
    evidence: str
    source_record_key: str


@dataclass
class ResolvedEntity:
    """解析後的機構實體：由一或多筆原始紀錄合併而成。

    - entity_id：實體識別碼。以 park_id 為優先（最可靠）；否則以正規化名稱
      為基礎，冠上 'name:' 前綴以區別。
    - canonical_name：代表名稱（取首筆非空原始名稱）。
    - records：組成此實體的原始紀錄清單。
    - merge_decisions：每筆紀錄併入的可追溯依據（R17.4）。
    - pending_manual：無法可靠判定同一實體時為 True，不強制合併（R17.3）。

    Validates: Requirements 17.2, 17.3, 17.4
    """
    entity_id: str
    canonical_name: str
    records: list[dict] = field(default_factory=list)
    merge_decisions: list[MergeDecision] = field(default_factory=list)
    pending_manual: bool = False


# --------------------------------------------------------------------------
# 輔助：取出紀錄的鍵值
# --------------------------------------------------------------------------
def _get_park_id(record: dict) -> str | None:
    """取出可靠的 park_id（園所代碼）；空值/缺值回傳 None。"""
    pid = record.get("park_id")
    if pid is None:
        return None
    pid = str(pid).strip()
    return pid or None


def _get_name(record: dict) -> str:
    """取出原始名稱字串（供 canonical_name 與追溯依據）。"""
    name = record.get("park_name") or record.get("name") or ""
    return str(name).strip()


# --------------------------------------------------------------------------
# 主流程：實體解析（R17.2, R17.3, R17.4）
# --------------------------------------------------------------------------
def resolve_entity(records: list[dict]) -> list[ResolvedEntity]:
    """將一組跨來源/跨年度的原始紀錄解析為機構實體清單。

    合併規則（依可靠度由高至低）：
      1. 相同 `park_id` → 併為同一實體（最可靠，method='park_id'）（R17.2）。
      2. 無 park_id 時，以 `normalize_name` 後相等者 → 併為同一實體
         （method='normalized_name'）（R17.2）。
      3. 正規化後名稱為空（無 park_id 亦無可辨識名稱）→ 無法可靠判定，
         各自成為獨立實體並標記 `pending_manual=True`，不強制合併（R17.3）。

    每一筆紀錄的併入皆記錄 `MergeDecision` 作為可追溯依據（R17.4）。

    冪等性（Property 38）：本函式為純函式，對同一輸入重複呼叫，
    每筆紀錄被指派的 entity_id 與分群結果完全一致。輸出實體順序依
    首次出現順序穩定排列，故重複解析結果不變。

    參數：
      records：原始紀錄清單，每筆為 dict，至少含 'park_name'（或 'name'），
               可選 'park_id'、'year' 等欄位。

    回傳：
      list[ResolvedEntity]，依實體首次出現順序排列。
    """
    if not records:
        return []

    # 以 entity_id 為鍵累積實體；order 保留首次出現順序以確保穩定輸出。
    entities: dict[str, ResolvedEntity] = {}
    order: list[str] = []

    # 待人工判讀（無法可靠判定）的紀錄，各自成為獨立實體（R17.3）。
    pending_counter = 0

    for record in records:
        park_id = _get_park_id(record)
        name = _get_name(record)
        norm = normalize_name(name)

        if park_id is not None:
            # 規則 1：park_id 相同 → 同一實體（最可靠）。
            entity_id = park_id
            decision = MergeDecision(
                method="park_id",
                evidence=f"園所代碼相符：park_id={park_id}",
                source_record_key=park_id,
            )
            pending = False
        elif norm:
            # 規則 2：正規化名稱相同 → 同一實體。
            entity_id = f"name:{norm}"
            decision = MergeDecision(
                method="normalized_name",
                evidence=f"正規化名稱相符：'{name}' → '{norm}'",
                source_record_key=name or norm,
            )
            pending = False
        else:
            # 規則 3：無 park_id 且名稱無法辨識 → 無法可靠判定，
            # 各自成為獨立實體並標記 pending_manual（R17.3）。
            pending_counter += 1
            entity_id = f"pending:{pending_counter}"
            decision = MergeDecision(
                method="unresolved",
                evidence="無園所代碼且名稱無法辨識，無法可靠判定同一實體，待人工判讀。",
                source_record_key=name or "<空白>",
            )
            pending = True

        if entity_id not in entities:
            entities[entity_id] = ResolvedEntity(
                entity_id=entity_id,
                canonical_name=name,
                pending_manual=pending,
            )
            order.append(entity_id)

        entity = entities[entity_id]
        entity.records.append(record)
        entity.merge_decisions.append(decision)

        # canonical_name 補值：首筆為空、後續有非空名稱時採用之。
        if not entity.canonical_name and name:
            entity.canonical_name = name

    return [entities[eid] for eid in order]
