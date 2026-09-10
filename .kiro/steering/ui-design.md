# UI 設計準則（反 AI 生成風、政府/企業級）

本產品「Smart Watchdog 小小守護員」是 Government-grade / Enterprise-grade 的公部門資料治理平台。
設計目標：看起來像「政府稽查人員每天真的會用的專業系統」，不是「AI 新創的概念展示網站」。
可信度 > 科技感；資訊清楚 > 視覺炫技；證據與資料 > AI 裝飾。

## 禁止的視覺風格（絕對避免）
Cyberpunk、Sci-fi dashboard、未來感全息、霓虹漸層、紫藍 AI 漸層、Glassmorphism、
過度透明、發光邊框/發光圖表、浮動卡片、過度陰影、過度大圓角（>12px）、3D 裝飾物件、
機器人插圖、AI 頭像/機器人臉、抽象 AI 大腦圖、電路板裝飾、數位粒子、過度動畫、
巨大「AI」字樣、通用「AI-powered」行銷圖。

## 色彩原則
- 中性色為主（約 90%）：white / light gray / dark gray / neutral background。
- 功能色只佔約 10%，且只用於對應語意：
  - Red = high risk / critical anomaly
  - Orange = warning
  - Yellow = medium risk
  - Green = normal / safe
  - Blue = primary interaction / information
- 禁止大量使用 purple / neon blue / pink / rainbow 漸層。禁止用漸層當主要 UI 語言。
- 對齊既有 tokens：app/lib/common.py 的 BG/SURFACE/INK/BORDER 中性骨架 + RISK 五階語意色。

## 版面與資訊密度
- 這是資料密集型政府系統。用 spacing / divider / border / typography / table / section heading 建立階層，
  卡片只在真的需要分組時使用（不要全部包成卡片）。
- border-radius 克制在 4–12px；陰影極少（border 優先於 shadow）。
- 高資訊密度 + 高可讀性；不要像 Landing Page 大量留白，但也不要擁擠。
- 應包含：tables、filters、rankings、charts、timestamps、data source、update time、evidence、status。

## Typography
- 現代、乾淨、可讀的無襯線字體（沿用 Inter / Noto Sans TC）。
- 標題克制，不用未來感/裝飾字體、不用超大行銷標題。
- 「AI」字樣只在真正的 AI 功能出現，不到處貼 AI POWERED / SMART AI / AI INSIGHT。

## 圖表
- 優先：line / bar / scatter / heatmap / 地理地圖 / table / timeline。
- 避免：3D 圖、發光圖、未來感視覺化、過多甜甜圈圖、裝飾性圖表。
- 地圖用 Leaflet + OpenStreetMap（免金鑰），標記依風險等級紅/黃/綠。

## AI 功能呈現
- AI 是「調查輔助工具」，不是大型聊天機器人。
- 呈現：AI 分析結果、主要異常原因、證據、建議查核方向。
- AI 回答必須連結到資料、Evidence Chain 與原始來源。

## 三種模式（同一品牌，依任務調整資訊密度）
- Government：全域監控、資料分析、資源配置。
- Inspector：案件、證據、時間軸、調查。
- Parent：公開資訊、收費、評鑑、透明度。

## 已核准例外（刻意保留，勿當違規移除）
- 側欄「System Status」的 live 綠點（common.py 的 `swStatusPulse` 呼吸動畫）：
  屬輕量運作中狀態指示，真實企業後台常見，經團隊決定保留。此為唯一允許的
  發光/動畫例外，不得擴散到其他元件。

## 最終標準
第一眼感覺應是：Professional / Trustworthy / Government-grade / Data-driven。
不是：AI / Futuristic / Cyberpunk / Startup / Sci-fi。
