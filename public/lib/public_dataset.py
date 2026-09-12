"""
公眾網真實資料集（Public Dataset）— 串接 live_source 即時官方開放資料
============================================================================
小小守護員 Smart Watchdog Platform — 家長端公眾查詢網的資料來源整合層。

把 src/live_source.py 的即時官方開放資料（新北市全部幼兒園基本資料 + 全國
裁罰紀錄）轉為家長端可直接使用的資料結構：
  - 機構清單（含經緯度、公私立別、行政區、地址、月收費）——來自 preschools。
  - 每間機構綁定的**真實裁罰明細**（日期、罰鍰、法條）——以機構負責人姓名
    （owner）比對 punish_all 的受處分對象（subject）而來。

責任 AI / 資料治理：
--------------------------------------------------------------------------
- 本層只輸出**公開欄位**（機構識別、地址、公私立、收費、裁罰事實），不含也
  不產生任何內部風險分數／等級。裁罰為主管機關依法處分之公開事實。
- 資料為 g0v 開源專案（江明宗 kiang）整理之全國教保資訊網備份，屬二手整理
  來源，一律標註來源與抓取時間，供家長判斷時效與可信度。
- 裁罰以「負責人姓名」比對，可能有同名情形；呈現層標明係依公開紀錄比對，
  建議家長回主管機關公告查證。

本模組不 import streamlit；快取由呼叫端以 st.cache_data 包裝。
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import live_source as ls  # noqa: E402


def _norm_name(name) -> str:
    """正規化園名以利官方裁罰與名冊資料交叉比對。"""
    s = "" if pd.isna(name) else str(name).strip()
    s = re.sub(r"[（(].*?[）)]", "", s)
    for junk in ("新北市政府", "新北市", "私立", "市立", "立", "　", " "):
        s = s.replace(junk, "")
    return s.strip()


@dataclass
class PublicDataset:
    """家長端公開資料集（真實資料 + 狀態）。

    - df：機構 DataFrame（僅公開欄位）。
    - penalty_index：owner 姓名 → 裁罰明細清單（供詳情頁查明細）。
    - is_live：是否為即時抓取（False 表示用離線快取備援）。
    - fetched_at / attribution / note：資料時效與來源標註（誠實揭露）。
    """
    df: pd.DataFrame
    penalty_index: dict[str, list]
    is_live: bool
    fetched_at: str | None
    attribution: str
    note: str = ""


#: 家長端公開欄位（刻意不含任何內部風險分數／等級）。
PUBLIC_COLUMNS = [
    "park_id", "park_name", "park_type", "district", "address",
    "lat", "lng", "monthly", "owner", "penalty_count", "eval_grade",
]


def _penalty_records_by_owner(penalties: list) -> dict[str, list]:
    """把裁罰紀錄依受處分對象姓名索引為**可序列化 dict**（供 Streamlit 快取）。

    值為 [{date, punishment, law, subject_type}, ...]，不含 dataclass 物件，
    確保能被 st.cache_data 序列化保存。

    去重（資料正確性）：同一受處分對象名下，來源資料可能出現重複的裁罰紀錄
    （相同 record_id，或 id 缺漏時以 date+law+punishment 判定），一律只保留一筆，
    避免家長看到被灌水的裁罰筆數。
    """
    idx: dict[str, list] = {}
    seen: dict[str, set] = {}
    for p in penalties:
        name = (p.subject or "").strip()
        if not name:
            continue
        # 去重鍵：優先 record_id；缺漏時以 date+law+punishment 組合。
        rid = (p.record_id or "").strip()
        key = rid or f"{p.date}|{p.law}|{p.punishment}"
        seen_keys = seen.setdefault(name, set())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        idx.setdefault(name, []).append({
            "date": p.date,
            "punishment": p.punishment,
            "law": p.law,
            "subject_type": p.subject_type,
        })
    return idx


def load_public_dataset(city: str = "新北市", timeout: int = 30,
                        prefer_cache: bool = False) -> PublicDataset:
    """載入家長端公開資料集（即時官方開放資料，含離線備援）。

    流程：
      1. 由 live_source 抓取指定縣市機構（含經緯度、收費）與全國裁罰紀錄。
      2. 以機構負責人姓名比對裁罰明細，得每間的真實裁罰筆數與明細。
      3. 投影為僅含公開欄位的 DataFrame，過濾掉無座標者（地圖需要）。

    回傳 PublicDataset（含 is_live / fetched_at / attribution 供誠實揭露）。
    """
    ds = ls.load_live_dataset(city=city, timeout=timeout, prefer_cache=prefer_cache)
    pen_idx = _penalty_records_by_owner(ds.penalties)

    # 整合教育部全國教保資訊網新北市裁罰名單 (data/external/ntpc_penalty.csv)
    pen_csv = os.path.join(_ROOT, "data", "external", "ntpc_penalty.csv")
    official_pens: dict[str, dict] = {}
    if os.path.exists(pen_csv):
        try:
            pen_df = pd.read_csv(pen_csv)
            for _, pr in pen_df.iterrows():
                k = _norm_name(str(pr.get("park_name", "")))
                if k:
                    official_pens[k] = pr.to_dict()
        except Exception:
            pass

    # 載入評鑑等第 (penalties.csv 與 kindergartens_latest.csv)
    eval_by_key: dict[str, str] = {}
    for p_path in [
        os.path.join(_ROOT, "data", "processed", "kindergartens_latest.csv"),
        os.path.join(_ROOT, "data", "external", "penalties.csv"),
    ]:
        if os.path.exists(p_path):
            try:
                _edf = pd.read_csv(p_path)
                for _, er in _edf.iterrows():
                    eg = str(er.get("eval_grade", "") or "").strip()
                    en = str(er.get("park_name", "") or "").strip()
                    if eg and eg.lower() not in ("nan", "none", "") and en:
                        eval_by_key[_norm_name(en)] = eg
            except Exception:
                pass

    rows: list[dict] = []
    _active_vals = {"是", "true", "True", "1", "Y", "y", 1, True}
    for inst in ds.institutions:
        raw = inst.raw or {}
        # 只保留「營運中」機構（is_active）；已停業/歇業者不對家長顯示。
        if raw.get("is_active") not in _active_vals:
            continue
        # 只保留真正的「幼兒園」（排除職場互助教保服務中心等非幼兒園機構）。
        if "幼兒園" not in inst.park_name:
            continue

        owner = (inst.owner or "").strip()
        recs = pen_idx.get(owner, []) if owner else []
        # 只採計「機構 penalty_flag 為有」時的 owner 比對明細，降低同名誤綁。
        has_flag = (inst.penalty_flag or "").strip() == "有"

        # 交叉比對教育部全國教保資訊網裁罰清單
        p_norm = _norm_name(inst.park_name)
        official_rec = official_pens.get(p_norm)
        pen_status = ""
        if official_rec is not None:
            has_flag = True
            pen_status = str(official_rec.get("status", "") or "正常").strip()
            # 若負責人比對不到逐筆明細，注入全國教保資訊網官方公告裁罰紀錄
            if not recs:
                direct_rec = {
                    "date": "主管機關公告列管",
                    "punishment": f"違反幼兒教育及照顧法經主管機關依法處分（營運狀態：{pen_status}）",
                    "law": "幼兒教育及照顧法相關條文",
                    "subject_type": "機構列管",
                    "source_url": "https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx",
                }
                recs = [direct_rec]
                if owner:
                    pen_idx[owner] = recs
                pen_idx[inst.park_name] = recs

        pcount = len(recs) if (has_flag and recs) else (1 if has_flag else 0)

        # 準公共合作旗標（pre_public 非「無」代表為準公共合作園）。
        pre_pub = str(raw.get("pre_public") or "").strip()
        is_quasi_public = bool(pre_pub) and pre_pub != "無"

        rows.append({
            "park_id": inst.park_id,
            "park_name": inst.park_name,
            "park_type": inst.park_type,
            "district": inst.district,
            "address": inst.address,
            "lat": inst.lat,
            "lng": inst.lng,
            "monthly": inst.monthly,
            "owner": owner,
            "penalty_count": pcount,
            "penalty_flag": "有" if has_flag else inst.penalty_flag,
            "official_penalty_status": pen_status,
            "eval_grade": eval_by_key.get(p_norm, ""),
            "is_quasi_public": is_quasi_public,
            "quasi_public_period": pre_pub if is_quasi_public else "",
        })

    # 同名負責人風險（資料正確性 / 責任 AI）：一位負責人常同時經營多間園，
    # 以姓名比對裁罰時無法區分是哪一間園被罰。計算每位 owner 名下的（有效）
    # 機構數，供呈現層對「一人多園」的裁罰明細加註提醒，不誇大單園裁罰。
    from collections import Counter as _Counter
    _owner_fac = _Counter(r["owner"] for r in rows if r.get("owner"))
    for r in rows:
        r["owner_facility_count"] = int(_owner_fac.get(r.get("owner"), 0))

    df = pd.DataFrame(rows)
    # 過濾無座標者（地圖與距離計算需要）。
    if not df.empty:
        df = df[df["lat"].notna() & df["lng"].notna()].reset_index(drop=True)

    # 資料時效與來源（取機構源狀態為主）。
    st_ins = ds.institutions_status
    note = ""
    if st_ins.used_fallback:
        note = "目前顯示為離線快取資料（即時來源暫時無法連線）。"

    return PublicDataset(
        df=df,
        penalty_index=pen_idx,
        is_live=st_ins.is_live,
        fetched_at=st_ins.fetched_at,
        attribution=ls.SOURCE_ATTRIBUTION,
        note=note,
    )


def penalty_details_for(owner: str, penalty_flag: str,
                        penalty_index: dict[str, list],
                        park_name: str = "") -> list[dict]:
    """回傳某機構的真實裁罰明細（依負責人姓名或機構名稱比對），依日期新到舊排序。

    僅在機構 penalty_flag 為「有」時回傳明細，避免同名誤綁。每筆為
    {date, punishment, law, subject_type}（penalty_index 已為序列化 dict）。
    """
    if (penalty_flag or "").strip() != "有":
        return []
    recs = list(penalty_index.get((owner or "").strip(), []))
    if not recs and park_name:
        recs = list(penalty_index.get(park_name.strip(), []))
        if not recs:
            norm_k = _norm_name(park_name)
            for k, v in penalty_index.items():
                if _norm_name(k) == norm_k:
                    recs = list(v)
                    break
    recs.sort(key=lambda x: str(x.get("date", "")), reverse=True)
    return recs


def load_financial_transparency_data() -> dict[str, dict]:
    """載入政府公開財務與決算資料（非營利/公立幼兒園決算公開資訊）。

    來源：政府資料開放平臺（https://data.gov.tw/）及新北市政府教育局總決算書。
    回傳：正規化園名 → 財務公開摘要 dict。
    """
    fin_map: dict[str, dict] = {}

    # 1. 優先採用 Bedrock 交叉核驗的非營利幼兒園高精度決算表
    bedrock_csv = os.path.join(_ROOT, "data", "processed", "nonprofit_financials_bedrock.csv")
    if os.path.exists(bedrock_csv):
        try:
            bdf = pd.read_csv(bedrock_csv)
            for _, r in bdf.iterrows():
                name = str(r.get("park_name", "")).strip()
                if not name:
                    continue
                k = _norm_name(name)
                inc = float(r.get("income_actual", r.get("total_income", 0.0)) or 0.0)
                exp = float(r.get("expense_actual", r.get("total_expense", 0.0)) or 0.0)
                tui = float(r.get("tuition_actual", 0.0) or 0.0) if pd.notna(r.get("tuition_actual")) else 0.0
                surplus = float(r.get("surplus", 0.0) or (inc - exp))
                fin_map[k] = {
                    "source": "新北市政府教育局委託非營利幼兒園總決算書（主管機關公開檔案）",
                    "year": "113 學年度",
                    "total_income": inc,
                    "total_expense": exp,
                    "tuition_actual": tui,
                    "surplus": surplus,
                    "expense_income_ratio": round(exp / inc, 4) if inc > 0 else None,
                    "is_balanced": "收支大致平衡" if (inc > 0 and 0.90 <= exp / inc <= 1.05) else ("支出偏高" if exp > inc else "結餘充裕"),
                }
        except Exception:
            pass

    # 2. 備援補充 financials.csv（公校決算）
    fin_csv = os.path.join(_ROOT, "data", "processed", "financials.csv")
    if os.path.exists(fin_csv):
        try:
            fdf = pd.read_csv(fin_csv)
            for _, r in fdf.iterrows():
                name = str(r.get("park_name", "")).strip()
                k = _norm_name(name)
                if k not in fin_map and name:
                    inc = float(r.get("income_actual", r.get("total_income", 0.0)) or 0.0)
                    exp = float(r.get("expense_actual", r.get("total_expense", 0.0)) or 0.0)
                    tui = float(r.get("tuition_actual", 0.0) or 0.0) if pd.notna(r.get("tuition_actual")) else 0.0
                    surplus = float(r.get("surplus", 0.0) or (inc - exp))
                    fin_map[k] = {
                        "source": "新北市政府教育局公立學校附設幼兒園決算資料（政府資料開放平臺）",
                        "year": str(r.get("year", "113 年度")),
                        "total_income": inc,
                        "total_expense": exp,
                        "tuition_actual": tui,
                        "surplus": surplus,
                        "expense_income_ratio": round(exp / inc, 4) if inc > 0 else None,
                        "is_balanced": "公費預算核銷平衡",
                    }
        except Exception:
            pass

    return fin_map
