# Implementation Plan: 小小守護員 Smart Watchdog Platform

## Overview

本實作計畫將 `design.md` 轉為一系列漸進式、可交由程式生成的編碼任務，嚴格建立於既有基線（`src/forensic.py`、`src/risk_score.py`、`src/ai_report.py`、`app/`、`data/`）之上——**延伸而非重寫**。任務排序對齊 30 小時決賽策略：先鞏固 P0 可 Demo 骨幹（風險引擎、白盒評分、三入口、地圖、AI 助手），再擴展 P1 加分（分派最佳化、模擬、NLP、資料管線、治理），P2 文件類需求以文件交付不列為編碼任務。

每個任務皆以既有契約檔 `kindergartens_latest.csv` / `kindergartens.csv` 為共同資料源，確保現有 Streamlit 頁面不被破壞。屬性測試以 Hypothesis 實作，每個 Correctness Property 對應單一屬性測試，並置於其實作任務附近以及早捕捉錯誤。

實作語言為 **Python 3**（依 design.md 技術棧：pandas、numpy、scipy、scikit-learn、SHAP、Hypothesis、pytest、Streamlit）。

## Tasks

- [x] 1. 建立測試骨架與共用型別
  - 建立 `tests/` 目錄與 `pytest` 設定（`pytest.ini` 或 `pyproject` 區塊），加入 `hypothesis` 至 `requirements.txt`
  - 在 `src/models.py` 定義共用 dataclass 型別：`SourceRef`、`Metric`、`ForensicMetrics`、`AnomalyMethodResult`、`AnomalyResult`、`RiskBreakdown`、`EvidenceLink`、`AllocationItem`、`AllocationResult`、`SimParams`、`PublicInstitutionView`、`AuditEntry`、`HITLFeedback`、`DataConfidence`、`FinancialRecord`
  - 建立測試共用 Hypothesis 產生器模組 `tests/generators.py`（財務金額含 0/負/None/極大值、名稱變體、時效邊界、分派 N 邊界）
  - _Requirements: 7.1, 8.1, 10.1, 3.1, 6.1, 17.1, 21.1_

- [x] 2. 鑑識會計核心指標（延伸 `src/forensic.py`）
  - [x] 2.1 實作明確公式指標與精度輸出
    - 新增 `compute_metrics(row, peer_stats) -> ForensicMetrics`，計算收入成長率、支出成長率、人事費占比、業務費占比、每名幼兒收入、每名幼兒支出，並以小數點後 4 位輸出
    - 每一 `Metric` 附非空 `formula` 字串；計算收入/招生一致性指標與同儕 z-score/百分位
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.9_

  - [x] 2.2 實作支出結構占比與缺值保護
    - 計算人事/業務/其他三類占總支出比例（合計介於 0.99–1.01）
    - 分母為 0 或缺值（前年度值 0、總支出 0、招生人數 0）時將該指標標記 `computable=False`，排除於突變判定與同儕比較，且不中斷其餘指標
    - _Requirements: 7.3, 7.11_

  - [x] 2.3 實作突變門檻與跨年度趨勢
    - 新增 `sudden_change_flag(yoy_rate, threshold=0.30)`，threshold 可設定範圍 0.01–5.00
    - 提供涵蓋至少 3 個年度的跨年度趨勢；不足 3 年取全部可得年度
    - 保留既有班佛（MAD+卡方）、Beneish 改良版、Isolation Forest、IQR 離群方法
    - _Requirements: 7.6, 7.7, 7.10_

  - [ ] 2.3b 實作人事費可負擔性勾稽指標
    - 新增 `personnel_affordability(row, min_wage, threshold=1.3) -> AffordabilityCheck`
    - ratio =（登記教職員數 × 法定最低薪資 × 12）/ 決算人事費；ratio > 門檻(1.0–5.0) → 標記「人事費與登記人數不一致」待查訊號並附三項原始值
    - 任一因子為 0/缺值 → 標記不可計算並排除判定，不中斷其餘指標
    - _Requirements: 7.12, 7.13_

  - [ ]* 2.4 撰寫鑑識指標公式與精度屬性測試
    - **Property 19: 鑑識指標公式與精度**
    - **Validates: Requirements 7.1, 7.2, 7.4**

  - [ ]* 2.4b 撰寫人事費可負擔性勾稽屬性測試
    - **Property 46: 人事費可負擔性勾稽正確與缺值安全**
    - **Validates: Requirements 7.12, 7.13**

  - [ ]* 2.5 撰寫支出結構占比屬性測試
    - **Property 20: 支出結構占比合計為一**
    - **Validates: Requirements 7.3**

  - [ ]* 2.6 撰寫除零／缺值安全屬性測試
    - **Property 24: 除零／缺值安全（不可計算標記）**
    - **Validates: Requirements 7.11**

  - [ ]* 2.7 撰寫突變門檻、趨勢覆蓋與公式定義屬性測試
    - **Property 21: 突變門檻判定**（Validates: Requirements 7.6）
    - **Property 22: 跨年度趨勢覆蓋**（Validates: Requirements 7.7）
    - **Property 23: 每指標具明確公式定義**（Validates: Requirements 7.9）

  - [ ]* 2.8 撰寫既有方法回歸單元測試
    - 驗證班佛/Beneish/IForest/IQR 仍正常運作
    - _Requirements: 7.10_

