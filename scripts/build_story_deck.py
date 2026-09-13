# -*- coding: utf-8 -*-
"""
小小守護員 Smart Watchdog — 競賽故事版簡報
===========================================
這份簡報不沿用既有模板，而是重新設計成「上台故事線」：
  問題 -> 可能關聯 -> 解法 -> 資料 -> 評分 -> 派工 -> 架構 -> 介面 -> 結論

輸出：reports/小小守護員_競賽故事版簡報.pptx
"""
from __future__ import annotations

import os
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reports", "小小守護員_競賽故事版簡報_v2.pptx")

FONT = "Microsoft JhengHei"

NAVY = RGBColor(0x13, 0x23, 0x38)
NAVY2 = RGBColor(0x1E, 0x3A, 0x5D)
BLUE = RGBColor(0x2A, 0x5C, 0x9F)
TEAL = RGBColor(0x38, 0x9C, 0xB4)
GREEN = RGBColor(0x3B, 0x8C, 0x5A)
YELLOW = RGBColor(0xF0, 0xB3, 0x42)
ORANGE = RGBColor(0xE8, 0x7A, 0x35)
RED = RGBColor(0xD9, 0x3C, 0x3C)
GRAY = RGBColor(0x5E, 0x69, 0x73)
LIGHT = RGBColor(0xF5, 0xF7, 0xFA)
BORDER = RGBColor(0xD7, 0xDE, 0xE6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
blank = prs.slide_layouts[6]


def add_slide():
    return prs.slides.add_slide(blank)


def add_textbox(slide, x, y, w, h, paragraphs, font_size=None, color=GRAY, weight=False, align=PP_ALIGN.LEFT):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for i, para in enumerate(paragraphs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(0)
        p.space_before = Pt(0)
        for run_text, run_size, run_bold, run_color in para:
            run = p.add_run()
            run.text = run_text
            run.font.name = FONT
            run.font.size = Pt(run_size if font_size is None else font_size)
            run.font.bold = run_bold or weight
            run.font.color.rgb = run_color if run_color else color
    return box


def add_rect(slide, x, y, w, h, fill=None, line=None, radius=0, line_w=1):
    if radius:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    else:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if fill is None:
        shape.fill.background()
    else:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w)
    return shape


def add_arrow(slide, x, y, w, h, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x), Inches(y), Inches(w), Inches(h))
    shape.fill.solid(); shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_chip(slide, x, y, w, h, text, fill, fg=WHITE, size=12):
    add_rect(slide, x, y, w, h, fill=fill, line=None, radius=True, line_w=1)
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = 6
    tf.margin_right = 6
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    run = p.add_run()
    run.text = text
    run.font.name = FONT
    run.font.bold = True
    run.font.size = Pt(size)
    run.font.color.rgb = fg
    return box


def add_header(slide, kicker, title, idx=None):
    add_rect(slide, 0, 0, 13.333, 0.9, fill=WHITE, line=None, radius=False)
    add_rect(slide, 0.5, 0.3, 0.12, 0.42, fill=BLUE)
    add_textbox(slide, 0.72, 0.28, 5.5, 0.3, [[(kicker, 10, True, BLUE)]])
    add_textbox(slide, 0.72, 0.56, 11.5, 0.45, [[(title, 22, True, NAVY)]])
    add_rect(slide, 0.72, 0.9, 11.8, 0.02, fill=BORDER)
    if idx is not None:
        add_textbox(slide, 12.3, 0.3, 0.7, 0.3, [[(f"{idx:02d}", 12, True, BORDER)]], align=PP_ALIGN.RIGHT)


