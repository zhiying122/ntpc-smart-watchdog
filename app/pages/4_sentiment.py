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

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib import auth  # noqa: E402
from lib import common  # noqa: E402
from lib import permissions  # noqa: E402

common.setup_page(
    page_title="Fiscalint｜輿情分析",
    header_title="輿情分析",
    subtitle="網路評論情緒分析（離線示範，不計入風險分）。展示架構可規模化至全體機構的能力。",
    module="輿情分析",
    allowed_roles=[permissions.ROLE_GOV, permissions.ROLE_INSPECTOR],
)

# 資料授權層：政府/稽查員皆為全欄位可見，仍走一致流程。
df = permissions.authorize_dataframe(common.require_data(),
                                     auth.get_current_role() or permissions.ROLE_GOV)

# ---------- 內建小樣本評論（示範用，實際應由爬蟲取得）----------
SAMPLE_COMMENTS = {
    "新北市立林口幼兒園": [
        ("老師很有耐心，孩子很喜歡上學", "pos"),
        ("聽說收費有爭議，家長群組在討論", "neg"),
        ("環境還算乾淨，但人數好像超收", "neg"),
        ("報名很難抽，代表很多人想讀", "pos"),
    ],
    "新北市立深坑幼兒園": [
        ("財務公開不夠透明，希望改善", "neg"),
        ("餐點普通，設施有點舊", "neg"),
        ("交通方便，老師親切", "pos"),
    ],
    "新北市立板橋幼兒園": [
        ("口碑很好，老師專業", "pos"),
        ("活動豐富，孩子成長很多", "pos"),
        ("報名秒殺，很搶手", "pos"),
    ],
}

NEG_WORDS = ["爭議", "超收", "不透明", "舊", "投訴", "缺失", "違規", "退費", "髒"]
POS_WORDS = ["耐心", "喜歡", "親切", "專業", "乾淨", "方便", "豐富", "口碑", "搶手"]


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

neg_n = sum(1 for t, _ in comments if score_comment(t) == "neg")
total_n = len(comments)
neg_ratio = neg_n / total_n if total_n else 0

common.kpi_band([
    ("評論則數", f"{total_n}"),
    ("負面則數", f"{neg_n}"),
    ("負面比例", f"{neg_ratio*100:.0f}%", neg_ratio >= 0.5),
])

common.section("評論明細", "sentiment")
LABEL_BG = {"pos": common.LEVEL_BG["低"], "neg": common.LEVEL_BG["高"], "neu": "#EEF0F3"}
body = ""
for text, _ in comments:
    pred = score_comment(text)
    tag = (f"<span class='sw-badge' style='background:{LABEL_BG[pred]};"
           f"color:{LABEL_COLOR[pred]};'>{LABEL_TEXT[pred]}</span>")
    body += f"<tr><td class='l'>{text}</td><td class='l'>{tag}</td></tr>"
st.markdown(
    "<table class='sw-table'><thead><tr>"
    "<th class='l'>評論內容</th><th class='l'>情緒</th>"
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
