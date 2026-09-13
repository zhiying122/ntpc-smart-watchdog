"""
舞弊三角理論框架（Fraud Triangle, Cressey 1953）
================================================
文獻依據：Cressey, D. R. (1953) *Other People's Money: A Study in the Social
Psychology of Embezzlement*. Free Press. 三構面：Pressure（壓力/動機）、
Opportunity（機會）、Rationalization（合理化）。並經 AICPA SAS No. 99 (2002)
納入審計準則，屬鑑識會計/查核實務標準框架。

【設計原則：白盒子、不黑箱】
本模組「不」訓練新模型、「不」引入新的隱藏權重。它是一個結構化「對映層」：
把風險引擎已算好、且皆可解釋的分項（Altman 困境、班佛/Beneish、勾稽、評鑑、
裁罰破窗、輿情）翻譯成稽查員熟悉的三構面語言，並判定「三角成形程度」以引導
查核優先與方向。所有輸入皆為既有欄位，故可完整回溯、與白盒總分不衝突。

【構面對映邏輯（可對評審逐項說明）】
- Pressure 壓力＝財務困境與收支壓力：
    Altman Z'' 困境分（altman_score）為主，佐以收支比與賸餘短絀。
    學理：財務困境是 Cressey「不可共享的財務壓力」在機構層次的對應。
- Opportunity 機會＝內控/治理弱點與帳務異常空間：
    評鑑缺失（治理/內控弱）、班佛/Beneish/基金勾稽異常（數字有動手腳的空間）。
    學理：內控薄弱＝有機可乘。
- Rationalization 合理化＝重複違規未改善之行為型態與外部negative signal：
    裁罰（破窗效應，重複/近期/未改善）為主，佐以負面輿情。
    學理：重複違規而未矯正，反映將違規「正當化」的行為傾向（可觀察代理）。
"""
from __future__ import annotations

import pandas as pd

from src.models import FraudTriangleFactor, FraudTriangleResult

# 構面存在門檻：分數達此值視為該構面「成形」（0–100）。取 50 為中性偏高門檻，
# 避免輕微訊號即判定三角成形（降低假陽性，符合責任 AI）。
VERTEX_THRESHOLD = 50.0


def _z(v) -> float:
    """缺值/NaN 安全轉 0（中性），避免污染彙整分數。"""
    if v is None:
        return 0.0
    try:
        if pd.isna(v):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _ratio_pressure_pts(ratio) -> float:
    """收支比 > 1（入不敷出）換算壓力點：超支 20% 即滿分（與 score_financial 同語意）。"""
    r = _z(ratio)
    if r > 1:
        return min((r - 1) * 500, 100.0)
    return 0.0


def _deficit_pts(surplus, income) -> float:
    """賸餘短絀率換算壓力點：短絀達收入 10% 即滿分（與 score_financial 同語意）。"""
    s = _z(surplus)
    inc = _z(income)
    if inc and s < 0:
        return min(abs(s) / inc * 1000, 100.0)
    return 0.0


