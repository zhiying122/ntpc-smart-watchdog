"""
非營利園掃描財報批次抽取管線（Non-Profit Financial Report Batch Pipeline）
============================================================================
小小守護員 Smart Watchdog Platform — 將 132 份非營利園掃描財報（無文字層）
以 OCR 抽取為結構化財務資料，併入風險引擎，補齊「非營利園」這一大類資料。

對應題目：命題明確提供「非營利園及公立園決算報告」，非營利園為私人經營、
最需財務監理的一群，鑑識會計抓弊價值最高。

設計原則（政府級、可切換、可續跑、誠實）：
--------------------------------------------------------------------------
  - 引擎可切換：engine="tesseract"（本地免費，今日用）或 "bedrock"（AWS
    多模態，明日用）。同一批 PDF 換引擎即可重抽，不需改管線。
  - 只 OCR 財務報表頁（預設 5–8 頁，即淨資產變動表 + 收支餘絀表），
    避免整份 42 頁 OCR 過慢。
  - 逐份輸出 JSON（含原始 OCR 文字，供追溯與人工複核），可續跑（已完成者
    跳過），132 份可安全分段執行。
  - 誠實標註信心：OCR 抽取本質有誤差，每份標記 extraction_confidence 與
    needs_review；抽不到關鍵數字者標為 low 信心，不強迫填值。
  - 併入風險引擎時，非營利園財務標示來源為 OCR，並由既有基金勾稽（期末=
    期初+本期餘絀）自動抓出抽取異常，交人工複核（責任 AI）。

本模組的 OCR 引擎沿用 src/ocr_nonprofit.py（單一事實來源），不重寫。
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any

from src import ocr_nonprofit as ocr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_DIR = os.path.join(ROOT, "E_教育局-資料集", "資料集", "非營利園財報")
OUTPUT_DIR = os.path.join(ROOT, "data", "derived", "nonprofit_ocr")

# 財務報表所在頁（1-based）：淨資產變動表 + 收支餘絀表，跨園一致落於此區間。
DEFAULT_FINANCIAL_PAGES = (5, 6, 7, 8)

# 檔名格式：N01安溪_113學年度財務報告.pdf → code=N01, name=安溪, year=113
_FILENAME_RE = re.compile(r"^(N\d+)([^_]+)_(\d{3})學年度")


@dataclass
class NonprofitFinancials:
    """單一非營利園單一學年度的抽取結果。"""
    code: str                    # N01…（園所編號）
    name: str                    # 安溪…（園名）
    year: int                    # 學年度（113…）
    source_file: str             # 來源 PDF 相對路徑
    engine: str                  # tesseract / bedrock
    income_total: int | None = None      # 收入合計（本期）
    expense_total: int | None = None     # 支出合計（本期）
    surplus: int | None = None           # 本期稅後餘絀
    extraction_confidence: str = "low"   # high / medium / low
    needs_review: bool = True            # 是否需人工複核
    notes: list[str] = field(default_factory=list)
    raw_ocr_pages: dict[int, str] = field(default_factory=dict)  # 頁碼→原始OCR文字


# --------------------------------------------------------------------------
# 檔名解析
# --------------------------------------------------------------------------
def parse_filename(filename: str) -> tuple[str, str, int] | None:
    """從財報檔名解析 (code, name, year)。不符格式回傳 None。"""
    m = _FILENAME_RE.match(filename)
    if not m:
        return None
    return m.group(1), m.group(2), int(m.group(3))


# --------------------------------------------------------------------------
# 數字抽取（從 OCR 文字，盡力而為 + 誠實標信心）
# --------------------------------------------------------------------------
# 關鍵字 → 可能的多種寫法（含 OCR 常見誤字容忍）。
_KW = {
    "income_total": ["收入合計", "收入總計", "收入總額", "收入合", "收人合計"],
    "expense_total": ["支出合計", "支出總計", "支出總額", "支出合", "費用合計"],
    "surplus": ["本期稅後餘絀", "本期稅後餘繹", "本期餘絀", "本期賸餘",
                "稅後餘絀", "本期稅前餘"],
}

# 金額樣式：可含括號（負數）、$、逗號。
_AMOUNT_RE = re.compile(r"\(?\$?\s*(-?[\d,]{4,})\s*\)?")


def _first_amount_after(text: str, keyword: str) -> tuple[int, bool] | None:
    """在 keyword 之後就近抓第一個金額；回傳 (值, 是否為括號負數)。找不到→None。"""
    idx = text.find(keyword)
    if idx < 0:
        return None
    tail = text[idx + len(keyword): idx + len(keyword) + 60]
    m = _AMOUNT_RE.search(tail)
    if not m:
        return None
    raw = m.group(1).replace(",", "")
    try:
        val = int(raw)
    except ValueError:
        return None
    # 括號代表負數（收支餘絀表常見）。
    seg = tail[:m.end()]
    is_paren = "(" in seg and ")" in tail[m.start():m.end() + 2]
    return (-abs(val) if is_paren else val, is_paren)


def _extract_amounts_by_line(text: str) -> dict[str, int]:
    """逐行掃描：對每個關鍵字，取「同一行或下一行」的第一個金額。

    比全文 find 更貼近表格「標題—數字同列」的結構，減少跨列誤抓。
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    found: dict[str, int] = {}
    for field_name, kws in _KW.items():
        if field_name in found:
            continue
        for li, line in enumerate(lines):
            if any(kw in line for kw in kws):
                # 先找本行，再找下一行的第一個金額。
                for cand in (line, lines[li + 1] if li + 1 < len(lines) else ""):
                    m = _AMOUNT_RE.search(cand)
                    if m:
                        raw = m.group(1).replace(",", "")
                        try:
                            val = int(raw)
                        except ValueError:
                            continue
                        seg = cand[m.start():m.end() + 1]
                        found[field_name] = -abs(val) if "(" in seg else val
                        break
                if field_name in found:
                    break
    return found


