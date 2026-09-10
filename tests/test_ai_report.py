"""
AI 稽查助手（Copilot）單元測試（AI_Copilot, R15/R19）
=========================================================
驗證 src/ai_report.py 強化後的行為：
  - answer(question, entity) -> CopilotAnswer：
      * 以機構資料為依據回答（R15.1）
      * 關鍵陳述附資料來源（R15.2）
      * 資料不足明確告知、不杜撰（R15.4）
      * 不作違法/舞弊斷言、不貼定性標籤（R15.3, R19.2, R19.3）
      * 附「風險不等於違法」聲明（R19.4）
  - sanitize_output：輸出後過濾（第二道關卡）中和違法/舞弊字樣。
  - build_prompt 含負向約束（R15.3, R19.2）。
  - 既有函式（build_prompt/generate_with_bedrock/generate_fallback/
    generate_report）仍存在並運作（回歸, R15.6）。

對應 Task 16.1（Requirements 15.1, 15.2, 15.3, 15.4, 15.6, 19.1, 19.2, 19.3）。
違法/舞弊斷言的屬性測試（Property 31）另見 Task 16.3。
"""
import inspect

import pytest

from src.ai_report import (
    RESPONSIBLE_AI_CONSTRAINTS,
    CopilotAnswer,
    answer,
    build_prompt,
    generate_fallback,
    generate_report,
    generate_with_bedrock,
    sanitize_output,
)


# --------------------------------------------------------------------------
# 既有函式回歸（R15.6：延伸既有 ai_report.py，不破壞既有機制）
# --------------------------------------------------------------------------
def test_existing_functions_preserved():
    """既有四個函式仍可呼叫（簽名存在）。"""
    for fn in (build_prompt, generate_with_bedrock, generate_fallback, generate_report):
        assert callable(fn)


def test_generate_report_returns_text_and_source():
    """無 AWS 金鑰時 generate_report 走 fallback，回傳 (text, 'fallback')。"""
    row = {"park_name": "示範幼兒園", "risk_total": 55.0, "risk_level": "中"}
    text, source = generate_report(row, prefer_bedrock=False)
    assert isinstance(text, str) and text.strip()
    assert source == "fallback"


def test_generate_fallback_nonempty():
    """規則式範本在最小輸入下仍產生非空建議。"""
    text = generate_fallback({"park_name": "小樹幼兒園"})
    assert isinstance(text, str) and text.strip()


# --------------------------------------------------------------------------
# 提示詞負向約束（R15.3, R19.2）
# --------------------------------------------------------------------------
def test_build_prompt_contains_negative_constraints():
    """build_prompt 內含責任 AI 負向約束段落。"""
    prompt = build_prompt({"park_name": "測試園", "risk_total": 80})
    assert RESPONSIBLE_AI_CONSTRAINTS.strip()[:6] in prompt
    assert "違法" in prompt and "舞弊" in prompt   # 明確要求禁止此類斷言


# --------------------------------------------------------------------------
# 輸出後過濾（R15.3, R19.2, R19.3）
# --------------------------------------------------------------------------
@pytest.mark.parametrize("term", [
    "違法", "舞弊", "犯罪", "詐欺", "貪污", "洗錢", "圖利",
    "fraud", "illegal", "corruption",
])
def test_sanitize_removes_illegality_terms(term):
    """任何違法/舞弊字樣經過濾後不再出現。"""
    dirty = f"該機構明顯{term}，應立即移送。"
    clean = sanitize_output(dirty)
    assert term.lower() not in clean.lower()


@pytest.mark.parametrize("label", ["不合格", "高風險機構", "問題園所", "黑心"])
def test_sanitize_removes_qualitative_labels(label):
    """定性標籤字樣經過濾後被中和（R19.3）。"""
    clean = sanitize_output(f"這是一間{label}。")
    assert label not in clean


def test_sanitize_preserves_neutral_text():
    """中性文字不含斷言字樣時內容不受影響。"""
    text = "總風險分 62 分，建議優先查核人事費與採購憑證。"
    assert sanitize_output(text) == text


