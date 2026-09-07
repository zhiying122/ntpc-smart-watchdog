"""
PDF 拆頁 / 文字抽取工具
================================
解決「財報 PDF 太大、無法上傳或難以檢視」的問題。

兩種模式：

  --mode split   把指定頁抽成一個小 PDF（保留原解析度，適合再做 OCR，通常遠小於原檔）
  --mode text    直接把整份或指定頁的「文字層」抽成 .txt（僅適用有文字層的 PDF，例如公校決算書）
  --mode info    只印出頁數與每頁是否含文字層，幫你判斷該用哪個模式

用法範例：
    # 先看這份 PDF 有幾頁、哪些頁有文字
    python -m src.pdf_extract_pages "C:\\Users\\user\\Downloads\\N01安溪_112學年度財務報告.pdf" --mode info

    # 把第 6、7 頁抽成小 PDF（存到 data/derived/）
    python -m src.pdf_extract_pages "路徑\\財報.pdf" --mode split --pages 6 7

    # 把有文字層的決算書全部抽成純文字
    python -m src.pdf_extract_pages "路徑\\決算書.pdf" --mode text
"""
import argparse
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "derived")


def _open(pdf_path):
    import pymupdf
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"找不到檔案：{pdf_path}")
    return pymupdf.open(pdf_path)


def mode_info(pdf_path):
    """印出頁數與每頁文字層概況，幫忙判斷是否需要 OCR。"""
    doc = _open(pdf_path)
    size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    print(f"檔案：{os.path.basename(pdf_path)}")
    print(f"大小：{size_mb:.1f} MB，頁數：{len(doc)}")
    print("-" * 40)
    for i, page in enumerate(doc, start=1):
        text = page.get_text().strip()
        n = len(text)
        tag = "有文字層" if n > 20 else "無文字層(掃描圖，需OCR)"
        preview = text[:30].replace("\n", " ")
        print(f"第 {i:>3} 頁：{tag}  文字長度={n:<6} {preview}")
    doc.close()


def mode_split(pdf_path, pages):
    """把指定頁抽成一個新的小 PDF，保留原始品質。"""
    import pymupdf
    doc = _open(pdf_path)
    new = pymupdf.open()
    for p in pages:
        if 1 <= p <= len(doc):
            new.insert_pdf(doc, from_page=p - 1, to_page=p - 1)
        else:
            print(f"[!] 略過超出範圍的頁碼：{p}（總頁數 {len(doc)}）")
    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    tag = "_".join(str(p) for p in pages)
    out_path = os.path.join(OUT_DIR, f"{base}_p{tag}.pdf")
    new.save(out_path, deflate=True, garbage=4)
    out_mb = os.path.getsize(out_path) / (1024 * 1024)
    new.close()
    doc.close()
    print(f"[OK] 已輸出：{out_path}")
    print(f"     大小：{out_mb:.2f} MB（原檔的一小部分，可直接檢視或上傳）")
    return out_path


def mode_text(pdf_path, pages=None):
    """把文字層抽成 .txt。pages 為 None 時抽全部。"""
    doc = _open(pdf_path)
    target = pages if pages else range(1, len(doc) + 1)
    chunks, empty = [], 0
    for p in target:
        if not (1 <= p <= len(doc)):
            continue
        text = doc[p - 1].get_text().strip()
        if not text:
            empty += 1
        chunks.append(f"===== 第 {p} 頁 =====\n{text}")
    doc.close()

    os.makedirs(OUT_DIR, exist_ok=True)
    base = os.path.splitext(os.path.basename(pdf_path))[0]
    out_path = os.path.join(OUT_DIR, f"{base}.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(chunks))
    print(f"[OK] 已輸出文字：{out_path}")
    if empty:
        print(f"[!] 有 {empty} 頁沒有文字層（可能是掃描影像）。")
        print("    這些頁需要走 OCR：python -m src.ocr_nonprofit ... --engine bedrock")
    return out_path


def main():
    ap = argparse.ArgumentParser(description="PDF 拆頁 / 文字抽取工具")
    ap.add_argument("pdf", help="來源 PDF 路徑（可放在專案外，例如下載資料夾）")
    ap.add_argument("--mode", choices=["info", "split", "text"], default="info")
    ap.add_argument("--pages", nargs="+", type=int, default=None,
                    help="要處理的頁碼(1-based)，split 模式必填")
    args = ap.parse_args()

    if args.mode == "info":
        mode_info(args.pdf)
    elif args.mode == "split":
        if not args.pages:
            ap.error("--mode split 需要指定 --pages，例如 --pages 6 7")
        mode_split(args.pdf, args.pages)
    elif args.mode == "text":
        mode_text(args.pdf, args.pages)


if __name__ == "__main__":
    main()
