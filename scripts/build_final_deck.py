# -*- coding: utf-8 -*-
"""
小小守護員 Smart Watchdog — 決賽完整簡報（合併版，含故事線）
================================================================
把「主簡報」與「資料運用補強」統整為一份有敘事主線的完整簡報，
並加入以文獻實證支撐的動機頁（經費薄弱 → 師資不足 → 安全風險）與
AWS 架構圖頁（含行政/民眾同一中台、雙介面權限投影的說明）。

故事線（Story Spine）：
  痛點 → 為什麼是我們（動機/實證）→ 解法總覽 → 護城河(鑑識會計) →
  白盒分數 → 資料運用(靜態/動態/備援) → AWS 架構圖 → 雙介面操作 → 收尾

所有內容依實際程式碼與已查證文獻，措辭守「關聯 associated，非導致 causes」。

用法：python scripts/build_final_deck.py
輸出：reports/小小守護員_決賽完整簡報.pptx
"""
import os

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "reports", "小小守護員_決賽完整簡報.pptx")

EMU = 914400
IN = EMU
SW = int(13.333 * EMU)
SH = int(7.5 * EMU)

INK = RGBColor(0x1A, 0x1F, 0x2B)
INK_MUTED = RGBColor(0x5B, 0x63, 0x72)
BG = RGBColor(0xFF, 0xFF, 0xFF)
SURFACE = RGBColor(0xF4, 0xF6, 0xF9)
SURFACE2 = RGBColor(0xEA, 0xEE, 0xF3)
BORDER = RGBColor(0xD5, 0xDB, 0xE3)
PRIMARY = RGBColor(0x1F, 0x4E, 0x79)
PRIMARY_DK = RGBColor(0x14, 0x33, 0x50)
ACCENT = RGBColor(0x2C, 0x6E, 0x9B)
RISK_RED = RGBColor(0xD6, 0x45, 0x45)
RISK_ORANGE = RGBColor(0xE0, 0x7B, 0x2B)
RISK_YELLOW = RGBColor(0xE0, 0xA9, 0x3B)
RISK_GREEN = RGBColor(0x3F, 0x8F, 0x5B)
AWS_ORANGE = RGBColor(0xEC, 0x91, 0x2D)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
GOLD = RGBColor(0xFF, 0xD9, 0x7A)
GRAYBOX = RGBColor(0x5B, 0x63, 0x72)

FONT = "Microsoft JhengHei"

prs = Presentation()
prs.slide_width = SW
prs.slide_height = SH
BLANK = prs.slide_layouts[6]


def slide():
    return prs.slides.add_slide(BLANK)


def rect(s, x, y, w, h, color, line=None, line_w=None, rounded=False):
    shp = s.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)))
    if color is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = color
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w or 1)
    shp.shadow.inherit = False
    return shp


def arrow(s, x, y, w, h, color, direction="right"):
    shape = {"right": MSO_SHAPE.RIGHT_ARROW, "down": MSO_SHAPE.DOWN_ARROW}[direction]
    shp = s.shapes.add_shape(shape, Emu(int(x)), Emu(int(y)), Emu(int(w)),
                             Emu(int(h)))
    shp.fill.solid()
    shp.fill.fore_color.rgb = color
    shp.line.fill.background()
    shp.shadow.inherit = False
    return shp


def txt(s, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
        space_after=4, line_spacing=1.0, wrap=True):
    tb = s.shapes.add_textbox(Emu(int(x)), Emu(int(y)), Emu(int(w)), Emu(int(h)))
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    paras = [runs] if runs and isinstance(runs[0], tuple) else runs
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_after = Pt(space_after)
        p.space_before = Pt(0)
        p.line_spacing = line_spacing
        for (t, size, bold, color) in para:
            r = p.add_run()
            r.text = t
            r.font.size = Pt(size)
            r.font.bold = bold
            r.font.name = FONT
            r.font.color.rgb = color
    return tb


def card(s, x, y, w, h, fill=SURFACE, line=BORDER):
    return rect(s, x, y, w, h, fill, line=line, line_w=1, rounded=True)


def chip(s, x, y, w, h, label, fill, fg=WHITE, size=11, bold=True):
    c = rect(s, x, y, w, h, fill, rounded=True)
    tf = c.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = Pt(3)
    tf.margin_right = Pt(3)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = label
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.name = FONT
    r.font.color.rgb = fg
    return c


def header(s, kicker, title, idx=None, chapter=None):
    rect(s, 0, 0, SW, int(1.35 * IN), BG)
    rect(s, int(0.6 * IN), int(0.42 * IN), int(0.09 * IN), int(0.62 * IN), PRIMARY)
    line = kicker if not chapter else f"{chapter}　·　{kicker}"
    txt(s, int(0.85 * IN), int(0.38 * IN), int(10 * IN), int(0.3 * IN),
        [(line, 12, True, ACCENT)])
    txt(s, int(0.85 * IN), int(0.62 * IN), int(11.2 * IN), int(0.62 * IN),
        [(title, 25, True, INK)])
    rect(s, int(0.85 * IN), int(1.24 * IN), int(11.6 * IN), Emu(12700), BORDER)
    if idx is not None:
        txt(s, int(11.9 * IN), int(0.5 * IN), int(0.9 * IN), int(0.3 * IN),
            [(f"{idx:02d}", 12, True, BORDER)], align=PP_ALIGN.RIGHT)


def bullet(s, x, y, w, color, head, body, hsize=13, bsize=11):
    rect(s, x, y + int(0.07 * IN), int(0.13 * IN), int(0.13 * IN), color)
    if head:
        txt(s, x + int(0.24 * IN), y, w - int(0.3 * IN), int(0.35 * IN),
            [(head, hsize, True, INK)])
        txt(s, x + int(0.24 * IN), y + int(0.32 * IN), w - int(0.3 * IN),
            int(0.7 * IN), [(body, bsize, False, INK_MUTED)], line_spacing=1.12)
    else:
        txt(s, x + int(0.24 * IN), y, w - int(0.3 * IN), int(0.6 * IN),
            [(body, bsize, False, INK)], line_spacing=1.12)


