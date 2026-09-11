"""
可解釋風險評分模型（白盒子）
================================
把鑑識會計指標 + 裁罰 + 評鑑，組成 0-100 的總風險分。
核心原則：可解釋。每個分項規則寫死在設定裡，能對評審講清楚
「51 分 = 財務18 + 裁罰27 + 評鑑6」怎麼來的。
（現行三項制：財務 50% + 裁罰 34% + 評鑑 16%。輿情資料源尚未接入，
故不納入計分，原 10% 依比例分配給其餘三項。）

輸出：data/processed/kindergartens.csv （交給組員做儀表板的契約檔）
"""
import os
import pandas as pd

from src.forensic import analyze
from src.models import RiskBreakdown
from src.penalty_nlp import penalty_severity_score, classify_penalty_text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

# ---------- 分項權重（可調，簡報時秀這張）----------
WEIGHTS = {
    # 只用「已接入的真實資料源」組成總分，避免佔位值稀釋真實性。
    # 輿情資料源尚未接入（無真實爬蟲/NLP），故不納入計分；原 10% 依比例
    # 分配給其餘三項（45:30:15 → 50:34:16，合計 100%）。
    "financial": 0.50,   # 財務異常（四層鑑識會計，資料最完整可靠）
    "penalty": 0.34,     # 裁罰紀錄
    "eval": 0.16,        # 評鑑結果
}


def score_financial(row):
    """
    財務異常分(0-100)：四層鑑識會計方法疊合，全部可解釋。
    可解釋組成：
      班佛定律 25% + Beneish改良版 20% + Isolation Forest 25%
      + 收支比離群 10% + 跨年度突變 10% + 賸餘短絀率 10%
    多層方法互相佐證：多個方法同時指向的園，風險最高。
    """
    # NaN 安全轉 0：非營利園無逐筆明細 → benford_score 為 NaN，該層視為中性(0)，
    # 不可用「NaN or 0」（NaN 為 truthy 會保留 NaN 並汙染總分）。
    def _z(v):
        return 0.0 if v is None or pd.isna(v) else float(v)

    benford = _z(row.get("benford_score"))
    beneish = _z(row.get("beneish_score"))
    iforest = _z(row.get("iforest_score"))
    outlier = 100 if row.get("outlier_expense_ratio") else 0
    # 收支比 >1 (入不敷出) 加權：超過越多分越高
    ratio = row.get("expense_income_ratio")
    ratio_pts = 0
    if pd.notna(ratio) and ratio > 1:
        ratio_pts = min((ratio - 1) * 500, 100)  # 超支20%即滿分
    yoy = row.get("expense_yoy_pct")
    yoy_pts = min(abs(yoy) * 2, 100) if pd.notna(yoy) else 0
    # 賸餘短絀率：本期短絀占收入比，短絀越大代表基金被侵蝕，是重要財務警訊
    deficit_pts = 0
    surplus = row.get("surplus")
    income = row.get("income_actual")
    if pd.notna(surplus) and pd.notna(income) and income and surplus < 0:
        deficit_ratio = abs(surplus) / income
        deficit_pts = min(deficit_ratio * 1000, 100)  # 短絀達收入10%即滿分

    score = (0.25 * benford + 0.20 * beneish + 0.25 * iforest
             + 0.10 * ratio_pts + 0.10 * yoy_pts + 0.10 * deficit_pts)
    return round(min(score, 100), 1)


def score_penalty(row):
    """
    裁罰分(0-100)：改用「裁罰性質分類 + 嚴重度」，而非純次數。
    看違規性質——2 次收費違規(90) 應遠重於 2 次行政缺失(45)。詳見 src/penalty_nlp.py。

    向後相容：
      - 傳入純量（int/float 或 NaN）→ 視為「只有次數、無事由文字」，以中性
        嚴重度 50 為基底遞增（0 次=0、1 次=50、2 次=60…）。相容既有以
        score_penalty(2) 純次數呼叫的程式與測試。
      - 傳入 dict / pandas.Series（含 penalty_count、penalty_reason）→ 依事由
        分類取主類別嚴重度為基底，再依次數遞增（收費 1 次=80、2 次=90…）。
    """
    if isinstance(row, (int, float)) or row is None or (
            not hasattr(row, "get")):
        # 純量介面：只有次數、無事由文字
        return penalty_severity_score(row, "")
    return penalty_severity_score(row.get("penalty_count"), row.get("penalty_reason"))


