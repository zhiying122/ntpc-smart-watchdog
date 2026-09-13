"""See which Linkou schools would match raw scandal headlines."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path[:0] = [".", "public", "app"]

from lib import news_crawler as nc
from lib import public_dataset as pdset

raw = json.loads(Path("data/cache/sentiment_raw_debug.json").read_text(encoding="utf-8"))
titles = sorted({r["title"].split(" - ")[0] for r in raw})

pub = pdset.load_public_dataset(timeout=8, prefer_cache=True)
df = pub.df
linkou = df[df["district"].astype(str).str.contains("林口", na=False)].copy()

matches = []
for _, row in linkou.iterrows():
    name = str(row["park_name"])
    core = nc.name_core(name)
    hit_titles = [t for t in titles if nc._title_matches(t, core, "林口區", name)]
    if hit_titles:
        matches.append({"park": name, "core": core, "hits": hit_titles})

# Also show titles containing 雙語 / 補習
special = [t for t in titles if any(k in t for k in ("雙語", "補習", "虐", "體罰", "市立林口", "私立林口"))]
out = {
    "n_titles": len(titles),
    "special_titles": special,
    "school_hits": matches,
    "linkou_cores_sample": [
        {"park": r.park_name, "core": nc.name_core(str(r.park_name))}
        for r in linkou.itertuples()
        if len(nc.name_core(str(r.park_name))) >= 2
    ][:30],
}
Path("data/cache/sentiment_linkou_match.json").write_text(
    json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(json.dumps({"n_titles": len(titles), "special": special, "hits": matches}, ensure_ascii=False, indent=2))
