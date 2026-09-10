# 資料字典 & 組員使用指南

給組員（介面與 AI 呈現線）看的交接文件。你不用碰資料抽取，只要讀 CSV 就能做儀表板、地圖、AI 報告。

## 你要用哪個檔？

| 檔案 | 用途 | 特性 |
|------|------|------|
| `data/processed/kindergartens_latest.csv` | **排名表、地圖、雷達圖、AI報告** | 每園一列（已去重取最新年度），已按風險排序 |
| `data/processed/kindergartens.csv` | **跨年度趨勢圖**（想做時間軸才用） | 每園每年一列，同園多列 |

**結論：主要用 `kindergartens_latest.csv` 就對了。** 只有要畫「某園三年趨勢」才用完整檔。

## 快速上手（Streamlit 範例）

```python
import pandas as pd
df = pd.read_csv("data/processed/kindergartens_latest.csv")

# 1) 風險排名表（已排好序）
st.dataframe(df[["park_name", "risk_total", "risk_level"]])

# 2) 地圖只顯示有座標的園
map_df = df.dropna(subset=["lat", "lng"])
# 用 folium/st.map 標點，依 risk_level 上色

# 3) 單園雷達圖用這四個分項
radar_cols = ["score_financial", "score_penalty", "score_eval", "score_sentiment"]
```

## 欄位說明

### 識別與位置
| 欄位 | 意義 | 備註 |
|------|------|------|
| `park_name` | 園所名稱 | 顯示用主鍵 |
| `park_type` | 公校/非營利 | 目前皆公校 |
| `year` | 年度 | 快照檔為最新年度 |
| `lat` / `lng` | 緯度/經度 | **可能為空**（少數園無地址），地圖要 dropna |

### 風險分數（核心）
| 欄位 | 意義 | 範圍 | 用途 |
|------|------|------|------|
| `risk_total` | **總風險分** | 0-100 | 排名、地圖顏色主依據 |
| `risk_level` | 風險等級 | 高/中/低 | 紅/黃/綠 |
| `score_financial` | 財務異常分 | 0-100 | 雷達圖第1軸 |
| `score_penalty` | 裁罰分 | 0-100 | 雷達圖第2軸 |
| `score_eval` | 評鑑分 | 0-100 | 雷達圖第3軸 |
| `score_sentiment` | 輿情分 | 0-100 | 雷達圖第4軸 |

### 鑑識會計指標（做明細頁 / 給 AI 當輸入）
| 欄位 | 意義 | 怎麼解讀 |
|------|------|---------|
| `benford_mad` | 班佛偏離度 | 越大越可疑 |
| `benford_score` | 班佛相對風險分 | 0-100 組內排名 |
| `beneish_score` | Beneish改良分 | 越高越可能操縱 |
| `iforest_score` | 孤立森林異常分 | 0-100 越高越異常 |
| `iforest_explain` | 異常主因(前3特徵) | 字典字串，做AI輸入用 |
| `expense_income_ratio` | 收支比 | >1 代表入不敷出 |
| `expense_yoy_pct` | 支出年增率(%) | 暴增暴減看這個 |
| `income_yoy_pct` | 收入年增率(%) | 交叉規則用 |
| `enrollment` | 核定招生數 | 全國教保資訊網，分班已合計 |
| `income_per_child` | 每生單位收入 | 收入 ÷ 核定人數 |
| `income_per_child_z` | 每生收入同儕 z 分數 | 同 park_type 分群 |
| `cross_unit_income_outlier` | [F7] 單位收入偏離同儕 | z≥1.5 觸發 |
| `rev_exp_growth_gap` | 收入年增 − 支出年增(pp) | 交叉背離用 |
| `cross_rev_exp_divergence` | [F8] 收入-支出成長背離 | |≥25pp| 觸發 |
| `penalty_count` | 裁罰次數 | |
| `penalty_reason` | 裁罰事由（文字） | 供分類/嚴重度用 |
| `penalty_category` | 裁罰主類別 | 收費/人力/安全/教保/行政（見 `src/penalty_nlp.py`）|
| `eval_grade` | 評鑑等第 | |

## 顏色建議（地圖 / 排名）
- 高風險（≥60）：紅 `#D1495B`
- 中風險（35-59）：黃 `#E8A33D`
- 低風險（<35）：綠 `#4C9F70`

## AI 稽查報告怎麼串（給你的 Bedrock 模組用）
把單園這幾個欄位組成 prompt 丟給 Bedrock：
`park_name, risk_total, benford_mad, beneish_score, expense_income_ratio, expense_yoy_pct, penalty_count`
請 AI 產出白話稽查建議。範例 prompt 見 `src/ocr_nonprofit.py` 的 bedrock 寫法可參考。

## 有問題先看這裡
- 地圖某些園不見了 → 那些園 lat/lng 是空的，正常，dropna 即可
- 同一間園出現多次 → 你用錯檔了，排名/地圖要用 `_latest.csv`
- 分數想知道怎麼算 → 看 `docs/methodology.md`
