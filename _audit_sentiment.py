"""Live audit: crawl news/PTT for sample NTPC parks and count negatives."""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[0]
sys.path[:0] = [str(ROOT), str(ROOT / "public"), str(ROOT / "app")]

from lib import news_crawler as nc
from lib import sentiment_watch as sw
from src import ptt_crawler as ptt

SAMPLES = [
    ("新北市立林口幼兒園", "林口區"),
    ("新北市立中和幼兒園", "中和區"),
    ("新北市立三重幼兒園", "三重區"),
    ("新北市私立林口幼兒園", "林口區"),
    ("新北市新莊非營利幼兒園", "新莊區"),
    ("新北市文中非營利幼兒園", "新莊區"),
]


def main() -> None:
    ref = date.today()
    out = []
    for name, district in SAMPLES:
        news = nc.fetch_all_news(name, district, reference=ref, limit=40)
        matched_news = [r for r in news if r.get("matched")]
        try:
            posts = ptt.fetch_ptt(name, district, reference=ref, limit=20)
        except Exception as e:  # noqa: BLE001
            posts = []
            print(f"PTT fail {name}: {e}")
        matched_ptt = [r for r in posts if r.get("matched")]
        all_m = matched_news + matched_ptt
        neg_titles = []
        for r in all_m:
            title = r.get("title", "")
            sent = sw.classify_sentiment(f"{title} {r.get('excerpt', '')}")
            if sent == "neg":
                neg_titles.append(
                    {
                        "title": title[:80],
                        "platform": r.get("source_platform") or r.get("source_type"),
                        "matched": r.get("matched"),
                    }
                )
        row = {
            "park": name,
            "news_matched": len(matched_news),
            "ptt_matched": len(matched_ptt),
            "neg_count": len(neg_titles),
            "neg_samples": neg_titles[:5],
            "all_matched_titles": [r.get("title", "")[:60] for r in all_m[:8]],
        }
        out.append(row)
        print(
            f"{name}: news={row['news_matched']} ptt={row['ptt_matched']} "
            f"neg={row['neg_count']}"
        )
        for n in neg_titles[:3]:
            print(f"  NEG [{n['platform']}] {n['title']}")

    Path("data/cache/sentiment_live_audit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
