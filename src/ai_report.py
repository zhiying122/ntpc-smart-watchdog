"""
AI 稽查建議報告生成（AWS Bedrock）
====================================
把單園的鑑識會計數字組成 prompt，丟給 Bedrock 的 Claude 產出白話稽查建議。
價值定位：Bedrock 不拿來算分數（算分用規則+統計，可解釋），
          而是「把數字翻譯成稽查員看得懂的話 + 給稽查建議」，降低人力負擔。

金鑰一律用 os.environ 讀取（禁止寫死）。若 Bedrock 未設定/失敗，
自動退化為「規則式範本文字」，確保 Demo 一定跑得出東西。

責任 AI（Responsible AI）：系統輸出僅限「發現異常、排序、解釋、提供證據、
建議稽查方向」五類（R19.1）。AI 稽查助手（Copilot）以機構資料為依據回答
（R15.1），關鍵陳述附來源（R15.2），資料不足明確告知不杜撰（R15.4），
且絕不宣稱任何機構違法/舞弊/犯罪（R15.3, R19.2）——此約束同時透過
提示詞負向約束與「輸出後過濾」兩道關卡落實（Property 31）。
"""
import json
import os
import re
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# 責任 AI 型別與負向約束（Responsible AI, R15/R19）
# --------------------------------------------------------------------------

# EntityData：Copilot 回答所依據的機構資料。沿用本模組既有 dict-like 慣例
# （見 build_prompt/generate_fallback 的 row），型別上接受任意 Mapping。
# 為維持既有基線可攜性，不強制引入額外 dataclass。
EntityData = dict


@dataclass
class CopilotAnswer:
    """AI 稽查助手（Copilot）對單一問題的回答（R15）。

    - text：面向稽查員的回答文字，已通過負向約束過濾（R15.3, R19.2）。
    - sources：關鍵陳述所依據的資料來源（R15.2）；資料不足時可為空。
    - grounded：True 表示回答建立在該機構的實際資料上（R15.1）；
      False 表示資料不足、已明確告知而未杜撰（R15.4）。
    - data_sufficient：是否有足夠資料回答此問題（R15.4）。
    - not_illegality_notice：非空「風險不等於違法」聲明（R19.4）。

    Validates: Requirements 15.1, 15.2, 15.3, 15.4, 19.1, 19.2
    """
    text: str
    sources: list = field(default_factory=list)
    grounded: bool = False
    data_sufficient: bool = False
    not_illegality_notice: str = "風險不等於違法（Risk does not equal illegality）。"


# 提示詞負向約束（第一道關卡）：附加於送往 Bedrock 的 prompt。
RESPONSIBLE_AI_CONSTRAINTS = (
    "【責任 AI 約束（務必遵守）】\n"
    "1. 你只能做以下五件事：發現異常、排序、解釋、提供證據、建議稽查方向。\n"
    "2. 嚴禁宣稱或暗示任何機構『違法、舞弊、犯罪、詐欺、貪污、洗錢、圖利』。"
    "風險分數僅代表『需優先查核的可能性』，不等於違法事實。\n"
    "3. 不得僅以單一訊號為機構貼上定性標籤；請以『需進一步查核』等中性措辭表述。\n"
    "4. 只能引用下方提供的資料；資料不足時必須明確說『資料不足，無法回答』，"
    "絕不可杜撰數字或來源。\n"
    "5. 關鍵陳述請標明其資料依據（來源／指標名稱）。\n"
)

# 輸出後過濾（第二道關卡）：即使模型或範本不慎產出斷言字樣，也一律中和，
# 確保 Property 31（不作違法／舞弊宣稱）在 Bedrock 與 fallback 兩條路徑皆成立。
# 涵蓋定性斷言用語；替換為中性的『需進一步查核』語意。
_ILLEGALITY_TERMS = [
    "違法", "舞弊", "犯罪", "詐欺", "詐騙", "貪污", "貪汙", "洗錢",
    "圖利", "掏空", "作假帳", "做假帳", "違規事實", "不法",
    "illegal", "fraud", "fraudulent", "crime", "criminal",
    "embezzle", "embezzlement", "corruption", "money laundering",
]
# 定性標籤（避免僅以單一訊號貼標籤，R19.3）：不將機構直接標為高風險/不合格。
_LABEL_TERMS = ["不合格", "高風險機構", "問題園所", "黑心"]

_SANITIZE_REPLACEMENT = "需進一步查核之疑慮"

# 責任 AI 聲明（R19.4）：合法且必要的「風險不等於違法」用語，過濾時須白名單保留。
_NOT_ILLEGALITY_NOTICE = "風險不等於違法"


def _num(row, key):
    """從 row 取數值；缺值/NaN/非數值回傳 None。"""
    v = row.get(key)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN → None


