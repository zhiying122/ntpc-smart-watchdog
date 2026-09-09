"""
AI 稽查建議報告生成（AWS Bedrock）
====================================
把單園的鑑識會計數字組成 prompt，丟給 Bedrock 的 Claude 產出白話稽查建議。
價值定位：Bedrock 不拿來算分數（算分用規則+統計，可解釋），
          而是「把數字翻譯成稽查員看得懂的話 + 給稽查建議」，降低人力負擔。

金鑰一律用 os.environ 讀取（禁止寫死）。若 Bedrock 未設定/失敗，
自動退化為「規則式範本文字」，確保 Demo 一定跑得出東西。
"""
import json
import os


def build_prompt(row):
    """把單園關鍵指標組成給 Claude 的 prompt。row 為 dict-like。"""
    def g(k, default="無資料"):
        v = row.get(k)
        return default if v is None or (isinstance(v, float) and v != v) else v

    ratio = g("expense_income_ratio")
    ratio_note = ""
    try:
        if float(ratio) > 1:
            ratio_note = f"（支出達收入 {float(ratio):.2f} 倍，入不敷出）"
    except (TypeError, ValueError):
        pass

    facts = f"""園所名稱：{g('park_name')}
所在行政區：{g('district')}
機構類型：{g('park_type')}
總風險分：{g('risk_total')}／100（風險等級：{g('risk_level')}）
分項分數：財務異常 {g('score_financial')}、裁罰 {g('score_penalty')}、評鑑 {g('score_eval')}、輿情 {g('score_sentiment')}
收支比：{ratio} {ratio_note}
班佛偏離度(MAD)：{g('benford_mad')}
Beneish 操縱分：{g('beneish_score')}
孤立森林異常分：{g('iforest_score')}
年度支出增減：{g('expense_yoy_pct')}%
裁罰次數：{g('penalty_count')} 次
評鑑等第：{g('eval_grade')}"""

    prompt = (
        "你是一位協助新北市教育局的稽查分析助理。以下是一間教保機構的風險量化指標，"
        "全部由『鑑識會計方法（班佛定律、Beneish、Isolation Forest）』與公開資料算出。\n\n"
        f"{facts}\n\n"
        "請用繁體中文，寫一段 120-200 字、給稽查員看的稽查建議，需包含：\n"
        "1) 一句話總結風險程度；\n"
        "2) 指出最該注意的 1-2 個異常訊號（用白話解釋數字代表什麼）；\n"
        "3) 具體建議優先查哪些憑證或項目（如人事費、採購、收費、財報）。\n"
        "語氣專業、客觀、不誇大，不要杜撰指標裡沒有的資訊。"
    )
    return prompt


def generate_with_bedrock(row):
    """呼叫 Bedrock Claude 產出建議。失敗會拋例外，由呼叫端決定是否 fallback。"""
    import boto3

    client = boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("BEDROCK_REGION",
                                   os.environ.get("AWS_DEFAULT_REGION", "us-east-1")),
    )
    model_id = os.environ.get("BEDROCK_MODEL_ID",
                              "anthropic.claude-3-sonnet-20240229-v1:0")
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 600,
        "temperature": 0.3,
        "messages": [{"role": "user",
                      "content": [{"type": "text", "text": build_prompt(row)}]}],
    }
    resp = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    return payload["content"][0]["text"].strip()


def generate_fallback(row):
    """
    規則式範本建議（不需 AWS）。Bedrock 未設定時的保底，確保 Demo 可跑。
    依實際指標挑選要提的訊號，讀起來仍像一段稽查建議。
    """
    def num(k, default=0.0):
        v = row.get(k)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    name = row.get("park_name", "該園")
    total = num("risk_total")
    level = row.get("risk_level", "中")
    ratio = num("expense_income_ratio")
    yoy = num("expense_yoy_pct")
    pen = int(num("penalty_count"))
    benford = num("benford_mad")
    beneish = num("beneish_score")

    signals, suggests = [], []
    if ratio > 1:
        signals.append(f"支出達收入的 {ratio:.2f} 倍、呈現入不敷出")
        suggests.append("支出憑證與採購核銷")
    if pen > 0:
        signals.append(f"已有 {pen} 次裁罰紀錄")
        suggests.append("前次裁罰改善情形")
    if abs(yoy) >= 20:
        signals.append(f"年度支出較前年變動 {yoy:.0f}%、波動偏大")
        suggests.append("人事費與大額支出明細")
    if benford >= 0.015:
        signals.append(f"財務數字首位分布偏離自然律（MAD {benford:.3f}）、有人為調整嫌疑")
        suggests.append("原始帳冊與明細分類帳")
    if beneish >= 40:
        signals.append("收支成長背離、疑似財務操縱")
        suggests.append("收入認列與應計項目")

    if not signals:
        signals.append("各項指標尚無明顯單一異常，惟綜合分數需留意")
    if not suggests:
        suggests.append("財務報表與收費作業")

    summary_level = {"高": "屬高風險，建議優先安排實地稽查",
                     "中": "屬中度風險，建議納入例行稽查追蹤",
                     "低": "風險相對偏低，維持常態管理即可"}.get(level, "建議持續觀察")

    text = (
        f"{name}總風險分 {total:.1f} 分，{summary_level}。"
        f"主要風險訊號為：{'；'.join(signals)}。"
        f"建議優先查核：{'、'.join(dict.fromkeys(suggests))}等項目，"
        "以釐清數字異常成因並確認經費使用合規性。"
    )
    return text


