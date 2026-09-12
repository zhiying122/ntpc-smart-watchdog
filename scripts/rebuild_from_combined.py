"""從 financials_combined.csv 重建契約檔（含附幼 behavioral），並驗證評分檔分布。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["FISCALINT_FINANCIALS"] = str(ROOT / "data" / "processed" / "financials_combined.csv")

from src import risk_score  # noqa: E402

risk_score.main()

import pandas as pd  # noqa: E402
d = pd.read_csv(ROOT / "data" / "processed" / "kindergartens_latest.csv")
print("latest rows:", len(d))
print("types:", d["park_type"].value_counts().to_dict())
print("profiles:", d["scoring_profile"].value_counts().to_dict())
beh = d[d["scoring_profile"] == "behavioral"]
if len(beh):
    print("\n[behavioral 附幼]")
    print(beh[["park_name", "score_penalty", "score_eval",
               "risk_total", "risk_level"]].to_string(index=False))