# Slide 1
s = add_slide()
add_rect(s, 0, 0, 13.333, 7.5, fill=NAVY)
add_rect(s, 0, 0, 0.18, 7.5, fill=BLUE)
add_chip(s, 0.8, 0.9, 5.8, 0.42, "2026 新北市 AI 智慧城市黑客松競賽｜教育局組", NAVY2, fg=WHITE, size=12)
add_textbox(s, 0.8, 1.7, 8.8, 1.2, [[("小小守護員", 34, True, WHITE), (" Smart Watchdog", 34, True, RGBColor(0x7B, 0xB0, 0xE6))]])
add_textbox(s, 0.8, 3.2, 10.0, 0.5, [[("AI × 鑑識會計，讓幼兒園安全風險提前被看見", 20, True, RGBColor(0xE2, 0xEB, 0xF5))]])
add_rect(s, 0.8, 4.4, 11.6, 1.0, fill=RGBColor(0x22, 0x3A, 0x50), radius=0.1)
add_textbox(s, 1.1, 4.55, 10.8, 0.8, [[("我們不是做一個風險分數表，而是做一個能真正幫稽查人員提前判斷、派工與查核的 AI 稽查官", 18, False, RGBColor(0xDF, 0xE8, 0xF4))]])
add_textbox(s, 0.8, 6.0, 8.0, 0.5, [[("公務後台: http://18.236.246.233:8601", 14, True, RGBColor(0xC8, 0xDD, 0xF3)), ("  ｜  ", 14, False, WHITE), ("公眾查詢網: http://18.236.246.233:8602", 14, True, RGBColor(0xC8, 0xDD, 0xF3))]], align=PP_ALIGN.LEFT)

# Slide 2: Problem
s = add_slide(); add_header(s, "問題意識", "我想問的，不只是「有沒有問題」，而是「什麼時候該先察覺」", 2)
add_textbox(s, 0.85, 1.4, 11.7, 0.45, [[("我們觀察到，近年幼兒園安全事件與照顧品質問題的討論頻繁，而風險很可能與經費壓力、師資不足、照護過載有關聯。", 15, False, GRAY)]])
chain = [
    ("經費不足", "人力/設備不足", RED),
    ("老師與照護人力不足", "照顧過載", ORANGE),
    ("系統性監督失效", "風險被放大", YELLOW),
    ("兒童安全與照護風險", "需提前預警", GRAY),
]
start_x = 0.9; gap = 0.4; w = 2.2; y = 2.2
for idx, (t, d, c) in enumerate(chain):
    x = start_x + idx * (w + gap)
    add_rect(s, x, y, w, 1.2, fill=WHITE, line=c, radius=True, line_w=2)
    add_rect(s, x, y, 0.14, 1.2, fill=c)
    add_textbox(s, x + 0.28, y + 0.18, w - 0.45, 0.4, [[(t, 15, True, NAVY)]])
    add_textbox(s, x + 0.28, y + 0.65, w - 0.45, 0.4, [[(d, 11, False, GRAY)]])
    if idx < len(chain) - 1:
        add_arrow(s, x + w + 0.05, y + 0.45, 0.27, 0.18, c)

add_textbox(s, 0.85, 4.15, 11.8, 0.35, [[("這不是在說「財務不好就一定有問題」；而是：財務與人力壓力，常是較早出現的前兆訊號。", 13, True, BLUE)]])
card_w = 3.7
cards = [
    ("經費壓力", "基金短絀、收入與支出失衡，可能反映機構承壓程度；我們把它當成重要警訊。", BLUE),
    ("師資不足", "照顧人力不足可能增加細節漏失、壓力與失控風險。", ORANGE),
    ("監理資料分散", "決算、收費、評鑑、裁罰、新聞各自散落，缺少整合視角。", GREEN),
]
for i, (t, d, c) in enumerate(cards):
    x = 0.85 + i * (card_w + 0.25)
    add_rect(s, x, 4.75, card_w, 1.8, fill=LIGHT, line=BORDER, radius=True)
    add_rect(s, x, 4.75, 3.7, 0.1, fill=c)
    add_textbox(s, x + 0.2, 4.95, 3.15, 0.35, [[(t, 15, True, NAVY)]])
    add_textbox(s, x + 0.2, 5.45, 3.2, 0.8, [[(d, 10.5, False, GRAY)]])

