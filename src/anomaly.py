"""
異常偵測子系統（Anomaly Detector, R8）
==========================================
小小守護員 Smart Watchdog Platform — 涵蓋點、情境、集體三類異常的多方法偵測。

本模組延伸既有 `src/forensic.py` 的 Isolation Forest 與 IQR 離群邏輯（R8.6），
補齊需求 R8 所要求的完整偵測能力：

- `detect(entity, methods) -> AnomalyResult`
    對「點異常（point）／情境異常（contextual）／集體異常（collective）」
    三類各輸出一個布林旗標與一個異常分數（R8.1）。

- 提供七種偵測方法：Isolation Forest、Local Outlier Factor、Z-score、
  穩健統計（MAD / robust z）、時間序列（YoY 突變）、變化點（change point）、
  分群（clustering）。每一方法輸出「異常分數」與「由門檻導出的布林旗標」（R8.2）。

- 樣本不足時，該方法標記 `insufficient_sample` 並跳過，不中斷其餘方法（R8.5）。

設計要點（對齊 design.md「Anomaly_Detector」與 Correctness Property 25）：
    * 每個 `AnomalyMethodResult` 的不變式：`flag == (score >= threshold)`。
      唯有 `applicable=True`（樣本足夠）的方法才可能 `flag=True`；
      樣本不足（`applicable=False`）的方法 `flag` 恆為 False 且不參與命中計數。
    * 分數一律正規化至 0–100（越高越異常），使不同方法的門檻語意一致、可解釋。

責任 AI（Responsible AI）：本模組僅「發現異常並給出分數」，不判定違法或舞弊。
異常（anomaly）不等於違法（illegality）。
"""
from __future__ import annotations

import math
from typing import Any, Iterable

from src.models import (
    AnomalyMethodResult,
    AnomalyResult,
    ConsolidatedAnomaly,
    MethodNote,
)

# --------------------------------------------------------------------------
# 方法清單與預設門檻（分數 0–100，越高越異常）
# --------------------------------------------------------------------------
# 每一方法各自需要的最小樣本數（低於此值標記樣本不足並跳過，R8.5）。
_METHOD_MIN_SAMPLES: dict[str, int] = {
    "isolation_forest": 4,
    "lof": 5,
    "zscore": 3,
    "robust": 5,
    "timeseries": 2,
    "changepoint": 4,
    "clustering": 4,
}

# 每一方法的預設異常門檻（0–100）。flag == (score >= threshold)。
_METHOD_THRESHOLD: dict[str, float] = {
    "isolation_forest": 60.0,
    "lof": 60.0,
    "zscore": 60.0,
    "robust": 60.0,
    "timeseries": 60.0,
    "changepoint": 60.0,
    "clustering": 60.0,
}

# 方法對應主要偵測的異常類型（供三類旗標整合與適用性說明 R8.3）。
_METHOD_ANOMALY_TYPE: dict[str, str] = {
    "isolation_forest": "collective",  # 多維整體離群
    "lof": "point",                    # 局部密度點離群
    "zscore": "point",                 # 單點偏離
    "robust": "point",                 # 抗離群單點偏離
    "timeseries": "contextual",        # 相對自身歷史脈絡
    "changepoint": "contextual",       # 序列中的脈絡轉折
    "clustering": "collective",        # 群體結構離群
}

# 方法適用性說明（R8.3）：適用異常類型、資料前提、已知限制。
_METHOD_NOTES: dict[str, dict[str, str]] = {
    "isolation_forest": {
        "anomaly_type": "collective",
        "assumption": "多維數值特徵、樣本數 >= 4",
        "limitation": "小樣本或高度相關特徵時分數不穩定",
    },
    "lof": {
        "anomaly_type": "point",
        "assumption": "數值特徵具局部密度結構、樣本數 >= 5",
        "limitation": "對鄰居數 k 敏感，極小樣本不可靠",
    },
    "zscore": {
        "anomaly_type": "point",
        "assumption": "資料近似常態、標準差 > 0、樣本數 >= 3",
        "limitation": "受極端值影響大，非常態分布易誤判",
    },
    "robust": {
        "anomaly_type": "point",
        "assumption": "以中位數與 MAD 抗離群、樣本數 >= 5",
        "limitation": "MAD 為 0（過半數值相同）時退化",
    },
    "timeseries": {
        "anomaly_type": "contextual",
        "assumption": "同一機構跨年度序列、至少 2 個年度",
        "limitation": "序列過短無法辨識趨勢脈絡",
    },
    "changepoint": {
        "anomaly_type": "contextual",
        "assumption": "有序時間序列、樣本數 >= 4",
        "limitation": "僅偵測均值位移，漸變趨勢敏感度低",
    },
    "clustering": {
        "anomaly_type": "collective",
        "assumption": "可分群的多維特徵、樣本數 >= 4",
        "limitation": "群數與尺度選擇影響結果",
    },
}

