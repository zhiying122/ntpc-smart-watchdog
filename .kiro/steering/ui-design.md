# UI 設計準則（互動體驗優先、政府/企業級）

本產品「Smart Watchdog 小小守護員」是 Government-grade / Enterprise-grade 的公部門資料治理平台。
設計目標：看起來像「政府稽查人員每天真的會用、而且用起來很順手的專業系統」。

**核心原則：好用 > 好看，互動服務於任務。**
以使用者（稽查官）的實際工作動線為中心設計畫面——先想「他這一刻要做什麼決定」，
再決定畫面怎麼排。互動（即時回饋、狀態轉場、順手操作）是為了讓任務更快完成，
不是為了炫技。真正專業的系統（Bloomberg 終端、法院案件系統、審計工作台）互動性
其實很強，只是互動都「有用」而非「裝飾」。

## 鼓勵的互動（為了好用，全開）
- 即時回饋：點擊後畫面立即有反應（狀態變更、徽章更新、成功提示）。
- 狀態轉場：案件狀態切換（待研判→建議派查→調查中→結案）要有清楚的視覺變化。
- Hover / focus 效果：可點元素在游標移入時給予明確可互動提示。
- 平滑過渡：展開/收合、切換、載入的過場動畫（150–300ms，克制不浮誇）。
- 可展開/收合、可篩選、即時預覽：讓稽查官快速鑽取與比較，不用重新整理。
- 行動優先排版：把「下決定的按鈕」放在使用者最先看到的位置，證據往下支撐。
- 鍵盤/快捷操作、一鍵動作（一鍵派查、一鍵產出文件）視情況加入。

## 仍建議克制的（為了不像玩具，省著用）
- 純裝飾且無功能意義的視覺：無意義的發光、賽博龐克配色、3D 漂浮物件、
  數位粒子、電路板裝飾、抽象 AI 大腦圖、機器人插圖/AI 頭像。
- 巨大「AI」字樣、通用「AI-powered」行銷圖、超大 Landing Page 行銷標題。
- 判斷標準很簡單：這個效果讓稽查官「更快完成任務」→ 加；只是「更好看」→ 省。
  面對的是教育局公務評審，雷點是「看起來像不穩重的新創玩具」。

## 色彩原則
- 中性色為主（約 85–90%）：white / light gray / dark gray / neutral background。
- 功能色用於對應語意：
  - Red = high risk / critical anomaly
  - Orange = warning
  - Yellow = medium risk
  - Green = normal / safe
  - Blue = primary interaction / information
- 互動狀態（hover、active、selected）可用主色強化，讓操作回饋清楚。
- 避免大面積 purple / neon / rainbow 漸層當主要 UI 語言（小面積互動點綴可接受）。
- 對齊既有 tokens：app/lib/common.py 的 BG/SURFACE/INK/BORDER 骨架 + RISK 五階語意色。

## 版面與資訊密度
- 這是資料密集型政府系統。用 spacing / divider / border / typography / table / section heading
  建立階層；卡片在需要分組或承載可互動單元（如案件卡、決策條）時使用。
- border-radius 建議 4–12px；陰影克制（可用於浮起可互動元素如按鈕 hover、卡片提升）。
- 高資訊密度 + 高可讀性；行動元素優先靠上。
- 應包含：tables、filters、rankings、charts、timestamps、data source、update time、evidence、status。

## Typography
- 現代、乾淨、可讀的無襯線字體（沿用 Inter / Noto Sans TC）。
- 「AI」字樣只在真正的 AI 功能出現，不到處貼 AI POWERED / SMART AI。

## 圖表
- 優先：line / bar / scatter / heatmap / 地理地圖 / table / timeline。
- 互動圖表鼓勵：hover tooltip、可切換維度、可篩選、鑽取。
- 避免：純裝飾性 3D 圖、無意義發光圖。
- 地圖用 Leaflet + OpenStreetMap（免金鑰），標記依風險等級紅/黃/綠。

## AI 功能呈現
- AI 是「調查輔助工具」，呈現：AI 分析結果、主要異常原因、證據、建議查核方向。
- AI 回答必須連結到資料、Evidence Chain 與原始來源。

## 三種模式（同一品牌，依任務調整資訊密度）
- Government：全域監控、資料分析、資源配置。
- Inspector：案件、證據、時間軸、調查、下決定。
- Parent：公開資訊、收費、評鑑、透明度。

## 已保留元素
- 側欄「System Status」的 live 綠點呼吸動畫（common.py 的 `swStatusPulse`）：運作中狀態指示，保留。

## 最終標準
第一眼感覺應是：Professional / Trustworthy / 而且「一看就知道怎麼操作、用起來很順」。
不是：不穩重的玩具 / 純炫技 demo。
