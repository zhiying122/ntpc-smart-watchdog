"""完整重建（含 district）：geocode(offline,含district) → extract_public → merge → risk_score。"""
import importlib
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = Path(__file__).resolve().parent / "rebuild_all_result.txt"
log = []
OUT.write_text("START", encoding="utf-8")
try:
    import build_geocode
    importlib.reload(build_geocode)
    build_geocode.main(online=False)
    log.append("geocode OK")
    OUT.write_text("\n".join(log), encoding="utf-8")

    from src import extract_public
    importlib.reload(extract_public)
    extract_public.main()
    log.append("extract_public OK")
    OUT.write_text("\n".join(log), encoding="utf-8")

    import merge_financials
    importlib.reload(merge_financials)
    merge_financials.main()
    log.append("merge OK")
    OUT.write_text("\n".join(log), encoding="utf-8")

    from src import forensic, risk_score
    importlib.reload(forensic)
    importlib.reload(risk_score)
    risk_score.main()
    log.append("risk_score OK")

    import pandas as pd
    geo = pd.read_csv(ROOT / "data/processed/geocoded.csv")
    d = pd.read_csv(ROOT / "data/processed/kindergartens_latest.csv")
    log.append(f"geocoded 欄位: {list(geo.columns)}")
    log.append(f"latest 欄位含 district: {'district' in d.columns}")
    log.append(f"latest={len(d)}  district 缺={int(d['district'].isna().sum()) if 'district' in d.columns else 'NO'}/{len(d)}")
except Exception:
    log.append("ERR:\n" + traceback.format_exc())
OUT.write_text("\n".join(log), encoding="utf-8")
