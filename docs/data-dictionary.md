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

# 3) 單園雷達圖用這幾個分項
#    financial/penalty/eval 讀自 CSV；sentiment 由前端以 neg_ratio 即時計算（不在 CSV）
radar_cols = ["score_financial", "score_penalty", "score_eval"]  # + 前端即時算的 sentiment
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
| `risk_level` | 風險等級（**前端唯一顯示**） | 高/中/低 | 紅/黃/綠 |
| `risk_level_abs` | 絕對門檻分級（對照備用） | 高/中/低 | 不在前端顯示 |
| `eng_risk_level` | 白盒四級絕對分級（引擎內部） | 低/中/高/極高 | 不在前端顯示 |
| `score_financial` | 財務異常分 | 0-100 | 雷達圖第1軸 |
| `score_penalty` | 裁罰分 | 0-100 | 雷達圖第2軸 |
| `score_eval` | 評鑑分 | 0-100 | 雷達圖第3軸 |

> **等級系統使用規範（重要，避免跨頁不一致）**：CSV 內並存三套等級欄位，語意不同、刻度不同：
> - `risk_level`（**主用、前端唯一顯示**）：分機構類型的**百分位相對分級**（前 15% 高、次 35% 中、其餘低），目的是「稽查優先序排序」。主頁、地圖、案件、AI 頁一律只顯示這個，故全站等級一致。
> - `risk_level_abs`：**絕對門檻**（≥60 高、≥35 中），僅供對照，不在前端顯示。
> - `eng_risk_level`：白盒 `score()` 的**四級絕對分級**（<40 低、40–69 中、70–89 高、≥90 極高），供引擎內部單機構絕對評估，**不在前端顯示**。
>
> 三套刻度不同，同一間園在不同系統下可能落在不同等級（例如百分位「高」但絕對「中」，屬正常，因語意不同）。**前端請一律使用 `risk_level`，切勿混用或同時顯示絕對分級，以免同園跨頁等級不一致誤導使用者。** 若未來要在前端呈現絕對等級，需與 `risk_level` 明確區隔標示（例如「相對優先序：高／絕對風險：中」），不可讓兩者看起來像互相矛盾。

> 註：輿情分（`score_sentiment`）**不在 CSV**。輿情資料源尚未接入真實資料，為避免以示範值稀釋真實風險分，總分權重僅 financial/penalty/eval 三項（見 `src/risk_score.py` 的 `WEIGHTS`）。雷達圖第 4 軸的輿情值由前端（`app/lib/inspector.py`）以 `neg_ratio` 即時計算顯示，不計入 `risk_total`。

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
| `fund_balance_begin` | 期初基金餘額 | 決算書本年度決算數（公校有，非營利留空） |
| `fund_balance_end` | 期末基金餘額 | 同上；供基金餘額勾稽 |
| `fund_recon_score` | 同期勾稽可疑分 | 0-100；期末≠期初+本期賸餘的偏離度，一致=0 |
| `fund_recon_consistent` | 同期勾稽是否一致 | True/False/空（缺基金資料） |
| `fund_continuity_score` | 跨年度連續性可疑分 | 0-100；本年期初≠上年期末的偏離度，一致=0 |
| `penalty_count` | 裁罰次數 | |
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
