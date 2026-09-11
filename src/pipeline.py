"""
資料整合管線（Data Pipeline, R17.1）
========================================
小小守護員 Smart Watchdog Platform — 整合財務／裁罰／評鑑／收費／地理五類
資料源。

⚠️ 實作狀態（務必先讀）：本模組為 **design.md R17 規格對齊實作**，展示可規模化
的整合／實體解析架構，但**目前未接入實際資料主幹**。現行 live 契約檔
（data/processed/kindergartens_latest.csv、kindergartens.csv）**實際是由
`src/risk_score.py` 的 `main()` 產生**（流程見 scripts/rebuild_all.py），
並非由本模組的 `run_pipeline` / `write_contract_files` 產生。因此：
  - 追蹤真正的資料流，請看 scripts/rebuild_all.py 與 src/risk_score.py。
  - 本模組的 `CONTRACT_COLUMNS`（見下）為規格層欄位定義，與 risk_score.py
    實際輸出的 42 欄**不完全相同**（實際多出 fund_*、penalty_reason/category、
    eng_* 白盒欄位）。若需契約真相，以 risk_score.py::main() 的 `cols` 為準。
本模組保留供規格對齊與未來規模化擴充，測試會驗證其行為，但不落地 live 契約檔。

對應 design.md「Components and Interfaces / 12. Data Pipeline + Entity_Resolver」：

    def run_pipeline(sources) -> IntegratedDataset
        \"\"\"整合財務/裁罰/評鑑/收費/地理(R17.1)。\"\"\"

設計原則：
  - 以 `src.entity_resolver.resolve_entity` 跨名稱變體/年度將紀錄歸併為同一
    機構實體（R17.2/17.3/17.4），確保多源資料以「同一實體」為軸整合。
  - 財務資料保留「每園每年一列」（供跨年度契約檔 kindergartens.csv）；
    裁罰／評鑑／收費／地理以「每園」層級併入最新年度列（供 latest 契約檔）。
  - **不破壞既有契約**：輸出欄位以既有 kindergartens_latest.csv /
    kindergartens.csv 的欄位為基礎，缺欄位以中性空值補齊；未知額外欄位
    以附加方式加入，符合 design.md「契約檔（維持既有，不破壞現有 UI）」。
  - 純資料轉換：計分（forensic/scorer）不在本管線內回流，維持白盒資料流
    （RAW → Pipeline → Forensic/Anomaly → Scorer）。本管線只做「整合」。
  - **安全**：`run_pipeline` 僅回傳 `IntegratedDataset`（記憶體物件），
    不主動覆寫磁碟上的既有資料檔；如需落地，另以 `write_contract_files`
    明確呼叫，避免破壞既有 UI 載入的資料。

本模組僅依賴標準函式庫與 `src.entity_resolver`；pandas 為選用相依，僅在
明確要求 DataFrame / 寫檔輸出時才需要，維持既有基線可攜性。
"""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field

from .entity_resolver import ResolvedEntity, resolve_entity

# --------------------------------------------------------------------------
# 契約檔欄位（維持既有 kindergartens_latest.csv / kindergartens.csv 順序）
# --------------------------------------------------------------------------
# 依 data/processed/kindergartens_latest.csv 的既有表頭定義，確保輸出不破壞
# app/lib/common.py 的載入契約。新增欄位一律以「附加」方式加在既有欄位之後。
CONTRACT_COLUMNS: tuple[str, ...] = (
    "park_id", "park_name", "park_type", "year", "district", "lat", "lng",
    "income_actual", "expense_actual", "tuition_actual", "surplus",
    "expense_income_ratio", "benford_mad", "benford_sample_n", "benford_score",
    "benford_chi2", "benford_pvalue", "benford_significant", "beneish_score",
    "beneish_egdi", "beneish_tata", "iforest_score", "iforest_explain",
    "expense_yoy_pct", "penalty_count", "eval_grade",
    "score_financial", "score_penalty", "score_eval",
    "risk_total", "risk_level", "risk_level_abs",
)

# 由裁罰源可併入 latest 列的欄位（每園層級）。
_PENALTY_FIELDS = ("penalty_count", "penalty_reason", "eval_grade")
# 由地理源可併入的欄位。
_GEO_FIELDS = ("district", "lat", "lng", "address")
# 由收費源可併入的欄位。
_FEE_FIELDS = ("tuition_actual",)
# 由評鑑源可併入的欄位。
_EVAL_FIELDS = ("eval_grade",)


