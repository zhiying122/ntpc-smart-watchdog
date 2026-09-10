"""
財務文件解析器與美化輸出（Financial Parser & Pretty Printer, R17.1）
======================================================================
小小守護員 Smart Watchdog Platform — 將財務原始物件序列化為標準文字表示，
並可將該文字表示解析回等價的結構化財務物件。

對應 design.md「Components and Interfaces / 13. 文件解析器與序列化器」與
「Data Models / FinancialRecord」：

    def parse_financial_record(raw_text: str) -> FinancialRecord
        \"\"\"將原始文件文字解析為結構化財務物件。\"\"\"
    def print_financial_record(record: FinancialRecord) -> str
        \"\"\"將財務物件美化輸出為標準文字表示（pretty printer）。\"\"\"

    # 往返一致性：parse(print(x)) 等價於 x（Property 39）。

設計原則（round-trip 正確性優先）：
  - Property 39 要求：對任意有效 `FinancialRecord` x，`parse(print(x))` 等價於 x，
    且 `print(parse(print(x))) == print(x)`（美化輸出穩定）。
  - `FinancialRecord` 欄位涵蓋：任意文字（park_id / park_name，含全形、空白、
    特殊字元、換行）、可為 None 的浮點數（含 0、負值、極大值）、整數明細清單，
    以及可為 None 的巢狀 `SourceRef`（其 url / last_updated 亦可為 None）。
  - 為保證任意值皆可無失真往返，本模組採「每欄位一行、鍵值以冒號分隔、
    值以 JSON 編碼」的行導向格式：
      * JSON 編碼可無歧義地保留字串中的特殊字元、換行、全形字元與 Unicode，
        並精確保留浮點數值（透過 float <-> repr 的往返）與 None（JSON null）。
      * 每欄位獨立成行且以固定鍵標示，順序固定，故輸出穩定且可讀（pretty）。
  - 本模組僅依賴標準函式庫（json），不引入額外執行期相依，維持既有基線可攜性。

責任 AI：本模組僅做資料序列化／解析，不產生任何風險判定或違法／舞弊宣稱。
"""
from __future__ import annotations

import json
from datetime import date

from src.models import FinancialRecord, SourceRef

# --------------------------------------------------------------------------
# 格式常數
# --------------------------------------------------------------------------
# 文件標頭，標示這是一份財務紀錄的標準文字表示。
_HEADER = "# FinancialRecord"

# 巢狀 SourceRef 各欄位鍵（以 "source_ref." 前綴命名，維持扁平單行格式）。
_SOURCE_PREFIX = "source_ref."

# FinancialRecord 頂層欄位輸出順序（固定順序 → 輸出穩定）。
_FIELD_ORDER = [
    "park_id",
    "park_name",
    "year",
    "income_actual",
    "expense_actual",
    "tuition_actual",
    "surplus",
    "income_last_year",
    "expense_last_year",
    "enrollment",
    "detail_amounts",
]

# SourceRef 欄位輸出順序。
_SOURCE_FIELD_ORDER = ["dataset", "authority", "url", "last_updated"]