- [x] 3. 異常偵測（延伸 `src/forensic.py` / 新增 `src/anomaly.py`）
  - [x] 3.1 實作點/情境/集體三類異常與多方法輸出
    - 新增 `detect(entity, methods) -> AnomalyResult`，對 point/contextual/collective 各輸出 (bool flag, score)
    - 提供 Isolation Forest、LOF、Z-score、穩健統計、時間序列、變化點、分群等方法，每方法輸出 score + 由門檻導出的 flag
    - 樣本不足時標記 `insufficient_sample` 並跳過，不中斷其餘方法；保留既有 Isolation Forest 與 IQR
    - _Requirements: 8.1, 8.2, 8.5, 8.6_

  - [x] 3.2 實作方法適用性說明與一致性整合
    - `method_applicability(method) -> MethodNote`（適用異常類型、資料前提、已知限制）
    - `consolidate(results) -> ConsolidatedAnomaly`：≥2 方法命中 → `high_confidence` 並記命中數；單一方法 → `to_confirm`
    - _Requirements: 8.3, 8.4_

  - [ ]* 3.3 撰寫異常旗標與分數一致屬性測試
    - **Property 25: 異常旗標與分數一致**
    - **Validates: Requirements 8.1, 8.2**

  - [ ]* 3.4 撰寫異常一致性整合屬性測試
    - **Property 26: 異常一致性整合**
    - **Validates: Requirements 8.4**