# --------------------------------------------------------------------------
# 輸入：五類資料源
# --------------------------------------------------------------------------
@dataclass
class DataSources:
    """管線輸入：五類資料源，每類為紀錄清單（dict）。

    每筆紀錄至少含機構識別資訊（park_id 或 park_name）；其餘欄位依來源而異。
    缺席的來源以空清單處理，不中斷整合（R17 錯誤處理：不中斷、誠實揭露）。

    Validates: Requirements 17.1
    """
    financial: list[dict] = field(default_factory=list)   # 財務（每園每年）
    penalty: list[dict] = field(default_factory=list)     # 裁罰（每園）
    evaluation: list[dict] = field(default_factory=list)  # 評鑑（每園）
    fee: list[dict] = field(default_factory=list)         # 收費（每園）
    geo: list[dict] = field(default_factory=list)         # 地理座標/地址（每園）


# --------------------------------------------------------------------------
# 輸出：整合資料集
# --------------------------------------------------------------------------
@dataclass
class IntegratedDataset:
    """管線輸出：整合後的資料集（R17.1）。

    - entities：解析後的機構實體清單（含每筆紀錄的合併可追溯依據）。
    - per_year_rows：每園每年一列（對應 kindergartens.csv 契約）。
    - latest_rows：每園一列（取最新年度＋併入裁罰/評鑑/收費/地理，
      對應 kindergartens_latest.csv 契約）。
    - columns：契約欄位順序（供寫檔）。
    - unresolved_count：無法可靠判定而標記 pending_manual 的實體數（R17.3）。

    Validates: Requirements 17.1, 17.2, 17.3
    """
    entities: list[ResolvedEntity] = field(default_factory=list)
    per_year_rows: list[dict] = field(default_factory=list)
    latest_rows: list[dict] = field(default_factory=list)
    columns: tuple[str, ...] = CONTRACT_COLUMNS
    unresolved_count: int = 0


# --------------------------------------------------------------------------
# 輔助：安全取值與年度解析
# --------------------------------------------------------------------------
def _year_of(record: dict) -> int:
    """取出年度用於排序；缺值/非數值視為極小值（排在最舊）。"""
    y = record.get("year")
    try:
        return int(y)
    except (TypeError, ValueError):
        return -1 << 30


def _merge_fields(dst: dict, src: dict, fields_: tuple[str, ...]) -> None:
    """將 src 指定欄位併入 dst；僅在 src 有非空值時覆寫，避免用空值蓋掉既有值。"""
    for f in fields_:
        if f not in src:
            continue
        val = src[f]
        if val is None or val == "":
            continue
        dst[f] = val


def _index_by_entity(
    records: list[dict],
) -> dict[str, dict]:
    """將輔助來源（裁罰/評鑑/收費/地理）依解析後 entity_id 建索引（每園一筆）。

    同一實體多筆時取最後一筆（後者覆蓋），以簡單且確定性的方式併入。
    """
    index: dict[str, dict] = {}
    for entity in resolve_entity(records):
        # 以合併後的紀錄集合逐筆疊加（確定性：依原始順序）。
        merged: dict = {}
        for rec in entity.records:
            for k, v in rec.items():
                if v is None or v == "":
                    continue
                merged[k] = v
        index[entity.entity_id] = merged
    return index