def assess(entity) -> FraudTriangleResult:
    """對單一機構（dict 或 pandas.Series）產出舞弊三角評估。

    僅讀取既有已算欄位，皆為可解釋來源：
      altman_score, expense_income_ratio, surplus, income_actual,
      score_eval, benford_score, beneish_score, fund_recon_score,
      fund_continuity_score, score_penalty, score_sentiment。
    缺值一律以中性 0 處理，不放大風險（責任 AI）。
    """
    # 統一以 .get 取值：dict / pandas.Series 走原生 .get；其餘物件退回
    # getattr（讀屬性），確保 docstring 宣稱的「dict 或 Series 或屬性物件」
    # 皆能正確取值，而非靜默回預設致三構面全歸零。
    get = entity.get if hasattr(entity, "get") else (
        lambda k, d=None: getattr(entity, k, d))

    # ---------- Pressure 壓力：財務困境為主 ----------
    altman = _z(get("altman_score"))
    ratio_pts = _ratio_pressure_pts(get("expense_income_ratio"))
    deficit_pts = _deficit_pts(get("surplus"), get("income_actual"))
    # Altman 為主（0.6），收支比與短絀各佐（0.2/0.2）。
    pressure_score = round(0.6 * altman + 0.2 * ratio_pts + 0.2 * deficit_pts, 1)
    pressure_signals = []
    if altman >= 50:
        pressure_signals.append("Altman Z'' 顯示財務困境（營運結餘/基金厚度偏弱）")
    if ratio_pts >= 50:
        pressure_signals.append("收支比 > 1，入不敷出")
    if deficit_pts >= 50:
        pressure_signals.append("本期短絀顯著，基金遭侵蝕")
    if not pressure_signals:
        pressure_signals.append("財務壓力訊號不明顯")

    # ---------- Opportunity 機會：內控/治理弱點與帳務異常空間 ----------
    eval_pts = _z(get("score_eval"))
    benford = _z(get("benford_score"))
    beneish = _z(get("beneish_score"))
    recon = max(_z(get("fund_recon_score")), _z(get("fund_continuity_score")))
    # 評鑑缺失（治理）0.4；帳務異常空間（班佛/Beneish/勾稽取最大）0.6。
    account_anomaly = max(benford, beneish, recon)
    opportunity_score = round(0.4 * eval_pts + 0.6 * account_anomaly, 1)
    opportunity_signals = []
    if eval_pts >= 50:
        opportunity_signals.append("評鑑結果偏低，內控/治理可能薄弱")
    if benford >= 50:
        opportunity_signals.append("班佛定律偏離，數字分佈異常")
    if beneish >= 50:
        opportunity_signals.append("Beneish 收支背離，疑似操縱空間")
    if recon >= 50:
        opportunity_signals.append("基金餘額勾稽不一致，帳務內部矛盾")
    if not opportunity_signals:
        opportunity_signals.append("內控/帳務機會訊號不明顯")

    # ---------- Rationalization 合理化：重複違規行為型態 + 負面輿情 ----------
    penalty = _z(get("score_penalty"))
    sentiment = _z(get("score_sentiment"))
    # 裁罰（破窗：重複/近期/未改善）為主 0.7；負面輿情佐 0.3。
    rationalization_score = round(0.7 * penalty + 0.3 * sentiment, 1)
    rationalization_signals = []
    if penalty >= 50:
        rationalization_signals.append("裁罰紀錄顯示重複/近期違規（破窗效應）")
    if sentiment >= 50:
        rationalization_signals.append("負面輿情比例偏高")
    if not rationalization_signals:
        rationalization_signals.append("重複違規/負面訊號不明顯")

    pressure = FraudTriangleFactor(
        construct="pressure",
        score=pressure_score,
        present=pressure_score >= VERTEX_THRESHOLD,
        signals=pressure_signals,
    )
    opportunity = FraudTriangleFactor(
        construct="opportunity",
        score=opportunity_score,
        present=opportunity_score >= VERTEX_THRESHOLD,
        signals=opportunity_signals,
    )
    rationalization = FraudTriangleFactor(
        construct="rationalization",
        score=rationalization_score,
        present=rationalization_score >= VERTEX_THRESHOLD,
        signals=rationalization_signals,
    )

    vertices = sum(f.present for f in (pressure, opportunity, rationalization))
    completeness = {3: "complete", 2: "partial", 1: "weak", 0: "none"}[vertices]

    present_names = [
        name for f, name in (
            (pressure, "壓力"), (opportunity, "機會"), (rationalization, "合理化"))
        if f.present
    ]
    if vertices == 3:
        narrative = "舞弊三角完整成形（壓力＋機會＋合理化皆具備），建議列為優先深度查核對象。"
    elif vertices == 2:
        narrative = f"舞弊三角部分成形（{ '＋'.join(present_names) }），建議補查缺口構面以確認風險。"
    elif vertices == 1:
        narrative = f"僅單一構面（{present_names[0]}）達門檻，建議持續監測、暫不列優先。"
    else:
        narrative = "三構面訊號皆不明顯，暫無舞弊三角成形跡象。"

    return FraudTriangleResult(
        pressure=pressure,
        opportunity=opportunity,
        rationalization=rationalization,
        vertices_present=vertices,
        completeness=completeness,
        narrative=narrative,
    )
