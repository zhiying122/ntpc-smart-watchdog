# Fiscalint — 教保機構監理作業系統

**2026 新北市 AI 智慧城市黑客松競賽｜教育局組**（參賽題目：小小守護員 Smart Watchdog）

> **一句話定位**：別人做幼兒園風險評分，我們做「AI 稽查官」——用審計界抓弊案的**鑑識會計**方法，算出可解釋的白盒子風險分數，再讓生成式 AI（AWS Bedrock）產出稽查建議，把稽查人力產能放大十倍。

AI × 鑑識會計，打造教保機構智慧風險預警管理系統。整合公開財務、裁罰、評鑑、收費與**真實網路輿情**（新聞 + PTT），用可量化、可解釋的風險評分模型，把「事後被動稽查」提前為「事前主動示警」。

---

## 🌐 線上服務（Live on AWS EC2）

本平台採**網路區隔設計**，切分為兩個獨立系統，共用同一套鑑識風險中台：

| 系統 | 使用者 | 網址 | 說明 |
|------|--------|------|------|
| **公務後台** | 教育局 / 稽查員 | http://18.236.246.233:8601 | 完整風險分數、鑑識分析、AI 稽查建議、案件派工 |
| **公眾查詢網** | 一般民眾 / 家長 | http://18.236.246.233:8602 | 去識別化公開資訊，**不含任何風險分數** |

> 兩系統以 `systemd` 常駐、GitHub Actions 自動部署（push→main → EC2 self-hosted runner → 重啟服務 → 健康檢查）。

---

## 🎯 專案目標

- **提升風險辨識率**：從公開資料中有效篩選出高風險教保機構。
- **縮短預警時間**：從「事後被動稽查」提前為「事前主動示警」。
- **降低人力負擔**：讓有限的稽查人力精準投放在最需關注的機構。

---

## 👥 兩種使用者、兩個系統

### 🏛️ 行政人員端 — 公務後台（:8601）

供教育局/稽查員使用的**稽查作戰工作台**。使用者動線：**全局監控 → 下鑽單園 → 下決定 → 派工結案**。

| 頁面 | 功能 | 對應程式 |
|------|------|---------|
| **風險總覽（主頁）** | 全市 KPI 帶、完整風險排名表（可篩選/排序/下載 CSV）、各行政區風險組成堆疊圖、今日待處理工作台、模型鑑別力驗證 | `app/主頁.py` |
| **案件工作台** | 單園雷達圖攤開四分項、決策條（建議派查/存疑待補/不成立結案）、案件狀態流 | `app/pages/1_case.py` |
| **風險地圖** | Leaflet + OpenStreetMap，紅/黃/綠標記，點選看園名+風險分+訊號，排稽查路線 | `app/pages/2_map.py` |
| **AI 稽查建議** | AWS Bedrock（Claude）產出白話稽查建議 + AI 稽查助手問答（附資料來源） | `app/pages/3_ai.py` |
| **輿情觀測** | 五層來源交叉驗證（官方/司法/新聞/陳情/社群）、微弱訊號偵測 | `app/pages/4_sentiment.py` |
| **派工台** | 高風險機構派工、排除已稽查 | `app/pages/5_dispatch.py` |
| **治理 / 資料整合 / 健康檢查** | 資料來源矩陣、動態資料同步、系統健康監控 | `app/pages/6~8` |

**案件狀態流**：`待研判 → 建議派查 → 調查中 → 結案·屬實 / 結案·不成立`（附時間戳與稽核軌跡，`app/lib/case_status.py`）。

### 👨‍👩‍👧 民眾端 — 公眾查詢網（:8602）「安心找幼兒園」

供家長使用的**公開資訊平台**，無需登入。刻意與後台分離，語氣溫暖、資訊誠實。

| 功能 | 說明 |
|------|------|
| **找附近幼兒園** | 輸入地址 → OpenStreetMap Nominatim 定位 → 找出鄰近幼兒園、地圖標點與距離 |
| **看得懂學費** | 公開收費資訊揭露、透明比較 |
| **安全放心** | 公開評鑑等第、裁罰狀態 |
| **輿情觀測** | 即時爬公開新聞 RSS，每則附原文連結與發布時間；改用描述性「近期關注度：平靜期/有討論/值得留意」，**不使用**後台的「高/中/低風險」字眼 |