- [x] 4. 同儕比較與資料可信度（新增 `src/peer.py`、`src/confidence.py`）
  - [x] 4.1 實作同儕群組與統計量
    - `build_peer_group(entity, population, by=("park_type","size_band","district"))`
    - `peer_stats(entity, group) -> PeerComparison`：中位數/百分位/z-score/穩健偏差；樣本 < 門檻標記 `insufficient`
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 4.2 實作資料可信度分數
    - `confidence(record) -> DataConfidence`，輸出 0–100 分與 factors 明細
    - _Requirements: 18.1_

  - [ ]* 4.3 撰寫同儕統計量屬性測試
    - **Property 35: 同儕統計量正確**
    - **Validates: Requirements 13.2**

  - [ ]* 4.4 撰寫資料可信度範圍屬性測試
    - **Property 37: 資料可信度落於有效範圍**
    - **Validates: Requirements 18.1**

  - [x] 4.5 實作破窗效應累犯加權分數（新增 `src/broken_window.py`）並接入裁罰分項（R25.7）
    - `broken_window_score(violations, as_of, half_life_months=18, window_months=36) -> BrokenWindowResult`
    - 分數 = min(100, 頻率放大係數 × Σ(嚴重度權重 × 時效衰減))；嚴重度 輕微=3/中度=6/重大=12；時效衰減 = 0.5^(月數/半衰期)（H 範圍 6–36）；頻率放大 = 1 + 0.15×(筆數−1)；筆數 0 → 分數 0
    - 評估窗預設近 36 個月可設定；每筆附貢獻明細（類型/嚴重度/月數/衰減/貢獻值）
    - 缺類型或發生日期 → 標記待人工確認並排除計算，不中斷其餘；相同輸入確定性輸出
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.6, 25.8, 25.9_

  - [x]* 4.6 撰寫破窗效應公式、上限與確定性屬性測試
    - **Property 44: 破窗效應累犯加權—公式、上限與確定性**
    - **Validates: Requirements 25.1, 25.2, 25.3, 25.4, 25.9**

  - [x]* 4.7 撰寫破窗效應時效單調性與缺值排除屬性測試
    - **Property 45: 破窗效應累犯加權—時效單調性與缺值排除**
    - **Validates: Requirements 25.3, 25.8**

- [x] 5. Checkpoint — 確認鑑識引擎與異常偵測測試通過
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 白盒混合風險評分（延伸 `src/risk_score.py`）
  - [x] 6.1 實作分項貢獻明細與可加性
    - 新增 `score(entity, weights, confidence) -> RiskBreakdown`，輸出 total(0–100) + 各分項貢獻明細 + level(低/中/高/極高)
    - 確保 `round(sum(contributions.values()),1) == total`；保留既有加權與百分位相對分級
    - _Requirements: 10.1, 10.2, 10.3, 10.6, 5.2_

  - [ ] 6.1b 擴充為四分項權重並併入破窗與輿情
    - 將權重由三分項更新為四頂層分項：財務異常 0.40 + 裁罰(含 Broken_Window_Score) 0.30 + 評鑑 0.15 + 輿情 0.15（合計 1.0）
    - 裁罰分項納入 `broken_window_score` 輸出（不改變裁罰於總分的既定權重）
    - 輿情分項貢獻 clamp 至 ≤ 15 分；輿情來自抽樣示範時於明細標示 `demo_estimate`
    - 以附加欄位承接輿情分數，不破壞 `app/lib/common.py` 契約
    - _Requirements: 10.7, 10.8, 10.9, 25.7_

  - [ ]* 6.1c 撰寫輿情分項貢獻上限屬性測試
    - **Property 48: 輿情分項貢獻上限**
    - **Validates: Requirements 10.7, 10.8**

  - [ ] 6.1d 實作雙評分檔（財務鑑識園 vs 行為監測園）(P1)
    - 新增 `resolve_scoring_profile(entity) -> str`：具可用獨立財務決算 → `forensic`，否則 → `behavioral`（確定性）
    - 定義 `PROFILE_WEIGHTS`：forensic {財務 0.40, 裁罰 0.30, 評鑑 0.15, 輿情 0.15}；behavioral {裁罰 0.50, 評鑑 0.30, 輿情 0.20}（財務標記 N/A 不計入）
    - `score()` 依評分檔套用權重；behavioral 檔財務分項不以 0/佔位放大或壓低；兩檔總分 0–100、輿情上限 15
    - behavioral 三分項皆無真實資料 → 中性處理不判高風險 + 降可信度 + 標示「可用資料不足以評估」
    - `RiskBreakdown` 新增 `scoring_profile` 與 `profile_notice` 欄位；於風險呈現標示評分檔別與（behavioral）「無獨立財報…」揭露訊息
    - 附幼名單/裁罰/評鑑資料以快照提供時標示為抽樣/快照示範並聲明可規模化
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7, 26.8, 26.9, 26.10_

  - [ ]* 6.1e 撰寫雙評分檔權重、範圍與確定性屬性測試
    - **Property 49: 雙評分檔權重、範圍與確定性**
    - **Validates: Requirements 26.1, 26.2, 26.3, 26.4, 26.7, 26.9**

  - [x] 6.2 實作缺資料中性處理與責任 AI 標示
    - 缺資料分項以中性值代入而不放大風險；低可信度不得單獨推高風險
    - 每個 `RiskBreakdown` 附非空「風險不等於違法」聲明與 `data_confidence`
    - _Requirements: 10.4, 10.5, 18.2, 18.3, 19.4_

  - [ ]* 6.3 撰寫白盒分數可加性屬性測試
    - **Property 17: 白盒分數可加性**
    - **Validates: Requirements 5.2, 10.3**

  - [ ]* 6.4 撰寫風險總分範圍屬性測試
    - **Property 28: 風險總分落於有效範圍**
    - **Validates: Requirements 10.1**

  - [ ]* 6.5 撰寫責任 AI 聲明與低可信度不放大屬性測試
    - **Property 29: 風險不等於違法聲明恆存在**（Validates: Requirements 10.4, 19.4）
    - **Property 30: 低可信度／缺資料不放大風險**（Validates: Requirements 10.5, 18.2）

