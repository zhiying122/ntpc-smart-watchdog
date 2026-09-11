# -*- coding: utf-8 -*-
"""
全量抽取非營利園財報（132 份）— 批次執行腳本
用法：python scripts/run_nonprofit_ocr.py [--engine tesseract|bedrock]
逐份存 JSON 至 data/derived/nonprofit_ocr/，可續跑（已完成者跳過）。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault(
    "TESSDATA_PREFIX",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "data", "tessdata"))

from src import nonprofit_pipeline as npp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="tesseract",
                    choices=["tesseract", "textract", "bedrock"])
    ap.add_argument("--years", nargs="*", default=None,
                    help="指定學年度資料夾，如 113學年度；省略＝全部")
    args = ap.parse_args()

    start = time.time()
    stats = {"high": 0, "medium": 0, "low": 0}

    def progress(done, total, item):
        stats[item.extraction_confidence] = stats.get(
            item.extraction_confidence, 0) + 1
        elapsed = time.time() - start
        print(f"[{done}/{total}] {item.code} {item.name} {item.year} "
              f"-> {item.extraction_confidence} "
              f"(收{item.income_total} 支{item.expense_total} 餘{item.surplus}) "
              f"| 已用 {elapsed:.0f}s", flush=True)

    results = npp.run_batch(engine=args.engine, year_dirs=args.years,
                            resume=True, progress=progress)

    print("\n===== 完成 =====", flush=True)
    print(f"總份數: {len(results)}", flush=True)
    print(f"信心分布: {stats}", flush=True)
    print(f"總耗時: {time.time() - start:.0f}s", flush=True)


if __name__ == "__main__":
    main()
