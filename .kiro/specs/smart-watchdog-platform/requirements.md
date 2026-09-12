# Requirements Document

冠軍級平台：小小守護員 Smart Watchdog Platform

---

## Introduction

本文件將「小小守護員 Smart Watchdog」冠軍級願景（39 大構面）轉譯為可驗證的需求規格，供 2026 新北市 AI 智慧城市黑客松競賽（教育局組）決賽（2026/9/12–13，30 小時，2 人團隊，限用 AWS Bedrock）使用。

系統定位為「AI 稽查官」：以審計界的**鑑識會計方法**產出可解釋的教保機構風險分數，再以生成式 AI（AWS Bedrock）產出稽查建議，放大稽查員產能。系統的三大差異化武器維持不變：(1) 鑑識會計護城河、(2) 可解釋白盒子分數、(3) AI 生成稽查建議（AI 不用來算分數）。

**現有實作基線（Existing Baseline，本規格會延伸）：**
- `src/forensic.py`：四層鑑識會計引擎（班佛定律 MAD + 卡方、Beneish 改良版、Isolation Forest + SHAP、IQR 離群、跨年度突變）。
- `src/risk_score.py`：白盒子加權風險分（財務 50% + 裁罰 34% + 評鑑 16%）、百分位相對分級與絕對門檻分級。
- `src/ai_report.py`：Bedrock 稽查建議報告產生器，含規則式 fallback。
- `app/`：Streamlit 多頁介面（主頁、case、map、ai、sentiment），Leaflet 風險地圖。
- `data/`：112/113/114 年度公校決算財務資料、裁罰、評鑑、地理座標。

**責任聲明（Responsible AI，貫穿全文件）：** 本系統只能**發現異常、排序、解釋、提供證據、建議稽查方向**；**不得**判定犯罪、舞弊或違法，**不得**僅以單一訊號為機構貼上標籤。風險（risk）不等於違法（illegality）。

**核心痛點故事（Motivating Scenario，界定系統目標）：** 教保機構的重大違法事件（如管理階層濫權、照顧安全事故）通常並非突發，而是**長期管理異常累積後的爆發後果**——師資頻繁流動導致內部監督失效與過勞、封閉式管理排擠有正義感的教職員、頻繁的輕微違規（超收、進用未具資格人員、隱匿稽查）未見改善。現行定期稽查僅能審閱機構備妥的書面資料，難以預判此種「破窗效應」下的惡化趨勢。本系統的目標是綜合**財務異常（鑑識會計）、頻繁小違規（破窗效應加權）與家長／社群輿情微弱訊號**，將呈現高風險管理環境的機構提前標記，讓有限稽查人力精準投放，在憾事發生前介入。

**目標界定與責任邊界（務必嚴守）：** 系統預測的目標變數是「**高風險管理環境**」（可作為優先稽查依據），**並非**預測特定犯罪事件。系統**不得**宣稱能預測、判定或歸因任何刑事案件，亦不得將任何單一新聞事件、社群貼文或違規紀錄作為認定機構違法的依據。上述痛點故事僅用於界定系統的社會價值與預警目標，不改變責任 AI 邊界。

---

## 需求優先級與範疇註記（Priority & Scoping Note）

為對齊 30 小時決賽策略與評分權重（技術可行性 30%、資料應用性 30%、完成度 20%、主題契合度 20%），需求分為三個優先級。實作時 P0 優先確保可 Demo。

| 優先級 | 定義 | 對應需求 |
|--------|------|----------|
| **P0（決賽決勝，必做可 Demo）** | 決賽現場展示的核心體驗，多數已有基線可延伸 | R1、R2、R5、R7、R8、R10、R11、R12、R13、R15、R19、R23 |
| **P1（加分，時間允許則做）** | 顯著提升說服力但非展示成敗關鍵 | R3、R4、R6、R9、R14、R16、R17、R18、R20、R21 |
| **P2（未來擴展／文件為主）** | 以計畫書、架構圖、藍圖形式交付，非執行程式碼 | R22、R24 |

「延伸現有」與「淨新增」於每則需求標題後標示：**[延伸現有]** 代表建立於 `src/` 或 `app/` 既有程式碼之上；**[淨新增]** 代表全新能力。

---

## Glossary