# ============================================================ 01 封面
def s_cover():
    s = slide()
    rect(s, 0, 0, SW, SH, PRIMARY_DK)
    rect(s, 0, 0, int(0.16 * IN), SH, PRIMARY)
    chip(s, int(0.85 * IN), int(0.9 * IN), int(5.7 * IN), int(0.42 * IN),
         "2026 新北市 AI 智慧城市黑客松競賽 ｜ 教育局組",
         RGBColor(0x2A, 0x4A, 0x6B), fg=RGBColor(0xCF, 0xE0, 0xF0), size=13)
    txt(s, int(0.85 * IN), int(1.95 * IN), int(11.6 * IN), int(1.3 * IN),
        [[("小小守護員 ", 50, True, WHITE),
          ("Smart Watchdog", 50, True, RGBColor(0x7F, 0xB5, 0xDA))]])
    txt(s, int(0.85 * IN), int(3.2 * IN), int(11.6 * IN), int(0.7 * IN),
        [("AI × 鑑識會計，打造教保機構智慧風險預警管理系統", 21, True,
          RGBColor(0xE6, 0xEE, 0xF6))])
    bar = rect(s, int(0.85 * IN), int(4.35 * IN), int(11.6 * IN),
               int(1.05 * IN), RGBColor(0x24, 0x42, 0x60), rounded=True)
    txt(s, int(1.15 * IN), int(4.45 * IN), int(11.0 * IN), int(0.9 * IN),
        [[("別人做幼兒園風險評分，我們做「", 15, False, RGBColor(0xD7, 0xE3, 0xEF)),
          ("AI 稽查官", 15, True, GOLD),
          ("」──用審計界抓弊案的鑑識會計", 15, False, RGBColor(0xD7, 0xE3, 0xEF))],
         [("算出可解釋的白盒子風險分數，讓生成式 AI 產出稽查建議，把稽查人力產能放大十倍。",
           15, False, RGBColor(0xD7, 0xE3, 0xEF))]],
        anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.15)
    txt(s, int(0.85 * IN), int(6.2 * IN), int(11.6 * IN), int(0.9 * IN),
        [[("公務後台（稽查官）:8601", 12, True, RGBColor(0x9F, 0xBE, 0xDC)),
          ("　｜　", 12, False, RGBColor(0x6E, 0x8A, 0xA6)),
          ("公眾查詢網（家長）:8602", 12, True, RGBColor(0x9F, 0xBE, 0xDC))],
         [("Live on AWS EC2 · systemd 常駐 · GitHub Actions 自動部署",
           11, False, RGBColor(0x6E, 0x8A, 0xA6))]], space_after=3)


# ============================================================ 02 為什麼要做（動機/實證）
def s_why():
    s = slide()
    header(s, "WHY ｜ 我們為什麼做這件事", "一個安全事件的背後，往往有可量化的財務前兆",
           2, chapter="第一章　問題")
    txt(s, int(0.85 * IN), int(1.45 * IN), int(11.6 * IN), int(0.55 * IN),
        [[("近年教保機構不當管理與兒童安全事件頻傳。我們追問一個問題：", 13, False, INK_MUTED),
          ("這些事件是否有更早、可從公開資料看見的前兆？", 13, True, PRIMARY)]],
        line_spacing=1.15)

    # 因果鏈（文獻實證，用「關聯」不用「導致」）
    chain = [
        ("經費薄弱", "財務吃緊、\n入不敷出", RISK_RED),
        ("師資比惡化", "人力不足、\n照顧超載", RISK_ORANGE),
        ("照顧品質下降", "壓力升高、\n監督不足", RISK_YELLOW),
        ("安全風險上升", "威脅兒童安全\n情況增加", GRAYBOX),
    ]
    x0 = int(0.85 * IN)
    bw = int(2.35 * IN)
    y = int(2.2 * IN)
    bh = int(1.25 * IN)
    gapx = (int(11.6 * IN) - len(chain) * bw) // (len(chain) - 1)
    for i, (t, d, color) in enumerate(chain):
        x = x0 + i * (bw + gapx)
        rect(s, x, y, bw, bh, WHITE, line=color, line_w=2, rounded=True)
        rect(s, x, y, int(0.09 * IN), bh, color)
        txt(s, x + int(0.25 * IN), y + int(0.16 * IN), bw - int(0.4 * IN),
            int(0.4 * IN), [(t, 14, True, INK)])
        txt(s, x + int(0.25 * IN), y + int(0.6 * IN), bw - int(0.4 * IN),
            int(0.6 * IN), [(d, 10.5, False, INK_MUTED)], line_spacing=1.05)
        if i < len(chain) - 1:
            arrow(s, x + bw + int(0.03 * IN), y + int(0.45 * IN),
                  gapx - int(0.06 * IN), int(0.34 * IN), color)

    # 文獻佐證卡
    ty = int(3.85 * IN)
    txt(s, x0, ty, int(11.6 * IN), int(0.35 * IN),
        [("國際實證文獻佐證（措辭均為「關聯 associated」，非單一因果）", 13, True, INK)])
    evid = [
        ("師資比 ↔ 安全",
         "「第二位照顧者在場，與幼托機構中兒虐可能性降低有關聯」；較低師生比與「較少威脅兒童安全的情況」有關。",
         "Child Trends (2017)，引 Howes 1990"),
        ("照顧超載 ↔ 失控",
         "當照顧者負責超過其能力所及的兒童數，壓力升高、可能失去自制力。",
         "ERIC ED281642"),
        ("經費補助 ↔ 兒虐率",
         "較慷慨的托育補助政策（所得資格放寬）與較低的兒虐調查／通報率在州層級有關聯。",
         "MDPI Children (2023)；PMC 補助研究"),
    ]
    ew = (int(11.6 * IN) - 2 * int(0.28 * IN)) // 3
    ey = int(4.28 * IN)
    eh = int(2.15 * IN)
    for i, (tag, body, ref) in enumerate(evid):
        x = x0 + i * (ew + int(0.28 * IN))
        card(s, x, ey, ew, eh, fill=WHITE)
        rect(s, x, ey, ew, int(0.07 * IN), PRIMARY)
        txt(s, x + int(0.22 * IN), ey + int(0.18 * IN), ew - int(0.4 * IN),
            int(0.35 * IN), [(tag, 13, True, PRIMARY)])
        txt(s, x + int(0.22 * IN), ey + int(0.6 * IN), ew - int(0.4 * IN),
            int(1.1 * IN), [(body, 10.5, False, INK)], line_spacing=1.15)
        txt(s, x + int(0.22 * IN), ey + eh - int(0.5 * IN), ew - int(0.4 * IN),
            int(0.42 * IN), [[("來源：", 9, True, ACCENT),
                              (ref, 9, False, INK_MUTED)]], line_spacing=1.0)

    txt(s, x0, int(6.6 * IN), int(11.6 * IN), int(0.4 * IN),
        [[("我們的切入點：", 12, True, RISK_RED),
          ("與其等安全事件發生才被動稽查，不如把「財務薄弱」當成可量化的最早期前兆訊號，事前示警。",
           12, False, INK_MUTED)]], line_spacing=1.1)