def score_eval(grade):
    """評鑑分(0-100)：優=0 良=20 中=50 待改進=90。缺資料=中性30。"""
    mapping = {"優": 0, "甲": 10, "良": 20, "乙": 40, "中": 50,
               "丙": 70, "待改進": 90, "不通過": 100}
    if pd.isna(grade) or grade == "":
        return 30
    return mapping.get(str(grade).strip(), 30)


def score_sentiment(neg_ratio):
    """輿情分(0-100)：負面比例 * 100。缺資料=中性20。"""
    if pd.isna(neg_ratio):
        return 20
    return round(min(float(neg_ratio) * 100, 100), 1)


def risk_level_absolute(total):
    """絕對門檻分級（保留備用）：≥60高, ≥35中, 其餘低。"""
    if total >= 60:
        return "高"
    if total >= 35:
        return "中"
    return "低"


def risk_level_percentile(series):
    """
    百分位相對分級（主用）：以全體同儕分布做相對風險等級。
    前 15% = 高風險（最需優先稽查）、次 35% = 中風險、其餘 = 低風險。
    學理：同儕比較 (peer benchmarking) + 百分位分級，適合「排序稽查優先序」的目的，
    不宣稱絕對造假門檻。文獻見 docs/methodology.md 同儕比較段落。
    """
    ranks = series.rank(pct=True)  # 0~1，越大分數越高

    def level(r):
        if r >= 0.85:
            return "高"
        if r >= 0.50:
            return "中"
        return "低"
    return ranks.apply(level)


def risk_level_by_group(df, score_col="risk_total", group_col="park_type",
                        min_group=7):
    """
    分組百分位相對分級（公平性版）：在每個機構類型內部各自做百分位分級。

    問題背景：公校有逐筆明細 → 有班佛分項；非營利園無明細 → 班佛分項以中性
    0 計入，財務分被系統性低估。若把兩類機構放同一把尺做全體百分位（見
    risk_level_percentile），非營利園會被結構性地壓在後段，導致實務上「整類
    機構被隱形、稽查資源永遠不投向非營利園」的偏誤。

    正解（對齊 R13 同儕比較精神，見 src/peer.py）：同儕比較應在「可比同儕
    群組」內進行。公校與非營利園屬不同同儕群組，分開排序才公平——每一類都能
    篩出「該類型中相對最需優先稽查」的機構。

    min_group：某類型樣本數 < min_group 時，該類型改用全體百分位，避免小樣本
    下百分位分級不穩定（例如某類型只有 3 間，「前 15%」無統計意義）。

    回傳與 df 對齊的等級 Series（高/中/低）。
    """
    if group_col not in df.columns:
        return risk_level_percentile(df[score_col])

    result = pd.Series(index=df.index, dtype="object")
    all_rank = df[score_col].rank(pct=True)
    for _gval, idx in df.groupby(group_col).groups.items():
        sub = df.loc[idx, score_col]
        if len(sub) >= min_group:
            result.loc[idx] = risk_level_percentile(sub)
        else:
            # 小樣本：退回以全體分布計算的百分位，較穩健。
            result.loc[idx] = all_rank.loc[idx].apply(
                lambda r: "高" if r >= 0.85 else ("中" if r >= 0.50 else "低"))
    return result


def risk_level_four(total):
    """
    四級絕對分級（R10.2）：低／中／高／極高（critical）。
    對齊 R2.1 的門檻並向上延伸出「極高」一級，供白盒 score() 輸出：
      < 40 低、40–69 中、70–89 高、>= 90 極高。
    百分位相對分級（risk_level_percentile）仍為稽查優先序排序主用（R10.6），
    本四級為單一機構檢視（Inspector_Workspace, R5.1）的絕對等級標示。
    """
    if total >= 90:
        return "極高"
    if total >= 70:
        return "高"
    if total >= 40:
        return "中"
    return "低"