- **Watchdog_System**：整體「小小守護員」平台，涵蓋資料整合、風險引擎、AI 助手與三種使用者介面。
- **Risk_Engine**：風險計算子系統，含鑑識會計引擎與混合風險評分器（延伸 `src/forensic.py`、`src/risk_score.py`）。
- **Forensic_Engine**：鑑識會計引擎，實作班佛定律、Beneish、Isolation Forest、IQR 等方法（`src/forensic.py`）。
- **Risk_Scorer**：混合風險評分器，輸出 0–100 分與風險等級（`src/risk_score.py`）。
- **Anomaly_Detector**：異常偵測子系統，涵蓋點／情境／集體異常方法。
- **NLP_Engine**：文字分析子系統，處理裁罰／評鑑／公告文本分類與摘要。
- **AI_Copilot**：AI 稽查助手，以 AWS Bedrock 為基礎，回答須以資料為依據並附來源（延伸 `src/ai_report.py`）。
- **Report_Generator**：AI 稽查建議報告產生器（`src/ai_report.py`）。
- **Gov_Console**：政府指揮中心介面（Government Command Center）。
- **Inspector_Workspace**：稽查員調查工作台（Inspector Investigation Workspace）。
- **Parent_Portal**：家長信任中心公開透明入口（Parent Trust Center）。
- **Allocation_Optimizer**：智慧稽查分派最佳化子系統。
- **Simulation_Engine**：What-if 情境模擬子系統。
- **Evidence_Chain**：證據鏈，串接「AI 結論 → 特徵 → 原始資料 → 官方來源」。
- **Risk_Taxonomy**：風險分類體系（收費／人事／照顧／安全／行政／財務／其他）。
- **Knowledge_Graph**：風險知識圖譜（訊號 → 類別 → 風險融合）。
- **Entity_Resolver**：實體解析子系統，跨名稱變體與年度辨識同一機構。
- **Data_Source_Matrix**：資料來源矩陣，記錄每一資料源的屬性與可信度。
- **Confidence_Scorer**：資料可信度評分子系統。
- **Audit_Logger**：稽核軌跡紀錄子系統。
- **Institution**：受監理的教保機構（公立幼兒園、非營利幼兒園等）。
- **Inspector**：新北市教育局稽查員（使用者角色）。
- **Gov_User**：政府管理者／決策者（使用者角色）。
- **Parent_User**：家長或一般民眾（使用者角色）。
- **Risk_Score**：0–100 的機構風險總分。
- **Risk_Level**：風險等級，四級為 低／中／高／極高（critical）。
- **Peer_Group**：同儕群組，依機構類型／規模／區域劃分的比較基準。
- **Change_Point**：時間序列中統計上顯著的變化點。
- **Data_Confidence_Score**：單一資料紀錄或機構的資料可信度分數（0–100）。
- **HITL_Feedback**：人在迴路（Human-in-the-loop）審核回饋標記。
- **MAD**：平均絕對偏差（班佛定律指標）。
- **Weak_Signal**：輿情微弱訊號，指重大事件爆發前於家長／社群文本中出現的早期警訊（如師資頻繁更換、幼兒抗拒上學、監視設備異常）。
- **Broken_Window_Score**：破窗效應累犯加權分數，依違規嚴重度、時效衰減與頻率放大計算的裁罰分項組成。
- **Personnel_Affordability_Ratio**：人事費可負擔性比率，交叉勾稽登記教職員數應有人事支出與決算實際人事費的鑑識會計指標。

---

## Requirements

### Requirement 1: 三種使用者決策模式 [淨新增] (P0)

**User Story:** 作為系統設計者，我想要提供政府、稽查員、家長三種「不同的決策體驗」而非只是不同帳號，讓每一類使用者依其目標獲得最適介面與資訊揭露層級。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 提供三種且僅三種使用者模式：政府指揮中心（Gov_Console）、稽查員調查工作台（Inspector_Workspace）、家長信任中心（Parent_Portal），且任一登入使用者在同一時間僅對應其中一種模式。
2. WHEN Gov_User 完成登入，THE Watchdog_System SHALL 於預設進入畫面呈現 Gov_Console，且該畫面 SHALL 包含全轄區風險總覽（含高風險機構數量統計）與資源決策清單（依風險分數排序之機構列表）。
3. WHEN Inspector 完成登入，THE Watchdog_System SHALL 於預設進入畫面呈現 Inspector_Workspace，且該畫面 SHALL 提供選定單一機構後的深入調查檢視，包含該機構之風險分項明細與稽查建議。
4. WHEN Parent_User 完成登入，THE Watchdog_System SHALL 於預設進入畫面呈現 Parent_Portal，且該畫面 SHALL 提供機構公開資訊查詢功能，查詢結果僅包含公開透明欄位。
5. WHERE 使用者模式為 Parent_Portal，THE Watchdog_System SHALL 於所有畫面隱藏內部風險分數數值與風險等級標籤，且不提供任何可還原該分數或等級之欄位。
6. THE Watchdog_System SHALL 使三種模式各自對應之功能集合互不重疊，亦即任一功能項目 SHALL 僅屬於三種模式其中之一，不得同時出現於兩種以上模式。
7. IF 使用者未通過身分驗證或其使用者類型無法對應至三種模式之任一，THEN THE Watchdog_System SHALL 拒絕進入任一模式介面，並向該使用者顯示存取遭拒的提示，且不揭露任何機構風險分數或風險等級資訊。

---

### Requirement 2: 政府指揮中心 [延伸現有] (P0)

**User Story:** 作為政府管理者，我想要一個全市／分區的風險總覽指揮中心，讓我快速掌握整體風險態勢並做資源決策。

#### Acceptance Criteria