# ============================================================ 03 四痛點
def s_pain():
    s = slide()
    header(s, "PAIN POINTS ｜ 現況痛點", "現行監理的四個結構性缺口", 3, chapter="第一章　問題")
    pains = [
        ("01", "資料分散、整合困難",
         "基本資料、評鑑、裁罰、收費、決算散落各處、格式不一，未納入即時輿情，無法形成完整風險判斷。"),
        ("02", "財務異常難及早發現",
         "決算與財報雖依法公告，卻缺乏與收費、園所規模的交叉勾稽，數字異常往往事後才被發現。"),
        ("03", "缺乏可量化的預警工具",
         "沒有標準化、可量化的風險評估方法，難以從大量機構中篩出該優先關注的高風險對象。"),
        ("04", "人力吃緊、決策缺依據",
         "機構數量龐大，仰賴人工逐一篩選耗時費力，資源配置缺乏數據支撐的決策依據。"),
    ]
    x0 = int(0.85 * IN)
    gap = int(0.3 * IN)
    cw = (int(11.6 * IN) - gap) // 2
    ch = int(2.15 * IN)
    y0 = int(1.7 * IN)
    for i, (num, title, body) in enumerate(pains):
        col = i % 2
        row = i // 2
        x = x0 + col * (cw + gap)
        y = y0 + row * (ch + int(0.3 * IN))
        card(s, x, y, cw, ch)
        rect(s, x, y, int(0.09 * IN), ch, RISK_ORANGE)
        txt(s, x + int(0.28 * IN), y + int(0.28 * IN), int(1.1 * IN),
            int(0.6 * IN), [(num, 30, True, RGBColor(0xC6, 0xCE, 0xD8))])
        txt(s, x + int(1.25 * IN), y + int(0.32 * IN), cw - int(1.5 * IN),
            int(0.5 * IN), [(title, 17, True, INK)])
        txt(s, x + int(1.25 * IN), y + int(0.92 * IN), cw - int(1.5 * IN),
            int(1.1 * IN), [(body, 12, False, INK_MUTED)], line_spacing=1.2)


# ============================================================ 04 解法總覽
def s_solution():
    s = slide()
    header(s, "SOLUTION ｜ 解決方案說明", "抓資料 → 算風險 → 出建議：三段式 AI 稽查官",
           4, chapter="第二章　解法")
    steps = [
        ("抓資料", "整合公開多源資料",
         ["公校決算書（PDF 文字層抽取）", "非營利園掃描財報（Bedrock/OCR）",
          "裁罰、評鑑、收費、社群輿情"], PRIMARY),
        ("算風險", "鑑識會計白盒子分數",
         ["班佛定律、Beneish、Altman、孤立森林", "財務比率交叉勾稽、基金餘額勾稽",
          "0–100 可攤開解釋，非黑盒子"], ACCENT),
        ("出建議", "生成式 AI 稽查輔助",
         ["AWS Bedrock（Claude）翻譯數字成白話", "指出異常、給具體查核方向",
          "責任 AI：風險 ≠ 違法，附證據鏈"], RISK_GREEN),
    ]
    x0 = int(0.85 * IN)
    gap = int(0.35 * IN)
    cw = (int(11.6 * IN) - 2 * gap) // 3
    y0 = int(1.65 * IN)
    ch = int(3.35 * IN)
    for i, (tag, sub, items, color) in enumerate(steps):
        x = x0 + i * (cw + gap)
        card(s, x, y0, cw, ch, fill=WHITE)
        rect(s, x, y0, cw, int(0.85 * IN), color, rounded=True)
        rect(s, x, y0 + int(0.6 * IN), cw, int(0.25 * IN), color)
        chip(s, x + int(0.25 * IN), y0 + int(0.22 * IN), int(0.5 * IN),
             int(0.42 * IN), str(i + 1), WHITE, fg=color, size=17)
        txt(s, x + int(0.9 * IN), y0 + int(0.16 * IN), cw - int(1.0 * IN),
            int(0.6 * IN), [(tag, 20, True, WHITE)], anchor=MSO_ANCHOR.MIDDLE)
        txt(s, x + int(0.3 * IN), y0 + int(1.05 * IN), cw - int(0.6 * IN),
            int(0.4 * IN), [(sub, 14, True, INK)])
        yy = y0 + int(1.6 * IN)
        for it in items:
            rect(s, x + int(0.32 * IN), yy + int(0.08 * IN), int(0.12 * IN),
                 int(0.12 * IN), color)
            txt(s, x + int(0.55 * IN), yy, cw - int(0.85 * IN), int(0.6 * IN),
                [(it, 11.5, False, INK_MUTED)], line_spacing=1.1)
            yy += int(0.56 * IN)
    y = int(5.4 * IN)
    benefits = [("提升風險辨識率", "從公開資料篩出高風險機構"),
                ("縮短預警時間", "事後被動稽查 → 事前主動示警"),
                ("降低人力負擔", "有限人力精準投放最該查的園")]
    bw = (int(11.6 * IN) - 2 * int(0.3 * IN)) // 3
    for i, (t, d) in enumerate(benefits):
        x = x0 + i * (bw + int(0.3 * IN))
        card(s, x, y, bw, int(1.15 * IN))
        rect(s, x, y, int(0.09 * IN), int(1.15 * IN), RISK_GREEN)
        txt(s, x + int(0.28 * IN), y + int(0.18 * IN), bw - int(0.4 * IN),
            int(0.4 * IN), [(t, 14, True, INK)])
        txt(s, x + int(0.28 * IN), y + int(0.62 * IN), bw - int(0.4 * IN),
            int(0.45 * IN), [(d, 11, False, INK_MUTED)], line_spacing=1.1)


