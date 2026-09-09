"""
輿情分析（小樣本示範）
======================================
抓少量幼兒園相關網路評論，用簡易情緒分析標記正負面，
負面比例併入 score_sentiment（輿情分）。範圍刻意小，為加分亮點。

Demo 版用內建小樣本 + 關鍵詞情緒法（可離線跑）。
接上 Bedrock 後可改用 Claude 做更準的情緒判讀，架構相同。
"""
import os
import sys

import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import common  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜輿情分析",
    header_title="輿情分析",
    subtitle="網路評論情緒分析（離線示範，不計入風險分）。展示架構可規模化至全體機構的能力。",
    module="輿情分析",
)

df = common.require_data()

# ---------- 內建小樣本評論（示範用，實際應由爬蟲取得）----------
# 每則：(月份, 評論內容, 標註情緒)
SAMPLE_COMMENTS = {
    "新北市立林口幼兒園": [
        ("1月", "老師很有耐心，孩子很喜歡上學", "pos"),
        ("2月", "聽說收費有爭議，家長群組在討論", "neg"),
        ("3月", "環境還算乾淨，但人數好像超收", "neg"),
        ("3月", "報名很難抽，代表很多人想讀", "pos"),
        ("4月", "餐點份量偏少，反映後沒改善", "neg"),
        ("5月", "又聽到超收的傳聞，家長很擔心", "neg"),
    ],
    "新北市立深坑幼兒園": [
        ("1月", "財務公開不夠透明，希望改善", "neg"),
        ("2月", "餐點普通，設施有點舊", "neg"),
        ("3月", "交通方便，老師親切", "pos"),
        ("4月", "退費流程很麻煩，溝通不良", "neg"),
    ],
    "新北市立板橋幼兒園": [
        ("1月", "口碑很好，老師專業", "pos"),
        ("2月", "活動豐富，孩子成長很多", "pos"),
        ("3月", "報名秒殺，很搶手", "pos"),
        ("4月", "環境乾淨，餐點用心", "pos"),
    ],
}

NEG_WORDS = ["爭議", "超收", "不透明", "舊", "投訴", "缺失", "違規", "退費", "髒", "麻煩", "偏少"]
POS_WORDS = ["耐心", "喜歡", "親切", "專業", "乾淨", "方便", "豐富", "口碑", "搶手", "用心"]

# 主題分類關鍵詞（讓稽查員看出「民眾在氣什麼」）
TOPIC_WORDS = {
    "收費爭議": ["收費", "爭議", "退費", "費用"],
    "超收/員額": ["超收", "人數", "員額", "名額"],
    "餐點/衛生": ["餐點", "髒", "衛生", "份量", "偏少"],
    "設施/安全": ["設施", "舊", "安全", "環境"],
    "財務透明": ["財務", "不透明", "公開"],
    "師資/服務": ["老師", "耐心", "專業", "親切", "溝通", "麻煩"],
}


def classify_topic(text):
    for topic, words in TOPIC_WORDS.items():
        if any(w in text for w in words):
            return topic
    return "其他"


def score_comment(text):
    neg = sum(w in text for w in NEG_WORDS)
    pos = sum(w in text for w in POS_WORDS)
    if neg > pos:
        return "neg"
    if pos > neg:
        return "pos"
    return "neu"


LABEL_TEXT = {"pos": "正面", "neg": "負面", "neu": "中性"}
LABEL_COLOR = {"pos": common.LEVEL_COLOR["低"], "neg": common.LEVEL_COLOR["高"],
               "neu": common.MUTED}

park = st.selectbox("選擇機構", list(SAMPLE_COMMENTS.keys()))
comments = SAMPLE_COMMENTS[park]

common.section(f"{park}　網路評論情緒分析", "sentiment")

neg_n = sum(1 for _m, t, _l in comments if score_comment(t) == "neg")
total_n = len(comments)
neg_ratio = neg_n / total_n if total_n else 0

common.kpi_band([
    ("評論則數", f"{total_n}"),
    ("負面則數", f"{neg_n}", neg_ratio >= 0.5),
    ("負面比例", f"{neg_ratio*100:.0f}%", neg_ratio >= 0.5),
])

# ---------- 情緒趨勢折線（功能11）----------
common.section("負面情緒趨勢", "sentiment")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "逐月負面評論則數趨勢。負評連月攀升是「事前示警」訊號，"
    "比單一時點的絕對值更值得稽查關注。</div>",
    unsafe_allow_html=True,
)
months_order = ["1月", "2月", "3月", "4月", "5月", "6月"]
present_months = [m for m in months_order if any(c[0] == m for c in comments)]
neg_by_month = {m: 0 for m in present_months}
tot_by_month = {m: 0 for m in present_months}
for m, t, _l in comments:
    tot_by_month[m] += 1
    if score_comment(t) == "neg":
        neg_by_month[m] += 1

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=present_months, y=[neg_by_month[m] for m in present_months],
    mode="lines+markers", name="負面則數",
    line=dict(color=common.RISK["high"][0], width=2.5),
    marker=dict(size=9, color=common.RISK["high"][0]),
    fill="tozeroy", fillcolor=f"{common.RISK['high'][0]}22"))