1. THE Gov_Console SHALL 顯示全市與各行政區的風險總覽。
2. THE Gov_Console SHALL 依據風險分數（0 至 100 分）將機構分為三個風險等級：高風險（70 分以上）、中風險（40 分至 69 分）、低風險（40 分以下）。
3. THE Gov_Console SHALL 顯示 KPI 計數，包含高風險機構數、中風險機構數、低風險機構數與新增異常機構數，且各計數為非負整數。
4. THE Gov_Console SHALL 顯示以 Leaflet 與 OpenStreetMap 呈現的風險地圖，並依風險等級以紅色（高風險）、黃色（中風險）、綠色（低風險）標示機構標記。
5. THE Gov_Console SHALL 顯示各行政區依風險分數由高至低排序的風險排名。
6. THE Gov_Console SHALL 顯示風險分數由高至低排序的高風險機構排名清單，最多顯示前 20 筆。
7. THE Gov_Console SHALL 顯示涵蓋近三個年度的風險趨勢。
8. THE Gov_Console SHALL 顯示風險熱點區域。
9. WHEN Gov_User 在地圖上點選一個機構標記，THE Gov_Console SHALL 顯示該機構名稱、風險分數與主要風險訊號。
10. IF Gov_User 點選的機構標記缺少風險分數或主要風險訊號資料，THEN THE Gov_Console SHALL 顯示該機構名稱並以提示訊息標示該資料尚未提供。

---

### Requirement 3: 智慧稽查分派最佳化 [淨新增] (P1)

**User Story:** 作為政府管理者，我想要在給定稽查員人數與差旅／區域限制下，得到一組能最大化風險覆蓋的稽查名單，讓有限人力精準投放。

#### Acceptance Criteria

1. WHEN Gov_User 提供稽查員人數 N（介於 1 至 1000 的整數）、區域限制、每間機構的風險分數（0 至 100）、已稽查清單與優先政策，THE Allocation_Optimizer SHALL 輸出一組稽查機構集合。
2. THE Allocation_Optimizer SHALL 以「在所有限制條件下，使所選機構風險分數總和達到可行解中的最大值」為最佳化目標產生稽查集合，其中風險覆蓋定義為所選機構風險分數之總和。
3. IF 存在多組風險分數總和相同的最佳解，THEN THE Allocation_Optimizer SHALL 依機構風險分數由高至低、風險分數相同時依機構識別碼由小至大之順序選取，使相同輸入永遠產生相同輸出。
4. THE Allocation_Optimizer SHALL 將已稽查清單中的機構排除於本次輸出之外。
5. WHERE 設定了區域限制，THE Allocation_Optimizer SHALL 使輸出的每一間機構皆滿足該區域限制。
6. THE Allocation_Optimizer SHALL 使輸出的稽查機構數量不超過稽查員人數 N，且在滿足所有限制條件下選取盡可能多但至多 N 間機構。
7. IF 滿足限制條件的合格機構數量少於 N，THEN THE Allocation_Optimizer SHALL 輸出全部合格機構並於結果中標示合格機構數少於 N。
8. IF 無任何機構滿足限制條件，THEN THE Allocation_Optimizer SHALL 回傳空集合並附帶說明無合格機構原因的訊息。
9. IF 稽查員人數 N 非介於 1 至 1000 的整數，THEN THE Allocation_Optimizer SHALL 拒絕該次請求、不產生稽查集合，並回傳指出 N 無效的錯誤訊息。
10. THE Allocation_Optimizer SHALL 為輸出集合中的每一間機構提供可解釋的分派理由，內容至少包含該機構的風險分數與其入選的依據。

---

### Requirement 4: What-if 情境模擬 [淨新增] (P1)

**User Story:** 作為政府管理者，我想要在調整配額、權重或排除條件時即時重新排序，讓我在決策前預覽不同政策的影響。

#### Acceptance Criteria

1. WHEN Gov_User 將稽查配額變更為介於 1 至 999 的指定值（如 5 或 10），THE Simulation_Engine SHALL 依新配額重新產生稽查優先序清單。
2. WHEN Gov_User 選擇權重方案（如純財務、費用優先），THE Simulation_Engine SHALL 依所選權重重新計算並重新排序機構。
3. WHEN Gov_User 選擇排除近期已稽查機構，THE Simulation_Engine SHALL 從結果中移除近 12 個月內已稽查的機構後重新排序。
4. THE Simulation_Engine SHALL 使模擬結果不覆寫系統的基準風險分數。
5. WHEN 任一模擬參數變更，THE Simulation_Engine SHALL 於 2 秒內回傳更新後的排序結果。
6. IF 模擬參數無效（配額非 1 至 999 的整數、權重方案不在允許清單內），THEN THE Simulation_Engine SHALL 拒絕該次模擬並回傳指出參數無效的訊息，且不變更既有顯示結果。

---

### Requirement 5: 稽查員調查工作台 [延伸現有] (P0)

**User Story:** 作為稽查員，我想要針對單一機構的完整調查工作台，讓我在一個畫面內完成風險判讀、佐證與稽查準備。

#### Acceptance Criteria