# ============================================================ 05 護城河 鑑識會計
def s_forensic():
    s = slide()
    header(s, "MOAT ｜ 差異化護城河", "鑑識會計搬進幼兒園：多層方法，全部有文獻",
           5, chapter="第二章　解法")
    txt(s, int(0.85 * IN), int(1.42 * IN), int(11.6 * IN), int(0.4 * IN),
        [[("90% 隊伍只做「風險評分」，", 12.5, False, INK_MUTED),
          ("我們用審計界抓弊案的鑑識會計方法", 12.5, True, PRIMARY),
          ("，每一層都可解釋、有學術佐證。", 12.5, False, INK_MUTED)]])
    methods = [
        ("班佛定律 Benford's Law", "逐筆明細首位數分布偏離自然律 → 數字造假傾向（MAD + 卡方）", "Nigrini；Durtschi 2004"),
        ("Beneish M-Score 改良版", "收入與支出成長背離、應計異常 → 盈餘操縱（非營利在地化）", "Beneish 1999"),
        ("Altman Z'' 困境分", "財務困境代理比率 → 對應舞弊三角的「壓力」構面", "Altman 1968 / 2013"),
        ("Isolation Forest + SHAP", "非監督多維異常偵測，SHAP 解釋為何異常，維持白盒", "Protiviti 白皮書"),
        ("財務比率交叉勾稽 + IQR", "每幼兒單位成本、人事費占比、收支比 vs 同儕離群", "PCAOB AS 2305"),
        ("基金餘額勾稽", "期末 = 期初 + 本期賸餘；跨年度連續性，接不上即紅旗", "政府基金會計恆等式"),
    ]
    x0 = int(0.85 * IN)
    gap = int(0.28 * IN)
    cw = (int(11.6 * IN) - 2 * gap) // 3
    ch = int(1.7 * IN)
    y0 = int(2.05 * IN)
    for i, (name, desc, ref) in enumerate(methods):
        col = i % 3
        row = i // 3
        x = x0 + col * (cw + gap)
        y = y0 + row * (ch + int(0.25 * IN))
        card(s, x, y, cw, ch, fill=WHITE)
        rect(s, x, y, cw, int(0.08 * IN), PRIMARY)
        txt(s, x + int(0.24 * IN), y + int(0.2 * IN), cw - int(0.45 * IN),
            int(0.55 * IN), [(name, 13.5, True, INK)])
        txt(s, x + int(0.24 * IN), y + int(0.78 * IN), cw - int(0.45 * IN),
            int(0.7 * IN), [(desc, 10.5, False, INK_MUTED)], line_spacing=1.1)
        txt(s, x + int(0.24 * IN), y + int(1.42 * IN), cw - int(0.45 * IN),
            int(0.25 * IN),
            [[("文獻：", 9, True, ACCENT), (ref, 9, False, INK_MUTED)]])


# ============================================================ 06 白盒子
def s_whitebox():
    s = slide()
    header(s, "EXPLAINABLE ｜ 白盒子風險分數", "禁止黑盒子：每一分都攤得開",
           6, chapter="第二章　解法")
    x0 = int(0.85 * IN)
    lw = int(5.5 * IN)
    card(s, x0, int(1.55 * IN), lw, int(2.55 * IN), fill=SURFACE)
    txt(s, x0 + int(0.3 * IN), int(1.68 * IN), lw - int(0.6 * IN), int(0.4 * IN),
        [("分項權重（可解釋加權，四項全計入）", 15, True, INK)])
    weights = [("財務異常", "45%", "鑑識會計多層方法", RISK_RED),
               ("裁罰紀錄", "30%", "事由分類 + 嚴重度 / 破窗效應", RISK_ORANGE),
               ("評鑑結果", "15%", "優0 / 良20 / 乙40 / 待改進90", RISK_YELLOW),
               ("網路輿情", "10%", "真實公開新聞負面度·上限15分", RISK_GREEN)]
    yy = int(2.12 * IN)
    for name, pct, desc, color in weights:
        rect(s, x0 + int(0.3 * IN), yy + int(0.04 * IN), int(0.14 * IN),
             int(0.4 * IN), color)
        txt(s, x0 + int(0.55 * IN), yy, int(1.5 * IN), int(0.45 * IN),
            [[(name + "  ", 12.5, True, INK), (pct, 14, True, color)]])
        txt(s, x0 + int(2.2 * IN), yy + int(0.05 * IN), int(3.1 * IN),
            int(0.45 * IN), [(desc, 9.5, False, INK_MUTED)])
        yy += int(0.44 * IN)
    txt(s, x0 + int(0.3 * IN), int(3.68 * IN), lw - int(0.6 * IN),
        int(0.42 * IN),
        [("＊輿情已接入真實公開新聞爬蟲（Google/Bing News + 台灣媒體 RSS），",
          8.5, False, INK_MUTED),
         ("白盒 NLP 判負面度、每筆附原文可追溯，故正式計入總分（誠實揭露）",
          8.5, False, INK_MUTED)], line_spacing=1.05)

    rx = x0 + lw + int(0.4 * IN)
    rw = int(11.6 * IN) - lw - int(0.4 * IN)
    card(s, rx, int(1.55 * IN), rw, int(2.55 * IN), fill=WHITE)
    rect(s, rx, int(1.55 * IN), rw, int(0.55 * IN), PRIMARY, rounded=True)
    rect(s, rx, int(1.9 * IN), rw, int(0.2 * IN), PRIMARY)
    txt(s, rx + int(0.3 * IN), int(1.63 * IN), rw - int(0.6 * IN), int(0.4 * IN),
        [("判定範例：新北市立林口幼兒園 59.0 分", 14, True, WHITE),],
        anchor=MSO_ANCHOR.MIDDLE)
    lines = [("財務異常  53.4 × 0.45", "= 24.0", RISK_RED),
             ("裁罰(2次) 90  × 0.30", "= 27.0", RISK_ORANGE),
             ("評鑑(乙)  40  × 0.15", "=  6.0", RISK_YELLOW),
             ("輿情(中性)20  × 0.10", "=  2.0", RISK_GREEN)]
    yy = int(2.2 * IN)
    for left, right, color in lines:
        txt(s, rx + int(0.35 * IN), yy, int(3.6 * IN), int(0.4 * IN),
            [(left, 12.5, False, INK)])
        txt(s, rx + int(3.7 * IN), yy, int(1.4 * IN), int(0.4 * IN),
            [(right, 12.5, True, color)], align=PP_ALIGN.RIGHT)
        yy += int(0.4 * IN)
    rect(s, rx + int(0.35 * IN), yy, rw - int(0.7 * IN), Emu(12700), BORDER)
    yy += int(0.08 * IN)
    txt(s, rx + int(0.35 * IN), yy, int(3.6 * IN), int(0.4 * IN),
        [("總風險分（相對分級：高）", 13, True, INK)])
    txt(s, rx + int(3.7 * IN), yy, int(1.4 * IN), int(0.4 * IN),
        [("59.0", 17, True, RISK_RED)], align=PP_ALIGN.RIGHT)

    y = int(4.35 * IN)
    txt(s, x0, y, int(11.6 * IN), int(0.35 * IN),
        [("模型鑑別力驗證（以官方裁罰為標籤，python -m src.validate 即時產生）",
          13, True, INK)])
    metrics = [("AUC-ROC", "0.906", "辨識力優異 (>0.9)"),
               ("Recall", "1.00", "被裁罰園零漏抓"),
               ("相關係數", "0.733", "風險分與裁罰高度正相關"),
               ("權重敏感度", "ρ≥0.97", "改權重排名幾乎不變")]
    mw = (int(11.6 * IN) - 3 * int(0.25 * IN)) // 4
    yb = int(4.65 * IN)
    for i, (t, v, d) in enumerate(metrics):
        x = x0 + i * (mw + int(0.25 * IN))
        card(s, x, yb, mw, int(1.55 * IN))
        rect(s, x, yb, mw, int(0.07 * IN), RISK_GREEN)
        txt(s, x, yb + int(0.2 * IN), mw, int(0.35 * IN),
            [(t, 12, True, INK_MUTED)], align=PP_ALIGN.CENTER)
        txt(s, x, yb + int(0.55 * IN), mw, int(0.5 * IN),
            [(v, 26, True, PRIMARY)], align=PP_ALIGN.CENTER)
        txt(s, x + int(0.1 * IN), yb + int(1.08 * IN), mw - int(0.2 * IN),
            int(0.4 * IN), [(d, 9.5, False, INK_MUTED)],
            align=PP_ALIGN.CENTER, line_spacing=1.0)