# Slide 3: pain points and opportunity
s = add_slide(); add_header(s, "痛點與切入點", "現在的問題不是缺資料，而是缺一個可執行的風險前置工具", 3)
points = [
    ("01", "資料散落：決算、評鑑、裁罰、收費、新聞不是同一張表。", RED),
    ("02", "稽查人力有限：全市機構多，無法逐一做深度人工檢查。", ORANGE),
    ("03", "風險分數不透明：若只是黑盒，不敢在政府部門裡被責問。", YELLOW),
    ("04", "部門需要決策依據：不是只知道「有問題」，而是知道「先查誰」。", GREEN),
]
for i, (n, txt, c) in enumerate(points):
    x = 0.8 + (i % 2) * 6.1; y = 1.7 + (i // 2) * 2.1
    add_rect(s, x, y, 5.7, 1.5, fill=WHITE, line=BORDER, radius=True)
    add_rect(s, x, y, 0.14, 1.5, fill=c)
    add_textbox(s, x + 0.28, y + 0.18, 0.7, 0.4, [[(n, 22, True, c)]])
    add_textbox(s, x + 1.1, y + 0.18, 4.2, 0.8, [[(txt, 12, True, NAVY)]])

add_textbox(s, 0.8, 5.7, 11.6, 0.4, [[("所以我們做的，不是「AI 直接判定誰違法」，而是：用可解釋的風險評分讓稽查員先知道誰值得查、查什麼、怎麼派工。", 13, True, BLUE)]])

# Slide 4: solution overview
s = add_slide(); add_header(s, "解決方案說明", "三步驟：抓資料 → 算風險 → 派人去勘查", 4)
steps = [
    ("抓資料", "整合公校決算、非營利園財報、裁罰、評鑑、公開新聞、PTT 討論與地理資訊", BLUE),
    ("算風險", "用鑑識會計與白盒規則，計算財務異常、裁罰、評鑑、輿情四項分數", TEAL),
    ("派人勘查", "依風險總分與分區/已查狀態進行排序，讓每位稽查員投入最需要的人力", GREEN),
]
for i, (title, content, color) in enumerate(steps):
    x = 0.9 + i * 4.1
    add_rect(s, x, 1.8, 3.8, 3.7, fill=WHITE, line=BORDER, radius=True)
    add_rect(s, x, 1.8, 3.8, 0.7, fill=color)
    add_textbox(s, x + 0.25, 2.0, 3.3, 0.35, [[(title, 18, True, WHITE)]])
    add_textbox(s, x + 0.25, 2.9, 3.3, 1.3, [[(content, 11.5, False, GRAY)]])
    add_chip(s, x + 0.35, 4.9, 2.9, 0.45, f"核心價值 {i+1}", color, fg=WHITE, size=12)

add_textbox(s, 0.9, 6.2, 11.6, 0.45, [[("這個系統的核心不是替代人，而是把稽查人員變成高效率的決策者：先看高風險、再看證據、最後出任務。", 13, True, BLUE)]])

# Slide 5: data sources and usage
s = add_slide(); add_header(s, "數據及資料運用", "靜態資料 × 動態資料 × 輿情資料，真正形成完整風險圖譜", 5)
left_w = 5.8; right_w = 5.7
add_rect(s, 0.85, 1.45, left_w, 3.9, fill=WHITE, line=BORDER, radius=True)
add_rect(s, 0.85, 1.45, left_w, 0.6, fill=BLUE)
add_textbox(s, 1.1, 1.67, 3.5, 0.25, [[("靜態資料：官方事實資料", 18, True, WHITE)]])
static = [
    "公校決算書 PDF：逐筆明細供班佛定律、收益/支出結構、基金檢核",
    "非營利幼兒園財報：OCR 抽取收入、支出、基金餘額、跨年度趨勢",
    "評鑑資料：優/良/中/待改進等官方等級，作為照護品質基線",
    "裁罰紀錄：違規次數、違反項目、官方處分內容，作為安全事件證據",
]
for i, item in enumerate(static):
    y = 2.55 + i * 0.72
    add_rect(s, 1.05, y, 0.18, 0.18, fill=BLUE)
    add_textbox(s, 1.38, y-0.02, 4.3, 0.32, [[(item, 10.8, False, GRAY)]])

add_rect(s, 6.9, 1.45, right_w, 3.9, fill=WHITE, line=BORDER, radius=True)
add_rect(s, 6.9, 1.45, right_w, 0.6, fill=GREEN)
add_textbox(s, 7.2, 1.67, 3.5, 0.25, [[("動態與輿情資料：風險警示層", 18, True, WHITE)]])
live = [
    "全國教保資訊網：機構基本資料、收費、裁罰、評鑑與更新狀態",
    "新聞/媒體 RSS：Google News / Bing News / 政策報導，追蹤負面事件",
    "PTT、社群討論：家長與社會關注度，做為風險提示而非直接定罪",
    "資料快取與歷史快照：確保異常事件、版本差異可回溯與審計",
]
for i, item in enumerate(live):
    y = 2.55 + i * 0.72
    add_rect(s, 7.18, y, 0.18, 0.18, fill=GREEN)
    add_textbox(s, 7.5, y-0.02, 4.4, 0.32, [[(item, 10.8, False, GRAY)]])

add_textbox(s, 0.8, 5.75, 11.6, 0.5, [[("設計原則：官方資料負責『證據』，新聞與輿情負責『警示』；二者分層處理，避免單一來源誤導決策。", 13, True, BLUE)]])

# Slide 6: scoring formula
s = add_slide(); add_header(s, "分數怎麼算", "白盒風險分數：每一分都可以講得清楚", 6)
add_rect(s, 0.8, 1.6, 5.9, 3.4, fill=LIGHT, line=BORDER, radius=True)
add_textbox(s, 1.1, 1.8, 4.7, 0.35, [[("總風險分 = 財務異常 × 45% + 裁罰紀錄 × 30% + 評鑑 × 15% + 輿情 × 10%", 16, True, NAVY)]])
weights = [
    ("財務異常", "45%", "Benford、Beneish、Altman、Isolation Forest、收支比等多層檢查", RED),
    ("裁罰紀錄", "30%", "重點看違反性質與頻率；僅有明細時採破窗效應計分", ORANGE),
    ("評鑑結果", "15%", "優/良/乙/待改進，缺資料則以中性值處理", YELLOW),
    ("網路輿情", "10%", "新聞與PTT負面程度，查無訊號不放大風險", GREEN),
]
start_y = 2.45
for i, (name, pct, desc, color) in enumerate(weights):
    add_rect(s, 1.0, start_y + i * 0.72, 0.18, 0.18, fill=color)
    add_textbox(s, 1.35, start_y + i * 0.72 - 0.02, 1.2, 0.3, [[(name, 12, True, NAVY)]])
    add_textbox(s, 2.7, start_y + i * 0.72 - 0.02, 0.7, 0.3, [[(pct, 12, True, color)]])
    add_textbox(s, 3.6, start_y + i * 0.72 - 0.02, 3.1, 0.3, [[(desc, 9.8, False, GRAY)]])
add_rect(s, 7.1, 1.8, 5.3, 3.2, fill=WHITE, line=BORDER, radius=True)
add_textbox(s, 7.45, 2.2, 2.2, 0.35, [[("實例：林口幼兒園 59.0 分", 16, True, NAVY)]])
example = [
    ("財務異常", "53.4 × 0.45", "24.0"),
    ("裁罰", "90 × 0.30", "27.0"),
    ("評鑑", "40 × 0.15", "6.0"),
    ("輿情", "20 × 0.10", "2.0"),
]
for i, (name, formula, val) in enumerate(example):
    y = 2.9 + i * 0.55
    add_textbox(s, 7.5, y, 2.0, 0.25, [[(name, 11.5, False, GRAY)]])
    add_textbox(s, 9.2, y, 1.4, 0.25, [[(formula, 11.5, False, GRAY)]], align=PP_ALIGN.RIGHT)
    add_textbox(s, 10.8, y, 0.8, 0.25, [[(val, 12, True, RED)]], align=PP_ALIGN.RIGHT)
add_rect(s, 7.45, 5.5, 4.6, 0.02, fill=BORDER)
add_textbox(s, 7.5, 5.65, 2.6, 0.3, [[("總分 = 59.0", 14, True, NAVY)]])
add_textbox(s, 10.2, 5.65, 1.5, 0.3, [[("高風險", 14, True, RED)]], align=PP_ALIGN.RIGHT)

# Slide 7: dispatch procedure
s = add_slide(); add_header(s, "如何派人去勘查", "不是把所有人都查，而是讓高風險機構先被選中，且保證公平與可追溯", 7)
add_textbox(s, 0.85, 1.5, 11.6, 0.35, [[("派工核心目標：在有限稽查人力中，選出能最大化風險覆蓋的機構；若同風險則按照固定規則排隊，不讓系統隨機。", 12.5, True, BLUE)]])
logic = [
    ("Step 1", "排除已稽查機構與不符合區域限制者", BLUE),
    ("Step 2", "依風險分數由高到低排序", ORANGE),
    ("Step 3", "取前 N 名，最多派給 N 位稽查員", GREEN),
    ("Step 4", "若合格機構少於 N，則輸出全部合格機構", TEAL),
]
for i, (step, desc, color) in enumerate(logic):
    x = 0.9 + i * 3.0
    add_rect(s, x, 2.2, 2.6, 2.4, fill=WHITE, line=BORDER, radius=True)
    add_rect(s, x, 2.2, 2.6, 0.5, fill=color)
    add_textbox(s, x + 0.2, 2.4, 1.5, 0.2, [[(step, 15, True, WHITE)]])
    add_textbox(s, x + 0.25, 3.1, 2.1, 0.9, [[(desc, 10.5, False, GRAY)]])

add_rect(s, 0.8, 5.3, 11.7, 1.2, fill=LIGHT, line=BORDER, radius=True)
add_textbox(s, 1.1, 5.6, 5.3, 0.35, [[("派工公式的感念：", 12.5, True, NAVY), (" 風險覆蓋最大化 = 選擇最高風險、最可能需要查核的機構。", 12.5, False, GRAY)]])
add_textbox(s, 1.1, 6.0, 9.5, 0.35, [[("這裡的關鍵不是把風險當犯罪認定，而是把資源投給最值得查核的單位，讓有限的勘查人力更有效。", 11.5, False, GRAY)]])

# Slide 8: AWS architecture
s = add_slide(); add_header(s, "AWS 雲端技術架構", "資料來源 → 雲端處理 → 風險中台 → 雙介面展示", 8)
add_rect(s, 0.8, 1.6, 11.7, 0.55, fill=LIGHT, line=BORDER, radius=True)
add_textbox(s, 1.1, 1.82, 10.6, 0.2, [[("① 資料來源", 12, True, BLUE), ("  |  公校決算 / 非營利園財報 / 裁罰 / 評鑑 / 新聞 / PTT / 司法事實", 11, False, GRAY)]])
add_rect(s, 0.8, 2.4, 11.7, 1.3, fill=WHITE, line=BORDER, radius=True)
boxes = [
    ("Amazon S3", "資料儲存", 1.05, 2.75, 2.2, 0.85, ORANGE),
    ("Textract / Tesseract", "OCR 抽數字", 3.55, 2.75, 2.3, 0.85, YELLOW),
    ("Amazon Bedrock\nClaude", "生成建議", 6.2, 2.75, 2.3, 0.85, TEAL),
    ("EC2 + IAM Role", "運算主機 / 免金鑰", 8.85, 2.75, 2.2, 0.85, GREEN),
]
for title, subtitle, x, y, w, h, c in boxes:
    add_rect(s, x, y, w, h, fill=c, line=None, radius=True)
    add_textbox(s, x + 0.18, y + 0.15, w - 0.36, 0.35, [[(title, 12, True, WHITE)]], align=PP_ALIGN.CENTER)
    add_textbox(s, x + 0.18, y + 0.48, w - 0.36, 0.24, [[(subtitle, 9, False, WHITE)]], align=PP_ALIGN.CENTER)
add_arrow(s, 5.9, 2.1, 0.3, 0.2, BLUE)
add_arrow(s, 8.7, 2.1, 0.3, 0.2, BLUE)
add_rect(s, 0.8, 4.1, 11.7, 1.05, fill=WHITE, line=BORDER, radius=True)
add_textbox(s, 1.1, 4.35, 10.8, 0.45, [[("③ 鑑識風險中台：forensic.py / risk_score.py / evidence.py / ai_report.py", 12, True, NAVY)]])
add_rect(s, 0.8, 5.4, 11.7, 1.05, fill=WHITE, line=BORDER, radius=True)
add_textbox(s, 1.1, 5.68, 10.8, 0.45, [[("④ 雙介面：公務後台 8601（稽查官）｜公眾查詢網 8602（家長）", 12, True, NAVY)]])

# Slide 9: gov app and public app
s = add_slide(); add_header(s, "介面與操作流程", "兩個入口，兩種權限，卻共用同一套風險中台；每一步顯示都可被解釋、可被追溯", 9)
left = 0.85; right = 6.9; top = 1.6; h = 3.8
add_rect(s, left, top, 5.6, h, fill=WHITE, line=BORDER, radius=True)
add_rect(s, left, top, 5.6, 0.6, fill=BLUE)
add_textbox(s, left + 0.3, top + 0.12, 3.2, 0.28, [[("公務後台：8601", 18, True, WHITE)]])
ops = [
    "風險總覽：全市 KIP、優先案件、區域熱點",
    "風險地圖：紅黃綠標記，供稽查主管快速聚焦高危區域",
    "單園工作台：風險分數、證據鏈、AI 建議與歷史變化",
    "派工模組：依風險排序與區域限制分配有限稽查人力",
]
for i, item in enumerate(ops):
    y = top + 0.9 + i * 0.7
    add_rect(s, left + 0.25, y, 0.18, 0.18, fill=BLUE)
    add_textbox(s, left + 0.55, y - 0.02, 4.3, 0.35, [[(item, 11.5, False, GRAY)]])

add_rect(s, right, top, 5.6, h, fill=WHITE, line=BORDER, radius=True)
add_rect(s, right, top, 5.6, 0.6, fill=GREEN)
add_textbox(s, right + 0.3, top + 0.12, 3.2, 0.28, [[("公眾查詢網：8602", 18, True, WHITE)]])
public_ops = [
    "輸入地址，查詢鄰近幼兒園資訊",
    "查看公開學費、評鑑、裁罰與新聞關注度",
    "看地理位置與服務範圍，增強資訊透明與選擇能力",
    "資料層過濾風險欄位，確保家長拿不到內部決策分數",
]
for i, item in enumerate(public_ops):
    y = top + 0.9 + i * 0.7
    add_rect(s, right + 0.25, y, 0.18, 0.18, fill=GREEN)
    add_textbox(s, right + 0.55, y - 0.02, 4.3, 0.35, [[(item, 11.5, False, GRAY)]])

add_textbox(s, 0.85, 5.8, 11.7, 0.4, [[("關鍵設計：同一套中台共用資料，但權限不同。政府看風險與證據，家長看公開資訊與透明度，讓系統兼顧效率與信任。", 13, True, BLUE)]])

# Slide 10: close
s = add_slide(); add_rect(s, 0, 0, 13.333, 7.5, fill=NAVY)
add_rect(s, 0, 0, 0.18, 7.5, fill=BLUE)
add_textbox(s, 0.85, 1.0, 8.5, 0.5, [[("結論：把事後被動稽查，轉成事前主動示警", 26, True, WHITE)]])
items = [
    ("讓政府知道先查誰", "不再靠人工逐間翻資料，而是以風險排序優化人力投放"),
    ("讓家長知道什麼可查", "公開資訊端增加透明度，降低資訊不對稱"),
    ("讓風險可被解釋", "白盒分數與證據鏈讓決策能被追問、能被執行"),
]
for i, (t, d) in enumerate(items):
    y = 2.2 + i * 1.45
    add_rect(s, 0.9, y, 11.4, 0.85, fill=RGBColor(0x1E, 0x3A, 0x5D), radius=True)
    add_textbox(s, 1.15, y + 0.15, 3.3, 0.25, [[(t, 15, True, RGBColor(0xD9, 0xE8, 0xF9))]])
    add_textbox(s, 4.7, y + 0.15, 6.7, 0.4, [[(d, 11.5, False, RGBColor(0xEA, 0xF2, 0xF8))]])

add_textbox(s, 0.85, 6.5, 11.2, 0.35, [[("小小守護員，不只是做風險評分，而是把幼兒園安全管理從「被動應對」前移到「主動預警」。", 15, True, RGBColor(0xD9, 0xE8, 0xF9))]])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
prs.save(OUT)
print(f"[OK] 已產出 {OUT}")
