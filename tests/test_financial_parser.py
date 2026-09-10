"""
財務文件解析器與美化輸出單元測試（Financial Parser Unit Tests, R17.1）
=========================================================================
小小守護員 Smart Watchdog Platform — 驗證 `src.financial_parser` 的
`parse_financial_record` 與 `print_financial_record` 具體行為與往返一致性。

聚焦具體範例與邊界：缺值(None)、0、負值、極大值、特殊字元／換行的名稱、
空明細清單、有／無巢狀 SourceRef、SourceRef 各欄位為 None 等。

往返一致性（Property 39 之具體案例）：
  parse_financial_record(print_financial_record(x)) 等價於 x，
  且 print_financial_record(parse_financial_record(print(x))) == print(x)。
"""
from __future__ import annotations

from datetime import date

from src.financial_parser import parse_financial_record, print_financial_record
from src.models import FinancialRecord, SourceRef


def _roundtrip(record: FinancialRecord) -> None:
    """輔助：驗證單一物件往返等價且美化輸出穩定。"""
    text = print_financial_record(record)
    parsed = parse_financial_record(text)
    assert parsed == record
    # 美化輸出穩定：print(parse(print(x))) == print(x)
    assert print_financial_record(parsed) == text


def test_print_starts_with_header():
    """輸出首行為標頭。"""
    rec = FinancialRecord(park_id="A1", park_name="陽光幼兒園", year=112)
    text = print_financial_record(rec)
    assert text.splitlines()[0] == "# FinancialRecord"


def test_roundtrip_minimal_record():
    """最小紀錄（多數欄位為預設 None / 空）往返一致。"""
    rec = FinancialRecord(park_id="A1", park_name="陽光幼兒園", year=113)
    _roundtrip(rec)


def test_roundtrip_full_record_with_source():
    """完整紀錄（含巢狀 SourceRef 與明細）往返一致。"""
    rec = FinancialRecord(
        park_id="13601",
        park_name="新北市立幼兒園",
        year=114,
        income_actual=1_234_567.89,
        expense_actual=1_000_000.0,
        tuition_actual=500_000.0,
        surplus=234_567.89,
        income_last_year=1_100_000.0,
        expense_last_year=950_000.0,
        enrollment=120,
        detail_amounts=[100, 2_000, 30_000, 444],
        source_ref=SourceRef(
            dataset="112年度決算書",
            authority="新北市政府教育局",
            url="https://example.gov.tw/data",
            last_updated=date(2024, 3, 15),
        ),
    )
    _roundtrip(rec)


def test_roundtrip_none_amounts():
    """所有金額為缺值（None）往返一致。"""
    rec = FinancialRecord(
        park_id="B2",
        park_name="快樂非營利幼兒園",
        year=112,
        income_actual=None,
        expense_actual=None,
        tuition_actual=None,
        surplus=None,
        income_last_year=None,
        expense_last_year=None,
        enrollment=None,
        detail_amounts=[],
        source_ref=None,
    )
    _roundtrip(rec)


def test_roundtrip_zero_and_negative_amounts():
    """0 與負值（短絀）往返一致。"""
    rec = FinancialRecord(
        park_id="C3",
        park_name="小天使幼兒園",
        year=113,
        income_actual=0.0,
        expense_actual=-50_000.0,   # 短絀
        surplus=-50_000.0,
        income_last_year=0.0,
        enrollment=0,
        detail_amounts=[1],
    )
    _roundtrip(rec)


def test_roundtrip_extreme_and_negative_zero():
    """極大值與 -0.0（等於 0.0）往返一致。"""
    rec = FinancialRecord(
        park_id="D4",
        park_name="板橋國小附設幼兒園",
        year=114,
        income_actual=1e12,
        expense_actual=-1e12,
        tuition_actual=-0.0,
        detail_amounts=[10_000_000],
    )
    _roundtrip(rec)


def test_roundtrip_special_characters_in_names():
    """名稱含全形空白、換行、引號、冒號等特殊字元往返一致。"""
    rec = FinancialRecord(
        park_id='id: "with" : colons',
        park_name="新北市立　幼兒園\n第二行\t制表\"引號\"",
        year=112,
        detail_amounts=[1, 2, 3],
    )
    _roundtrip(rec)


def test_roundtrip_empty_names():
    """空字串名稱往返一致。"""
    rec = FinancialRecord(park_id="", park_name="", year=113)
    _roundtrip(rec)


def test_roundtrip_source_ref_with_none_fields():
    """SourceRef 的 url 與 last_updated 為 None 往返一致。"""
    rec = FinancialRecord(
        park_id="E5",
        park_name="測試幼兒園",
        year=114,
        source_ref=SourceRef(
            dataset="裁罰紀錄",
            authority="教育局",
            url=None,
            last_updated=None,
        ),
    )
    _roundtrip(rec)


def test_source_ref_none_serializes_as_null():
    """source_ref 為 None 時序列化為 null 行且解析回 None。"""
    rec = FinancialRecord(park_id="F6", park_name="無來源園", year=112, source_ref=None)
    text = print_financial_record(rec)
    assert "source_ref: null" in text
    parsed = parse_financial_record(text)
    assert parsed.source_ref is None


def test_parse_ignores_blank_lines():
    """解析時容忍多餘空白行。"""
    rec = FinancialRecord(park_id="G7", park_name="容錯園", year=113)
    text = print_financial_record(rec)
    noisy = text + "\n\n"
    assert parse_financial_record(noisy) == rec