# ============================================================ 07 資料全景 + 靜態/動態
def s_data_overview():
    s = slide()
    header(s, "DATA ｜ 數據及資料運用 (1/2)", "靜態一手精抽 × 動態官方 API：雙軌互補",
           7, chapter="第三章　資料")
    txt(s, int(0.85 * IN), int(1.42 * IN), int(11.6 * IN), int(0.4 * IN),
        [[("回應痛點 1：", 12, True, PRIMARY),
          ("把系統從「靜態一次性資料」升級為「動態串接官方開放資料 + 快取 + 離線備援」的整合平台。",
           12, False, INK_MUTED)]], line_spacing=1.1)

    x0 = int(0.85 * IN)
    gap = int(0.4 * IN)
    cw = (int(11.6 * IN) - gap) // 2
    y0 = int(2.05 * IN)
    ch = int(3.1 * IN)
    # 靜態
    card(s, x0, y0, cw, ch, fill=WHITE)
    rect(s, x0, y0, cw, int(0.7 * IN), PRIMARY_DK, rounded=True)
    rect(s, x0, y0 + int(0.45 * IN), cw, int(0.25 * IN), PRIMARY_DK)
    txt(s, x0 + int(0.3 * IN), y0 + int(0.08 * IN), cw - int(0.6 * IN),
        int(0.55 * IN), [[("靜態資料 ", 17, True, WHITE), ("STATIC", 12, True, GOLD)]],
        anchor=MSO_ANCHOR.MIDDLE)
    static_items = [
        ("公校決算書 PDF", "PyMuPDF 文字層抽取，含逐筆明細供班佛檢定"),
        ("非營利園掃描財報", "Tesseract OCR + Bedrock 多模態，自我勾稽把關"),
        ("地理座標（衍生）", "Nominatim geocoding 產生 lat/lng"),
    ]
    yy = y0 + int(0.95 * IN)
    for t, d in static_items:
        bullet(s, x0 + int(0.3 * IN), yy, cw - int(0.5 * IN), PRIMARY, t, d)
        yy += int(0.72 * IN)
    # 動態
    rx = x0 + cw + gap
    card(s, rx, y0, cw, ch, fill=WHITE)
    rect(s, rx, y0, cw, int(0.7 * IN), RISK_GREEN, rounded=True)
    rect(s, rx, y0 + int(0.45 * IN), cw, int(0.25 * IN), RISK_GREEN)
    txt(s, rx + int(0.3 * IN), y0 + int(0.08 * IN), cw - int(0.6 * IN),
        int(0.55 * IN), [[("動態資料 ", 17, True, WHITE), ("LIVE API", 12, True, GOLD)]],
        anchor=MSO_ANCHOR.MIDDLE)
    dyn_items = [
        ("幼兒園基本資料 / 收費", "preschools.json（GeoJSON 含座標），HTTPS GET 免金鑰"),
        ("全國裁罰紀錄", "punish_all.json，含日期/法條/罰鍰，即時解析"),
        ("連接器 live_source.py", "load_live_dataset() 一鍵同步，UI 按鈕觸發"),
    ]
    yy = y0 + int(0.95 * IN)
    for t, d in dyn_items:
        bullet(s, rx + int(0.3 * IN), yy, cw - int(0.5 * IN), RISK_GREEN, t, d)
        yy += int(0.72 * IN)

    rect(s, x0, int(5.5 * IN), int(11.6 * IN), int(0.9 * IN), SURFACE,
         line=BORDER, line_w=1, rounded=True)
    txt(s, x0 + int(0.35 * IN), int(5.6 * IN), int(11.0 * IN), int(0.75 * IN),
        [[("為什麼雙軌？　", 13, True, PRIMARY),
          ("決算書需逐冊校對精抽才能做班佛檢定，適合靜態；基本資料/裁罰是結構化 JSON、量大時效敏感，適合動態即時串接。",
           12, False, INK_MUTED)]], anchor=MSO_ANCHOR.MIDDLE, line_spacing=1.15)