1. WHEN Inspector 開啟一個機構的工作台，THE Inspector_Workspace SHALL 於 3 秒內在單一畫面顯示該機構的總風險分數（0 到 100）與對應風險等級（高／中／低）。
2. THE Inspector_Workspace SHALL 以雷達圖顯示風險分數的分項組成（財務、裁罰、評鑑、輿情四類分項），且各分項加權後之總和 SHALL 等於顯示的總風險分數。
3. THE Inspector_Workspace SHALL 顯示該機構的風險時間軸，涵蓋所有可取得年度且依年度由舊到新排序。
4. THE Inspector_Workspace SHALL 顯示財務、收費、營運、法規與 NLP 五類分析結果，每一類 SHALL 呈現對應的判讀結論與佐證數據。
5. THE Inspector_Workspace SHALL 顯示該機構與其同儕群組（相同機構類型）在各風險分項上的比較數值。
6. THE Inspector_Workspace SHALL 顯示異常偵測結果，每一筆異常 SHALL 標示異常類型與觸發該異常的來源指標。
7. THE Inspector_Workspace SHALL 顯示證據鏈（Evidence_Chain），每一筆風險判讀 SHALL 可追溯至其對應的來源證據項目。
8. THE Inspector_Workspace SHALL 顯示可解釋 AI 的特徵歸因，列出對總風險分數貢獻最高的前 5 項特徵及其貢獻方向（提高／降低）。
9. THE Inspector_Workspace SHALL 顯示可操作的調查檢核清單，每一項 SHALL 可被稽查員標記為已完成或未完成。
10. THE Inspector_Workspace SHALL 提供 AI 稽查助手（AI_Copilot）互動入口，供稽查員輸入問題並取得回覆。
11. THE Inspector_Workspace SHALL 為每一個分析結果提供連結至其原始資料來源的可點擊連結。
12. WHERE 某一分析類別無可用資料，THE Inspector_Workspace SHALL 於該類別區塊顯示標示無資料的狀態，而非顯示空白或錯誤。
13. IF 機構工作台資料載入失敗，THEN THE Inspector_Workspace SHALL 顯示指出載入失敗的訊息並提供重新載入的操作，且不覆寫既有已顯示的資料。
14. IF 某一原始資料來源連結無法開啟，THEN THE Inspector_Workspace SHALL 顯示指出該來源無法存取的提示，且保留該機構工作台其餘內容可正常操作。

---

### Requirement 6: 家長信任中心（公開透明入口與責任 AI）[淨新增] (P1)

**User Story:** 作為家長，我想要一個公開透明的入口查詢教保機構的公開資訊，讓我在不被誤導的情況下了解機構狀況。

#### Acceptance Criteria

1. WHEN 家長開啟某機構頁面，THE Parent_Portal SHALL 顯示該機構的基本資訊、公私立別、收費資訊、公開評鑑結果與公開裁罰紀錄，且每一欄位皆取自官方公開資料來源。
2. THE Parent_Portal SHALL 針對每一項揭露資訊顯示其官方資料來源連結與該來源的最後更新時間。
3. IF 某一揭露欄位無對應官方公開資料，THEN THE Parent_Portal SHALL 將該欄位標示為「查無公開資料」，並且不以推估值、預設值或空白替代。
4. IF 某一欄位的官方資料來源最後更新時間距今超過 365 天，THEN THE Parent_Portal SHALL 於該欄位顯示「資料可能過時」之時效提示。
5. WHEN 顯示公開摘要，THE Parent_Portal SHALL 僅陳述可回溯至官方公開資料來源的事實，且每一則陳述皆標註其對應來源。
6. THE Parent_Portal SHALL 不顯示任何內部風險分數、風險等級或其衍生排序。
7. THE Parent_Portal SHALL 不將任何機構標示為高風險、違法、舞弊或不合格，亦不產生前述性質之文字或視覺標記。
8. WHEN 顯示公開摘要，THE Parent_Portal SHALL 不對機構作出任何違法、舞弊或未經官方認定之推論或評價陳述。

---

### Requirement 7: 鑑識會計核心 [延伸現有] (P0)

**User Story:** 作為稽查分析者，我想要以明確公式的鑑識會計指標與多維比較，讓財務異常判讀有學理根據且可解釋。

#### Acceptance Criteria

1. THE Forensic_Engine SHALL 計算下列指標，並以小數點後 4 位精度輸出：收入成長率 =（本年度收入 − 前年度收入）/ 前年度收入；支出成長率 =（本年度支出 − 前年度支出）/ 前年度支出；人事費占比 = 人事費 / 總支出；業務費占比 = 業務費 / 總支出；每名幼兒收入 = 收入 / 招生人數；每名幼兒支出 = 支出 / 招生人數。
2. THE Forensic_Engine SHALL 計算收入與招生人數的一致性指標，定義為每名幼兒收入相對同儕群組中位數的偏離比例。
3. THE Forensic_Engine SHALL 計算支出結構組成比例，將支出分為人事費、業務費與其他三類並輸出各類占總支出比例，且三類占比合計 SHALL 介於 0.99 至 1.01。
4. THE Forensic_Engine SHALL 計算年度對年度（YoY）變動率，定義為（本年度值 − 前年度值）/ 前年度值。
5. THE Forensic_Engine SHALL 計算機構各指標相對同儕群組的偏差，以 z-score 與百分位表示。
6. WHEN 某指標的 YoY 變動率絕對值達到門檻（預設 0.30，可設定範圍 0.01 至 5.00），THE Forensic_Engine SHALL 將該指標標記為突變（sudden change）。
7. THE Forensic_Engine SHALL 提供涵蓋至少 3 個年度的跨年度趨勢；若可得年度不足 3 個，則取全部可得年度。
8. THE Forensic_Engine SHALL 以同儕、年度、規模、區域與歷史五個維度進行多維比較。
9. THE Forensic_Engine SHALL 為每一項指標提供明確的計算公式定義。
10. THE Forensic_Engine SHALL 保留既有班佛定律（MAD 與卡方）、Beneish 改良版、Isolation Forest 與 IQR 離群方法。
11. IF 任一指標的分母為 0 或缺值（前年度值為 0、總支出為 0、招生人數為 0），THEN THE Forensic_Engine SHALL 將該指標標記為不可計算，將其排除於突變判定與同儕比較之外，且不中斷其餘指標的計算。
12. THE Forensic_Engine SHALL 計算人事費可負擔性勾稽指標（Personnel Affordability Cross-check），定義為 人事費可負擔性比率 =（登記教職員數 × 當年度法定最低薪資 × 12）/ 決算報告人事費支出；WHEN 該比率大於可設定門檻（預設 1.3，範圍 1.0 至 5.0），THE Forensic_Engine SHALL 將該機構標記為「人事費與登記人數不一致」之待查訊號，並於訊號中附登記教職員數、法定最低薪資基準與決算人事費三項原始值。
13. IF 登記教職員數或法定最低薪資或決算人事費任一為 0 或缺值，THEN THE Forensic_Engine SHALL 將人事費可負擔性勾稽指標標記為不可計算，並排除於待查訊號判定之外，且不中斷其餘指標計算。