# ---------- 缺資料中性值與責任 AI 常數（R10.4, R10.5, R18.2, R19.4）----------
# 各分項「缺乏真實資料來源」時代入的中性值（0–100）。
# 設計原則（R10.5）：中性值不得放大風險 —— 對每一分項，中性值 ≤ 100（該分項
# 最大風險值），故以中性值代入所得 total 必不高於「該分項採用最大風險」的 total。
# 選值與既有分項函式的缺值行為一致，確保 score() 與批次 build() 可解釋且一致：
#   financial：缺逐筆明細/財報 → 0（該鑑識層視為中性、不貢獻風險）。
#   penalty  ：查無裁罰紀錄 → 0（誠實：無資料不等於有裁罰）。
#   eval     ：查無評鑑 → 30（略偏保守的中性值，仍遠低於「待改進 90」等高風險）。
NEUTRAL_SUBSCORES = {
    "financial": 0.0,
    "penalty": 0.0,
    "eval": 30.0,
}

# 責任 AI（R10.4, R19.4）：任何面向使用者的風險陳述皆附非空「風險不等於違法」聲明。
NOT_ILLEGALITY_NOTICE = (
    "風險不等於違法（Risk does not equal illegality）。"
    "本分數僅為稽查優先序參考，非違法或舞弊之認定。"
)


def _is_missing(v):
    """判定分項來源值是否「缺乏真實資料」（None 或 NaN 視為缺值）。"""
    if v is None:
        return True
    try:
        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return False


# ---------- 白盒混合風險評分：分項貢獻明細與可加性（R10.1–R10.3, R5.2）----------
def _confidence_value(confidence):
    """將傳入的可信度正規化為 0–100 的浮點數。

    接受：None（視為 100 滿分）、數值、或帶 `.score` 屬性的 DataConfidence。
    """
    if confidence is None:
        return 100.0
    if hasattr(confidence, "score"):
        confidence = confidence.score
    try:
        val = float(confidence)
    except (TypeError, ValueError):
        return 100.0
    return max(0.0, min(val, 100.0))


def score(entity, weights=None, confidence=None):
    """輸出白盒風險分解 RiskBreakdown（R10.1–R10.3, R5.2）。

    參數
    ----
    entity : dict | pandas.Series
        單一機構的評分輸入，需可取得各分項原始分（見下）或其計算來源欄位。
    weights : dict | None
        分項顯示權重；預設沿用既有加權（financial 0.50 + penalty 0.34
        + eval 0.16）。權重鍵須落在 {financial, penalty, eval}。
    confidence : float | DataConfidence | None
        資料可信度（0–100），寫入 RiskBreakdown.data_confidence 併同顯示（R18.3）。

    回傳
    ----
    RiskBreakdown
        total(0–100) + 各分項加權貢獻明細 contributions + level(低/中/高/極高)。
        不變式：round(sum(contributions.values()), 1) == total（R5.2, R10.3）。

    設計說明
    --------
    - 沿用既有分項評分函式（score_financial / score_penalty / score_eval），
      確保與批次 build() 的計分一致、可解釋（R10.6）。
    - 各分項貢獻 = 權重 × 分項分數；貢獻明細加總四捨五入至一位小數即為 total，
      直接由貢獻回推 total 以保證可加性（雷達圖攤開即為總分，R5.2）。

    缺資料中性處理（R10.5, R18.2）
    ------------------------------
    - 當某分項缺乏真實資料來源（既無 score_* 亦無可計算之來源欄位）時，以
      NEUTRAL_SUBSCORES 的中性值代入，而非佔位放大風險。中性值 ≤ 100（該分項
      最大風險），故缺資料所得 total 必 ≤「該分項採用最大風險值」之 total
      （Property 30 上界性質）。
    - data_confidence 僅作為併同顯示的資料可信度（R18.3），不參與 total/level
      的計算 —— 低可信度不會僅因其低而推高風險或等級（R18.2, Property 30）。

    責任 AI（R10.4, R19.4）
    -----------------------
    - 每個 RiskBreakdown 皆帶非空 not_illegality_notice「風險不等於違法」聲明。
    """
    if weights is None:
        weights = WEIGHTS

    # entity 可為 dict 或 pandas.Series；統一以 .get 取值。
    get = entity.get if hasattr(entity, "get") else (lambda k, d=None: entity[k] if k in entity else d)

    def _resolve(subkey, precomputed_key, computer):
        """取分項原始分（0–100）。

        優先取已算好的 score_*；否則以來源欄位即時計算；若來源亦缺
        （computer 回傳缺值），則代入該分項的中性值（R10.5）而不放大風險。
        """
        pre = get(precomputed_key)
        if not _is_missing(pre):
            return float(pre)
        computed = computer()
        if _is_missing(computed):
            return NEUTRAL_SUBSCORES[subkey]
        return float(computed)

    raw_scores = {
        "financial": _resolve("financial", "score_financial",
                              lambda: score_financial(entity)),
        "penalty": _resolve("penalty", "score_penalty",
                            lambda: score_penalty(get("penalty_count"))),
        "eval": _resolve("eval", "score_eval",
                         lambda: score_eval(get("eval_grade"))),
    }

    # 各分項加權貢獻；只計入 weights 有定義的分項。
    contributions = {
        k: round(weights[k] * raw_scores[k], 4)
        for k in weights if k in raw_scores
    }

    # total 直接由貢獻回推 → 保證 round(sum(contributions.values()),1) == total。
    # data_confidence 不進入此計算 → 低可信度不會單獨推高風險（R18.2）。
    total = round(sum(contributions.values()), 1)
    total = max(0.0, min(total, 100.0))

    # 責任 AI：確保聲明非空，即使呼叫端未提供亦落實 R10.4/R19.4。
    notice = NOT_ILLEGALITY_NOTICE

    return RiskBreakdown(
        total=total,
        level=risk_level_four(total),
        contributions=contributions,
        weights={k: weights[k] for k in weights if k in raw_scores},
        not_illegality_notice=notice,
        data_confidence=_confidence_value(confidence),
    )