# ============================================================ 08 三層備援 + 治理
def s_data_resilience():
    s = slide()
    header(s, "DATA ｜ 數據及資料運用 (2/2)", "政府級韌性 + 誠實治理：外部源掛了也不倒",
           8, chapter="第三章　資料")
    # 三層備援
    x0 = int(0.85 * IN)
    txt(s, x0, int(1.45 * IN), int(11.6 * IN), int(0.35 * IN),
        [[("三層備援 Fallback Chain（src/live_source.py）：", 13, True, INK),
          ("即時網路 → 本地快取 → 版控快照，任一層可用即回傳，FetchResult 誠實回報新鮮度。",
           11.5, False, INK_MUTED)]])
    layers = [
        ("① 即時網路", "抓取成功 → 寫本地快取", "is_live = True", RISK_GREEN),
        ("② 本地快取", "抓取失敗 → 退回最近快取", "used_fallback = True", RISK_YELLOW),
        ("③ 版控快照", "GitHub Actions 每日更新進版控", "線上部署也讀得到", ACCENT),
    ]
    lw = (int(11.6 * IN) - 2 * int(0.28 * IN)) // 3
    ly = int(1.95 * IN)
    lh = int(1.55 * IN)
    for i, (t, act, flag, color) in enumerate(layers):
        x = x0 + i * (lw + int(0.28 * IN))
        card(s, x, ly, lw, lh, fill=WHITE)
        rect(s, x, ly, lw, int(0.5 * IN), color, rounded=True)
        rect(s, x, ly + int(0.28 * IN), lw, int(0.22 * IN), color)
        txt(s, x + int(0.2 * IN), ly + int(0.05 * IN), lw - int(0.4 * IN),
            int(0.42 * IN), [(t, 13, True, WHITE)], anchor=MSO_ANCHOR.MIDDLE)
        txt(s, x + int(0.22 * IN), ly + int(0.62 * IN), lw - int(0.4 * IN),
            int(0.5 * IN), [(act, 11.5, True, INK)], line_spacing=1.1)
        chip(s, x + int(0.22 * IN), ly + lh - int(0.5 * IN), lw - int(0.44 * IN),
             int(0.36 * IN), flag, SURFACE2, fg=PRIMARY, size=10)

    # KPI + 治理
    ky = int(3.75 * IN)
    txt(s, x0, ky, int(11.6 * IN), int(0.35 * IN),
        [("實際運算成果（真實資料，非模擬）", 13, True, INK)])
    kpis = [("61 間", "已完成鑑識會計評分"), ("1,114 間", "全市納管基本資料"),
            ("2,838 筆", "真實裁罰動態串接"), ("7,688 筆", "全國機構名冊快照")]
    kw = (int(11.6 * IN) - 3 * int(0.25 * IN)) // 4
    kky = int(4.15 * IN)
    for i, (v, d) in enumerate(kpis):
        x = x0 + i * (kw + int(0.25 * IN))
        card(s, x, kky, kw, int(1.15 * IN), fill=SURFACE)
        rect(s, x, kky, kw, int(0.07 * IN), PRIMARY)
        txt(s, x, kky + int(0.18 * IN), kw, int(0.45 * IN),
            [(v, 22, True, PRIMARY)], align=PP_ALIGN.CENTER)
        txt(s, x + int(0.08 * IN), kky + int(0.72 * IN), kw - int(0.16 * IN),
            int(0.4 * IN), [(d, 10, False, INK_MUTED)], align=PP_ALIGN.CENTER)

    gy = int(5.55 * IN)
    gov = [("誠實三態標記", "已確認 / 未確認 / 不適用；官方全量 API 未取得就標「未確認」，絕不虛構", RISK_GREEN),
           ("來源可追溯", "動態源標註 g0v 整理 + 原始教育部，記錄抓取時間，上架前抽查核對", ACCENT),
           ("責任 AI + 資安", "風險 ≠ 違法；唯讀 GET 不外傳；金鑰放 .env，上傳前掃描", PRIMARY)]
    gw = (int(11.6 * IN) - 2 * int(0.28 * IN)) // 3
    for i, (t, d, color) in enumerate(gov):
        x = x0 + i * (gw + int(0.28 * IN))
        card(s, x, gy, gw, int(1.2 * IN), fill=WHITE)
        rect(s, x, gy, int(0.09 * IN), int(1.2 * IN), color)
        txt(s, x + int(0.25 * IN), gy + int(0.14 * IN), gw - int(0.4 * IN),
            int(0.35 * IN), [(t, 12.5, True, INK)])
        txt(s, x + int(0.25 * IN), gy + int(0.52 * IN), gw - int(0.4 * IN),
            int(0.6 * IN), [(d, 10, False, INK_MUTED)], line_spacing=1.12)