def generate_report(row, prefer_bedrock=True):
    """
    對外主函式。回傳 (report_text, source)。
    source: "bedrock" 表示真的用了 Bedrock；"fallback" 表示用範本。
    """
    if prefer_bedrock and os.environ.get("AWS_ACCESS_KEY_ID"):
        try:
            return generate_with_bedrock(row), "bedrock"
        except Exception as e:  # 網路/權限/模型未開通等
            return (generate_fallback(row)
                    + f"\n\n（註：AWS Bedrock 呼叫失敗，已改用規則式範本。原因：{type(e).__name__}）",
                    "fallback")
    return generate_fallback(row), "fallback"


def build_briefing(row):
    """
    稽查前情報告（結構化）。回傳 dict：
    {summary, suspicions:[...], checks:[...], documents:[...]}
    純規則式（不依賴 Bedrock），把鑑識指標翻成稽查員可直接用的行動清單。
    Bedrock 可用時，generate_report() 仍提供白話段落版；此函式提供結構化骨架，
    兩者互補：骨架保證有結構、Bedrock 補語意潤飾。
    """
    def num(k, default=0.0):
        v = row.get(k)
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    name = row.get("park_name", "該機構")
    total = num("risk_total")
    level = row.get("risk_level", "中")
    ratio = num("expense_income_ratio")
    yoy = num("expense_yoy_pct")
    pen = int(num("penalty_count"))
    benford = num("benford_mad")
    beneish = num("beneish_score")
    iforest = num("iforest_score")

    suspicions, checks, documents = [], [], []

    if ratio > 1:
        suspicions.append(f"入不敷出：支出達收入的 {ratio:.2f} 倍，長期恐影響營運與幼生權益")
        checks.append("支出憑證與採購核銷是否合規、有無異常大額支出")
        documents.append("支出明細、採購合約與核銷憑證")
    if abs(yoy) >= 20:
        suspicions.append(f"支出年增率 {yoy:.0f}%，波動偏離常態")
        checks.append("該年度支出暴增／暴減的科目與原因")
        documents.append("前後年度決算比較表")
    if benford >= 0.015:
        suspicions.append(f"財務數字首位分布偏離自然律（班佛 MAD {benford:.4f}），具人為調整嫌疑")
        checks.append("原始帳冊金額是否有湊整、重複或人為填充跡象")
        documents.append("明細分類帳與原始傳票")
    if beneish >= 40:
        suspicions.append(f"Beneish 操縱分 {beneish:.0f}，收支成長背離或應計項目異常")
        checks.append("收入認列時點與應收／應計項目合理性")
        documents.append("收入認列明細與應計項目底稿")
    if iforest >= 60:
        suspicions.append(f"多維財務特徵綜合離群（孤立森林 {iforest:.0f}）")
        checks.append("整體財務結構與同儕的顯著差異項")
        documents.append("完整決算書與財務比率分析")
    if pen > 0:
        suspicions.append(f"已有 {pen} 次裁罰紀錄，屬已知風險標的")
        checks.append("前次裁罰事項的改善與追蹤情形")
        documents.append("歷次裁罰函與改善計畫")

    if not suspicions:
        suspicions.append("各單項指標尚無明顯異常，惟綜合風險分需留意")
    if not checks:
        checks.append("財務報表與收費作業例行查核")
    if not documents:
        documents.append("最新年度決算書與收費明細")

    summary_map = {
        "高": f"{name}總風險 {total:.0f} 分，屬高風險，建議本週優先安排實地稽查。",
        "中": f"{name}總風險 {total:.0f} 分，屬中度風險，建議納入例行稽查追蹤。",
        "低": f"{name}總風險 {total:.0f} 分，風險相對偏低，維持常態管理即可。",
    }
    return {
        "summary": summary_map.get(level, f"{name}總風險 {total:.0f} 分，建議持續觀察。"),
        "suspicions": suspicions,
        "checks": list(dict.fromkeys(checks)),
        "documents": list(dict.fromkeys(documents)),
    }