- [x] 7. 風險時間軸與變化點偵測（新增 `src/timeline.py`）
  - [x] 7.1 實作時間軸建構與變化點偵測
    - `build_timeline(entity_years) -> RiskTimeline`（年度由舊到新排序，涵蓋所有可取得年度）
    - `detect_change_points(series) -> list[ChangePoint]`：統計顯著變化點，每點附觸發指標說明
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 5.3_

  - [ ]* 7.2 撰寫時間軸排序屬性測試
    - **Property 18: 風險時間軸排序與完整**
    - **Validates: Requirements 5.3, 12.1**

  - [ ]* 7.3 撰寫變化點標記與說明屬性測試
    - **Property 36: 變化點標記與說明**
    - **Validates: Requirements 12.2, 12.3, 12.4**

- [x] 8. 證據鏈與知識圖譜（延伸 SHAP + 新增 `src/evidence.py`）
  - [x] 8.1 實作證據鏈與知識圖譜
    - `build_evidence_chain(conclusion) -> EvidenceChain`：結論 → 特徵歸因 → 原始資料值 → 官方來源，每一環可追溯
    - `build_knowledge_graph(signals) -> KnowledgeGraph`：訊號 → 類別 → 風險節點與關係，每風險節點可回溯來源訊號
    - 保留既有 SHAP 特徵歸因作為可解釋輸出
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 14.1, 14.2, 14.3_

  - [ ]* 8.2 撰寫證據鏈完整可追溯屬性測試
    - **Property 32: 證據鏈完整可追溯**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.4**

  - [ ]* 8.3 撰寫知識圖譜可回溯屬性測試
    - **Property 33: 知識圖譜可回溯**
    - **Validates: Requirements 14.1, 14.2, 14.3**