EXTERNAL = os.path.join(ROOT, "data", "external")


def _merge_external(df):
    """併入裁罰/評鑑、地址座標等外部資料（若檔案存在）。"""
    # 裁罰與評鑑
    pen_path = os.path.join(EXTERNAL, "penalties.csv")
    if os.path.exists(pen_path):
        pen = pd.read_csv(pen_path).drop_duplicates("park_name", keep="first")
        pen_cols = ["park_name", "penalty_count", "eval_grade"]
        # 裁罰事由文字：供「事由分類 + 嚴重度」計分用（若來源含此欄）
        if "penalty_reason" in pen.columns:
            pen_cols.append("penalty_reason")
        df = df.merge(pen[pen_cols], on="park_name", how="left")
    # 座標
    geo_path = os.path.join(ROOT, "data", "processed", "geocoded.csv")
    if os.path.exists(geo_path):
        geo = pd.read_csv(geo_path).drop_duplicates("park_name", keep="first")
        geo_cols = ["park_name", "lat", "lng"]
        if "district" in geo.columns:
            geo_cols.append("district")
        df = df.merge(geo[geo_cols], on="park_name", how="left")
    return df


def build(df):
    """輸入 financials.csv，輸出完整風險評分 DataFrame。"""
    df = analyze(df)  # 先算鑑識會計指標
    df = _merge_external(df)  # 併入裁罰/評鑑/座標

    # 若沒有裁罰/評鑑/輿情欄位，先給預設
    if "penalty_count" not in df.columns:
        df["penalty_count"] = 0
    if "eval_grade" not in df.columns:
        df["eval_grade"] = ""

    # 併外部資料後，非營利園（無裁罰紀錄）penalty_count 會是 NaN。
    # 介面以 int() 顯示裁罰次數，NaN 會導致 "cannot convert float NaN to integer"。
    # 誠實預設：非營利園無裁罰資料 → 0 次；評鑑無資料 → 空字串（介面顯示 —）。
    df["penalty_count"] = df["penalty_count"].fillna(0).astype(int)
    df["eval_grade"] = df["eval_grade"].fillna("")
    # 裁罰事由文字（供分類/嚴重度）；非營利園或無裁罰者為空字串
    if "penalty_reason" not in df.columns:
        df["penalty_reason"] = ""
    df["penalty_reason"] = df["penalty_reason"].fillna("")
    # 裁罰主類別（收費/人力/安全/教保/行政），供前端與派工重點使用
    df["penalty_category"] = df.apply(
        lambda r: classify_penalty_text(r.get("penalty_reason"))["primary"] or "", axis=1)
    # 班佛樣本數：非營利園無逐筆明細 → 0（介面 int 顯示用）
    if "benford_sample_n" in df.columns:
        df["benford_sample_n"] = df["benford_sample_n"].fillna(0).astype(int)

    df["score_financial"] = df.apply(score_financial, axis=1)
    # 裁罰分改用整列（事由分類 + 嚴重度）；無事由者自動退回中性次數規則
    df["score_penalty"] = df.apply(score_penalty, axis=1)
    df["score_eval"] = df["eval_grade"].apply(score_eval)

    df["risk_total"] = (
        WEIGHTS["financial"] * df["score_financial"]
        + WEIGHTS["penalty"] * df["score_penalty"]
        + WEIGHTS["eval"] * df["score_eval"]
    ).round(1)
    # 主用百分位相對分級（確保有高風險園、符合「稽查優先序」目的）。
    # 【公平性】分機構類型各自做百分位（見 risk_level_by_group）：避免非營利園
    # 因缺班佛分項在全體混合百分位下被系統性壓低、整類被隱形。
    df["risk_level"] = risk_level_by_group(df, "risk_total", "park_type", min_group=7)
    # 同時保留絕對門檻分級供對照
    df["risk_level_abs"] = df["risk_total"].apply(risk_level_absolute)

    return df.sort_values("risk_total", ascending=False)