def test_sanitize_none_and_empty():
    """None/空字串安全處理。"""
    assert sanitize_output("") == ""
    assert sanitize_output(None) is None


# --------------------------------------------------------------------------
# answer()：型別與資料依據（R15.1, R15.2）
# --------------------------------------------------------------------------
def _rich_entity():
    return {
        "park_name": "陽光非營利幼兒園",
        "district": "板橋區",
        "risk_total": 72.0,
        "risk_level": "高",
        "score_financial": 40.0,
        "score_penalty": 20.0,
        "penalty_count": 2,
        "expense_income_ratio": 1.15,
        "benford_mad": 0.02,
    }


def test_answer_returns_copilot_answer_type():
    """回傳型別為 CopilotAnswer。"""
    ans = answer("這間園的財務狀況如何？", _rich_entity())
    assert isinstance(ans, CopilotAnswer)


def test_answer_grounded_on_entity_data():
    """有資料時 grounded 為 True 且回答引用機構名稱與數值（R15.1）。"""
    ans = answer("這間園的財務狀況如何？", _rich_entity())
    assert ans.grounded is True
    assert ans.data_sufficient is True
    assert "陽光非營利幼兒園" in ans.text


def test_answer_attaches_sources():
    """關鍵陳述附上資料來源（R15.2）。"""
    ans = answer("財務有沒有問題？", _rich_entity())
    assert ans.sources
    # 來源說明也應體現在回答文字中（依據：...）
    assert "依據" in ans.text


def test_answer_relevant_to_question_penalty():
    """問裁罰時，回答納入裁罰相關資料。"""
    ans = answer("有沒有裁罰紀錄？", _rich_entity())
    assert "裁罰" in ans.text


# --------------------------------------------------------------------------
# answer()：資料不足告知、不杜撰（R15.4）
# --------------------------------------------------------------------------
def test_answer_insufficient_data_states_so():
    """資料不足時明確告知，且 grounded/data_sufficient 為 False（R15.4）。"""
    ans = answer("財務狀況如何？", {"park_name": "資料稀少園"})
    assert ans.grounded is False
    assert ans.data_sufficient is False
    assert "資料不足" in ans.text or "缺乏足夠資料" in ans.text
    assert ans.sources == []


def test_answer_no_fabrication_without_data():
    """無數值資料時，回答不得杜撰出具體風險數字，並明確表達不推測（R15.4）。"""
    ans = answer("風險分數多少？", {"park_name": "空資料園"})
    assert ans.data_sufficient is False
    # 明確表達資料不足/不杜撰，而非給出具體數值
    assert "缺乏足夠資料" in ans.text or "資料不足" in ans.text
    assert "為避免杜撰" in ans.text
    # 未杜撰任何具體風險分數值（純數字後接「分」的樣態不應出現）
    import re as _re
    assert _re.search(r"\d+(\.\d+)?\s*分", ans.text) is None


def test_answer_none_entity_insufficient():
    """entity 為 None 時安全回傳資料不足。"""
    ans = answer("風險如何？", None)
    assert ans.data_sufficient is False


# --------------------------------------------------------------------------
# answer()：不作違法/舞弊斷言 + 責任 AI 聲明（R15.3, R19.2, R19.4）
# --------------------------------------------------------------------------
def test_answer_never_asserts_illegality():
    """即便高風險，回答也不含違法/舞弊斷言（R15.3, R19.2）。

    合法且必要的「風險不等於違法」聲明（R19.4）除外——它是反向澄清而非斷言。
    """
    ans = answer("這間園是不是有問題？", _rich_entity())
    # 移除白名單聲明後，不得再出現任何違法/舞弊定性斷言字樣
    body = ans.text.replace("風險不等於違法", "")
    for term in ("違法", "舞弊", "犯罪", "詐欺"):
        assert term not in body


def test_answer_has_not_illegality_notice():
    """回答附「風險不等於違法」聲明（R19.4）。"""
    ans = answer("風險如何？", _rich_entity())
    assert ans.not_illegality_notice.strip()
    assert "違法" in ans.not_illegality_notice
    assert "風險不等於違法" in ans.text


