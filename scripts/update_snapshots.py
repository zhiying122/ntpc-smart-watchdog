"""
定時資料快照更新（Scheduled Data Snapshot Updater）
======================================================================
小小守護員 Smart Watchdog Platform — 供 GitHub Actions 每日自動執行，抓取
官方開放資料的最新版本，寫入 **data/snapshots/**（納入版控），讓線上部署
即使即時抓網失敗，也永遠有「近一天內」的新鮮備援資料可用。

抓取來源（皆為公開、免金鑰，沿用 src/live_source 的來源與解析）：
  1. 幼兒園基本資料 GeoJSON： PRESCHOOLS_URL
  2. 全國裁罰紀錄 JSON：      PUNISH_URL
上述為 g0v（江明宗 kiang）整理備份之全國教保資訊網資料。

設計原則：
  - 只做「抓取 + 落地 + 輕量健全性檢查」，不做任何風險計算或個資處理。
  - 抓取失敗（任一源）以非零結束碼結束，讓 GitHub Actions 顯示失敗、且不會
    以壞資料覆蓋既有快照（保留上一份可用快照）。
  - 寫出時附一份 snapshot_meta.json，記錄每個源的抓取時間與筆數，供頁面
    誠實揭露「上次自動更新時間」。

用法：
    python scripts/update_snapshots.py            # 抓取並更新快照
    python scripts/update_snapshots.py --check     # 只檢查現有快照，不觸網
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import live_source as ls  # noqa: E402

META_PATH = os.path.join(ls.SNAPSHOT_DIR, "snapshot_meta.json")

#: 健全性下限：低於此筆數視為來源異常，不覆蓋既有快照（避免壞資料上線）。
_MIN_FEATURES = 500      # preschools GeoJSON 的 features 數（全國幼兒園量級）
_MIN_PENALTY_KEYS = 10   # punish_all 的受處分對象數


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _feature_count(geojson: object) -> int:
    if isinstance(geojson, dict):
        feats = geojson.get("features")
        if isinstance(feats, list):
            return len(feats)
    return 0


def _penalty_key_count(punish: object) -> int:
    return len(punish) if isinstance(punish, dict) else 0


def _write_json(path: str, data: object) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def _fetch_source(url: str, out_path: str, *, kind: str, min_count: int,
                  counter) -> dict:
    """抓取單一來源並落地，回傳該源的 meta；失敗或資料異常則丟出例外。"""
    print(f"[update] 抓取 {kind}：{url}")
    data = ls._http_get_json(url, timeout=ls.DEFAULT_TIMEOUT)
    count = counter(data)
    if count < min_count:
        raise ValueError(
            f"{kind} 筆數異常（{count} < 下限 {min_count}），"
            "疑似來源異動或回傳不完整，放棄覆蓋既有快照。")
    _write_json(out_path, data)
    print(f"[update] {kind} 完成：{count} 筆 → {os.path.relpath(out_path, ROOT)}")
    return {"count": count, "fetched_at": _now_iso(),
            "source_url": url, "path": os.path.relpath(out_path, ROOT)}


def update_snapshots() -> int:
    """抓取兩個官方開放資料源並更新 data/snapshots/。回傳 0 成功、非 0 失敗。"""
    try:
        meta = {
            "attribution": ls.SOURCE_ATTRIBUTION,
            "updated_at": _now_iso(),
            "sources": {
                "preschools": _fetch_source(
                    ls.PRESCHOOLS_URL, ls.PRESCHOOLS_SNAPSHOT,
                    kind="幼兒園基本資料", min_count=_MIN_FEATURES,
                    counter=_feature_count),
                "penalties": _fetch_source(
                    ls.PUNISH_URL, ls.PUNISH_SNAPSHOT,
                    kind="裁罰紀錄", min_count=_MIN_PENALTY_KEYS,
                    counter=_penalty_key_count),
            },
        }
    except Exception as exc:  # noqa: BLE001 - 對外部來源的任何失敗都要明確非零退出
        print(f"[update] 失敗：{exc}", file=sys.stderr)
        print("[update] 既有快照保留不變（不以壞資料覆蓋）。", file=sys.stderr)
        return 1

    _write_json(META_PATH, meta)
    print(f"[update] 快照 meta 已更新 → {os.path.relpath(META_PATH, ROOT)}")
    return 0


def check_snapshots() -> int:
    """只檢查現有快照是否存在且筆數合理，不觸網。回傳 0 正常、非 0 異常。"""
    ok = True
    for kind, path, counter, floor in (
        ("幼兒園基本資料", ls.PRESCHOOLS_SNAPSHOT, _feature_count, _MIN_FEATURES),
        ("裁罰紀錄", ls.PUNISH_SNAPSHOT, _penalty_key_count, _MIN_PENALTY_KEYS),
    ):
        data, mtime = ls._read_cache(path)
        if data is None:
            print(f"[check] 缺少 {kind} 快照：{path}", file=sys.stderr)
            ok = False
            continue
        n = counter(data)
        status = "OK" if n >= floor else "偏低"
        print(f"[check] {kind}：{n} 筆（{status}），更新於 {mtime}")
        ok = ok and n >= floor
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="更新官方開放資料快照（data/snapshots/）")
    ap.add_argument("--check", action="store_true",
                    help="只檢查現有快照，不觸網")
    args = ap.parse_args()
    return check_snapshots() if args.check else update_snapshots()


if __name__ == "__main__":
    raise SystemExit(main())