fig.add_trace(go.Scatter(
    x=present_months, y=[tot_by_month[m] for m in present_months],
    mode="lines+markers", name="總則數",
    line=dict(color=common.PRIMARY, width=1.6, dash="dot"),
    marker=dict(size=6, color=common.PRIMARY)))
fig.update_layout(
    height=320, paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
    font=dict(family="Inter, Noto Sans TC, Microsoft JhengHei", color=common.INK),
    xaxis=dict(title="月份", gridcolor=common.BORDER),
    yaxis=dict(title="評論則數", gridcolor=common.BORDER, dtick=1),
    margin=dict(l=45, r=20, t=20, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
st.plotly_chart(fig, width="stretch")

# ---------- 主題分類彙整（功能11）----------
common.section("負面主題分類（民眾在氣什麼）", "sentiment")
st.markdown(
    f"<div style='color:{common.MUTED};font-size:.86rem;margin:-4px 0 10px;'>"
    "把負面評論自動歸類到稽查關注主題，讓稽查員一眼看出投訴集中在哪，"
    "現場查核就有方向。</div>",
    unsafe_allow_html=True,
)
topic_counts = {}
for _m, t, _l in comments:
    if score_comment(t) == "neg":
        topic = classify_topic(t)
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
if topic_counts:
    body = ""
    for topic, n in sorted(topic_counts.items(), key=lambda x: -x[1]):
        pct = n / neg_n * 100 if neg_n else 0
        body += (
            "<tr>"
            f"<td class='l'>{topic}</td>"
            f"<td style='color:{common.RISK['high'][0]};font-weight:600;'>{n}</td>"
            "<td>"
            "<span class='sw-bar-wrap'>"
            f"<span class='sw-bar-num' style='color:{common.RISK['high'][0]};'>{pct:.0f}%</span>"
            "<span class='sw-bar-track'>"
            f"<span class='sw-bar-fill' style='width:{pct:.0f}%;background:{common.RISK_BAR['high']};'></span>"
            "</span></span>"
            "</td></tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>負面主題</th><th>則數</th><th>佔負評比例</th>"
        f"</tr></thead><tbody>{body}</tbody></table>",
        unsafe_allow_html=True,
    )
    top_topic = max(topic_counts, key=topic_counts.get)
    common.callout(f"<b>主要投訴集中在「{top_topic}」</b>，"
                   "建議稽查時將此主題列為現場查核重點。")
else:
    common.empty_state("此機構無負面評論", "目前樣本中未偵測到負面評論。", "check")

common.section("評論明細", "sentiment")
LABEL_BG = {"pos": common.LEVEL_BG["低"], "neg": common.LEVEL_BG["高"], "neu": "#EEF0F3"}
body = ""
for month, text, _l in comments:
    pred = score_comment(text)
    tag = (f"<span class='sw-badge' style='background:{LABEL_BG[pred]};"
           f"color:{LABEL_COLOR[pred]};'>{LABEL_TEXT[pred]}</span>")
    topic = classify_topic(text) if pred == "neg" else "—"
    body += (f"<tr><td class='l' style='color:{common.INK_MUTED};'>{month}</td>"
             f"<td class='l'>{text}</td><td class='l'>{tag}</td>"
             f"<td class='l' style='color:{common.INK_2};'>{topic}</td></tr>")
st.markdown(
    "<table class='sw-table'><thead><tr>"
    "<th class='l'>月份</th><th class='l'>評論內容</th>"
    "<th class='l'>情緒</th><th class='l'>主題</th>"
    f"</tr></thead><tbody>{body}</tbody></table>",
    unsafe_allow_html=True,
)

# 情緒色點圖例
st.markdown(
    "<div style='margin-top:10px;color:%s;font-size:.82rem;'>情緒判定：%s&nbsp;&nbsp;%s&nbsp;&nbsp;%s</div>"
    % (common.MUTED,
       common.dot(LABEL_COLOR["pos"], "正面"),
       common.dot(LABEL_COLOR["neg"], "負面"),
       common.dot(LABEL_COLOR["neu"], "中性")),
    unsafe_allow_html=True,
)

common.callout(f"此頁為<b>離線示範</b>（內建樣本評論 + 關鍵詞情緒法），"
               f"負面比例約 <b>{neg_ratio*100:.0f}%</b>。"
               "目前<b>不計入</b>總風險分——真實網路輿情資料源尚未接入，"
               "為避免以示範值稀釋真實風險分。接入真實輿情後可再納入計分。")

with st.expander("這個功能如何規模化（架構說明）"):
    st.markdown(
        """
        目前為小樣本離線示範（內建評論 + 關鍵詞情緒法），驗證流程可跑。

        規模化路徑（架構相同、資料量放大）：
        1. 爬蟲定期抓 Google 評論、地方社團、新聞，存入資料湖（S3）
        2. 用 AWS Bedrock（Claude）做情緒判讀，比關鍵詞法更準、能理解語意
        3. 彙整每園負面比例，接入後即可納入總風險分計算並重新分配權重

        輿情是加分亮點；目前總風險分僅由已接入的真實資料（財務、裁罰、評鑑）組成。
        """
    )