# --------------------------------------------------------------------------
# 主流程：整合管線（R17.1）
# --------------------------------------------------------------------------
def run_pipeline(sources: DataSources) -> IntegratedDataset:
    """整合財務／裁罰／評鑑／收費／地理五類資料，輸出整合資料集（R17.1）。

    流程：
      1. 以財務紀錄為主軸（含 park_id/park_name/year），透過 entity_resolver
         跨名稱變體/年度解析為機構實體（R17.2/17.3/17.4）。
      2. 每園每年一列 → per_year_rows（對應 kindergartens.csv）。
      3. 每實體取最新年度列為基礎 → 併入裁罰/評鑑/收費/地理（每園層級），
         形成 latest_rows（對應 kindergartens_latest.csv）。
      4. 所有列補齊契約欄位（缺者為 None），確保不破壞既有載入契約。

    註：本管線只做「資料整合」，不計算風險分數（score_*/risk_*）；這些欄位
    保留為 None，由後續 Forensic/Anomaly/Scorer 階段填入（維持白盒資料流，
    AI 與計分不在整合階段回流）。

    參數：
      sources：DataSources，五類來源紀錄。

    回傳：
      IntegratedDataset。
    """
    # 1) 以財務為主軸解析實體（跨年度/名稱變體）。
    entities = resolve_entity(list(sources.financial))
    unresolved = sum(1 for e in entities if e.pending_manual)

    # 2) 輔助來源依實體索引（每園一筆）。
    penalty_idx = _index_by_entity(list(sources.penalty))
    eval_idx = _index_by_entity(list(sources.evaluation))
    fee_idx = _index_by_entity(list(sources.fee))
    geo_idx = _index_by_entity(list(sources.geo))

    # 為了用「名稱」對應輔助來源（輔助來源常無 park_id），另建名稱索引。
    from .entity_resolver import normalize_name

    def _by_name(index: dict[str, dict]) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for rec in index.values():
            nm = normalize_name(rec.get("park_name") or rec.get("name"))
            if nm:
                out[nm] = rec
        return out

    penalty_by_name = _by_name(penalty_idx)
    eval_by_name = _by_name(eval_idx)
    fee_by_name = _by_name(fee_idx)
    geo_by_name = _by_name(geo_idx)

    per_year_rows: list[dict] = []
    latest_rows: list[dict] = []

    for entity in entities:
        # 依實體 id 與名稱找出可併入的輔助資料。
        norm = normalize_name(entity.canonical_name)

        def _lookup(idx: dict[str, dict], by_name: dict[str, dict]) -> dict:
            if entity.entity_id in idx:
                return idx[entity.entity_id]
            return by_name.get(norm, {})

        penalty = _lookup(penalty_idx, penalty_by_name)
        evaluation = _lookup(eval_idx, eval_by_name)
        fee = _lookup(fee_idx, fee_by_name)
        geo = _lookup(geo_idx, geo_by_name)

        # 每園每年一列（per_year）。
        year_records = sorted(entity.records, key=_year_of)
        for rec in year_records:
            row = _blank_row()
            _merge_fields(row, rec, CONTRACT_COLUMNS)
            # 地理資訊對每年皆適用（同一實體共享）。
            _merge_fields(row, geo, _GEO_FIELDS)
            per_year_rows.append(row)

        # 最新年度列（latest）＝最新一筆財務 + 併入輔助來源。
        if year_records:
            latest = _blank_row()
            _merge_fields(latest, year_records[-1], CONTRACT_COLUMNS)
            _merge_fields(latest, geo, _GEO_FIELDS)
            _merge_fields(latest, fee, _FEE_FIELDS)
            _merge_fields(latest, evaluation, _EVAL_FIELDS)
            _merge_fields(latest, penalty, _PENALTY_FIELDS)
            latest_rows.append(latest)

    return IntegratedDataset(
        entities=entities,
        per_year_rows=per_year_rows,
        latest_rows=latest_rows,
        columns=CONTRACT_COLUMNS,
        unresolved_count=unresolved,
    )


def _blank_row() -> dict:
    """依契約欄位建立一列，所有欄位預設為 None（中性空值，不破壞契約）。"""
    return {col: None for col in CONTRACT_COLUMNS}


# --------------------------------------------------------------------------
# 落地輸出（明確呼叫；預設不覆寫既有資料檔）
# --------------------------------------------------------------------------
def _write_csv(path: str, rows: list[dict], columns: tuple[str, ...]) -> None:
    """以契約欄位順序寫出 CSV（UTF-8）。缺欄位輸出空字串。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            out = {c: ("" if row.get(c) is None else row.get(c)) for c in columns}
            writer.writerow(out)


def write_contract_files(
    dataset: IntegratedDataset,
    latest_path: str,
    full_path: str,
) -> None:
    """將整合資料集輸出至既有契約檔（明確呼叫，需由呼叫端指定路徑）。

    安全設計：`run_pipeline` 不會自動呼叫此函式，避免無意間覆寫既有
    data/processed 下供 UI 載入的資料檔。呼叫端須明確指定輸出路徑並
    自行負責備份，符合「不破壞既有 UI」與變更可控原則。

    參數：
      dataset     ：run_pipeline 的輸出。
      latest_path ：kindergartens_latest.csv 目標路徑（每園一列）。
      full_path   ：kindergartens.csv 目標路徑（每園每年一列）。
    """
    _write_csv(latest_path, dataset.latest_rows, dataset.columns)
    _write_csv(full_path, dataset.per_year_rows, dataset.columns)