- [x] 9. Checkpoint — 確認評分、時間軸與證據鏈測試通過
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. NLP 文字分析與風險分類體系（新增 `src/nlp_engine.py`）
  - [x] 10.1 實作文本分類、抽取與 Risk_Taxonomy 歸類
    - `analyze_text(text, doc_type) -> NLPResult`：分類、違規類型與嚴重度、關鍵字/主題、事件摘要與時間軸
    - 依 Risk_Taxonomy 歸類為收費/人事/照顧/安全/行政/財務/其他；無法歸類 → 「其他」並保留原文供人工判讀
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [x] 10.1a 實作官方公開信號來源（新增 `src/official_signals.py`）
    - 將契約檔既有裁罰/評鑑欄位（`penalty_count`/`penalty_reason`/`eval_grade`）轉為結構化官方信號
    - 每筆裁罰依 Risk_Taxonomy 歸類並標記嚴重度（輕微/中度/重大），附官方資料來源標示供證據鏈追溯
    - 改寫 `app/pages/4_sentiment.py` 為「官方公開信號分析」，取代示範評論，僅陳述官方已公開事實不作違法認定
    - _Requirements: 9.12, 9.13, 16.5_

  - [ ] 10.1b 實作社群輿情微弱訊號偵測（Bedrock + fallback）
    - 新增 `detect_weak_signals(text, source) -> WeakSignalResult`，偵測五類訊號：師資頻繁更換、幼兒抗拒上學、監視設備異常、管理封閉/拒絕溝通、照顧安全疑慮
    - 輸出命中訊號類別 + 情緒傾向 + 來源文本片段與來源標示（供證據鏈）；單一輿情文本不作違法認定依據
    - 優先以 AWS Bedrock 執行；不可用 → 規則式關鍵字比對 fallback；抽樣示範資料標示 `is_demo_sample` 並聲明可規模化
    - 未命中任何類別 → 標記 `no_signal` 不產生風險訊號
    - 準備 50–100 筆模擬輿情貼文資料集置於 `data/`
    - _Requirements: 9.7, 9.8, 9.9, 9.10, 9.11_

  - [ ]* 10.2 撰寫文本歸類屬性測試
    - **Property 27: 文本歸類落於分類體系**
    - **Validates: Requirements 9.5, 9.6**

  - [ ]* 10.2b 撰寫輿情微弱訊號歸類與責任邊界屬性測試
    - **Property 47: 輿情微弱訊號歸類與責任邊界**
    - **Validates: Requirements 9.7, 9.8, 9.11**

  - [ ]* 10.3 撰寫 NLP 具體案例單元測試
    - 分類/摘要/時間軸具體案例
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 11. 分派最佳化（新增 `src/allocation.py`）
  - [x] 11.1 實作風險覆蓋最大化與確定性 tie-break
    - `optimize(institutions, n, region_filter, inspected, policy) -> AllocationResult`
    - 在限制下最大化所選機構風險分數總和；多最佳解依 (風險分 desc, park_id asc) 確定性選取
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 11.2 實作限制過濾、輸出上限與邊界處理
    - 排除已稽查、滿足區域限制、輸出 ≤ N 且盡量多；合格 < N → 全輸出並標示 `fewer_than_n`；無合格 → 空集合+說明
    - N 非 1–1000 整數 → 拒絕+錯誤訊息；每機構附含風險分數的分派理由
    - _Requirements: 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10_

  - [ ]* 11.3 撰寫風險覆蓋最大化屬性測試（含小輸入暴力法參考）
    - **Property 9: 分派最佳化—風險覆蓋最大化**
    - **Validates: Requirements 3.2**

  - [ ]* 11.4 撰寫確定性與 tie-break 屬性測試
    - **Property 10: 分派確定性與 tie-break**
    - **Validates: Requirements 3.3**

  - [ ]* 11.5 撰寫限制滿足與輸出上限屬性測試
    - **Property 11: 分派輸出滿足所有限制**（Validates: Requirements 3.4, 3.5, 3.6）
    - **Property 12: 分派理由完整**（Validates: Requirements 3.10）
    - **Property 13: 無效稽查員人數被拒絕**（Validates: Requirements 3.9）

- [x] 12. What-if 情境模擬（新增 `src/simulation.py`）
  - [x] 12.1 實作重排序、參數效果與基準保護
    - `simulate(base, params) -> SimulationResult`：依配額(1–999)/權重方案/排除近12月已稽查重排序
    - 不覆寫基準風險分數；參數無效 → 拒絕+訊息且不變更既有顯示
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 12.2 撰寫模擬不覆寫基準分數屬性測試
    - **Property 14: 模擬不覆寫基準分數**
    - **Validates: Requirements 4.4**

  - [ ]* 12.3 撰寫模擬重排序與無效參數屬性測試
    - **Property 15: 模擬重排序與參數效果**（Validates: Requirements 4.1, 4.2, 4.3）
    - **Property 16: 無效模擬參數被拒絕且不變更顯示**（Validates: Requirements 4.6）