**資料安全（權限在資料層擋，非前端隱藏）**：民眾端透過 `permissions.authorize_dataframe(df, ROLE_PARENT)` 在**資料層直接移除**所有 `risk_*` / `score_*` 欄位——家長端拿到的資料**根本不含風險分數**，不是前端算完再隱藏。入口 `public/公開查詢.py`。

---

## 📊 資料來源（官方一手 × 自行蒐集，全部可追溯）

| 資料類別 | 來源機關 / 網站 | 取得方式 | 量 |
|---------|----------------|---------|-----|
| 公校決算書 | 新北市政府主計處（110–113 年度總決算） | 主辦方提供 + 公開下載 | PDF 文字層 |
| 非營利園財報 | 新北市政府教育局 | 主辦方提供 | 132 份掃描檔 |
| 全國機構名冊 | 全國教保資訊網（教育部） | 自行蒐集 | 1,111 筆 |
| 裁罰紀錄 | [全國教保資訊網裁罰查詢](https://ap.ece.moe.edu.tw/webecems/punishSearch.aspx) | 自行爬取 | 2,838 筆 |
| 基本 / 收費 / 座標 | 全國教保資訊網（經 g0v 開源專案整理） | 動態 API（免金鑰） | 全市 |
| 全市逐年統計 | 教育部統計處 | [data.gov.tw](https://data.gov.tw/) 開放資料 | 104–110 學年 |
| **新聞輿情** | Google News + Bing News + 自由時報 / 東森 / 中央社 / 聯合報 / 鏡週刊 / Newtalk（公開 RSS） | 自行爬取 | 即時 |
| **社群輿情** | PTT（BabyMother / BabyProducts 公開看板） | 自行爬取 | 即時 |
| **司法事實** | 司法院裁判書 / 各級行政處分 | 連接器（區分判決確定/程序中） | 事實層 |

**靜態 × 動態雙軌**：決算書需逐冊校對精抽才能做班佛檢定，適合靜態；基本資料/裁罰是結構化 JSON、量大時效敏感，適合動態即時串接（`src/live_source.py`，含三層備援：即時網路 → 本地快取 → 版控快照）。

---

## 🔬 風險是怎麼判定的（白盒子，可解釋）

我們的風險分數不是黑盒子。每一間幼兒園的總風險分 (0–100) 由**四個分項**加權而成，每項都能攤開解釋：

```
總風險分 = 財務異常 ×45%  +  裁罰紀錄 ×30%  +  評鑑結果 ×15%  +  網路輿情 ×10%
```

> 四項全部已接入真實資料源並計入計分。輿情已接入**真實新聞 + PTT 爬蟲**（白盒 NLP 判負面度、每筆附原文連結可追溯），輿情分項貢獻上限 15 分；查無新聞/討論之機構以缺值中性處理、不放大風險（責任 AI）。此處與 `src/risk_score.py` 的 `WEIGHTS` 一致。

### 分項一：財務異常分（最核心，45%）
由「多層鑑識會計方法」疊合，全部有學術文獻佐證（見 `docs/methodology.md`）：

| 方法 | 抓什麼 | 佔財務分 |
|------|--------|---------|
| 班佛定律 (Benford's Law) | 逐筆明細金額的首位數分布是否異常（數字造假傾向，MAD + 卡方檢定） | 22% |
| Beneish M-Score 改良版 | 收入與支出成長背離、應計項目異常（盈餘操縱） | 17% |
| Altman Z'' 在地化困境分 | 財務困境代理比率（對應舞弊三角的「壓力」構面） | 15% |
| Isolation Forest + SHAP | 多維財務特徵的整體異常（非監督式 AI，可解釋） | 22% |
| 收支比離群 (IQR) | 支出/收入比在全體同儕中是否離群 | 8% |
| 跨年度突變 | 收支較上年度暴增暴減 | 8% |
| 賸餘短絀率 | 本期短絀占收入比（基金被侵蝕） | 8% |
| 基金餘額勾稽（加成） | 期末=期初+本期賸餘；跨年度連續性，不一致才向上加成（最多 +15 分） | 不對稱加成 |

**多層交叉驗證**：多個獨立方法同時指向同一間園時，風險判定最可信。

### 分項二～四
- **裁罰紀錄 (30%)**：改用「裁罰事由分類 + 嚴重度」（收費違規遠重於行政缺失）；有逐筆明細者走破窗效應計分。
- **評鑑結果 (15%)**：優=0、良=20、乙=40、待改進=90，缺資料=中性 30。
- **網路輿情 (10%)**：真實新聞 + PTT 負面度（`neg_ratio`）；貢獻上限 15 分，查無訊號中性不放大。

### 風險等級（兩種分級並存，可對照）
- **相對分級（主用，`risk_level`）**：以同機構類型的分布做百分位分級 — 前 15% 高風險、次 35% 中風險、其餘低風險。分機構類型各自排序，避免非營利園被系統性壓低。
- **絕對分級（對照，`risk_level_abs`）**：≥60 高、≥35 中、其餘低。

---

## 🎯 判定範例（新北市立林口幼兒園 59.0 分）

```
財務異常 53.4 × 0.45 = 24.0
裁罰(2次) 90  × 0.30 = 27.0
評鑑(乙)  40  × 0.15 =  6.0
輿情(中性)20  × 0.10 =  2.0
─────────────────────────
總分 = 59.0（相對分級：高風險）
```

稽查員一看就知道：林口的高分主要來自「裁罰紀錄」與「財務異常」，應優先查這兩塊。

---

## 🤖 AI 生成稽查建議（AWS Bedrock）

- **定位**：Bedrock（Claude Sonnet 4.5）**不拿來算分數**（算分用規則+統計，可解釋），而是「把數字翻譯成稽查員看得懂的話 + 給稽查建議」，降低人力負擔。
- **兩用途**：(1) `src/ai_report.py` 生成單園稽查建議；(2) `scripts/extract_nonprofit_bedrock.py` 用 Claude 視覺（多模態）抽取非營利園掃描財報數字。
- **責任 AI 兩道關卡**：提示詞負向約束（只能做發現異常/排序/解釋/提供證據/建議查核方向五件事）+ 輸出後過濾（中和任何違法/舞弊斷言）。Bedrock 失敗時自動退化規則式範本，確保 Demo 一定跑得出來。
- **證據鏈**：`src/evidence.py` 建「結論 → 特徵 → 原始資料 → 官方來源」的可追溯鏈。

---

## ☁️ AWS 雲端技術架構

```
① 資料來源  公校決算PDF / 非營利園財報 / 裁罰·評鑑 / 新聞·PTT·司法
                          ↓
② AWS 處理   Amazon S3（儲存）· Textract/Tesseract OCR · Bedrock Claude · EC2+IAM Role
                          ↓
③ 鑑識中台   forensic.py（鑑識會計）· risk_score.py（白盒評分）· evidence.py · ai_report.py · geocode.py
                          ↓
④ 應用介面   公務後台 :8601（稽查官，全欄位）  ｜  公眾查詢網 :8602（家長，去識別化）
```

- **Bedrock 模型**：`us.anthropic.claude-sonnet-4-5-20250929-v1:0`（region `us-west-2`）。
- **憑證**：EC2 用 IAM Role（免金鑰）；本機用 `.env`。一律 `os.environ` 讀取。
- **CI/CD**：GitHub Actions push→main → self-hosted runner → `deploy/setup_ec2.sh` → systemd 重啟 + 健康檢查。

---

## 📈 模型效能（`python -m src.validate` 即時產生）

- **AUC-ROC = 0.906**（辨識能力優異，>0.9）
- **Recall = 1.0**（所有被裁罰的園都被歸入較高風險，零漏抓）
- **相關係數 = 0.733**（風險分與裁罰次數高度正相關）
- **權重敏感度 Spearman ≥ 0.974**（改變權重，高風險排名幾乎不變，結論穩健）

---

## 🚀 快速開始

### 1. 安裝

```
pip install -r requirements.txt
copy .env.example .env      # 填入 AWS Bedrock 金鑰（選用；無金鑰會自動退化規則式範本）
```

### 2. 產生資料（可選，repo 已附契約檔）

```
python scripts/build_sentiment.py          # 爬新聞 + PTT，產出輿情負面度
python scripts/rebuild_from_combined.py     # 重算風險分（輿情計入四項制）
```

### 3. 啟動兩個系統

```
python -m streamlit run app/主頁.py --server.port 8601        # 公務後台
python -m streamlit run public/公開查詢.py --server.port 8602  # 公眾查詢網
```

---

## 🔒 安全規範（重要）

比賽規定：上傳程式碼到 GitHub 前，務必確認**不含任何機密憑證**（AWS Access Key、API Token、資料庫密碼等）。

本專案已做以下防護：

1. `.gitignore` 已排除 `.env`、AWS 憑證檔、金鑰檔、原始資料集等。
2. 所有機密請放在 `.env`（此檔不會被上傳）。設定：`copy .env.example .env` 後編輯填入真實金鑰。
3. **每次 push 前**先跑機密掃描：`python scripts/check_secrets.py`，顯示 `[OK]` 才可上傳。

程式碼一律用 `os.environ` 讀取金鑰，禁止寫死。原始資料集（決算書、財報 PDF）放在 `E_教育局-資料集/`，已被 `.gitignore` 排除。

---

## 🧭 責任 AI（Responsible AI）

- 系統僅**發現異常、排序、解釋、提供證據、建議稽查方向**；不判定犯罪/舞弊/違法。
- 每則風險陳述附「**風險不等於違法**」聲明。
- 資料來源以三態誠實標示（已確認/未確認/不適用），官方全量 API 未取得者標「未確認」，絕不虛構（`src/data_source_matrix.py`）。
- 事實層（官方/判決確定）與輿情層（新聞/社群）嚴格分離；輿情不作為違法認定依據。

---

## 📁 專案概況

<!-- AUTO-STRUCTURE:START -->
> 本區塊由 `scripts/update_readme.py` 自動維護，最後更新：2026-09-13 01:10 (UTC+8)

### 專案結構
```
ntpc-smart-watchdog/
├── app/
│   ├── lib/
│   │   ├── auth.py
│   │   ├── case_status.py
│   │   ├── common.py
│   │   ├── dispatch.py
│   │   ├── gov_console.py
│   │   ├── inspector.py
│   │   ├── modes.py
│   │   ├── parent_portal.py
│   │   ├── permissions.py
│   │   └── risk_map.py
│   ├── pages/
│   │   ├── 1_case.py
│   │   ├── 2_map.py
│   │   ├── 3_ai.py
│   │   ├── 4_sentiment.py
│   │   ├── 5_dispatch.py
│   │   ├── 6_governance.py
│   │   ├── 7_integration.py
│   │   ├── 8_health.py
│   │   └── 9_public_preview.py
│   └── 主頁.py
├── data/
│   ├── cache/
│   │   ├── preschools.json
│   │   └── punish_all.json
│   ├── derived/
│   │   ├── nonprofit_bedrock/
│   │   │   ├── N01_113.json
│   │   │   ├── N02_113.json
│   │   │   ├── N03_113.json
│   │   │   ├── N04_113.json
│   │   │   ├── N05_113.json
│   │   │   ├── N06_113.json
│   │   │   ├── N07_113.json
│   │   │   ├── N08_113.json
│   │   │   ├── N09_113.json
│   │   │   ├── N10_113.json
│   │   │   ├── N11_113.json
│   │   │   ├── N12_113.json
│   │   │   ├── N13_113.json
│   │   │   ├── N14_113.json
│   │   │   ├── N15_113.json
│   │   │   ├── N16_113.json
│   │   │   ├── N17_113.json
│   │   │   ├── N18_113.json
│   │   │   ├── N19_113.json
│   │   │   ├── N20_113.json
│   │   │   ├── N21_113.json
│   │   │   ├── N22_113.json
│   │   │   ├── N23_113.json
│   │   │   ├── N24_113.json
│   │   │   ├── N25_113.json
│   │   │   ├── N26_113.json
│   │   │   ├── N27_113.json
│   │   │   ├── N28_113.json
│   │   │   ├── N29_113.json
│   │   │   ├── N30_113.json
│   │   │   ├── N31_113.json
│   │   │   ├── N32_113.json
│   │   │   ├── N33_113.json
│   │   │   ├── N34_113.json
│   │   │   ├── N35_113.json
│   │   │   ├── N36_113.json
│   │   │   ├── N37_113.json
│   │   │   └── N38_113.json
│   │   ├── nonprofit_ocr/
│   │   │   ├── N01_110_tesseract.json
│   │   │   ├── N01_111_tesseract.json
│   │   │   ├── N01_112_tesseract.json
│   │   │   ├── N01_113_tesseract.json
│   │   │   ├── N02_110_tesseract.json
│   │   │   ├── N02_111_tesseract.json
│   │   │   ├── N02_112_tesseract.json
│   │   │   ├── N02_113_tesseract.json
│   │   │   ├── N03_110_tesseract.json
│   │   │   ├── N03_111_tesseract.json
│   │   │   ├── N03_112_tesseract.json
│   │   │   ├── N03_113_tesseract.json
│   │   │   ├── N04_110_tesseract.json
│   │   │   ├── N04_111_tesseract.json
│   │   │   ├── N04_112_tesseract.json
│   │   │   ├── N04_113_tesseract.json
│   │   │   ├── N05_110_tesseract.json
│   │   │   ├── N05_111_tesseract.json
│   │   │   ├── N05_112_tesseract.json
│   │   │   ├── N05_113_tesseract.json
│   │   │   ├── N06_110_tesseract.json
│   │   │   ├── N06_111_tesseract.json
│   │   │   ├── N06_112_tesseract.json
│   │   │   ├── N06_113_tesseract.json
│   │   │   ├── N07_110_tesseract.json
│   │   │   ├── N07_111_tesseract.json
│   │   │   ├── N07_112_tesseract.json
│   │   │   ├── N07_113_tesseract.json
│   │   │   ├── N08_110_tesseract.json
│   │   │   ├── N08_111_tesseract.json
│   │   │   ├── N08_112_tesseract.json
│   │   │   ├── N08_113_tesseract.json
│   │   │   ├── N09_110_tesseract.json
│   │   │   ├── N09_111_tesseract.json
│   │   │   ├── N09_112_tesseract.json
│   │   │   ├── N09_113_tesseract.json
│   │   │   ├── N10_110_tesseract.json
│   │   │   ├── N10_111_tesseract.json
│   │   │   ├── N10_112_tesseract.json
│   │   │   ├── N10_113_tesseract.json
│   │   │   ├── N11_110_tesseract.json
│   │   │   ├── N11_111_tesseract.json
│   │   │   ├── N11_112_tesseract.json
│   │   │   ├── N11_113_tesseract.json
│   │   │   ├── N12_110_tesseract.json
│   │   │   ├── N12_111_tesseract.json
│   │   │   ├── N12_112_tesseract.json
│   │   │   ├── N12_113_tesseract.json
│   │   │   ├── N13_110_tesseract.json
│   │   │   ├── N13_111_tesseract.json
│   │   │   ├── N13_112_tesseract.json
│   │   │   ├── N13_113_tesseract.json
│   │   │   ├── N14_110_tesseract.json
│   │   │   ├── N14_111_tesseract.json
│   │   │   ├── N14_112_tesseract.json
│   │   │   ├── N14_113_tesseract.json
│   │   │   ├── N15_110_tesseract.json
│   │   │   ├── N15_111_tesseract.json
│   │   │   ├── N15_112_tesseract.json
│   │   │   ├── N15_113_tesseract.json
│   │   │   ├── N16_110_tesseract.json
│   │   │   ├── N16_111_tesseract.json
│   │   │   ├── N16_112_tesseract.json
│   │   │   ├── N16_113_tesseract.json
│   │   │   ├── N17_110_tesseract.json
│   │   │   ├── N17_111_tesseract.json
│   │   │   ├── N17_112_tesseract.json
│   │   │   ├── N17_113_tesseract.json
│   │   │   ├── N18_110_tesseract.json
│   │   │   ├── N18_111_tesseract.json
│   │   │   ├── N18_112_tesseract.json
│   │   │   ├── N18_113_tesseract.json
│   │   │   ├── N19_110_tesseract.json
│   │   │   ├── N19_111_tesseract.json
│   │   │   ├── N19_112_tesseract.json
│   │   │   ├── N19_113_tesseract.json
│   │   │   ├── N20_110_tesseract.json
│   │   │   ├── N20_111_tesseract.json
│   │   │   ├── N20_112_tesseract.json
│   │   │   ├── N20_113_tesseract.json
│   │   │   ├── N21_110_tesseract.json
│   │   │   ├── N21_111_tesseract.json
│   │   │   ├── N21_112_tesseract.json
│   │   │   ├── N21_113_tesseract.json
│   │   │   ├── N22_110_tesseract.json
│   │   │   ├── N22_111_tesseract.json
│   │   │   ├── N22_112_tesseract.json
│   │   │   ├── N22_113_tesseract.json
│   │   │   ├── N23_110_tesseract.json
│   │   │   ├── N23_111_tesseract.json
│   │   │   ├── N23_112_tesseract.json
│   │   │   ├── N23_113_tesseract.json
│   │   │   ├── N24_110_tesseract.json
│   │   │   ├── N24_111_tesseract.json
│   │   │   ├── N24_112_tesseract.json
│   │   │   ├── N24_113_tesseract.json
│   │   │   ├── N25_110_tesseract.json
│   │   │   ├── N25_111_tesseract.json
│   │   │   ├── N25_112_tesseract.json
│   │   │   ├── N25_113_tesseract.json
│   │   │   ├── N26_110_tesseract.json
│   │   │   ├── N26_111_tesseract.json
│   │   │   ├── N26_112_tesseract.json
│   │   │   ├── N26_113_tesseract.json
│   │   │   ├── N27_110_tesseract.json
│   │   │   ├── N27_111_tesseract.json
│   │   │   ├── N27_112_tesseract.json
│   │   │   ├── N27_113_tesseract.json
│   │   │   ├── N28_110_tesseract.json
│   │   │   ├── N28_111_tesseract.json
│   │   │   ├── N28_112_tesseract.json
│   │   │   ├── N28_113_tesseract.json
│   │   │   ├── N29_111_tesseract.json
│   │   │   ├── N29_112_tesseract.json
│   │   │   ├── N29_113_tesseract.json
│   │   │   ├── N30_111_tesseract.json
│   │   │   ├── N30_112_tesseract.json
│   │   │   ├── N30_113_tesseract.json
│   │   │   ├── N31_111_tesseract.json
│   │   │   ├── N31_112_tesseract.json
│   │   │   ├── N31_113_tesseract.json
│   │   │   ├── N32_111_tesseract.json
│   │   │   ├── N32_112_tesseract.json
│   │   │   ├── N32_113_tesseract.json
│   │   │   ├── N33_112_tesseract.json
│   │   │   ├── N33_113_tesseract.json
│   │   │   ├── N34_112_tesseract.json
│   │   │   ├── N34_113_tesseract.json
│   │   │   ├── N35_113_tesseract.json
│   │   │   ├── N36_113_tesseract.json
│   │   │   ├── N37_113_tesseract.json
│   │   │   └── N38_113_tesseract.json
│   │   └── case_status.json
│   ├── external/
│   │   ├── nonprofit_reports/
│   │   │   └── 113/
│   │   │       ├── N01安溪_113學年度財務報告.pdf
│   │   │       ├── N02山北_113學年度財務報告.pdf
│   │   │       ├── N03龍埔成長_113學年度財務報告.pdf
│   │   │       ├── N04海工_113學年度財務報告.pdf
│   │   │       ├── N05漢翔_113學年度財務報告.pdf
│   │   │       ├── N06昌平_113學年度財務報告.pdf
│   │   │       ├── N07北大_113學年度財務報告.pdf
│   │   │       ├── N08鷺江_113學年度財務報告.pdf
│   │   │       ├── N09安興_113學年度財務報告.pdf
│   │   │       ├── N10大觀_113學年度財務報告.pdf
│   │   │       ├── N11新林_113學年度財務報告.pdf
│   │   │       ├── N12昌福_113學年度財務報告.pdf
│   │   │       ├── N13三多_113學年度財務報告.pdf
│   │   │       ├── N14積穗_113學年度財務報告.pdf
│   │   │       ├── N15新月_113學年度財務報告.pdf
│   │   │       ├── N16中平_113學年度財務報告.pdf
│   │   │       ├── N17中正_113學年度財務報告.pdf
│   │   │       ├── N18福營_113學年度財務報告.pdf
│   │   │       ├── N19中園_113學年度財務報告.pdf
│   │   │       ├── N20柏翠_113學年度財務報告.pdf
│   │   │       ├── N21文創_113學年度財務報告.pdf
│   │   │       ├── N22文仁_113學年度財務報告.pdf
│   │   │       ├── N23菁湖_113學年度財務報告.pdf
│   │   │       ├── N24佳林_113學年度財務報告.pdf
│   │   │       ├── N25碧城_113學年度財務報告.pdf
│   │   │       ├── N26新店及人_113學年度財務報告.pdf
│   │   │       ├── N27育平_113學年度財務報告.pdf
│   │   │       ├── N28新樂_113學年度財務報告.pdf
│   │   │       ├── N29東湖_113學年度財務報告.pdf
│   │   │       ├── N30文中_113學年度財務報告.pdf
│   │   │       ├── N31翠中_113學年度財務報告.pdf
│   │   │       ├── N32板橋員工子女_113學年度財務報告.pdf
│   │   │       ├── N33淡海_113學年度財務報告.pdf
│   │   │       ├── N34佳和_113學年度財務報告.pdf
│   │   │       ├── N35桃子腳_113學年度財務報告.pdf
│   │   │       ├── N36明德_113學年度財務報告.pdf
│   │   │       ├── N37清水高中_113學年度財務報告.pdf
│   │   │       └── N38崁頂_113學年度財務報告.pdf
│   │   ├── 110年度新北市總決算.pdf
│   │   ├── 111年度新北市總決算.pdf
│   │   ├── 112年度新北市總決算.pdf
│   │   ├── 113年度新北市總決算.pdf
│   │   ├── 113年度新北市總決算暨附屬單位決算及綜計表審核報告.pdf
│   │   ├── addresses.csv
│   │   ├── export1789190438.csv
│   │   ├── moe_ntpc_yearly.csv
│   │   ├── nonprofit.csv
│   │   ├── nonprofit_addresses.csv
│   │   ├── ntpc_penalty.csv
│   │   ├── ntpc_roster_raw.csv
│   │   └── penalties.csv
│   ├── processed/
│   │   ├── financials.csv
│   │   ├── financials_112.csv
│   │   ├── financials_113.csv
│   │   ├── financials_combined.csv
│   │   ├── geocode_cache.json
│   │   ├── geocoded.csv
│   │   ├── kindergartens.backup.csv
│   │   ├── kindergartens.csv
│   │   ├── kindergartens_latest.backup.csv
│   │   ├── kindergartens_latest.csv
│   │   ├── kindergartens_roster.csv
│   │   ├── nonprofit_financials_bedrock.csv
│   │   └── sentiment.csv
│   ├── raw/
│   │   ├── judicial_records.json
│   │   └── multi_source_signals.json
│   ├── snapshots/
│   │   ├── preschools.json
│   │   ├── punish_all.json
│   │   └── snapshot_meta.json
│   └── tessdata/
│       ├── chi_tra.traineddata
│       ├── eng.traineddata
│       └── osd.traineddata
├── deploy/
│   ├── setup_ec2.sh
│   ├── watchdog-gov.service
│   └── watchdog-public.service
├── docs/
│   ├── dashboard-guide.md
│   ├── data-dictionary.md
│   ├── data-integration-plan.md
│   ├── demo-narrative.md
│   ├── deploy-ec2.md
│   ├── deployment-security.md
│   ├── github-actions-deploy.md
│   ├── methodology.md
│   ├── ocr-plan.md
│   ├── questions-for-organizer.md
│   └── team-plan.md
├── public/
│   ├── data/
│   │   └── sentiment_demo.json
│   ├── lib/
│   │   ├── evaluation_cycle.py
│   │   ├── geocode.py
│   │   ├── input_guard.py
│   │   ├── news_crawler.py
│   │   ├── ntpc_districts.py
│   │   ├── parent_map.py
│   │   ├── public_dataset.py
│   │   ├── sentiment_score.py
│   │   └── sentiment_watch.py
│   └── 公開查詢.py
├── reports/
│   ├── validation.png
│   ├── ~$小小守護員_資料運用補強簡報.pptx
│   ├── 小小守護員_決賽完整簡報.pptx
│   ├── 小小守護員_決賽簡報.pptx
│   └── 小小守護員_資料運用補強簡報.pptx
├── scripts/
│   ├── add_affiliated_demo.py
│   ├── build_data_ppt.py
│   ├── build_final_deck.py
│   ├── build_geocode.py
│   ├── build_pitch_ppt.py
│   ├── build_sentiment.py
│   ├── check_bedrock.py
│   ├── check_consistency.py
│   ├── check_secrets.py
│   ├── deploy_ec2_launch.py
│   ├── deploy_ec2_setup_role.py
│   ├── deploy_ec2_teardown.py
│   ├── extract_nonprofit.py
│   ├── extract_nonprofit_address.py
│   ├── extract_nonprofit_bedrock.py
│   ├── extract_public.py
│   ├── fetch_moe_stats.py
│   ├── fetch_nonprofit_reports.py
│   ├── fetch_ntpc_penalty.py
│   ├── fetch_ntpc_roster.py
│   ├── integrate_nonprofit.py
│   ├── make_mock_data.py
│   ├── merge_financials.py
│   ├── rebuild_all.py
│   ├── rebuild_all_result.txt
│   ├── rebuild_from_combined.py
│   ├── run_nonprofit_ocr.py
│   ├── scan_kindergarten_coverage.py
│   ├── smoke_test_app.py
│   ├── update_readme.py
│   └── update_snapshots.py
├── src/
│   ├── __init__.py
│   ├── ai_report.py
│   ├── alert.py
│   ├── allocation.py
│   ├── anomaly.py
│   ├── audit.py
│   ├── broken_window.py
│   ├── confidence.py
│   ├── data_source_matrix.py
│   ├── entity_resolver.py
│   ├── evidence.py
│   ├── extract_public.py
│   ├── financial_parser.py
│   ├── forensic.py
│   ├── fraud_triangle.py
│   ├── geocode.py
│   ├── health.py
│   ├── integrate.py
│   ├── judicial_source.py
│   ├── kpi.py
│   ├── live_source.py
│   ├── models.py
│   ├── multi_source.py
│   ├── nlp_engine.py
│   ├── nonprofit_pipeline.py
│   ├── ocr_nonprofit.py
│   ├── official_signals.py
│   ├── pdf_extract_pages.py
│   ├── peer.py
│   ├── penalty_match.py
│   ├── penalty_nlp.py
│   ├── pipeline.py
│   ├── ptt_crawler.py
│   ├── risk_score.py
│   ├── sensitivity.py
│   ├── simulation.py
│   ├── timeline.py
│   ├── validate.py
│   └── validation.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── generators.py
│   ├── test_ai_report.py
│   ├── test_alert.py
│   ├── test_allocation.py
│   ├── test_altman.py
│   ├── test_anomaly.py
│   ├── test_apps_smoke.py
│   ├── test_audit.py
│   ├── test_auth.py
│   ├── test_broken_window.py
│   ├── test_confidence.py
│   ├── test_data_source_matrix.py
│   ├── test_dispatch_bridge.py
│   ├── test_entity_resolver.py
│   ├── test_evidence.py
│   ├── test_financial_parser.py
│   ├── test_forensic_metrics.py
│   ├── test_forensic_trend.py
│   ├── test_fraud_triangle.py
│   ├── test_fund_reconciliation.py
│   ├── test_gov_console.py
│   ├── test_health.py
│   ├── test_inspector.py
│   ├── test_integrate.py
│   ├── test_kpi.py
│   ├── test_live_source.py
│   ├── test_modes.py
│   ├── test_multi_source.py
│   ├── test_nlp_engine.py
│   ├── test_parent_portal.py
│   ├── test_peer.py
│   ├── test_penalty_match.py
│   ├── test_permissions.py
│   ├── test_pipeline.py
│   ├── test_public_portal.py
│   ├── test_risk_map.py
│   ├── test_risk_score.py
│   ├── test_scaffold.py
│   ├── test_simulation.py
│   ├── test_timeline.py
│   └── test_validation.py
├── 比賽要求/
│   ├── Supported AWS Services List 20260722.xlsx
│   └── 黑客松競賽環境規範與限制_20260722.pdf
├── bad_files.txt
├── ntpc-smart-watchdog.code-workspace
├── pytest.ini
├── README.md
├── requirements.txt
└── sw-ec2-key.pem
```

### 檔案統計
- `.json`：180 個
- `.py`：142 個
- `.pdf`：44 個
- `.csv`：20 個
- `.md`：12 個
- `.pptx`：4 個
- `(無副檔名)`：3 個
- `.txt`：3 個
- `.traineddata`：3 個
- `.service`：2 個
- `.example`：1 個
- `.code-workspace`：1 個
- `.ini`：1 個
- `.pem`：1 個
- `.sh`：1 個
- `.png`：1 個
- `.xlsx`：1 個
<!-- AUTO-STRUCTURE:END -->