---

### Requirement 8: 異常偵測 [延伸現有] (P0)

**User Story:** 作為風險分析者，我想要涵蓋點、情境與集體三類異常的偵測方法，並為每種方法提供適用理由，讓異常判讀方法完備且可辯護。

#### Acceptance Criteria

1. WHEN 對機構資料執行異常偵測，THE Anomaly_Detector SHALL 針對點異常（point anomaly）、情境異常（contextual anomaly）與集體異常（collective anomaly）三類各輸出一個布林旗標與一個異常分數。
2. THE Anomaly_Detector SHALL 提供 Isolation Forest、Local Outlier Factor、Z-score、穩健統計、時間序列、變化點與分群等方法，且每一方法 SHALL 輸出異常分數與由門檻導出的布林旗標。
3. THE Anomaly_Detector SHALL 為每一種所採用的偵測方法提供適用性說明，內容至少涵蓋其適用的異常類型、資料前提與已知限制。
4. WHEN 一個機構被 2 種以上獨立方法同時判為異常，THE Anomaly_Detector SHALL 將其標示為「高可信度異常」並記錄命中方法數；被單一方法判為異常時標示為「待確認異常」。
5. IF 機構資料量低於某方法可靠運作所需的最小樣本數，THEN THE Anomaly_Detector SHALL 跳過該方法、將其結果標示為樣本不足，且不中斷其餘方法的偵測。
6. THE Anomaly_Detector SHALL 保留既有 Isolation Forest 與 IQR 離群實作。

---

### Requirement 9: NLP 文字分析、風險分類體系與社群輿情微弱訊號 [淨新增] (P1)

**User Story:** 作為風險分析者，我想要對裁罰、評鑑、公告文本以及家長／社群輿情文本做結構化分析並建立風險分類體系，讓非結構化文字可轉為可用且可解釋的風險訊號。

#### Acceptance Criteria

1. WHEN 提供裁罰、評鑑或公告文本，THE NLP_Engine SHALL 對文本進行分類。
2. THE NLP_Engine SHALL 辨識違規類型與嚴重程度。
3. THE NLP_Engine SHALL 抽取關鍵字並進行主題分析。
4. THE NLP_Engine SHALL 產出事件摘要與事件時間軸。
5. THE NLP_Engine SHALL 依風險分類體系（Risk_Taxonomy）將文本歸類為收費、人事、照顧、安全、行政、財務或其他。
6. IF 文本無法對應任一既定分類，THEN THE NLP_Engine SHALL 歸類為「其他」並保留原始文本供人工判讀。
7. WHEN 提供家長或社群輿情文本，THE NLP_Engine SHALL 偵測預先定義的輿情微弱訊號（Weak Signal）關鍵字群，至少涵蓋：師資頻繁更換、幼兒抗拒上學、監視設備異常、管理封閉／拒絕溝通、照顧安全疑慮五類，並為每一則文本輸出命中的訊號類別與情緒傾向。
8. THE NLP_Engine SHALL 為每一則偵測到的輿情微弱訊號附上其來源文本片段與來源標示，供證據鏈追溯，且不將任何單一輿情文本作為認定機構違法之依據。
9. THE NLP_Engine SHALL 使用 AWS Bedrock 基礎模型執行輿情文本的訊號偵測與情緒分析；WHERE AWS Bedrock 不可用，THE NLP_Engine SHALL 退化為規則式關鍵字比對以維持可 Demo。
10. WHERE 輿情資料以抽樣示範資料集提供，THE NLP_Engine SHALL 於輸出中明確標示該結果為抽樣示範，並聲明架構可規模化至完整資料來源。
11. IF 一則輿情文本未命中任何預先定義的微弱訊號類別，THEN THE NLP_Engine SHALL 將其標記為「無明顯訊號」而不產生任何風險訊號。
12. THE NLP_Engine SHALL 以官方公開資料（裁罰紀錄與評鑑結果）作為機構關注信號的優先來源，將每一筆裁罰事由依 Risk_Taxonomy 歸類並標記嚴重度（輕微／中度／重大），且為每一筆官方信號附其官方資料來源標示供證據鏈追溯。
13. WHEN 呈現官方公開信號，THE NLP_Engine SHALL 僅陳述官方已公開之事實，不作違法、舞弊或不合格之認定。

---