# --------------------------------------------------------------------------
# 內部輔助：值的 JSON 編碼 / 解碼
# --------------------------------------------------------------------------
def _encode_value(value: object) -> str:
    """將單一欄位值編碼為單行 JSON 字串。

    以 `ensure_ascii=False` 保留全形字元的可讀性；JSON 對字串中的換行、
    引號、控制字元等會自動轉義，確保解析時無歧義且可完整還原。
    浮點數以 JSON number 表示，`json.loads` 還原時精度與原值一致。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _decode_value(text: str) -> object:
    """將單行 JSON 字串解碼回原始值（字串 / 數字 / None / list）。"""
    return json.loads(text)


def _format_line(key: str, value: object) -> str:
    """輸出一行 "key: <json-value>"。"""
    return f"{key}: {_encode_value(value)}"


# --------------------------------------------------------------------------
# Pretty printer：FinancialRecord -> str
# --------------------------------------------------------------------------
def print_financial_record(record: FinancialRecord) -> str:
    """將 `FinancialRecord` 美化輸出為標準文字表示（pretty printer）。

    輸出為行導向格式：首行為標頭，其後每一欄位一行，鍵固定、順序固定，
    值以 JSON 編碼以保證無失真還原。巢狀 `SourceRef` 以 `source_ref.*`
    前綴的欄位表示；當 `source_ref` 為 None 時，以 `source_ref: null` 表示。

    此函式與 `parse_financial_record` 互為反函式：
        parse_financial_record(print_financial_record(x)) 等價於 x（Property 39）。
    """
    lines: list[str] = [_HEADER]

    # 頂層欄位（固定順序）。
    field_values = {
        "park_id": record.park_id,
        "park_name": record.park_name,
        "year": record.year,
        "income_actual": record.income_actual,
        "expense_actual": record.expense_actual,
        "tuition_actual": record.tuition_actual,
        "surplus": record.surplus,
        "income_last_year": record.income_last_year,
        "expense_last_year": record.expense_last_year,
        "enrollment": record.enrollment,
        "detail_amounts": list(record.detail_amounts),
    }
    for key in _FIELD_ORDER:
        lines.append(_format_line(key, field_values[key]))

    # 巢狀 SourceRef。
    src = record.source_ref
    if src is None:
        lines.append(_format_line("source_ref", None))
    else:
        # 以標記行表示 source_ref 存在，其後為各子欄位。
        lines.append(_format_line("source_ref", "<present>"))
        source_values = {
            "dataset": src.dataset,
            "authority": src.authority,
            "url": src.url,
            # date 以 ISO 字串序列化；None 保持 None。
            "last_updated": src.last_updated.isoformat()
            if isinstance(src.last_updated, date)
            else None,
        }
        for key in _SOURCE_FIELD_ORDER:
            lines.append(_format_line(f"{_SOURCE_PREFIX}{key}", source_values[key]))

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Parser：str -> FinancialRecord
# --------------------------------------------------------------------------
def parse_financial_record(raw_text: str) -> FinancialRecord:
    """將標準文字表示解析回 `FinancialRecord`。

    解析步驟：
      1. 逐行讀取，跳過標頭行與空白行。
      2. 每行以第一個 ": " 分隔為 (key, json-value)。
      3. 依鍵還原頂層欄位；`source_ref.*` 前綴的欄位還原巢狀 `SourceRef`。

    與 `print_financial_record` 互為反函式，保證 round-trip 一致（Property 39）。

    參數：
      raw_text：由 `print_financial_record` 產生的標準文字表示。

    回傳：
      還原後的 `FinancialRecord`，與原物件等價。
    """
    fields: dict[str, object] = {}
    source_fields: dict[str, object] = {}
    has_source = False

    for line in raw_text.split("\n"):
        if not line or line == _HEADER:
            continue
        # 以第一個 ": " 分隔鍵與 JSON 值（值本身可能含 ": "，故只切一次）。
        sep = line.find(": ")
        if sep == -1:
            continue
        key = line[:sep]
        value_text = line[sep + 2:]
        value = _decode_value(value_text)

        if key == "source_ref":
            # None → 無 source_ref；"<present>" → 後續有子欄位。
            has_source = value is not None
        elif key.startswith(_SOURCE_PREFIX):
            source_fields[key[len(_SOURCE_PREFIX):]] = value
        else:
            fields[key] = value

    # 還原巢狀 SourceRef。
    source_ref: SourceRef | None = None
    if has_source:
        last_updated_raw = source_fields.get("last_updated")
        last_updated = (
            date.fromisoformat(last_updated_raw)
            if isinstance(last_updated_raw, str)
            else None
        )
        source_ref = SourceRef(
            dataset=source_fields.get("dataset"),
            authority=source_fields.get("authority"),
            url=source_fields.get("url"),
            last_updated=last_updated,
        )

    return FinancialRecord(
        park_id=fields.get("park_id"),
        park_name=fields.get("park_name"),
        year=fields.get("year"),
        income_actual=fields.get("income_actual"),
        expense_actual=fields.get("expense_actual"),
        tuition_actual=fields.get("tuition_actual"),
        surplus=fields.get("surplus"),
        income_last_year=fields.get("income_last_year"),
        expense_last_year=fields.get("expense_last_year"),
        enrollment=fields.get("enrollment"),
        detail_amounts=list(fields.get("detail_amounts") or []),
        source_ref=source_ref,
    )