def test_answer_signature():
    """answer(question, entity) 具兩個位置參數（對齊 design 簽名）。"""
    params = list(inspect.signature(answer).parameters)
    assert params[:2] == ["question", "entity"]


# --------------------------------------------------------------------------
# Task 16.2：Bedrock 不可用退化 fallback 保底（R15.5）
# 保底保證：任何 Bedrock 失敗（金鑰缺失、網路、權限、模型錯誤、空回傳）
#           皆退化為 fallback，回傳非空報告並標示來源 "fallback"。
# 對應 Property 43（Validates: Requirements 15.5）之單元範例；屬性測試見 Task 16.4。
# --------------------------------------------------------------------------
import src.ai_report as ai_report


def test_no_key_falls_back_nonempty():
    """無 AWS 金鑰時退化 fallback，回傳非空文字與來源 'fallback'（R15.5）。"""
    text, source = generate_report({"park_name": "無金鑰園"}, prefer_bedrock=True)
    assert source == "fallback"
    assert isinstance(text, str) and text.strip()


def test_bedrock_exception_falls_back(monkeypatch):
    """有金鑰但 Bedrock 呼叫拋例外時，退化 fallback、非空、標示 'fallback'（R15.5）。"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")

    def _boom(row):
        raise RuntimeError("network down")

    monkeypatch.setattr(ai_report, "generate_with_bedrock", _boom)
    text, source = generate_report({"park_name": "斷網園", "risk_total": 80.0})
    assert source == "fallback"
    assert text.strip()
    assert "已改用規則式範本" in text


@pytest.mark.parametrize("exc", [
    KeyError("content"),          # 模型回傳格式錯誤
    PermissionError("denied"),    # 權限不足
    ValueError("bad model"),      # 模型未開通
    ConnectionError("timeout"),   # 網路問題
])
def test_bedrock_various_failures_fall_back(monkeypatch, exc):
    """各類 Bedrock 失敗皆退化 fallback 並回傳非空報告（R15.5）。"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")

    def _raise(row):
        raise exc

    monkeypatch.setattr(ai_report, "generate_with_bedrock", _raise)
    text, source = generate_report({"park_name": "各類失敗園"})
    assert source == "fallback"
    assert text.strip()


def test_bedrock_empty_response_falls_back(monkeypatch):
    """Bedrock 回傳空字串視同不可用，退化 fallback（R15.5）。"""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "dummy")
    monkeypatch.setattr(ai_report, "generate_with_bedrock", lambda row: "   ")
    text, source = generate_report({"park_name": "空回傳園"})
    assert source == "fallback"
    assert text.strip()


def test_fallback_template_failure_uses_last_resort(monkeypatch):
    """即使規則式範本本身拋例外，仍以最終保底文字回傳非空報告（R15.5）。"""
    monkeypatch.setattr(ai_report, "generate_fallback",
                        lambda row: (_ for _ in ()).throw(RuntimeError("template boom")))
    text, source = generate_report({"park_name": "範本壞掉園"}, prefer_bedrock=False)
    assert source == "fallback"
    assert isinstance(text, str) and text.strip()


def test_fallback_empty_uses_last_resort(monkeypatch):
    """規則式範本回傳空字串時，改用最終保底文字（R15.5）。"""
    monkeypatch.setattr(ai_report, "generate_fallback", lambda row: "")
    text, source = generate_report({"park_name": "空範本園"}, prefer_bedrock=False)
    assert source == "fallback"
    assert text.strip()


def test_last_resort_report_is_sanitized():
    """最終保底文字本身通過責任 AI 過濾，不含違法/舞弊斷言（R15.3, R15.5）。"""
    text = ai_report._safe_fallback({"park_name": "測試"})
    for term in ("違法", "舞弊", "犯罪"):
        # 允許白名單聲明「風險不等於違法」
        assert term not in text.replace("風險不等於違法", "")
