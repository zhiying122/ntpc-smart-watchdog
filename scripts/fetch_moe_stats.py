"""
教育部統計處 - 新北市幼兒園逐年概況（統計趨勢圖層）
======================================================================
抓取教育部統計處開放資料「幼兒園概況—按學校所在縣市別分」，篩出新北市各
學年度總量統計（園數、幼生數、教師數等），供系統呈現「全市逐年概況趨勢」。

此為**全市總量統計**（非單園逐年），與單園鑑識分析互補：展現宏觀趨勢與
「系統可接更多官方開放資料」的可規模化性。不影響任何單園風險分計算。

資料來源：https://stats.moe.gov.tw/files/opendata/edu_B_2_2_1.csv
輸出：data/external/moe_ntpc_yearly.csv

用法：
    python scripts/fetch_moe_stats.py
    python scripts/fetch_moe_stats.py --offline
"""
from __future__ import annotations

import io
import os
import ssl
import sys
import urllib.request

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://stats.moe.gov.tw/files/opendata/edu_B_2_2_1.csv"
OUT_CSV = os.path.join(ROOT, "data", "external", "moe_ntpc_yearly.csv")
CITY = "新北市"

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _read(raw: bytes) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "big5"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            continue
    raise ValueError("無法解碼統計 CSV")


def main() -> pd.DataFrame:
    if "--offline" in sys.argv:
        if not os.path.exists(OUT_CSV):
            raise FileNotFoundError(f"離線模式找不到 {OUT_CSV}")
        return pd.read_csv(OUT_CSV)

    raw = urllib.request.urlopen(
        urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"}),
        timeout=40, context=_ctx).read()
    df = _read(raw)
    ntpc = df[df["縣市別"].astype(str).str.strip() == CITY].copy()
    ntpc = ntpc.sort_values("學年度").reset_index(drop=True)

    # 只保留供呈現的關鍵欄位（存在才取，容錯不同年度欄位差異）。
    keep = ["學年度", "園數總數", "公立園數", "幼生總數", "公立幼生總數",
            "教師總數", "教保員總數"]
    cols = [c for c in keep if c in ntpc.columns]
    out = ntpc[cols].copy()

    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"[OK] 已寫入 {OUT_CSV}")
    print(f"     新北市概況：{len(out)} 個學年度（{out['學年度'].min()}~{out['學年度'].max()}）")
    print(out.to_string())
    return out


if __name__ == "__main__":
    main()