- [x] 13. Checkpoint — 確認 NLP、分派與模擬測試通過
  - Ensure all tests pass, ask the user if questions arise.

- [x] 14. 資料管線、實體解析與文件解析器（新增 `src/pipeline.py`、`src/entity_resolver.py`、`src/financial_parser.py`）
  - [x] 14.1 實作整合管線與實體解析
    - `run_pipeline(sources) -> IntegratedDataset`：整合財務/裁罰/評鑑/收費/地理，輸出至既有契約檔
    - `resolve_entity(records)`：跨名稱變體/年度解析為同一實體；無法可靠判定 → `pending_manual` 不強制合併；每合併決策保留可追溯依據
    - _Requirements: 17.1, 17.2, 17.3, 17.4_

  - [x] 14.2 實作財務文件解析器與美化輸出（pretty printer）
    - `parse_financial_record(raw_text) -> FinancialRecord` 與 `print_financial_record(record) -> str`
    - 確保 round-trip 一致性：`parse(print(x))` 等價於 x
    - _Requirements: 17.1_

  - [ ]* 14.3 撰寫實體解析一致且冪等屬性測試
    - **Property 38: 實體解析一致且冪等**
    - **Validates: Requirements 17.2, 17.4**

  - [ ]* 14.4 撰寫財務文件解析往返一致屬性測試
    - **Property 39: 財務文件解析往返一致**
    - **Validates: Requirements 17.1**

- [x] 15. 資料來源矩陣、治理與 KPI（新增 `src/data_source_matrix.py`、`src/audit.py`、`src/kpi.py`）
  - [x] 15.1 實作資料來源矩陣
    - 靜態設定表記錄每資料源屬性與可信度；僅列實際存在資料集，未確認標「未確認」，不虛構
    - 將全國教保資訊網裁罰/評鑑列為機構關注信號之官方公開來源（免金鑰、可追溯）
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

  - [x] 15.2 實作稽核軌跡與 HITL 回饋
    - `log(actor, action, target, ts)` append-only 不可竄改；`query_audit(filter)` 依時間順序回傳
    - `submit_feedback(fb)`：確為異常/誤報/資料問題/需進一步稽查，關聯機構與判定
    - _Requirements: 20.1, 20.2, 20.3, 21.1, 21.2, 21.3_

  - [x] 15.3 實作 KPI 計算器
    - 計算 Risk Detection Rate、Recall@K、Precision@K、FPR、資料整合覆蓋率、可解釋性覆蓋率、來源可追溯率等，附定義與數值；缺真實標籤標「示範估算」
    - _Requirements: 23.1, 23.2, 23.3_

  - [ ]* 15.4 撰寫稽核軌跡屬性測試
    - **Property 40: 稽核軌跡僅可新增**（Validates: Requirements 21.1, 21.2）
    - **Property 41: 稽核軌跡時間排序**（Validates: Requirements 21.3）

  - [ ]* 15.5 撰寫 KPI 計算範圍屬性測試
    - **Property 42: KPI 計算落於定義範圍**
    - **Validates: Requirements 23.1**

- [x] 16. AI 稽查助手與報告（延伸 `src/ai_report.py`）
  - [x] 16.1 強化 Copilot 提示詞負向約束與資料依據回答
    - 新增 `answer(question, entity) -> CopilotAnswer`：以機構資料為依據回答，關鍵陳述附來源，資料不足明確告知不杜撰
    - 提示詞負向約束 + 輸出後過濾，避免違法/舞弊斷言；保留既有 `build_prompt`/`generate_with_bedrock`/`generate_fallback`/`generate_report`
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.6, 19.1, 19.2, 19.3_

  - [x] 16.2 確保 Bedrock 不可用退化 fallback 保底
    - Bedrock 失敗時 `generate_report` 回傳非空報告並標示來源 `fallback`
    - _Requirements: 15.5_

  - [ ]* 16.3 撰寫不作違法／舞弊宣稱屬性測試
    - **Property 31: 不作違法／舞弊宣稱**
    - **Validates: Requirements 6.7, 15.3, 19.2**

  - [ ]* 16.4 撰寫 AI 報告 fallback 保底屬性測試
    - **Property 43: AI 報告 fallback 保底**
    - **Validates: Requirements 15.5**

