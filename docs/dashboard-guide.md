# 儀表板操作、部署與錄影指南（組員線：介面與 AI 呈現）

這份文件涵蓋：本地啟動、四個頁面導覽、線上部署（Live Demo 網址）、錄影腳本。
交件必備的「Live Demo 網址」與「操作影片」都靠這份走完。

---

## 一、本地啟動（開發與 Demo）

前置：已安裝依賴（`pip install -r requirements.txt`）。

```powershell
# 1) 產生正式資料（真引擎，Demo 一律用這個）
python -m src.risk_score
# （選用）離線介面 fixture：產到 *_mock.csv，不會覆蓋正式檔
# python scripts/make_mock_data.py

# 2) 啟動儀表板
streamlit run app/主頁.py
```

瀏覽器會自動開啟 `http://localhost:8501`。左側自動出現四個分頁。

> 提醒：Streamlit 是常駐伺服器，請在自己的終端機手動執行，不要用會阻塞的自動化流程跑。

---

## 二、四個頁面導覽（Demo 動線建議）

| 順序 | 頁面 | 一句話賣點 | Demo 要點 |
|------|------|-----------|-----------|
| 1 | 🛡️ 主頁（風險排名表） | 一眼看出誰要優先查 | 用側邊篩選挑「高風險」，展示排序與等級色塊 |
| 2 | 🔍 單園詳情 | 白盒子可解釋 | 點風險最高的園，秀**雷達圖**哪一角凸出 + 分項貢獻拆解 |
| 3 | 🗺️ 風險地圖 | 精準投放人力 | 紅黃綠標點 + **高風險稽查建議路線**（最後一哩路）|
| 4 | 🤖 AI 稽查建議 | 降低人力負擔 | 一鍵生成白話稽查建議（Bedrock 或範本）|
| 5 | 💬 輿情分析 | 加分亮點 | 小樣本情緒分析 → 負面比例併入風險分 |

**建議 Demo 一句話串場**：
「排名表挑出高風險 → 詳情頁用雷達圖解釋為什麼高 → 地圖排出稽查路線 → AI 直接寫好稽查建議給稽查員。」

---

## 三、資料契約（與隊長線的交接）

介面只讀這兩個檔，欄位定義見 `docs/data-dictionary.md`：

- `data/processed/kindergartens_latest.csv`（每園一列，排名/地圖/雷達/AI 都用這個）
- `data/processed/kindergartens.csv`（每園每年一列，僅趨勢圖用）

**正式資料來源**：`python -m src.risk_score`（真引擎，讀真實決算/OCR 資料）產出上述兩個
正式檔，介面直接讀取、**不需修改任何程式碼**。
`scripts/make_mock_data.py` 僅供離線 fixture，預設輸出到 `*_mock.csv`，不會覆蓋正式檔；
除非明確加 `--force`（會先警告）。切勿在 Demo 前用假資料覆蓋正式檔。

---

## 四、AI 稽查建議接 AWS Bedrock

未設定 AWS 時，AI 頁自動用「規則式範本」產建議，Demo 照常可跑。要接真 Bedrock：

1. 複製環境變數範本並填入金鑰（金鑰只放 `.env`，`.gitignore` 已排除）：
   ```powershell
   copy .env.example .env
   # 編輯 .env，填 AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / BEDROCK_MODEL_ID
   ```
2. 重啟 streamlit，AI 頁會顯示「偵測到 AWS 憑證」並改用 Bedrock 生成。
3. 程式一律用 `os.environ` 讀金鑰（見 `src/ai_report.py`），**禁止寫死**。

> 上 GitHub 前務必跑 `python scripts/check_secrets.py`，顯示 `[OK]` 才可 push。

---

## 五、線上部署（Live Demo 網址，交件必備）

推薦 **Streamlit Community Cloud**（免費、與 GitHub 直連、最省時）：

1. 把專案 push 到 GitHub（先跑機密掃描）。
2. 到 <https://share.streamlit.io> 用 GitHub 登入，選本 repo。
3. 主檔路徑填 `app/主頁.py`，Python 版本選 3.12。
4. 若要用 Bedrock，在該平台的 **Secrets** 設定介面填 AWS 金鑰（不要進 git）。
5. 部署完成後會得到一個 `https://xxx.streamlit.app` 網址 → 這就是**交件用 Live Demo 網址**。

備援方案（擇一）：
- **本機 + ngrok**：`streamlit run app/主頁.py` 後 `ngrok http 8501`，得到臨時公開網址（適合 Demo 當天）。
- **Hugging Face Spaces**（選 Streamlit SDK）：同樣免費、支援 Secrets。

---

## 六、錄影腳本（操作影片，交件必備）

建議 90 秒～2 分鐘，畫面錄製工具：Windows 內建 `Win + Alt + R` 或 OBS。

分鏡：

1. **（10 秒）開場**：秀主頁標題，一句話定位「AI × 鑑識會計的教保機構風險預警」。
2. **（20 秒）排名表**：篩選高風險，游標指向前幾名，說明「這幾間要優先查」。
3. **（25 秒）詳情頁**：點最高風險園，停在**雷達圖**，說「這一角特別凸，代表財務異常」，再唸一次分項貢獻拆解（白盒子）。
4. **（20 秒）地圖**：切地圖頁，指紅點與**稽查建議路線**，說「稽查員照這條路線排班」。
5. **（20 秒）AI 建議**：點「產生 AI 稽查建議」，唸出生成的白話建議，強調「稽查員不用自己讀財報」。
6. **（10 秒）收尾**：一句「抽樣展示，架構可規模化到全部機構」。

> 錄影前先跑一次確認資料在、頁面不報錯（`python scripts/smoke_test_app.py`）。

---

## 七、自我驗證

```powershell
# 不開瀏覽器，快速確認五個頁面都能正常渲染、不拋例外
python scripts/smoke_test_app.py
```

看到 `結果：5/5 通過` 即代表介面健康。