def extract_financials_from_text(text: str) -> dict[str, Any]:
    """從合併 OCR 文字抽收入/支出/餘絀，並回傳信心評估。"""
    # 先用逐行（表格列）抽取，較貼近「標題—數字同列」結構；
    # 缺漏者再以全文就近抽取補齊。
    found: dict[str, int] = _extract_amounts_by_line(text)
    for field_name, kws in _KW.items():
        if field_name in found:
            continue
        for kw in kws:
            hit = _first_amount_after(text, kw)
            if hit is not None:
                found[field_name] = hit[0]
                break

    # 信心判定：
    #   high   — 收入、支出、餘絀三者齊全，且 收入-支出 與 餘絀 大致相符（勾稽）。
    #   medium — 收入與支出齊全（可算收支比），但餘絀缺或勾稽不符。
    #   low    — 關鍵數字不齊。
    inc = found.get("income_total")
    exp = found.get("expense_total")
    sur = found.get("surplus")
    notes: list[str] = []
    confidence = "low"

    if inc is not None and exp is not None and sur is not None:
        implied = inc - exp
        # 允許 OCR 誤差容忍：相對誤差 < 2% 視為勾稽通過。
        denom = max(abs(sur), 1)
        if abs(implied - sur) / denom < 0.02:
            confidence = "high"
            notes.append("收入−支出≈本期餘絀，勾稽通過。")
        else:
            confidence = "medium"
            notes.append(
                f"勾稽不符：收入−支出={implied:,}，本期餘絀={sur:,}，"
                f"差 {implied - sur:,}（疑 OCR 誤差，需人工複核）。")
    elif inc is not None and exp is not None:
        confidence = "medium"
        notes.append("有收入與支出（可算收支比），但缺本期餘絀。")
    else:
        notes.append("關鍵財務數字不齊，需人工複核或改用 Bedrock 引擎重抽。")

    return {
        "income_total": inc, "expense_total": exp, "surplus": sur,
        "extraction_confidence": confidence,
        "needs_review": confidence != "high",
        "notes": notes,
    }