def _fund_recon_fact(row):
    """產生「基金餘額勾稽」的誠實敘述（供 prompt facts）。

    - 有不一致（同期或跨年度分 > 0）→ 明確標示紅旗與偏離金額。
    - 一致（consistent 為 True 且兩分皆 0）→ 陳述通過會計恆等式勾稽（資料品質背書）。
    - 無基金資料（多為非營利園，未抽期初/期末餘額）→ 誠實說明缺資料、不計分。

    「勾稽」為台灣會計/審計用語：把應相符的數字互相核對、確認一致。
    """
    consistent = row.get("fund_recon_consistent")
    recon = _num(row, "fund_recon_score") or 0.0
    continuity = _num(row, "fund_continuity_score") or 0.0
    begin = _num(row, "fund_balance_begin")
    end = _num(row, "fund_balance_end")

    # 無任何基金資料 → 缺資料（誠實，不放大風險）。
    if begin is None and end is None and consistent is None:
        return "無基金餘額資料（此機構未提供期初／期末基金餘額，故不納入勾稽）"

    parts = []
    if recon > 0:
        diff = _num(row, "fund_recon_diff")
        diff_txt = f"，帳列期末與推算差 {diff:,.0f} 元" if diff is not None else ""
        parts.append(f"同期勾稽不一致（期末≠期初+本期賸餘{diff_txt}），需人工複核")
    if continuity > 0:
        cdiff = _num(row, "fund_continuity_diff")
        cdiff_txt = f"，差 {cdiff:,.0f} 元" if cdiff is not None else ""
        parts.append(f"跨年度連續性斷裂（本年期初≠上年期末{cdiff_txt}），需人工複核")
    if parts:
        return "；".join(parts)
    # 一致（含 consistent=True 或兩分皆 0）。
    return "通過會計恆等式勾稽（期末=期初+本期賸餘），且跨年度銜接一致，帳務內部一致"


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
基金餘額勾稽：{_fund_recon_fact(row)}
裁罰次數：{g('penalty_count')} 次
評鑑等第：{g('eval_grade')}"""

    prompt = (
        "你是一位協助新北市教育局的稽查分析助理。以下是一間教保機構的風險量化指標，"
        "全部由『鑑識會計方法（班佛定律、Beneish、Isolation Forest）』與公開資料算出。\n\n"
        f"{RESPONSIBLE_AI_CONSTRAINTS}\n"
        f"{facts}\n\n"
        "請用繁體中文，寫一段 120-200 字、給稽查員看的稽查建議，需包含：\n"
        "1) 一句話總結風險程度；\n"
        "2) 指出最該注意的 1-2 個異常訊號（用白話解釋數字代表什麼）；\n"
        "3) 具體建議優先查哪些憑證或項目（如人事費、採購、收費、財報）。\n"
        "語氣專業、客觀、不誇大，不要杜撰指標裡沒有的資訊。"
    )
    return prompt


def sanitize_output(text):
    """輸出後過濾（第二道關卡）：中和任何違法/舞弊斷言與定性標籤字樣。

    無論文字來自 Bedrock 或規則式範本，皆套用此過濾，確保系統輸出不將機構
    斷言為違法/舞弊/犯罪，亦不直接標為不合格/高風險機構（R15.3, R19.2, R19.3）。
    回傳過濾後文字（不改變其餘語意）。
    """
    if not text:
        return text
    cleaned = text
    # 白名單：合法且必要的責任 AI 聲明本身含「違法」二字（R19.4），
    # 必須保留不被過濾。先以佔位符保護，過濾完再還原。
    placeholder = "\x00NOTICE\x00"
    cleaned = cleaned.replace(_NOT_ILLEGALITY_NOTICE, placeholder)
    # 違法/舞弊/犯罪等定性斷言 → 中性措辭
    for term in _ILLEGALITY_TERMS:
        cleaned = re.sub(re.escape(term), _SANITIZE_REPLACEMENT,
                         cleaned, flags=re.IGNORECASE)
    # 定性標籤 → 中性措辭
    for term in _LABEL_TERMS:
        cleaned = re.sub(re.escape(term), "需優先關注", cleaned)
    cleaned = cleaned.replace(placeholder, _NOT_ILLEGALITY_NOTICE)
    return cleaned


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
    # 輸出後過濾（第二道關卡）：確保 Bedrock 路徑也不含違法/舞弊斷言（R15.3, R19.2）。
    return sanitize_output(payload["content"][0]["text"].strip())


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

    # 基金餘額勾稽：只在「不一致」時列為風險訊號（一致不提，避免對帳務健全園誤報）。
    recon = num("fund_recon_score")
    continuity = num("fund_continuity_score")
    if recon > 0:
        signals.append("基金餘額同期勾稽不一致（期末≠期初＋本期賸餘）")
        suggests.append("基金餘額帳務與決算數字勾稽")
    if continuity > 0:
        signals.append("基金餘額跨年度銜接不上（本年期初≠上年期末）")
        suggests.append("跨年度基金餘額連續性")

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
    # 輸出後過濾（第二道關卡）：規則式範本路徑同樣不得含違法/舞弊斷言（R15.3, R19.2）。
    return sanitize_output(text)


# 最終保底文字（Last-resort）：即使規則式範本本身也拋例外/回空，
# 仍確保 generate_report 回傳非空報告，維持可 Demo（R15.5, Property 43）。
_LAST_RESORT_REPORT = (
    "目前無法取得完整分析資料，系統暫以保底訊息回覆：建議稽查員就該機構之"
    "財務報表、裁罰紀錄、評鑑結果與收費作業進行例行查核，以釐清潛在疑慮。"
    "風險分數僅供稽查排序參考，風險不等於違法。"
)


def _safe_fallback(row):
    """呼叫規則式範本並確保回傳非空字串；範本本身失敗時退回最終保底文字。

    此為 R15.5／Property 43 的核心保底：無論 row 型別或內容為何，
    皆回傳一段非空、且已通過責任 AI 過濾的稽查建議文字。
    """
    try:
        text = generate_fallback(row)
    except Exception:  # 範本邏輯對非預期輸入拋例外時，仍需保底
        text = None
    if not (isinstance(text, str) and text.strip()):
        # 最終保底同樣套用輸出後過濾（第二道關卡）。
        return sanitize_output(_LAST_RESORT_REPORT)
    return text


def generate_report(row, prefer_bedrock=True):
    """
    對外主函式。回傳 (report_text, source)。
    source: "bedrock" 表示真的用了 Bedrock；"fallback" 表示用範本。

    保底保證（R15.5, Property 43）：只要 Bedrock 未設定或呼叫失敗（金鑰缺失、
    網路、權限、模型未開通、模型回傳錯誤等任何例外），本函式一律退化為規則式
    fallback，回傳「非空」報告文字並標示來源為 "fallback"，維持可 Demo。
    """
    if prefer_bedrock and os.environ.get("AWS_ACCESS_KEY_ID"):
        try:
            text = generate_with_bedrock(row)
            if isinstance(text, str) and text.strip():
                return text, "bedrock"
            # Bedrock 回傳空內容視同不可用，退化 fallback。
            raise ValueError("empty bedrock response")
        except Exception as e:  # 網路/權限/模型未開通/回傳錯誤等任何失敗
            note = f"\n\n（註：AWS Bedrock 呼叫失敗，已改用規則式範本。原因：{type(e).__name__}）"
            return _safe_fallback(row) + note, "fallback"
    return _safe_fallback(row), "fallback"


# --------------------------------------------------------------------------
# AI 稽查助手（Copilot）— 以資料為依據回答（R15）
# --------------------------------------------------------------------------

# 可回答的欄位 → (人類可讀標籤, 該欄位的資料來源說明)。
# 來源說明用於為關鍵陳述附上資料依據（R15.2）。
_ANSWERABLE_FIELDS = {
    "risk_total": ("總風險分", "白盒風險評分（鑑識會計指標加權）"),
    "risk_level": ("風險等級", "白盒風險評分分級（≥70 高／40–69 中／<40 低）"),
    "score_financial": ("財務異常分項", "鑑識會計財務指標"),
    "score_penalty": ("裁罰分項", "全國教保資訊網裁罰紀錄"),
    "score_eval": ("評鑑分項", "教保機構評鑑結果"),
    "score_sentiment": ("輿情分項", "網路輿情 NLP 分析"),
    "expense_income_ratio": ("收支比", "公校決算書／機構財報"),
    "benford_mad": ("班佛偏離度(MAD)", "班佛定律檢定（首位數分布）"),
    "beneish_score": ("Beneish 操縱分", "Beneish M-Score 模型"),
    "iforest_score": ("孤立森林異常分", "Isolation Forest 異常偵測"),
    "expense_yoy_pct": ("年度支出增減", "跨年度決算趨勢"),
    "fund_balance_end": ("期末基金餘額", "公校決算書基金來源用途及餘絀表"),
    "penalty_count": ("裁罰次數", "全國教保資訊網裁罰紀錄"),
    "eval_grade": ("評鑑等第", "教保機構評鑑結果"),
    "district": ("所在行政區", "機構基本資料"),
    "park_type": ("機構類型", "機構基本資料"),
}

# 依問題關鍵字挑選相關欄位（讓回答扣緊問題）。
_QUESTION_KEYWORDS = {
    "財務": ["score_financial", "expense_income_ratio", "benford_mad",
             "beneish_score", "expense_yoy_pct"],
    "收支": ["expense_income_ratio", "expense_yoy_pct"],
    "裁罰": ["score_penalty", "penalty_count"],
    "評鑑": ["score_eval", "eval_grade"],
    "輿情": ["score_sentiment"],
    "風險": ["risk_total", "risk_level"],
    "分數": ["risk_total", "risk_level"],
    "勾稽": ["fund_balance_end"],
    "基金": ["fund_balance_end"],
    "帳": ["fund_balance_end"],
}


def _entity_get(entity, key):
    """從 EntityData（dict 或具屬性物件）取值；缺值/NaN 視為 None。"""
    if entity is None:
        return None
    if isinstance(entity, dict):
        v = entity.get(key)
    else:
        v = getattr(entity, key, None)
    if v is None or (isinstance(v, float) and v != v):
        return None
    return v


def _select_relevant_fields(question):
    """依問題文字挑選相關欄位；若無命中則回傳一組預設核心欄位。"""
    q = question or ""
    selected = []
    for kw, fields in _QUESTION_KEYWORDS.items():
        if kw in q:
            selected.extend(fields)
    if not selected:
        selected = ["risk_total", "risk_level", "score_financial", "score_penalty"]
    # 去重並保序
    return list(dict.fromkeys(selected))


def answer(question, entity):
    """以該機構資料為依據回答稽查員提問，回傳 CopilotAnswer。

    - 以 entity 的實際資料為依據作答（R15.1）。
    - 關鍵陳述附上資料來源（R15.2）。
    - 資料不足以回答時，明確告知資料不足而不杜撰（R15.4）。
    - 透過提示詞負向約束 + 輸出後過濾，避免違法/舞弊斷言（R15.3, R19.2, R19.3）。
    - 僅產出解釋/提供證據/建議稽查方向類輸出（R19.1）。

    entity 為 EntityData（dict 或具對應屬性之物件），沿用本模組既有欄位命名。
    """
    name = _entity_get(entity, "park_name") or "該機構"
    relevant = _select_relevant_fields(question)

    # 蒐集有實際資料的欄位（作答依據）與其來源（R15.1, R15.2）。
    found = []   # (label, value, source_note)
    sources = []
    for key in relevant:
        if key not in _ANSWERABLE_FIELDS:
            continue
        val = _entity_get(entity, key)
        if val is None:
            continue
        label, source_note = _ANSWERABLE_FIELDS[key]
        found.append((label, val, source_note))
        if source_note not in sources:
            sources.append(source_note)

    notice = f"風險分數僅供稽查排序參考，{_NOT_ILLEGALITY_NOTICE}。"

    # 資料不足：明確告知、不杜撰（R15.4）。
    if not found:
        text = (
            f"關於「{name}」的這項提問，目前系統缺乏足夠資料可供回答，"
            "為避免杜撰，暫不提供推測。建議補齊對應的財務、裁罰、評鑑或輿情資料後再行查詢。"
            f" {notice}"
        )
        return CopilotAnswer(
            text=sanitize_output(text),
            sources=[],
            grounded=False,
            data_sufficient=False,
            not_illegality_notice=notice,
        )

    # 以資料為依據組出回答，關鍵陳述附來源（R15.1, R15.2）。
    def _fmt(v):
        if isinstance(v, float):
            return f"{v:.2f}".rstrip("0").rstrip(".")
        return str(v)

    statements = [
        f"{label} 為 {_fmt(value)}（依據：{source_note}）"
        for label, value, source_note in found
    ]

    # 基金餘額勾稽：問題涉及「勾稽／基金／帳」且該園有勾稽資料時，附白話判讀結論。
    # 勾稽是「一致/不一致」的判讀（非單純數值），故以完整結論句呈現而非「X 為 N」。
    q = question or ""
    if any(kw in q for kw in ("勾稽", "基金", "帳")):
        has_recon = (_entity_get(entity, "fund_recon_consistent") is not None
                     or _entity_get(entity, "fund_balance_end") is not None
                     or _entity_get(entity, "fund_balance_begin") is not None)
        if has_recon:
            recon_src = "基金餘額勾稽（會計恆等式：期末=期初+本期賸餘）"
            statements.append(f"基金餘額勾稽結果：{_fund_recon_fact(entity)}"
                              f"（依據：{recon_src}）")
            if recon_src not in sources:
                sources.append(recon_src)

    text = (
        f"依「{name}」現有資料，{'；'.join(statements)}。"
        "以上為需進一步查核之參考訊號，建議就相關憑證與明細優先核對。"
        f" {notice}"
    )

    return CopilotAnswer(
        text=sanitize_output(text),   # 輸出後過濾（第二道關卡）
        sources=sources,
        grounded=True,
        data_sufficient=True,
        not_illegality_notice=notice,
    )
