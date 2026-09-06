# 小小守護員 Smart Watchdog

**2026 新北市 AI 智慧城市黑客松競賽｜教育局組**

AI × 鑑識會計，打造教保機構智慧風險預警管理系統。整合公開財務、裁罰、評鑑、收費與社群輿情資料，用可量化、可解釋的風險評分模型，把「事後被動稽查」提前為「事前主動示警」。

## 專案目標

- 從公開資料中有效篩選出高風險教保機構
- 縮短預警時間，從事後稽查提前為事前示警
- 降低稽查人力負擔，讓有限人力精準投放

## 安全規範（重要）

比賽規定：上傳程式碼到 GitHub 前，務必確認**不含任何機密憑證**（AWS Access Key、API Token、資料庫密碼等）。

本專案已做以下防護：

1. `.gitignore` 已排除 `.env`、AWS 憑證檔、金鑰檔、原始資料集等。
2. 所有機密請放在 `.env`（此檔不會被上傳）。設定方式：
   ```
   copy .env.example .env
   ```
   然後編輯 `.env` 填入你的真實金鑰。
3. **每次 push 前**先跑機密掃描：
   ```
   python scripts/check_secrets.py
   ```
   顯示 `[OK]` 才可以上傳。

## 環境變數

需要哪些變數請看 `.env.example`。程式碼一律用 `os.environ` 讀取，禁止把金鑰寫死在程式裡。

## 資料集

比賽提供的原始資料（決算書、財報 PDF）放在 `E_教育局-資料集/`，此資料夾已被 `.gitignore` 排除，不會上傳（檔案大且可能含敏感資訊）。

## 專案概況

<!-- AUTO-STRUCTURE:START -->
> 本區塊由 `scripts/update_readme.py` 自動維護，最後更新：2026-09-06 23:07 (UTC+8)

### 專案結構
```
ntpc-smart-watchdog/
├── data/
│   ├── external/
│   │   ├── addresses.csv
│   │   └── penalties.csv
│   └── processed/
│       ├── financials.csv
│       ├── financials_112.csv
│       ├── financials_113.csv
│       ├── geocode_cache.json
│       ├── geocoded.csv
│       └── kindergartens.csv
├── docs/
│   ├── methodology.md
│   ├── ocr-plan.md
│   └── team-plan.md
├── reports/
│   └── validation.png
├── scripts/
│   ├── check_secrets.py
│   └── update_readme.py
├── src/
│   ├── __init__.py
│   ├── extract_public.py
│   ├── forensic.py
│   ├── geocode.py
│   ├── ocr_nonprofit.py
│   ├── risk_score.py
│   ├── sensitivity.py
│   └── validate.py
├── README.md
└── requirements.txt
```

### 檔案統計
- `.py`：10 個
- `.csv`：7 個
- `.md`：4 個
- `.example`：1 個
- `(無副檔名)`：1 個
- `.txt`：1 個
- `.json`：1 個
- `.png`：1 個
<!-- AUTO-STRUCTURE:END -->
