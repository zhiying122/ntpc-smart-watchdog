"""Audit demo sentiment classification and related roster facts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path[:0] = [".", "public", "app"]

from lib import public_dataset as pdset
from lib import sentiment_watch as sw

demo = json.loads(Path("public/data/sentiment_demo.json").read_text(encoding="utf-8"))
neu_but_should = []
counts = {"neg": 0, "neu": 0, "pos": 0}
for inst in demo["institutions"].values():
    for it in inst.get("items", []):
        text = f"{it.get('title', '')} {it.get('excerpt', '')}"
        s = sw.classify_sentiment(text)
        counts[s] = counts.get(s, 0) + 1
        keys = (
            "抱怨", "不滿", "問題", "貴", "超收", "退費", "複雜", "擔心", "失望",
            "差", "亂", "爭議", "不當", "虐", "裁罰", "投訴", "態度", "難溝通",
        )
        if s == "neu" and any(k in text for k in keys):
            neu_but_should.append(
                {
                    "park": inst.get("park_name"),
                    "title": it.get("title"),
                    "excerpt": (it.get("excerpt") or "")[:80],
                }
            )

print("demo_counts", counts)
print("neu_with_complaint_words", len(neu_but_should))
print(json.dumps(neu_but_should[:15], ensure_ascii=False, indent=2))

pub = pdset.load_public_dataset(timeout=8, prefer_cache=True)
df = pub.df
hit = df[df["park_name"].astype(str).str.contains("雙語|长庚|長庚", na=False)]
print("special_name_hits", len(hit))
print(hit[["park_name", "district"]].head(20).to_string())
print("penalty_flag_yes", int((df["penalty_flag"] == "有").sum()))
