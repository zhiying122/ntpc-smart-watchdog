"""Debug raw RSS hits vs title matching for one municipal park."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parents[0]
sys.path[:0] = [str(ROOT), str(ROOT / "public")]

from lib import news_crawler as nc

NAME = "新北市立林口幼兒園"
DIST = "林口區"
REF = date.today()


def main() -> None:
    core = nc.name_core(NAME)
    print("core", core, "generic", nc._is_generic_core(core, DIST))
    topics = list(nc._QUERY_TOPICS)
    raw_all = []
    for topic in topics:
        q = nc.build_query(NAME, DIST, extra=topic)
        url = nc._GNEWS_RSS.format(query=quote(q))
        try:
            resp = requests.get(url, headers=nc._HEADERS, timeout=12)
            print("topic", repr(topic), "status", resp.status_code, "len", len(resp.text))
            # parse quickly
            import xml.etree.ElementTree as ET

            root = ET.fromstring(resp.text)
            items = root.findall(".//item")
            print("  items", len(items))
            for it in items[:5]:
                title = (it.findtext("title") or "")[:100]
                matched = nc._title_matches(title, core, DIST, NAME)
                raw_all.append({"topic": topic, "title": title, "matched": matched})
                print("  ", "Y" if matched else "N", title)
        except Exception as e:  # noqa: BLE001
            print("topic fail", topic, e)

    # Also try looser queries that people would search
    for q in (
        f'"{core}" 幼兒園 虐童',
        f"市立{core}幼兒園",
        f"{NAME} 裁罰",
        "林口 幼兒園 虐童 新北",
    ):
        url = nc._GNEWS_RSS.format(query=quote(q))
        try:
            resp = requests.get(url, headers=nc._HEADERS, timeout=12)
            import xml.etree.ElementTree as ET

            root = ET.fromstring(resp.text)
            items = root.findall(".//item")
            print(f"\nLOOSE q={q!r} items={len(items)}")
            for it in items[:6]:
                title = (it.findtext("title") or "")[:120]
                print("  ", title)
        except Exception as e:  # noqa: BLE001
            print("loose fail", q, e)

    Path("data/cache/sentiment_raw_debug.json").write_text(
        json.dumps(raw_all, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