ALL_METHODS: tuple[str, ...] = (
    "isolation_forest",
    "lof",
    "zscore",
    "robust",
    "timeseries",
    "changepoint",
    "clustering",
)


# --------------------------------------------------------------------------
# 輸入正規化：把 entity 轉為「目標值 / 同儕母體 / 時間序列」
# --------------------------------------------------------------------------
def _clean_numbers(values: Iterable[Any]) -> list[float]:
    """過濾出有限數值（排除 None / NaN / inf）。"""
    out: list[float] = []
    for v in values:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isnan(f) or math.isinf(f):
            continue
        out.append(f)
    return out


def _extract_context(entity: Any) -> dict[str, Any]:
    """從多形態 entity 擷取偵測所需的欄位。

    支援兩種輸入形態，使呼叫端可彈性提供資料：
      1. dict：可含鍵 'value'（目標純量）、'population'（同儕母體序列）、
         'series'（同一機構的時間序列）、'features'（目標多維特徵）、
         'feature_matrix'（母體多維特徵矩陣）。
      2. 具上述同名屬性的物件。
    缺漏欄位以合理預設回填（空序列 / None），不拋例外。
    """
    def _get(key: str, default: Any = None) -> Any:
        if isinstance(entity, dict):
            return entity.get(key, default)
        return getattr(entity, key, default)

    value = _get("value", None)
    population = _clean_numbers(_get("population", []) or [])
    series = _clean_numbers(_get("series", []) or [])
    features = _get("features", None)
    feature_matrix = _get("feature_matrix", None)

    # 若未提供 value 但有 series，取序列最後一個值作為目標（最新年度）。
    if value is None and series:
        value = series[-1]

    return {
        "value": value,
        "population": population,
        "series": series,
        "features": features,
        "feature_matrix": feature_matrix,
    }


def _normalize_score(x: float) -> float:
    """把任意實數壓到 0–100（保底），並保留 1 位小數。"""
    if math.isnan(x) or math.isinf(x):
        return 0.0
    return round(max(0.0, min(100.0, x)), 1)


def _insufficient(method: str) -> AnomalyMethodResult:
    """建立「樣本不足」結果：applicable=False、flag=False、分數 0（R8.5）。"""
    note = dict(_METHOD_NOTES.get(method, {}))
    note["skipped"] = "insufficient_sample"
    return AnomalyMethodResult(
        method=method,
        score=0.0,
        flag=False,
        threshold=_METHOD_THRESHOLD.get(method, 60.0),
        applicable=False,
        note=note,
    )


def _make_result(method: str, score: float) -> AnomalyMethodResult:
    """由分數建立結果，落實不變式 flag == (score >= threshold)（Property 25）。"""
    threshold = _METHOD_THRESHOLD.get(method, 60.0)
    s = _normalize_score(score)
    return AnomalyMethodResult(
        method=method,
        score=s,
        flag=s >= threshold,
        threshold=threshold,
        applicable=True,
        note=dict(_METHOD_NOTES.get(method, {})),
    )


