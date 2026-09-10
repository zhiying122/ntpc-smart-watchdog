"""
實體解析單元測試（Entity Resolver Unit Tests）
================================================
對應 Task 14.1（src/entity_resolver.py），驗證 normalize_name / resolve_entity
的具體行為與邊界（R17.2, R17.3, R17.4）。

註：Property 38（實體解析一致且冪等）之屬性測試屬於獨立的選用任務 14.3，
本檔僅涵蓋具體範例與邊界之單元測試。
"""
from src.entity_resolver import (
    MergeDecision,
    ResolvedEntity,
    normalize_name,
    resolve_entity,
)


# --------------------------------------------------------------------------
# normalize_name（R17.2 名稱變體）
# --------------------------------------------------------------------------
def test_normalize_handles_fullwidth_whitespace_and_year_suffix():
    """全形空白、市立前綴、年度後綴等變體正規化為相同標準形式（R17.2）。"""
    a = normalize_name("新北市立　林口幼兒園（112學年度）")
    b = normalize_name("林口幼兒園")
    c = normalize_name("新北市立林口幼兒園 113年度")
    assert a == b == c == "林口幼兒園"


def test_normalize_none_and_empty():
    """None 與空字串安全回傳空字串（不拋例外）。"""
    assert normalize_name(None) == ""
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""


# --------------------------------------------------------------------------
# resolve_entity — park_id 合併（R17.2）
# --------------------------------------------------------------------------
def test_resolve_merges_by_park_id_across_years():
    """相同 park_id 的跨年度紀錄併為同一實體（R17.2）。"""
    records = [
        {"park_id": "13616", "park_name": "新北市立林口幼兒園", "year": 112},
        {"park_id": "13616", "park_name": "林口幼兒園", "year": 113},
        {"park_id": "13616", "park_name": "新北市立林口幼兒園", "year": 114},
    ]
    entities = resolve_entity(records)
    assert len(entities) == 1
    ent = entities[0]
    assert ent.entity_id == "13616"
    assert len(ent.records) == 3
    assert all(d.method == "park_id" for d in ent.merge_decisions)
    assert not ent.pending_manual


def test_resolve_merges_by_normalized_name_when_no_park_id():
    """無 park_id 時以正規化名稱合併名稱變體（R17.2）。"""
    records = [
        {"park_name": "新北市立三重幼兒園 112年度"},
        {"park_name": "三重幼兒園"},
    ]
    entities = resolve_entity(records)
    assert len(entities) == 1
    assert entities[0].entity_id == "name:三重幼兒園"
    assert all(d.method == "normalized_name" for d in entities[0].merge_decisions)


def test_resolve_keeps_distinct_entities_separate():
    """不同機構不被錯誤合併。"""
    records = [
        {"park_id": "1", "park_name": "板橋幼兒園"},
        {"park_id": "2", "park_name": "三重幼兒園"},
    ]
    entities = resolve_entity(records)
    assert len(entities) == 2
    assert {e.entity_id for e in entities} == {"1", "2"}


# --------------------------------------------------------------------------
# resolve_entity — 無法可靠判定 → pending_manual（R17.3）
# --------------------------------------------------------------------------
def test_unresolvable_records_flagged_pending_manual_and_not_merged():
    """無 park_id 且名稱無法辨識者各自獨立並標記 pending_manual（R17.3）。"""
    records = [
        {"park_name": ""},
        {"park_name": "   "},
    ]
    entities = resolve_entity(records)
    # 不強制合併：兩筆各自成為獨立實體。
    assert len(entities) == 2
    assert all(e.pending_manual for e in entities)
    assert all(e.merge_decisions[0].method == "unresolved" for e in entities)


# --------------------------------------------------------------------------
# resolve_entity — 可追溯依據（R17.4）
# --------------------------------------------------------------------------
def test_merge_decisions_recorded_for_traceability():
    """每筆併入皆保留可追溯依據（R17.4）。"""
    records = [
        {"park_id": "13616", "park_name": "林口幼兒園", "year": 112},
        {"park_id": "13616", "park_name": "林口幼兒園", "year": 113},
    ]
    ent = resolve_entity(records)[0]
    assert len(ent.merge_decisions) == 2
    for d in ent.merge_decisions:
        assert isinstance(d, MergeDecision)
        assert d.evidence  # 非空依據說明
        assert d.source_record_key


# --------------------------------------------------------------------------
# 冪等性（Property 38 精神；此處為單元層級驗證）
# --------------------------------------------------------------------------
def test_resolve_is_idempotent_on_repeated_calls():
    """同一輸入重複解析，實體識別碼指派不變（冪等）。"""
    records = [
        {"park_id": "13616", "park_name": "林口幼兒園", "year": 112},
        {"park_name": "三重幼兒園"},
        {"park_id": "13616", "park_name": "新北市立林口幼兒園", "year": 113},
    ]
    first = [(e.entity_id, len(e.records)) for e in resolve_entity(records)]
    second = [(e.entity_id, len(e.records)) for e in resolve_entity(records)]
    assert first == second


def test_empty_input_returns_empty_list():
    """空輸入安全回傳空清單。"""
    assert resolve_entity([]) == []