# --------------------------------------------------------------------------
# 單份抽取
# --------------------------------------------------------------------------
def extract_one(pdf_path: str, year: int, engine: str = "tesseract",
                pages: tuple[int, ...] = DEFAULT_FINANCIAL_PAGES,
                dpi: int = 300, keep_raw: bool = True) -> NonprofitFinancials:
    """對單份財報 OCR 指定頁並抽取財務數字。"""
    filename = os.path.basename(pdf_path)
    parsed = parse_filename(filename)
    code, name = (parsed[0], parsed[1]) if parsed else ("", filename)

    ocr_fn = ocr.ENGINES[engine]
    raw_pages: dict[int, str] = {}
    texts: list[str] = []
    import pymupdf
    doc = pymupdf.open(pdf_path)
    n = doc.page_count
    doc.close()
    for p in pages:
        if p > n:
            continue
        img = ocr.pdf_page_to_image(pdf_path, p - 1, dpi=dpi)
        text = ocr_fn(img)
        raw_pages[p] = text
        texts.append(text)

    merged = "\n".join(texts)
    ext = extract_financials_from_text(merged)

    return NonprofitFinancials(
        code=code, name=name, year=year,
        source_file=os.path.relpath(pdf_path, ROOT),
        engine=engine,
        income_total=ext["income_total"],
        expense_total=ext["expense_total"],
        surplus=ext["surplus"],
        extraction_confidence=ext["extraction_confidence"],
        needs_review=ext["needs_review"],
        notes=ext["notes"],
        raw_ocr_pages=raw_pages if keep_raw else {},
    )


# --------------------------------------------------------------------------
# 批次抽取（可續跑）
# --------------------------------------------------------------------------
def _output_path(code: str, year: int, engine: str) -> str:
    return os.path.join(OUTPUT_DIR, f"{code}_{year}_{engine}.json")


def list_reports(year_dirs: list[str] | None = None) -> list[tuple[str, int]]:
    """列出所有財報 (pdf_path, year)。year_dirs 為 None 時涵蓋全部學年度。"""
    reports: list[tuple[str, int]] = []
    if not os.path.isdir(DATASET_DIR):
        return reports
    for ydir in sorted(os.listdir(DATASET_DIR)):
        full = os.path.join(DATASET_DIR, ydir)
        if not os.path.isdir(full):
            continue
        if year_dirs and ydir not in year_dirs:
            continue
        ym = re.match(r"(\d{3})學年度", ydir)
        year = int(ym.group(1)) if ym else 0
        for fn in sorted(os.listdir(full)):
            if fn.lower().endswith(".pdf"):
                reports.append((os.path.join(full, fn), year))
    return reports


def run_batch(engine: str = "tesseract", year_dirs: list[str] | None = None,
              resume: bool = True, dpi: int = 300,
              progress=None) -> list[NonprofitFinancials]:
    """批次抽取全部（或指定學年度）財報，逐份存 JSON，可續跑。

    progress：可選 callback(done:int, total:int, item:NonprofitFinancials)。
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    reports = list_reports(year_dirs)
    total = len(reports)
    results: list[NonprofitFinancials] = []

    for i, (pdf_path, year) in enumerate(reports, start=1):
        parsed = parse_filename(os.path.basename(pdf_path))
        code = parsed[0] if parsed else os.path.basename(pdf_path)
        out = _output_path(code, year, engine)

        if resume and os.path.exists(out):
            with open(out, encoding="utf-8") as fh:
                data = json.load(fh)
            item = NonprofitFinancials(**data)
        else:
            item = extract_one(pdf_path, year, engine=engine, dpi=dpi)
            with open(out, "w", encoding="utf-8") as fh:
                json.dump(asdict(item), fh, ensure_ascii=False, indent=1)

        results.append(item)
        if progress:
            progress(i, total, item)
    return results


def aggregate_to_records(results: list[NonprofitFinancials]) -> list[dict]:
    """將抽取結果彙整為可併入風險引擎的 records（每園每年一列）。"""
    records = []
    for r in results:
        records.append({
            "park_id": f"{r.code}",
            "park_name": f"新北市{r.name}非營利幼兒園",
            "park_type": "非營利",
            "year": r.year,
            "income_actual": r.income_total,
            "expense_actual": r.expense_total,
            "surplus": r.surplus,
            "extraction_confidence": r.extraction_confidence,
            "needs_review": r.needs_review,
            "data_source": "非營利園財務報告（OCR 抽取）",
        })
    return records
