"""
非營利園掃描財報 OCR 抽取
================================
非營利園財報 PDF 內頁為掃描影像（無文字層），需 OCR 才能取數字。
本模組提供三種引擎，可依環境切換：

  engine="tesseract"  本地免費，需安裝 Tesseract 引擎 + 中文語言包(chi_tra)
  engine="textract"   AWS Textract，表格辨識率高（需 AWS 憑證）
  engine="bedrock"    AWS Bedrock 多模態(Claude 視覺)，一步到位並展現生成式AI

策略：主力資料走公校決算(有文字層)，非營利園用本模組抽 1-2 份做 Demo，
      證明「架構連掃描檔都能處理」。詳見 docs/ocr-plan.md。

用法：
    python -m src.ocr_nonprofit "路徑\\N01安溪_113學年度財務報告.pdf" --engine tesseract --pages 6 7
"""
import argparse
import os
import io
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pdf_page_to_image(pdf_path, page_index, dpi=300):
    """用 PyMuPDF 把指定頁轉成 PNG bytes。"""
    import pymupdf  # PyMuPDF
    doc = pymupdf.open(pdf_path)
    page = doc[page_index]
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
    img_bytes = pix.tobytes("png")
    doc.close()
    return img_bytes


# ---------- 引擎一：本地 Tesseract ----------
def ocr_tesseract(img_bytes, lang="chi_tra"):
    """本地 Tesseract OCR。需先安裝 Tesseract 引擎與中文語言包。"""
    import pytesseract
    from PIL import Image
    img = Image.open(io.BytesIO(img_bytes))
    try:
        return pytesseract.image_to_string(img, lang=lang)
    except pytesseract.TesseractNotFoundError:
        raise RuntimeError(
            "找不到 Tesseract 引擎。請安裝：\n"
            "  Windows: https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  並加裝繁中語言包 chi_tra，將安裝路徑加入 PATH。"
        )


# ---------- 引擎二：AWS Textract ----------
def ocr_textract(img_bytes):
    """AWS Textract 表格辨識。需設定 AWS 憑證(.env)。"""
    import boto3
    client = boto3.client("textract", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    resp = client.analyze_document(
        Document={"Bytes": img_bytes},
        FeatureTypes=["TABLES"],
    )
    # 把 LINE 區塊組回文字
    lines = [b["Text"] for b in resp.get("Blocks", []) if b.get("BlockType") == "LINE"]
    return "\n".join(lines)


# ---------- 引擎三：AWS Bedrock 多模態 ----------
def ocr_bedrock(img_bytes):
    """
    用 Bedrock Claude 視覺模型直接讀財報並回傳結構化資訊。
    展現生成式 AI 應用（比賽評分項）。需設定 AWS 憑證與 Bedrock 權限。
    """
    import base64
    import json
    import boto3

    client = boto3.client("bedrock-runtime",
                          region_name=os.environ.get("BEDROCK_REGION", "us-east-1"))
    model_id = os.environ.get("BEDROCK_MODEL_ID",
                              "anthropic.claude-3-sonnet-20240229-v1:0")
    b64 = base64.b64encode(img_bytes).decode()
    prompt = (
        "這是一張幼兒園財務報表掃描頁。請讀出其中的財務數字，"
        "以 JSON 回傳，欄位包含：收入總額、支出總額、人事費、學雜費收入。"
        "只回 JSON，數字去除逗號，找不到的欄位填 null。"
    )
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                 "media_type": "image/png", "data": b64}},
                {"type": "text", "text": prompt},
            ],
        }],
    }
    resp = client.invoke_model(modelId=model_id, body=json.dumps(body))
    payload = json.loads(resp["body"].read())
    return payload["content"][0]["text"]


# ---------- 從 OCR 文字抽財務數字 ----------
FIN_KEYWORDS = {
    "income": ["收入合計", "收入總計", "收入總額", "本期收入"],
    "expense": ["支出合計", "支出總計", "支出總額", "本期支出", "費用合計"],
    "personnel": ["職工薪資", "薪資", "人事費", "薪資費用"],
    "tuition": ["學費收入", "學雜費", "代辦費"],
}


def parse_financials(text):
    """從 OCR 文字用關鍵字+就近數字抽財務欄位（盡力而為）。"""
    result = {}
    for field, kws in FIN_KEYWORDS.items():
        for kw in kws:
            m = re.search(kw + r"[^\d\-]{0,10}(-?[\d,]{4,})", text)
            if m:
                result[field] = int(m.group(1).replace(",", ""))
                break
    return result


ENGINES = {"tesseract": ocr_tesseract, "textract": ocr_textract, "bedrock": ocr_bedrock}


def run(pdf_path, engine, pages, dpi=300):
    ocr_fn = ENGINES[engine]
    all_text = []
    for p in pages:
        img = pdf_page_to_image(pdf_path, p - 1, dpi=dpi)
        text = ocr_fn(img)
        all_text.append(f"===== 第 {p} 頁 (engine={engine}) =====\n{text}")
    full = "\n".join(all_text)
    financials = parse_financials(full)
    return full, financials


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", help="非營利園財報 PDF 路徑")
    ap.add_argument("--engine", choices=list(ENGINES), default="tesseract")
    ap.add_argument("--pages", nargs="+", type=int, default=[6, 7],
                    help="要 OCR 的頁碼(1-based)")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()

    try:
        text, fin = run(args.pdf, args.engine, args.pages, args.dpi)
    except RuntimeError as e:
        print(f"[!] {e}")
        return

    print(text[:2000])
    print("\n===== 解析出的財務數字 =====")
    print(fin if fin else "（未抽到，可能需調整頁碼或改用 textract/bedrock 引擎）")


if __name__ == "__main__":
    main()
