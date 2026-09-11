"""
裁罰紀錄文字分類 + 嚴重度（規則式，可解釋）
================================================
把裁罰紀錄的文字（penalty_reason）分類到五大稽查風險類別，並給嚴重度分數。
不用複雜 NLP 模型——用規則式關鍵字比對就足夠，且完全可解釋、可對評審逐條講清楚。

設計原則：
1. 分類依《幼兒教育及照顧法》的違規態樣歸納成五類：收費、人力、安全、教保、行政。
2. 嚴重度：不同違規對幼兒權益的實質影響不同，收費超收與安全缺失
   遠比一般行政申報缺失嚴重，權重必須拉開，不能只算「次數」。
3. 每一筆裁罰文字可能命中多個類別（例如「超收幼生與收費違規」同時是收費+人力），
   取其中最嚴重的類別作為主類別，嚴重度取命中類別的最大值。

嚴重度級距（0-100，供風險評分使用）：
    安全   90  幼兒人身安全，最優先
    收費   80  直接損及家長權益、常涉不當得利
    人力   70  師生比／資格不符，影響照顧品質與安全
    教保   55  課程與教保服務品質
    行政   35  申報／文件類程序缺失，實質危害較低
未分類（有裁罰但文字無法歸類）給中性偏高 50，避免漏接。
"""

# 五大類別 → (關鍵字清單, 嚴重度基準分)
# 關鍵字依實務裁罰用語歸納；同一詞只放最貼近的主類別。
PENALTY_CATEGORIES = {
    "安全": {
        "severity": 90,
        "keywords": ["安全", "設施", "建物", "消防", "公共安全", "逃生", "危險", "事故", "傷害"],
        "focus": "建物公共安全、消防與遊具設施檢查",
    },
    "收費": {
        "severity": 80,
        "keywords": ["收費", "超收", "退費", "費用", "不當得利", "溢收", "巧立名目", "代收代辦"],
        "focus": "收費項目與金額備查、退費機制、收據憑證",
    },
    "人力": {
        "severity": 70,
        "keywords": ["師生比", "員額", "人員資格", "教保員", "教師資格", "人力", "資格不符", "配置不足"],
        "focus": "教保服務人員資格、員額配置與師生比",
    },
    "教保": {
        "severity": 55,
        "keywords": ["教保", "課程", "教學", "體罰", "不當管教", "餐點", "衛生", "健康"],
        "focus": "教保服務內容、課程與餐點衛生",
    },
    "行政": {
        "severity": 35,
        "keywords": ["申報", "備查", "文件", "行政", "公告", "登記", "資料", "程序", "改善", "限期"],
        "focus": "文件申報、備查程序與限期改善",
    },
}

# 未能歸類但確有裁罰時的中性偏高值（避免漏接）
UNCLASSIFIED_SEVERITY = 50


def classify_penalty_text(text):
    """
    把一段裁罰文字分類，回傳 dict：
      {
        "categories": ["收費", "人力"],   # 命中的所有類別（依嚴重度高→低）
        "primary": "收費",                # 主類別（命中類別中最嚴重者）
        "severity": 80,                   # 主類別嚴重度
        "focus": "...",                   # 對應的建議查核重點
      }
    無文字或無命中時 categories 為空、severity 用未分類值。
    """
    if not isinstance(text, str) or not text.strip():
        return {"categories": [], "primary": None, "severity": 0, "focus": ""}

    hits = []
    for cat, cfg in PENALTY_CATEGORIES.items():
        if any(kw in text for kw in cfg["keywords"]):
            hits.append(cat)

    if not hits:
        # 有文字但無命中關鍵字 → 未分類，給中性偏高，避免漏接
        return {"categories": ["未分類"], "primary": "未分類",
                "severity": UNCLASSIFIED_SEVERITY, "focus": "裁罰事由請人工複核歸類"}

    # 依嚴重度由高到低排序，取最嚴重者為主類別
    hits.sort(key=lambda c: PENALTY_CATEGORIES[c]["severity"], reverse=True)
    primary = hits[0]
    return {
        "categories": hits,
        "primary": primary,
        "severity": PENALTY_CATEGORIES[primary]["severity"],
        "focus": PENALTY_CATEGORIES[primary]["focus"],
    }


def penalty_severity_score(penalty_count, penalty_reason):
    """
    裁罰風險分（0-100），取代舊的「純次數」計分。
    邏輯：以「主類別嚴重度」為基底，再依裁罰次數做遞增加權。
      - 0 次：0 分
      - 有裁罰：base = 主類別嚴重度；每多一次裁罰額外 +10（上限 100）
    這樣「2 次收費違規(80→90)」會明顯高於「2 次行政缺失(35→45)」，
    符合鑑識會計「看違規性質而非只看次數」的精神。
    無事由文字時以中性值 50 為基底遞增。
    """
    import pandas as pd
    if pd.isna(penalty_count):
        return 0.0
    c = int(penalty_count)
    if c <= 0:
        return 0.0

    info = classify_penalty_text(penalty_reason if isinstance(penalty_reason, str) else "")
    base = info["severity"] if info["severity"] > 0 else UNCLASSIFIED_SEVERITY
    # 次數加權：第 1 次用 base，之後每次 +10
    score = base + (c - 1) * 10
    return round(min(score, 100), 1)


if __name__ == "__main__":
    # 自我檢核：把幾個範例裁罰事由跑一遍，印出分類與分數
    samples = [
        (2, "超收幼生與收費違規"),
        (1, "師生比不符規定"),
        (1, "設施安全缺失"),
        (1, "人員資格不符"),
        (1, "財務申報缺失"),
        (0, ""),
        (3, "超收幼生與收費違規"),
    ]
    print(f"{'次數':<4}{'事由':<16}{'主類別':<8}{'嚴重度':<6}{'風險分':<6}")
    for c, txt in samples:
        info = classify_penalty_text(txt)
        s = penalty_severity_score(c, txt)
        print(f"{c:<5}{txt or '（無）':<17}{str(info['primary'] or '—'):<9}"
              f"{info['severity']:<7}{s}")