### Requirement 10: 混合風險評分 [延伸現有] (P0)

**User Story:** 作為系統，我想要以規則、財務異常、營運、法規、NLP、趨勢與同儕偏差融合出 0–100 的可解釋風險分，讓稽查優先序有明確依據。

#### Acceptance Criteria

1. THE Risk_Scorer SHALL 融合規則、財務異常、營運、法規、NLP、趨勢與同儕偏差等分項，輸出 0–100 的風險分數。
2. THE Risk_Scorer SHALL 將風險分數映射為四個等級：低、中、高、極高（critical）。
3. THE Risk_Scorer SHALL 為每個風險分數提供各分項的貢獻明細。
4. THE Risk_Scorer SHALL 明確標示風險分數不等於違法認定。
5. WHERE 任一分項缺乏真實資料來源，THE Risk_Scorer SHALL 以中性值處理該分項而不以佔位值放大風險。
6. THE Risk_Scorer SHALL 保留既有百分位相對分級以支援稽查優先序排序。
7. THE Risk_Scorer SHALL 將風險分數組成為四個可攤開的頂層分項並套用下列預設權重，且四項權重合計為 1.0：財務異常 0.40、裁罰（含破窗效應累犯加權）0.30、評鑑 0.15、輿情 0.15。
8. THE Risk_Scorer SHALL 將輿情分項的貢獻上限限制為總分的 15 分，使任何輿情微弱訊號皆不足以單獨將機構推入高風險等級，以符合責任 AI 之「不得僅以單一訊號貼標籤」原則。
9. WHERE 輿情分項來自抽樣示範資料，THE Risk_Scorer SHALL 於該分項貢獻明細中標示其為示範估算。

---

### Requirement 11: 可解釋 AI 與證據鏈 [延伸現有] (P0)

**User Story:** 作為稽查員，我想要每一個 AI 結論都能回溯到原始資料與官方來源，讓判讀可被信任與複查。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 為每一個 AI 結論建立證據鏈：AI 結論 → 特徵 → 原始資料 → 官方來源。
2. WHEN 顯示一個風險結論，THE Watchdog_System SHALL 顯示支撐該結論的特徵歸因。
3. THE Watchdog_System SHALL 使每一個特徵歸因可追溯至其原始資料值。
4. THE Watchdog_System SHALL 使每一筆原始資料值可追溯至其官方來源。
5. THE Watchdog_System SHALL 保留既有 SHAP 特徵歸因作為可解釋輸出。

---

### Requirement 12: 風險時間軸與變化點偵測 [淨新增] (P0)

**User Story:** 作為稽查員，我想要看到機構跨年度的風險時間軸並標出顯著變化點，讓我聚焦在情勢惡化的時點。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 為每個機構產生跨年度的風險時間軸。
2. THE Watchdog_System SHALL 在時間軸上標記統計上顯著的變化點（Change_Point）。
3. WHEN 某年度的指標相對歷史序列達到變化點判定條件，THE Watchdog_System SHALL 於時間軸標示該變化點。
4. THE Watchdog_System SHALL 為每個標示的變化點提供對應的觸發指標說明。

---

### Requirement 13: 同儕比較 [延伸現有] (P0)

**User Story:** 作為稽查員，我想要以同儕群組的統計量比較機構表現，讓「異常」的判定有相對基準而非絕對臆測。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 依機構類型、規模與區域劃分同儕群組（Peer_Group）。
2. THE Watchdog_System SHALL 計算機構相對同儕群組的中位數、百分位、z-score 與穩健偏差。
3. WHEN 顯示同儕比較，THE Watchdog_System SHALL 標示機構在同儕群組中的相對位置。
4. IF 同儕群組樣本數低於可靠比較門檻，THEN THE Watchdog_System SHALL 標示該比較為樣本不足。

---

### Requirement 14: 風險知識圖譜 [淨新增] (P1)

**User Story:** 作為風險分析者，我想要以知識圖譜串接訊號、類別與風險，讓多來源訊號的融合關係可視化且可解釋。

#### Acceptance Criteria

1. THE Knowledge_Graph SHALL 建立訊號 → 類別 → 風險的節點與關係。
2. WHEN 產生一個機構的風險結論，THE Knowledge_Graph SHALL 呈現貢獻該結論的訊號與其所屬類別的關聯。
3. THE Knowledge_Graph SHALL 使每一個風險節點可追溯至其來源訊號節點。

---

### Requirement 15: AI 稽查助手（Copilot）[延伸現有] (P0)

**User Story:** 作為稽查員，我想要一個以資料為依據並附來源的 AI 助手，讓我能用自然語言詢問機構風險並得到可信答覆。

#### Acceptance Criteria

1. WHEN Inspector 向 AI_Copilot 提出關於某機構的問題，THE AI_Copilot SHALL 以該機構的資料為依據產生回答。
2. THE AI_Copilot SHALL 為回答中的關鍵陳述附上資料來源。
3. THE AI_Copilot SHALL 避免宣稱任何機構違法或舞弊。
4. IF 資料不足以回答問題，THEN THE AI_Copilot SHALL 明確告知資料不足而不杜撰。
5. WHERE AWS Bedrock 服務不可用，THE AI_Copilot SHALL 退化為規則式回覆以維持可 Demo。
6. THE AI_Copilot SHALL 延伸既有 `src/ai_report.py` 的 Bedrock 呼叫與 fallback 機制。