def attach_whitebox_columns(df):
    """對每列套用白盒 score()，附加四級絕對等級與責任 AI 聲明欄位（不改既有欄位）。

    產出三個附加欄位（附加於既有欄位之後，不破壞載入契約與三級 risk_level）：
      eng_risk_total     : 白盒總分（與既有 risk_total 一致，可對照）。
      eng_risk_level     : 四級絕對等級（低/中/高/極高，R10.2），供單機構絕對等級標示；
                           既有 risk_level（三級）續作稽查優先序排序用（R10.6），兩者並存。
      eng_not_illegality : 「風險不等於違法」責任 AI 聲明（R10.4/R19.4），非空。

    設計依據：src/risk_score.score() 與 docs specs R10.2/R10.4——三級與四級並存、各司其職。
    """
    df = df.copy()
    breakdowns = df.apply(lambda r: score(r), axis=1)
    df["eng_risk_total"] = [b.total for b in breakdowns]
    df["eng_risk_level"] = [b.level for b in breakdowns]
    df["eng_not_illegality"] = [b.not_illegality_notice for b in breakdowns]
    return df


def main():
    src = os.path.join(PROC, "financials.csv")
    df = pd.read_csv(src)
    out = build(df)
    out = attach_whitebox_columns(out)

    # 輸出契約檔（給組員）
    cols = ["park_id", "park_name", "park_type", "year",
            "district", "lat", "lng",
            "income_actual", "expense_actual", "tuition_actual", "surplus",
            "expense_income_ratio", "benford_mad", "benford_sample_n", "benford_score",
            "benford_chi2", "benford_pvalue", "benford_significant",
            "beneish_score", "beneish_egdi", "beneish_tata",
            "iforest_score", "iforest_explain",
            "expense_yoy_pct",
            "penalty_count", "penalty_reason", "penalty_category", "eval_grade",
            "score_financial", "score_penalty", "score_eval",
            "risk_total", "risk_level", "risk_level_abs",
            # 白盒 score() 附加欄位：四級絕對等級 + 責任 AI 聲明（附加於後，
            # 不破壞既有三級 risk_level 與載入契約）。
            "eng_risk_total", "eng_risk_level", "eng_not_illegality"]
    cols = [c for c in cols if c in out.columns]
    out_path = os.path.join(PROC, "kindergartens.csv")
    out[cols].to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[OK] 風險評分完成（完整多年度）已寫入 {out_path}")

    # ---------- 給組員的「最新年度快照」：每園一列，供排名表與地圖直接用 ----------
    latest = (out.sort_values("year", ascending=False)
                 .drop_duplicates("park_name", keep="first")
                 .sort_values("risk_total", ascending=False)).copy()
    # 分級在快照本身重算：稽查看的是每園最新狀態，相對排名應以「每園一列」的
    # 最新快照分布為基準（否則多年度重複列會扭曲百分位）。一樣分機構類型各自算。
    latest["risk_level"] = risk_level_by_group(latest, "risk_total", "park_type", min_group=7)
    snap_path = os.path.join(PROC, "kindergartens_latest.csv")
    latest[cols].to_csv(snap_path, index=False, encoding="utf-8-sig")
    n_geo = latest["lat"].notna().sum() if "lat" in latest.columns else 0
    print(f"[OK] 最新年度快照（每園一列，{len(latest)}間，{n_geo}間有座標）已寫入 {snap_path}")
    print()
    print(out[["park_name", "risk_total", "risk_level", "score_financial",
               "benford_mad", "expense_income_ratio"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