# ============================================================ 09 AWS 架構圖
def s_aws():
    s = slide()
    header(s, "ARCHITECTURE ｜ AWS 雲端技術架構", "資料 → 鑑識引擎 → 雙介面，AWS 全託管",
           9, chapter="第四章　架構")
    x0 = int(0.7 * IN)
    full_w = int(11.9 * IN)
    top = int(1.5 * IN)

    def layer(y, h, title, color, fill):
        rect(s, x0, y, full_w, h, fill, line=BORDER, line_w=1, rounded=True)
        rect(s, x0, y, int(0.09 * IN), h, color)
        txt(s, x0 + int(0.22 * IN), y + int(0.07 * IN), int(4.0 * IN),
            int(0.3 * IN), [(title, 11, True, color)])

    def box(x, y, w, h, title, sub, fill, fg=WHITE, tsize=11.5):
        rect(s, x, y, w, h, fill, rounded=True)
        txt(s, x + int(0.08 * IN), y + int(0.1 * IN), w - int(0.16 * IN),
            int(0.42 * IN), [(title, tsize, True, fg)], align=PP_ALIGN.CENTER,
            anchor=MSO_ANCHOR.MIDDLE, line_spacing=0.95)
        if sub:
            txt(s, x + int(0.06 * IN), y + h - int(0.4 * IN),
                w - int(0.12 * IN), int(0.36 * IN), [(sub, 8.5, False, fg)],
                align=PP_ALIGN.CENTER, line_spacing=0.9)

    # L1
    y1 = top
    h1 = int(1.05 * IN)
    layer(y1, h1, "① 資料來源 DATA SOURCES", INK_MUTED, SURFACE)
    srcs = [("公校決算書", "PDF 文字層"), ("非營利園財報", "掃描影像"),
            ("裁罰／評鑑", "全國教保資訊網"), ("網路輿情", "新聞／社群")]
    bw = int(2.5 * IN)
    bx = x0 + int(0.95 * IN)
    for title, sub in srcs:
        box(bx, y1 + int(0.36 * IN), bw, int(0.58 * IN), title, sub, GRAYBOX)
        bx += bw + int(0.18 * IN)
    arrow(s, x0 + full_w // 2 - int(0.15 * IN), y1 + h1 + int(0.01 * IN),
          int(0.3 * IN), int(0.18 * IN), AWS_ORANGE, direction="down")

    # L2 AWS
    y2 = y1 + h1 + int(0.22 * IN)
    h2 = int(1.4 * IN)
    layer(y2, h2, "② AWS 雲端處理層 PROCESSING (boto3)", AWS_ORANGE,
          RGBColor(0xFC, 0xF3, 0xE6))
    aws_boxes = [("Amazon S3", "原始／衍生\n資料儲存"),
                 ("Textract /\nTesseract OCR", "掃描財報\n文字抽取"),
                 ("Amazon Bedrock\nClaude Sonnet 4.5", "多模態抽數字\n+ 生成建議"),
                 ("EC2 + IAM Role", "運算主機\n免金鑰外洩")]
    bx = x0 + int(0.95 * IN)
    for title, sub in aws_boxes:
        box(bx, y2 + int(0.38 * IN), bw, int(0.88 * IN), title, sub,
            AWS_ORANGE, tsize=11)
        bx += bw + int(0.18 * IN)
    arrow(s, x0 + full_w // 2 - int(0.15 * IN), y2 + h2 + int(0.01 * IN),
          int(0.3 * IN), int(0.18 * IN), PRIMARY, direction="down")

    # L3 core
    y3 = y2 + h2 + int(0.22 * IN)
    h3 = int(0.92 * IN)
    layer(y3, h3, "③ 鑑識風險中台 CORE ENGINE (src/) — 行政 / 民眾共用", PRIMARY,
          SURFACE2)
    eng = ["鑑識會計\nforensic.py", "白盒評分\nrisk_score.py",
           "證據鏈\nevidence.py", "AI 報告\nai_report.py", "地理編碼\ngeocode.py"]
    ew = int(2.0 * IN)
    ex = x0 + int(0.95 * IN)
    for t in eng:
        box(ex, y3 + int(0.3 * IN), ew, int(0.52 * IN), t, "", PRIMARY, tsize=9.5)
        ex += ew + int(0.15 * IN)
    arrow(s, x0 + full_w // 2 - int(0.15 * IN), y3 + h3 + int(0.01 * IN),
          int(0.3 * IN), int(0.18 * IN), PRIMARY_DK, direction="down")

    # L4 interfaces
    y4 = y3 + h3 + int(0.22 * IN)
    h4 = int(0.82 * IN)
    half = (full_w - int(0.3 * IN)) // 2
    box(x0, y4, half, h4, "公務後台 :8601（稽查官）",
        "風險排名·雷達圖·案件流·派工·AI建議｜全欄位可見", PRIMARY_DK, tsize=12.5)
    box(x0 + half + int(0.3 * IN), y4, half, h4, "公眾查詢網 :8602（家長）",
        "找園·距離·收費·評鑑·輿情｜資料層移除風險欄位", RISK_GREEN, tsize=12.5)
    txt(s, x0, y4 + h4 + int(0.04 * IN), full_w, int(0.32 * IN),
        [[("同一中台、兩種權限投影：", 10, True, PRIMARY),
          ("authorize_dataframe(df, ROLE_PARENT) 於資料層移除 risk_*，家長端根本拿不到風險分（非前端隱藏）　·　CI/CD：GitHub Actions push→main → EC2 self-hosted runner → systemd 常駐 + 健康檢查",
           9, False, INK_MUTED)]], line_spacing=1.0)


# ============================================================ 10 介面A 公務後台
def s_ui_gov():
    s = slide()
    header(s, "UI / FLOW ｜ 介面與操作流程 (1/2)", "公務後台 :8601 — 稽查官的作戰工作台",
           10, chapter="第五章　操作")
    txt(s, int(0.85 * IN), int(1.42 * IN), int(11.6 * IN), int(0.4 * IN),
        [[("使用者：", 12, True, PRIMARY), ("教育局 / 稽查員　｜　", 12, False, INK_MUTED),
          ("動線：全局監控 → 下鑽單園 → 下決定 → 派工結案", 12, True, INK)]])
    flow = [
        ("1  風險總覽", "KPI 帶 + 完整排名表 + 各行政區風險組成堆疊圖，一眼看出該優先查誰"),
        ("2  風險地圖", "Leaflet + OpenStreetMap，紅/黃/綠標記，排稽查路線精準投放"),
        ("3  單園工作台", "雷達圖攤開四分項 + 證據鏈下鑽（分數→特徵→原始決算→PDF來源）"),
        ("4  AI 稽查建議", "Bedrock 產出白話建議：這間該查什麼憑證，責任 AI 附來源"),
        ("5  案件狀態流", "待研判→建議派查→調查中→結案，附時間戳與稽核軌跡"),
        ("6  派工 / 資料整合", "排除已稽查、資料來源矩陣、模型鑑別力驗證、健康檢查"),
    ]
    x0 = int(0.85 * IN)
    gap = int(0.28 * IN)
    cw = (int(11.6 * IN) - 2 * gap) // 3
    ch = int(1.7 * IN)
    y0 = int(2.0 * IN)
    for i, (t, d) in enumerate(flow):
        col = i % 3
        row = i // 3
        x = x0 + col * (cw + gap)
        y = y0 + row * (ch + int(0.28 * IN))
        card(s, x, y, cw, ch, fill=WHITE)
        rect(s, x, y, cw, int(0.55 * IN), PRIMARY, rounded=True)
        rect(s, x, y + int(0.35 * IN), cw, int(0.2 * IN), PRIMARY)
        txt(s, x + int(0.22 * IN), y + int(0.06 * IN), cw - int(0.4 * IN),
            int(0.45 * IN), [(t, 14, True, WHITE)], anchor=MSO_ANCHOR.MIDDLE)
        txt(s, x + int(0.24 * IN), y + int(0.72 * IN), cw - int(0.45 * IN),
            int(0.95 * IN), [(d, 11, False, INK_MUTED)], line_spacing=1.15)
    y = int(5.95 * IN)
    states = [("待研判", RISK_YELLOW), ("建議派查", RISK_ORANGE),
              ("調查中", PRIMARY), ("結案·屬實", RISK_RED),
              ("結案·不成立", RISK_GREEN)]
    sx = x0
    sw2 = int(1.9 * IN)
    for i, (name, color) in enumerate(states):
        chip(s, sx, y, sw2, int(0.5 * IN), name, color, size=12)
        if i < len(states) - 1:
            txt(s, sx + sw2, y, int(0.28 * IN), int(0.5 * IN),
                [("→", 16, True, INK_MUTED)], align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.MIDDLE)
        sx += sw2 + int(0.28 * IN)