---

### Requirement 16: 資料來源矩陣 [淨新增] (P1)

**User Story:** 作為資料負責人，我想要一份誠實的資料來源矩陣，讓評審清楚每個資料源的屬性與可信度，且不虛構不存在的資料集。

#### Acceptance Criteria

1. THE Data_Source_Matrix SHALL 為每一資料源記錄來源、資料集、主管機關、更新頻率、格式、關鍵欄位、可信度、是否有 API、是否可下載、是否可追溯、用途與風險。
2. THE Data_Source_Matrix SHALL 僅列入實際存在或已確認的資料集。
3. WHERE 一個資料源的可用性尚未確認，THE Data_Source_Matrix SHALL 誠實標示為「未確認」而不宣稱可用。
4. THE Data_Source_Matrix SHALL 避免虛構任何資料集。
5. THE Data_Source_Matrix SHALL 將全國教保資訊網之裁罰紀錄與評鑑結果列為機構關注信號的官方公開來源，並記錄其為免金鑰、可公開追溯之資料源。

---

### Requirement 17: 資料整合管線與實體解析 [淨新增] (P1)

**User Story:** 作為資料工程者，我想要一條資料整合管線並能跨名稱變體與年度辨識同一機構，讓多來源資料能正確合併。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 提供整合財務、裁罰、評鑑、收費與地理資料的資料管線。
2. WHEN 同一機構出現名稱變體或跨年度紀錄，THE Entity_Resolver SHALL 將其解析為同一機構實體。
3. IF 兩筆紀錄的實體歸屬無法可靠判定，THEN THE Entity_Resolver SHALL 標示為待人工確認而不強制合併。
4. THE Entity_Resolver SHALL 為每一次合併決策保留可追溯的對應依據。

---

### Requirement 18: 資料可信度分數 [淨新增] (P1)

**User Story:** 作為風險分析者，我想要每筆資料都有可信度分數，讓低品質資料不會單獨造成誤判高風險。

#### Acceptance Criteria

1. THE Confidence_Scorer SHALL 為每一機構或資料紀錄計算 0–100 的資料可信度分數（Data_Confidence_Score）。
2. IF 一個機構的資料可信度分數低於設定門檻，THEN THE Risk_Scorer SHALL 不得僅因低可信度資料而將該機構判為高風險。
3. WHEN 顯示風險結論，THE Watchdog_System SHALL 併同顯示對應的資料可信度分數。

---

### Requirement 19: 責任 AI 政策 [淨新增] (P0)

**User Story:** 作為系統治理者，我想要明確的責任 AI 政策約束系統輸出，讓系統絕不越界做司法或違法認定。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 僅產出以下類型輸出：發現異常、排序、解釋、提供證據、建議稽查方向。
2. THE Watchdog_System SHALL 避免判定犯罪、舞弊或違法。
3. THE Watchdog_System SHALL 避免僅以單一訊號為機構貼上風險標籤。
4. WHEN 產生任何面向使用者的風險陳述，THE Watchdog_System SHALL 附帶「風險不等於違法」的聲明。

---

### Requirement 20: 人在迴路與回饋機制 [淨新增] (P1)

**User Story:** 作為稽查員，我想要對系統判定提供審核回饋，讓系統能納入人工判斷持續改進。

#### Acceptance Criteria

1. THE Inspector_Workspace SHALL 提供審核回饋按鈕，選項包含「確為異常」、「誤報」、「資料問題」與「需進一步稽查」。
2. WHEN Inspector 提交一筆審核回饋，THE Watchdog_System SHALL 記錄該回饋並關聯至對應機構與判定。
3. THE Watchdog_System SHALL 將累積的審核回饋提供予模型改進流程使用。

---

### Requirement 21: 稽核軌跡 [淨新增] (P1)

**User Story:** 作為系統治理者，我想要完整的稽核軌跡，讓每一項關鍵操作可被複查與問責。

#### Acceptance Criteria

1. WHEN 使用者執行風險判定、分派、模擬或回饋等關鍵操作，THE Audit_Logger SHALL 記錄操作者、時間、操作類型與對象。
2. THE Audit_Logger SHALL 使稽核紀錄僅可新增而不可竄改。
3. WHEN 治理者查詢稽核軌跡，THE Audit_Logger SHALL 依時間順序回傳相關操作紀錄。

---

### Requirement 22: 評估指標與標註策略 [淨新增] (P2，文件為主)

**User Story:** 作為評估負責人，我想要明確的評估指標與誠實的標註策略，讓模型效能可被衡量而不假裝擁有真實標籤。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 定義評估指標，包含 Precision、Recall、F1、FPR、FNR、PR-AUC、校準度、排序品質、可解釋性與人工一致性。
2. THE Watchdog_System SHALL 定義標註策略，包含專家標註、弱監督、歷史驗證、合成異常與規則基準。
3. WHERE 缺乏真實標籤，THE Watchdog_System SHALL 誠實揭露以替代標註策略評估，而不宣稱擁有真實標籤。
4. WHEN 報告評估結果，THE Watchdog_System SHALL 標示該結果所依據的標註來源與其限制。

---

### Requirement 23: 關鍵績效指標（KPI）[淨新增] (P0，展示指標)