- [x] 17. Checkpoint — 確認資料層、治理與 AI 層測試通過
  - Ensure all tests pass, ask the user if questions arise.

- [x] 18. 使用者模式路由與存取控制（新增 `app/lib/modes.py`）
  - [x] 18.1 實作三模式路由與存取拒絕
    - 依使用者類型路由至 Gov_Console / Inspector_Workspace / Parent_Portal；未驗證/無法對應 → 存取拒絕且不揭露任何分數/等級
    - 定義三模式功能集合，確保互斥不重疊
    - _Requirements: 1.1, 1.6, 1.7_

  - [x] 18.2 實作家長入口欄位白名單投影
    - `public_view()` 移除 `risk_total`、`risk_level`、所有 `score_*` 與衍生排序欄位後才呈現
    - _Requirements: 1.5, 6.6_

  - [ ]* 18.3 撰寫使用者模式屬性測試
    - **Property 1: 使用者模式唯一對應**（Validates: Requirements 1.1）
    - **Property 3: 功能集合互斥**（Validates: Requirements 1.6）
    - **Property 4: 未授權存取不揭露分數**（Validates: Requirements 1.7）

  - [ ]* 18.4 撰寫家長入口隱藏風險資訊屬性測試
    - **Property 2: 家長入口隱藏所有內部風險資訊**
    - **Validates: Requirements 1.5, 6.6**

- [x] 19. 政府指揮中心（延伸 `app/` — Gov_Console）
  - [x] 19.1 實作風險等級分級、KPI 計數與排名
    - 依分數分級（≥70 高、40–69 中、<40 低）；顯示高/中/低/新增異常計數（非負整數）
    - 顯示行政區風險排名與高風險機構排名（最多前 20 筆）、近三年趨勢、風險熱點
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8_

  - [x] 19.2 實作 Leaflet 風險地圖與標記點選
    - Leaflet + OpenStreetMap 地圖，依等級紅/黃/綠標記；點選標記顯示名稱+分數+主要風險訊號
    - 標記缺分數/訊號 → 顯示名稱並標示「資料尚未提供」
    - _Requirements: 2.4, 2.9, 2.10_

  - [ ]* 19.3 撰寫分級、KPI 計數、地圖顏色與排名屬性測試
    - **Property 5: 風險等級分級門檻**（Validates: Requirements 2.2）
    - **Property 6: KPI 計數非負且分類完備**（Validates: Requirements 2.3）
    - **Property 7: 地圖顏色映射確定**（Validates: Requirements 2.4）
    - **Property 8: 排名排序與截斷**（Validates: Requirements 2.5, 2.6）

- [x] 20. 稽查員調查工作台（延伸 `app/` — Inspector_Workspace）
  - [x] 20.1 實作單一機構調查檢視與雷達圖分項
    - 顯示總風險分數與等級、雷達圖分項組成（財務/裁罰/評鑑/輿情，加權總和==總分）、風險時間軸
    - 顯示財務/收費/營運/法規/NLP 五類分析、同儕比較、異常偵測結果、證據鏈、前 5 特徵歸因、AI Copilot 入口
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.10, 5.11_

  - [x] 20.2 實作調查檢核清單、HITL 回饋與錯誤處理
    - 可勾選檢核清單；HITL 回饋按鈕（確為異常/誤報/資料問題/需進一步稽查）
    - 無資料類別顯示「無資料」狀態；載入失敗顯示訊息+重新載入不覆寫既有；來源連結無法開啟顯示提示且其餘可操作
    - _Requirements: 5.9, 5.12, 5.13, 5.14, 20.1_