# ============================================================ 11 介面B 公眾網
def s_ui_public():
    s = slide()
    header(s, "UI / FLOW ｜ 介面與操作流程 (2/2)", "公眾查詢網 :8602 — 家長「安心找幼兒園」",
           11, chapter="第五章　操作")
    txt(s, int(0.85 * IN), int(1.42 * IN), int(11.6 * IN), int(0.55 * IN),
        [[("使用者：", 12, True, RISK_GREEN), ("一般民眾 / 家長（無需登入）　｜　", 12, False, INK_MUTED),
          ("與後台同一中台但資料層移除所有風險分數，家長端根本拿不到 risk_total", 12, True, INK)]],
        line_spacing=1.15)
    x0 = int(0.85 * IN)
    lw = int(5.6 * IN)
    needs = [("距離近", "輸入地址 → Nominatim 定位 → 找鄰近幼兒園、地圖標點"),
             ("看得懂學費", "公開收費揭露，透明比較"),
             ("安全放心", "公開評鑑、裁罰狀態、輿情觀測（平靜期/有討論/值得留意）")]
    yy = int(2.15 * IN)
    for t, d in needs:
        card(s, x0, yy, lw, int(1.15 * IN), fill=WHITE)
        rect(s, x0, yy, int(0.09 * IN), int(1.15 * IN), RISK_GREEN)
        txt(s, x0 + int(0.3 * IN), yy + int(0.16 * IN), lw - int(0.5 * IN),
            int(0.4 * IN), [(t, 15, True, INK)])
        txt(s, x0 + int(0.3 * IN), yy + int(0.6 * IN), lw - int(0.5 * IN),
            int(0.5 * IN), [(d, 11, False, INK_MUTED)], line_spacing=1.1)
        yy += int(1.3 * IN)
    rx = x0 + lw + int(0.4 * IN)
    rw = int(11.6 * IN) - lw - int(0.4 * IN)
    card(s, rx, int(2.15 * IN), rw, int(3.75 * IN), fill=SURFACE)
    rect(s, rx, int(2.15 * IN), rw, int(0.55 * IN), RISK_GREEN, rounded=True)
    rect(s, rx, int(2.5 * IN), rw, int(0.2 * IN), RISK_GREEN)
    txt(s, rx + int(0.3 * IN), int(2.22 * IN), rw - int(0.6 * IN), int(0.42 * IN),
        [("設計原則：溫暖、誠實、不恐慌", 15, True, WHITE)], anchor=MSO_ANCHOR.MIDDLE)
    points = [
        "不用後台「高/中/低風險」字眼，改用描述性「近期關注度」並附依據",
        "地圖用柔和暖色階（非警報紅），避免造成家長不必要恐慌",
        "輿情即時爬公開新聞 RSS，每則附原文連結與時間，可追溯",
        "地址定位用 OpenStreetMap Nominatim（免金鑰，不用 Google Maps）",
        "資料層 authorize_dataframe(df, ROLE_PARENT) 二次防禦，權限在資料層擋",
    ]
    py = int(2.95 * IN)
    for p in points:
        rect(s, rx + int(0.32 * IN), py + int(0.08 * IN), int(0.12 * IN),
             int(0.12 * IN), RISK_GREEN)
        txt(s, rx + int(0.55 * IN), py, rw - int(0.85 * IN), int(0.6 * IN),
            [(p, 11.5, False, INK)], line_spacing=1.1)
        py += int(0.58 * IN)


# ============================================================ 12 收尾
def s_close():
    s = slide()
    rect(s, 0, 0, SW, SH, PRIMARY_DK)
    rect(s, 0, 0, int(0.16 * IN), SH, PRIMARY)
    txt(s, int(0.85 * IN), int(0.8 * IN), int(11.5 * IN), int(0.4 * IN),
        [("第六章　結論　·　為什麼是我們", 14, True, RGBColor(0x9F, 0xBE, 0xDC))])
    txt(s, int(0.85 * IN), int(1.25 * IN), int(11.5 * IN), int(0.7 * IN),
        [("鑑識會計護城河 × 白盒可解釋 × 誠實可規模化", 28, True, WHITE)])
    items = [
        ("護城河", "鑑識會計多層方法，每層有文獻佐證。90% 隊伍不會講「鑑識會計」四個字。"),
        ("政府敢用", "白盒子分數可攤開拆解，責任 AI 全程「風險 ≠ 違法」附證據鏈，禁得起追問。"),
        ("真的能跑", "雙 app live on AWS EC2、61 間實測評分、AUC 0.906，Demo 當場可操作。"),
        ("誠實可擴", "抽樣深度 61 間 + 全市涵蓋 1,114 間，資料三態標示，架構可規模化至全市。"),
    ]
    x0 = int(0.85 * IN)
    gap = int(0.3 * IN)
    cw = (int(11.5 * IN) - gap) // 2
    ch = int(1.5 * IN)
    y0 = int(2.4 * IN)
    for i, (t, d) in enumerate(items):
        col = i % 2
        row = i // 2
        x = x0 + col * (cw + gap)
        y = y0 + row * (ch + int(0.25 * IN))
        rect(s, x, y, cw, ch, RGBColor(0x24, 0x42, 0x60), rounded=True)
        rect(s, x, y, int(0.09 * IN), ch, GOLD)
        txt(s, x + int(0.3 * IN), y + int(0.2 * IN), cw - int(0.5 * IN),
            int(0.4 * IN), [(t, 16, True, GOLD)])
        txt(s, x + int(0.3 * IN), y + int(0.66 * IN), cw - int(0.5 * IN),
            int(0.8 * IN), [(d, 12, False, RGBColor(0xDD, 0xE7, 0xF1))],
            line_spacing=1.2)
    txt(s, int(0.85 * IN), int(6.35 * IN), int(11.5 * IN), int(0.6 * IN),
        [[("小小守護員 Smart Watchdog", 16, True, WHITE),
          ("　｜　讓事後被動稽查，提前為事前主動示警。", 14, False,
           RGBColor(0xB9, 0xCA, 0xDD))]])


def main():
    s_cover()
    s_why()
    s_pain()
    s_solution()
    s_forensic()
    s_whitebox()
    s_data_overview()
    s_data_resilience()
    s_aws()
    s_ui_gov()
    s_ui_public()
    s_close()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    prs.save(OUT)
    print(f"[OK] 已產出 {OUT}（{len(prs.slides._sldIdLst)} 頁）")


if __name__ == "__main__":
    main()