**User Story:** 作為政府決策者，我想要一組營運 KPI，讓我衡量系統對稽查效能的實際貢獻。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 定義並計算下列 KPI：風險偵測率（Risk Detection Rate）、Recall@K、Precision@K、FPR、稽查時間縮減率（Investigation Time Reduction）、資料整合覆蓋率（Data Integration Coverage）、可解釋性覆蓋率（Explainability Coverage）、來源可追溯率（Source Traceability）與稽查資源效率（Inspection Resource Efficiency）。
2. WHEN Gov_User 檢視 KPI，THE Watchdog_System SHALL 為每一 KPI 顯示其定義與當前數值。
3. WHERE 某 KPI 因缺乏真實標籤而無法可靠計算，THE Watchdog_System SHALL 標示為「示範估算」並說明其依據。

---

### Requirement 24: 交付與文件產出 [淨新增] (P2，文件為主)

**User Story:** 作為參賽團隊，我想要完整的冠軍計畫書與各式簡報素材，讓決賽提案具備冠軍級完整度。

#### Acceptance Criteria

1. THE Watchdog_System SHALL 交付冠軍計畫書 V1.0（35 部分）。
2. THE Watchdog_System SHALL 以文字形式提供架構圖、資料流圖、AI 流程圖、風險評分圖與使用者模式圖。
3. THE Watchdog_System SHALL 提供 Demo 腳本。
4. THE Watchdog_System SHALL 提供 30 秒、1 分鐘、3 分鐘、5 分鐘與 10 分鐘五種長度的簡報稿。
5. THE Watchdog_System SHALL 提供 100 題評審問答集。
6. THE Watchdog_System SHALL 提供競品分析。
7. THE Watchdog_System SHALL 提供社會影響框架。
8. THE Watchdog_System SHALL 提供未來擴展規劃，涵蓋托嬰、長照與社福領域。

---

### Requirement 25: 破窗效應累犯加權 [淨新增] (P0)

**User Story:** 作為稽查分析者，我想要以有學理依據且可攤開解釋的方式，將機構「頻繁、近期、未改善的輕微違規」轉換為裁罰分項的加權分數，讓稽查優先序能反映破窗效應下的惡化趨勢，而非僅看違規總數。

**學理依據（供可辯護性，設計與簡報引用）：** 破窗理論（Wilson & Kelling；[The Spreading of Disorder, Keizer et al., Science 2008](https://www.researchgate.net/publication/23487060_The_Spreading_of_Disorder)）指出輕微失序訊號會誘發更嚴重的失序與擴散；動態再犯風險研究（[OxMore, Yukhnenko et al., Oxford](https://pmc.ncbi.nlm.nih.gov/articles/PMC7618717/)）證實近期急性事件較陳年紀錄更具預測力，支撐時效衰減設計。以上內容已改寫以符合授權限制。

#### Acceptance Criteria

1. THE Risk_Engine SHALL 計算破窗效應累犯加權分數（Broken_Window_Score），定義為機構於評估期間內每一筆違規紀錄之（嚴重度權重 × 時效衰減係數）之總和，再乘以頻率放大係數，並將結果上限截斷於 100。
2. THE Risk_Engine SHALL 依違規類型指派嚴重度權重，且分為三級：輕微（如超收、資料未依規公開）權重 3、中度（如進用未具資格人員、收費違規）權重 6、重大（如隱匿或規避稽查、照顧與安全疑慮）權重 12。
3. THE Risk_Engine SHALL 以時效衰減係數 = 0.5^(違規距今月數 / H) 計算每筆違規的時間權重，其中半衰期 H 為可設定值（預設 18 個月，範圍 6 至 36 個月），使近期違規權重高於久遠違規。
4. THE Risk_Engine SHALL 以頻率放大係數 = 1 + 0.15 ×（評估期間內違規總筆數 − 1）計算頻率放大，且違規筆數為 0 時破窗效應累犯加權分數為 0。
5. THE Risk_Engine SHALL 使評估期間預設為近 36 個月且為可設定值。
6. THE Risk_Engine SHALL 為每一個破窗效應累犯加權分數提供可攤開的貢獻明細，列出每一筆納入計算的違規之類型、嚴重度權重、距今月數、時效衰減係數與該筆之加權貢獻值。
7. THE Risk_Engine SHALL 將破窗效應累犯加權分數作為裁罰分項的組成之一併入混合風險評分，且不改變裁罰分項於總分中的既定權重。
8. IF 某違規紀錄缺少可辨識的違規類型或發生日期，THEN THE Risk_Engine SHALL 將該筆標記為待人工確認並排除於破窗效應累犯加權分數計算之外，且不中斷其餘違規紀錄的計算。
9. THE Risk_Engine SHALL 使相同的違規紀錄輸入永遠產生相同的破窗效應累犯加權分數（確定性）。

---

## 附註：解析器與序列化需求（Parser & Serializer Note）

本平台的資料整合管線（R17）涉及公校決算 PDF 文字層擷取與非營利園掃描財報（OCR / AWS Textract / Bedrock 多模態）的欄位解析。凡涉及將原始文件解析為結構化財務物件之處，設計階段 SHALL 納入對應的美化輸出（pretty printer）與往返一致性（round-trip：parse → print → parse 產生等價物件）驗證，以確保解析正確性。此附註供設計階段展開為具體元件需求。