- [x] 21. 家長信任中心（延伸 `app/` — Parent_Portal）
  - [x] 21.1 實作公開資訊揭露與來源時效標記
    - 顯示基本資訊/公私立別/收費/公開評鑑/公開裁罰，每欄位附官方來源連結與最後更新時間
    - 無官方資料 → 「查無公開資料」不以推估/預設/空白替代；來源超過 365 天 → 「資料可能過時」
    - 不顯示任何風險分數/等級/衍生排序；不作違法/舞弊/高風險標記
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.7, 6.8_

  - [ ]* 21.2 撰寫資料時效門檻標記屬性測試
    - **Property 34: 資料時效門檻標記**
    - **Validates: Requirements 6.4**

- [x] 22. 整合與端到端串接
  - [x] 22.1 串接風險引擎輸出至契約檔與三入口
    - 將 Forensic/Anomaly/Scorer/Timeline/Evidence 輸出寫入 `kindergartens_latest.csv` / `kindergartens.csv`（以附加欄位方式，不破壞 `app/lib/common.py` 載入契約）
    - 三入口與 Copilot 讀取已算好的分數與指標，確保 AI 不回流影響計分
    - _Requirements: 10.1, 11.1, 17.1_

  - [ ]* 22.2 撰寫資料管線端到端整合測試
    - 由 `data/` 原始資料跑至 `kindergartens_latest.csv`
    - _Requirements: 17.1_

  - [ ]* 22.3 撰寫 Bedrock 與 fallback 路徑整合測試
    - 有金鑰 1 範例 + 無金鑰 fallback 1 範例；HITL 回饋寫入與稽核軌跡查詢
    - _Requirements: 15.5, 20.2, 21.3_

- [x] 23. 最終 Checkpoint — 確認全部測試通過
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- 標記 `*` 的子任務為選用（測試類），可為加速 MVP 而略過；核心實作任務絕不標選用。
- 每個任務皆標註對應需求子條款以利追溯；每個屬性測試任務明確引用 design.md 的 Property 編號與其驗證的需求條款。
- Checkpoint 任務確保漸進式驗證。
- 屬性測試以 Hypothesis 實作，每個 Correctness Property 對應單一屬性測試，至少 100 次迭代，並標註 `Feature: smart-watchdog-platform, Property {number}`。
- P2 文件類需求（R22 評估指標與標註策略、R24 交付與文件產出）以文件形式交付，不列為編碼任務。
- 所有延伸任務建立於既有 `src/` 與 `app/` 基線之上，保留既有方法（班佛/Beneish/IForest/IQR/SHAP/百分位分級）。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2", "2.3", "2.3b", "3.1", "4.1", "4.2", "4.5", "10.1", "10.1a", "10.1b", "11.1", "14.1", "14.2", "15.1", "15.2", "15.3", "16.1", "18.1"] },
    { "id": 2, "tasks": ["2.4", "2.4b", "2.5", "2.6", "2.7", "2.8", "3.2", "3.3", "3.4", "4.3", "4.4", "4.6", "4.7", "6.1", "6.1b", "7.1", "8.1", "10.2", "10.2b", "10.3", "11.2", "12.1", "16.2", "18.2", "21.1"] },
    { "id": 3, "tasks": ["6.1c", "6.1d", "6.2", "6.3", "6.4", "7.2", "7.3", "8.2", "8.3", "11.3", "11.4", "11.5", "12.2", "12.3", "14.3", "14.4", "15.4", "15.5", "16.3", "16.4", "18.3", "18.4", "19.1", "19.2", "20.1", "21.2"] },
    { "id": 4, "tasks": ["6.1e", "6.5", "19.3", "20.2", "22.1"] },
    { "id": 5, "tasks": ["22.2", "22.3"] }
  ]
}
```