# --------------------------------------------------------------------------
# 個別偵測方法（每個回傳 AnomalyMethodResult）
# --------------------------------------------------------------------------
def _method_zscore(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """Z-score 點異常：|z| 越大越異常。分數 = min(|z| / 3 * 60, 100)。"""
    pop = ctx["population"]
    value = ctx["value"]
    if value is None or len(pop) < _METHOD_MIN_SAMPLES["zscore"]:
        return _insufficient("zscore")
    mean = sum(pop) / len(pop)
    var = sum((p - mean) ** 2 for p in pop) / len(pop)
    std = math.sqrt(var)
    if std == 0:
        # 無變異：目標等於母體常數則不異常，否則視為明確離群。
        score = 0.0 if float(value) == mean else 100.0
        return _make_result("zscore", score)
    z = abs((float(value) - mean) / std)
    # z=3（約 99.7 百分位）對映到門檻 60，超過即 flag。
    return _make_result("zscore", z / 3.0 * 60.0)


def _method_robust(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """穩健統計點異常：以中位數與 MAD 計算 robust z（抗離群）。"""
    pop = ctx["population"]
    value = ctx["value"]
    if value is None or len(pop) < _METHOD_MIN_SAMPLES["robust"]:
        return _insufficient("robust")
    s = sorted(pop)
    median = _median(s)
    abs_dev = sorted(abs(p - median) for p in pop)
    mad = _median(abs_dev)
    if mad == 0:
        score = 0.0 if float(value) == median else 100.0
        return _make_result("robust", score)
    # 0.6745 使 MAD 在常態下等價於標準差。
    robust_z = abs(0.6745 * (float(value) - median) / mad)
    return _make_result("robust", robust_z / 3.0 * 60.0)


def _method_timeseries(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """時間序列情境異常：以最新一期 YoY 變動幅度衡量脈絡突變。"""
    series = ctx["series"]
    if len(series) < _METHOD_MIN_SAMPLES["timeseries"]:
        return _insufficient("timeseries")
    prev, curr = series[-2], series[-1]
    if prev == 0:
        # 分母為 0：由 0 變為非 0 視為明顯突變，維持 0 則無變動。
        score = 100.0 if curr != 0 else 0.0
        return _make_result("timeseries", score)
    yoy = abs((curr - prev) / abs(prev))
    # YoY 30% 對映門檻 60（對齊 forensic 突變門檻精神）。
    return _make_result("timeseries", yoy / 0.30 * 60.0)


def _method_changepoint(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """變化點情境異常：偵測序列中最大均值位移（CUSUM 式簡化）。"""
    series = ctx["series"]
    if len(series) < _METHOD_MIN_SAMPLES["changepoint"]:
        return _insufficient("changepoint")
    n = len(series)
    overall_mean = sum(series) / n
    spread = max(series) - min(series)
    if spread == 0:
        return _make_result("changepoint", 0.0)
    # 掃描每個切點，計算前後段均值差的最大值（相對全距正規化）。
    best_shift = 0.0
    for k in range(1, n):
        left = series[:k]
        right = series[k:]
        lm = sum(left) / len(left)
        rm = sum(right) / len(right)
        best_shift = max(best_shift, abs(rm - lm))
    ratio = best_shift / spread  # 0..1
    return _make_result("changepoint", ratio * 100.0)


def _method_isolation_forest(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """Isolation Forest 集體異常（延伸既有 forensic 實作，R8.6）。

    以母體多維特徵矩陣訓練，取目標樣本的異常分數（0–100）。
    無 feature_matrix 時退化為以一維同儕母體建構特徵矩陣。
    """
    matrix, target_idx = _resolve_feature_matrix(ctx)
    if matrix is None or len(matrix) < _METHOD_MIN_SAMPLES["isolation_forest"]:
        return _insufficient("isolation_forest")
    try:
        import numpy as np
        from sklearn.ensemble import IsolationForest

        X = np.asarray(matrix, dtype=float)
        model = IsolationForest(
            n_estimators=100, contamination="auto", random_state=42
        )
        model.fit(X)
        raw = -model.decision_function(X)  # 越大越異常
        rng = raw.max() - raw.min()
        norm = (raw - raw.min()) / (rng + 1e-9) * 100.0
        score = float(norm[target_idx])
        return _make_result("isolation_forest", score)
    except Exception:
        return _insufficient("isolation_forest")


def _method_lof(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """Local Outlier Factor 點異常：以局部密度衡量目標離群程度。"""
    matrix, target_idx = _resolve_feature_matrix(ctx)
    if matrix is None or len(matrix) < _METHOD_MIN_SAMPLES["lof"]:
        return _insufficient("lof")
    try:
        import numpy as np
        from sklearn.neighbors import LocalOutlierFactor

        X = np.asarray(matrix, dtype=float)
        n_neighbors = min(20, len(X) - 1)
        lof = LocalOutlierFactor(n_neighbors=n_neighbors)
        lof.fit_predict(X)
        # negative_outlier_factor_ 越小（越負）越異常。
        raw = -lof.negative_outlier_factor_
        rng = raw.max() - raw.min()
        norm = (raw - raw.min()) / (rng + 1e-9) * 100.0
        score = float(norm[target_idx])
        return _make_result("lof", score)
    except Exception:
        return _insufficient("lof")


def _method_clustering(ctx: dict[str, Any]) -> AnomalyMethodResult:
    """分群集體異常：以目標點與最近群中心距離衡量結構離群。"""
    matrix, target_idx = _resolve_feature_matrix(ctx)
    if matrix is None or len(matrix) < _METHOD_MIN_SAMPLES["clustering"]:
        return _insufficient("clustering")
    try:
        import numpy as np
        from sklearn.cluster import KMeans

        X = np.asarray(matrix, dtype=float)
        k = min(3, len(X))
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        labels = km.fit_predict(X)
        centers = km.cluster_centers_
        dists = np.linalg.norm(X - centers[labels], axis=1)
        rng = dists.max() - dists.min()
        norm = (dists - dists.min()) / (rng + 1e-9) * 100.0
        score = float(norm[target_idx])
        return _make_result("clustering", score)
    except Exception:
        return _insufficient("clustering")


_METHOD_FUNCS = {
    "isolation_forest": _method_isolation_forest,
    "lof": _method_lof,
    "zscore": _method_zscore,
    "robust": _method_robust,
    "timeseries": _method_timeseries,
    "changepoint": _method_changepoint,
    "clustering": _method_clustering,
}


# --------------------------------------------------------------------------
# 輔助
# --------------------------------------------------------------------------
def _median(sorted_or_seq: list[float]) -> float:
    """中位數（接受已排序或未排序序列）。"""
    s = sorted(sorted_or_seq)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _resolve_feature_matrix(ctx: dict[str, Any]):
    """解析多維特徵矩陣與目標列索引。

    優先使用 ctx['feature_matrix'] + ctx['features']；
    否則以一維同儕母體 + 目標值退化建構（把純量當單一特徵）。
    回傳 (matrix, target_idx)；無法建構時回傳 (None, -1)。
    """
    matrix = ctx.get("feature_matrix")
    features = ctx.get("features")
    if matrix:
        rows = [list(map(float, r)) for r in matrix]
        if features is not None:
            rows = rows + [list(map(float, features))]
            return rows, len(rows) - 1
        # 無明確目標特徵：以第一列為目標（呼叫端已將目標納入矩陣）。
        return rows, 0

    # 退化：一維母體 + 目標值。
    pop = ctx["population"]
    value = ctx["value"]
    if value is None or not pop:
        return None, -1
    rows = [[p] for p in pop] + [[float(value)]]
    return rows, len(rows) - 1


# --------------------------------------------------------------------------
# 三類異常整合
# --------------------------------------------------------------------------
def _aggregate_type(results: list[AnomalyMethodResult], anomaly_type: str
                    ) -> tuple[bool, float]:
    """整合某一異常類型的 (flag, score)。

    取該類型下所有「適用」方法的最高分為代表分數；
    只要有任一適用方法 flag=True 即該類型 flag=True（R8.1）。
    無任何適用方法時回傳 (False, 0.0)。
    """
    relevant = [
        r for r in results
        if r.applicable and _METHOD_ANOMALY_TYPE.get(r.method) == anomaly_type
    ]
    if not relevant:
        return (False, 0.0)
    score = max(r.score for r in relevant)
    flag = any(r.flag for r in relevant)
    return (flag, round(score, 1))


# --------------------------------------------------------------------------
# 對外主函式
# --------------------------------------------------------------------------
def detect(entity: Any, methods: list[str] | None = None) -> AnomalyResult:
    """對單一機構執行多方法異常偵測並整合為三類異常結果（R8.1, R8.2, R8.5）。

    參數
        entity：dict 或物件，提供偵測所需欄位（見 `_extract_context`）。
        methods：欲執行的方法名稱清單；預設為全部方法（ALL_METHODS）。
                 未知方法名稱會被忽略。

    回傳
        AnomalyResult：
          - point / contextual / collective 各為 (bool flag, float score)（R8.1）。
          - methods：每一方法的 AnomalyMethodResult（含樣本不足標記，R8.5）。
          - method_hit_count：flag=True 的適用方法數。
          - confidence_label：>=2 命中 → 'high_confidence'；否則 'to_confirm'。
            （完整一致性整合語意於 task 3.2 `consolidate` 中另行處理，
             此處提供與 method_hit_count 一致的即時標示。）
    """
    if methods is None:
        methods = list(ALL_METHODS)

    ctx = _extract_context(entity)

    method_results: list[AnomalyMethodResult] = []
    for m in methods:
        func = _METHOD_FUNCS.get(m)
        if func is None:
            continue  # 忽略未知方法名稱
        try:
            method_results.append(func(ctx))
        except Exception:
            # 任一方法內部失敗不得中斷其餘方法（R8.5 精神）。
            method_results.append(_insufficient(m))

    point = _aggregate_type(method_results, "point")
    contextual = _aggregate_type(method_results, "contextual")
    collective = _aggregate_type(method_results, "collective")

    hit_count = sum(1 for r in method_results if r.applicable and r.flag)
    confidence_label = "high_confidence" if hit_count >= 2 else "to_confirm"

    return AnomalyResult(
        point=point,
        contextual=contextual,
        collective=collective,
        methods=method_results,
        confidence_label=confidence_label,
        method_hit_count=hit_count,
    )


# --------------------------------------------------------------------------
# 方法適用性說明與一致性整合（R8.3, R8.4）
# --------------------------------------------------------------------------
def method_applicability(method: str) -> MethodNote:
    """回傳某一偵測方法的適用性說明（R8.3）。

    內容至少涵蓋：適用的異常類型、資料前提（假設）與已知限制，
    資料來源為模組內既有的 `_METHOD_NOTES` 設定表，確保與 `detect()`
    產出的 `AnomalyMethodResult.note` 一致。

    參數
        method：方法名稱（須為 ALL_METHODS 之一）。

    回傳
        MethodNote：method / anomaly_type / assumption / limitation。

    例外
        ValueError：未知方法名稱（不在 ALL_METHODS 內）。
    """
    note = _METHOD_NOTES.get(method)
    if note is None:
        raise ValueError(f"未知的偵測方法：{method!r}")
    return MethodNote(
        method=method,
        anomaly_type=note.get("anomaly_type", _METHOD_ANOMALY_TYPE.get(method, "")),
        assumption=note.get("assumption", ""),
        limitation=note.get("limitation", ""),
    )


def consolidate(results: list[AnomalyMethodResult]) -> ConsolidatedAnomaly:
    """整合多方法結果為一致性判定（R8.4）。

    命中（hit）定義為「該方法適用（applicable=True）且 flag=True」。
    樣本不足（applicable=False）之方法不計入命中，符合 R8.5 的跳過語意。

      - 命中方法數 >= 2 → 'high_confidence'（高可信度異常）並記錄命中數。
      - 命中方法數 == 1 → 'to_confirm'（待確認異常）。
      - 命中方法數 == 0 → 'none'（無方法判為異常）。

    參數
        results：各方法的 AnomalyMethodResult 清單（通常取自 AnomalyResult.methods）。

    回傳
        ConsolidatedAnomaly：confidence_label / hit_count / hit_methods。
    """
    hit_methods = [r.method for r in results if r.applicable and r.flag]
    hit_count = len(hit_methods)
    if hit_count >= 2:
        label = "high_confidence"
    elif hit_count == 1:
        label = "to_confirm"
    else:
        label = "none"
    return ConsolidatedAnomaly(
        confidence_label=label,
        hit_count=hit_count,
        hit_methods=hit_methods,
    )
