"""
非營利園財報財務抽取（AWS Bedrock 多模態，最省點數版）
======================================================================
對 data/external/nonprofit_reports/<年度>/ 下的非營利園財報 PDF，用 AWS
Bedrock（Claude 視覺）抽取「收支餘絀表」的收入/支出/餘絀決算數。

省點數設計：
  - 只抽「收支餘絀表」所在的單一頁（預設第 6 頁；此批財報版面固定），
    每份僅 1 次 Bedrock 呼叫。
  - 自我勾稽（收入 − 支出 ≈ 餘絀，容許 2% 誤差）判定信心；勾稽通過才標
    high，作為併入計分的把關（避免抽錯數字污染風險分）。
  - resume：已抽過（有 JSON）者跳過，可續跑不重複花錢。

輸出：
  - 逐份 JSON：data/derived/nonprofit_bedrock/<code>_<year>.json
  - 彙整 CSV：data/processed/nonprofit_financials_bedrock.csv

用法：
    python scripts/extract_nonprofit_bedrock.py            # 全部（第6頁）
    python scripts/extract_nonprofit_bedrock.py --page 6   # 指定頁
    python scripts/extract_nonprofit_bedrock.py --limit 3  # 只抽前3份(測試)
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time

import boto3
import pandas as pd
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
load_dotenv(os.path.join(ROOT, ".env"))

from src import ocr_nonprofit as ocr  # noqa: E402

REPORTS_DIR = os.path.join(ROOT, "data", "external", "nonprofit_reports")
OUT_JSON_DIR = os.path.join(ROOT, "data", "derived", "nonprofit_bedrock")
OUT_CSV = os.path.join(ROOT, "data", "processed", "nonprofit_financials_bedrock.csv")

_FILENAME_RE = re.compile(r"^(N\d+)([^_]+)_(\d{3})學年度")
_PROMPT = (
    "這是幼兒園的『收支餘絀表』掃描頁。表格欄位為預算數(a)、決算數(b)、差異(c)。"
    "請讀出『決算數(b)』欄的三個總計數字，以純 JSON 回傳（不要任何多餘文字或說明）：\n"
    '{"income_total": 收入合計決算數, "expense_total": 支出合計決算數, '
    '"surplus": 本期賸餘或短絀決算數}\n'
    "數字去除逗號與貨幣符號；短絀（負數）用負號表示。找不到的欄位填 null。"
)


def _client():
    return boto3.client("bedrock-runtime",
                        region_name=os.environ.get("BEDROCK_REGION", "us-west-2"))


def _parse_filename(fn):
    m = _FILENAME_RE.match(fn)
    return (m.group(1), m.group(2), int(m.group(3))) if m else None


def _ask_bedrock(client, model, img_bytes):
    b64 = base64.b64encode(img_bytes).decode()
    body = {
        "anthropic_version": "bedrock-2023-05-31", "max_tokens": 512,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png", "data": b64}},
            {"type": "text", "text": _PROMPT}]}],
    }
    resp = client.invoke_model(modelId=model, body=json.dumps(body))
    txt = json.loads(resp["body"].read())["content"][0]["text"]
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def _confidence(inc, exp, sur):
    if inc is None or exp is None or sur is None:
        return "low"
    denom = max(abs(sur), 1)
    return "high" if abs((inc - exp) - sur) / denom < 0.02 else "medium"


def _list_reports(limit=None):
    out = []
    if not os.path.isdir(REPORTS_DIR):
        return out
    for ydir in sorted(os.listdir(REPORTS_DIR)):
        full = os.path.join(REPORTS_DIR, ydir)
        if not os.path.isdir(full):
            continue
        for fn in sorted(os.listdir(full)):
            if fn.lower().endswith(".pdf"):
                out.append((os.path.join(full, fn), ydir))
    return out[:limit] if limit else out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--page", type=int, default=6, help="收支餘絀表頁碼(1-based)")
    ap.add_argument("--limit", type=int, default=None, help="只處理前 N 份(測試用)")
    ap.add_argument("--dpi", type=int, default=250)
    args = ap.parse_args()

    os.makedirs(OUT_JSON_DIR, exist_ok=True)
    client = _client()
    model = os.environ.get("BEDROCK_MODEL_ID")
    reports = _list_reports(args.limit)
    print(f"[i] 待處理 {len(reports)} 份，模型 {model}")

    records, stats = [], {"high": 0, "medium": 0, "low": 0}
    for i, (pdf, ydir) in enumerate(reports, 1):
        parsed = _parse_filename(os.path.basename(pdf))
        if not parsed:
            continue
        code, name, year = parsed
        out_json = os.path.join(OUT_JSON_DIR, f"{code}_{year}.json")
        if os.path.exists(out_json):
            data = json.load(open(out_json, encoding="utf-8"))
        else:
            try:
                img = ocr.pdf_page_to_image(pdf, args.page - 1, dpi=args.dpi)
                res = _ask_bedrock(client, model, img)
            except Exception as e:  # noqa: BLE001
                print(f"  [{i}/{len(reports)}] {code} {name} 失敗: {e}")
                continue
            inc = res.get("income_total")
            exp = res.get("expense_total")
            sur = res.get("surplus")
            data = {
                "park_id": code, "park_name": f"新北市{name}非營利幼兒園",
                "park_type": "非營利", "year": year,
                "income_actual": inc, "expense_actual": exp, "surplus": sur,
                "extraction_confidence": _confidence(inc, exp, sur),
                "data_source": "非營利園財務報告（Bedrock 視覺抽取）",
            }
            json.dump(data, open(out_json, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=1)
            time.sleep(0.5)
        stats[data.get("extraction_confidence", "low")] = \
            stats.get(data.get("extraction_confidence", "low"), 0) + 1
        records.append(data)
        print(f"  [{i}/{len(reports)}] {code} {name} {year} -> "
              f"{data['extraction_confidence']} "
              f"(收{data['income_actual']} 支{data['expense_actual']} 餘{data['surplus']})")

    df = pd.DataFrame(records)
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n[OK] 已寫入 {OUT_CSV}（{len(df)} 筆）")
    print(f"[信心分布] {stats}")


if __name__ == "__main__":
    main()
