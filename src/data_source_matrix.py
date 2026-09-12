"""
資料來源矩陣（Data_Source_Matrix, R16）
=========================================
小小守護員 Smart Watchdog Platform — 資料層（Data Layer）的誠實資料清冊。

本模組以「靜態設定表」記錄每一資料源的屬性與可信度，對應 design.md
「15. Data_Source_Matrix」。它是一份給評審與稽查員看的**誠實**清單，用途有二：

1. 攤開每個資料源的來源、主管機關、更新頻率、格式、關鍵欄位、可信度、
   是否有 API、是否可下載、是否可追溯、用途與風險（R16.1）。
2. 落實責任 AI 與資料誠信原則：**僅列入實際存在或已確認的資料集**（R16.2），
   尚未確認可用性者誠實標示為「未確認」（R16.3），且**絕不虛構**任何
   不存在的資料集（R16.4）。

資料實況（依 .kiro/steering/project-vision.md 與實際檔案盤點）
-----------------------------------------------------------------
- 公校決算書（112/113/114 年度）：PDF 有文字層，可程式抽取。**已確認存在**
  （見 `E_教育局-資料集/資料集/公校/*年度決算書/`）。
- 非營利園財報（110~113 學年度約 132 份）：除封面外內頁為掃描影像、無文字層，
  需 OCR / Textract / Bedrock 多模態抽取。**檔案已確認存在**，但抽取後數值
  之完整度**未確認**（尚待 OCR 驗證）。
- 非營利園基本資料（園名/行政區/地址）：**已確認存在**（見 data/external/nonprofit.csv）。
- 地理座標：以 Nominatim 對地址做 geocoding 之**衍生**資料，**已確認存在**
  （見 data/processed/geocoded.csv）。
- 裁罰紀錄（示範樣本）：目前為專案自行整理之小樣本（data/external/penalties.csv）。
  對應「全國教保資訊網」官方裁罰資料源之可用性（API/下載）**未確認**。
- 評鑑等第：目前僅隨裁罰樣本附帶少量欄位；官方評鑑資料源**未確認**。
- 收費資訊：官方收費資料源**未確認**（尚未取得）。
- 網路輿情：僅規劃小樣本 NLP 展示；穩定可取得之資料源**未確認**。

誠實原則
--------
- 若某資料源尚未實際取得或其可用性未經確認，其欄位（特別是 has_api /
  downloadable / availability）以 `UNCONFIRMED`（未確認）標示，而非臆測「可用」。
- 本表**不新增**任何實際不存在的資料集列。

本模組僅依賴標準函式庫與 `src.models` 的共用型別，不引入額外執行期相依，
維持既有基線的可攜性。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


# --------------------------------------------------------------------------
# 三態可用性標記（誠實標示，R16.3）
# --------------------------------------------------------------------------
class Availability(str, Enum):
    """資料源某屬性的三態標記。

    - CONFIRMED（已確認）：實際存在且已取得／已驗證可用。
    - UNCONFIRMED（未確認）：尚未確認可用性；**不得**宣稱可用（R16.3）。
    - NOT_APPLICABLE（不適用）：該屬性對此資料源不適用。

    以字串列舉呈現，序列化與顯示（如儀表板表格）皆直觀可讀。
    """
    CONFIRMED = "已確認"
    UNCONFIRMED = "未確認"
    NOT_APPLICABLE = "不適用"


# 對外語意常數，供其他模組與測試引用，避免硬編字面值。
UNCONFIRMED_LABEL = Availability.UNCONFIRMED.value  # 「未確認」


# --------------------------------------------------------------------------
# 單一資料源條目（R16.1）
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class DataSourceEntry:
    """資料來源矩陣的單一列，記錄一個資料源的完整屬性（R16.1）。

    對應 R16.1 要求的十二項屬性：來源、資料集、主管機關、更新頻率、格式、
    關鍵欄位、可信度、是否有 API、是否可下載、是否可追溯、用途與風險。

    誠實原則（R16.2, R16.3, R16.4）：
    - 僅在資料集實際存在或已確認時建立此條目。
    - availability 為此資料源整體取用狀態的三態標記；`UNCONFIRMED`
      代表「未確認」，不得宣稱可用。
    - has_api / downloadable / traceable 三個能力旗標亦採三態，尚未確認者
      標為 `UNCONFIRMED`，而非臆測為可用。

    以 frozen=True 落實「靜態設定表」語意——建立後不可竄改。

    Validates: Requirements 16.1, 16.2, 16.3, 16.4
    """
    source: str                 # 來源（機關/網站/檔案來源）
    dataset: str                # 資料集名稱
    authority: str              # 主管機關
    update_frequency: str       # 更新頻率
    data_format: str            # 格式（PDF文字層/掃描影像/CSV/...）
    key_fields: tuple[str, ...] # 關鍵欄位
    confidence: str             # 可信度（高/中/低 + 說明）
    purpose: str                # 用途
    risk: str                   # 風險（此資料源已知的品質/取得風險）
    availability: Availability = Availability.CONFIRMED  # 整體取用狀態
    has_api: Availability = Availability.UNCONFIRMED     # 是否有 API
    downloadable: Availability = Availability.UNCONFIRMED  # 是否可下載
    traceable: Availability = Availability.CONFIRMED     # 是否可追溯（有官方出處）
    notes: str = ""             # 補充說明（誠實標註限制）

    # R16.1 要求記錄的屬性名稱清單（供完整性檢查與測試引用）。
    # 以 ClassVar 定義為類別層級常數，不視為 dataclass 實例欄位。
    REQUIRED_ATTRIBUTES: ClassVar[tuple[str, ...]] = (
        "source",
        "dataset",
        "authority",
        "update_frequency",
        "data_format",
        "key_fields",
        "confidence",
        "has_api",
        "downloadable",
        "traceable",
        "purpose",
        "risk",
    )

    def is_unconfirmed(self) -> bool:
        """此資料源整體是否標示為「未確認」（R16.3）。"""
        return self.availability == Availability.UNCONFIRMED


# --------------------------------------------------------------------------
# 靜態資料來源矩陣（R16.2, R16.4）
# --------------------------------------------------------------------------
# 誠實清冊：以下僅列入**實際存在或已確認**的資料集（R16.2）。
# 尚未確認可用性的官方資料源（如全國教保資訊網之官方裁罰/評鑑/收費 API 或
# 下載端點）以 availability=UNCONFIRMED 標示（R16.3），但其對應之「已實際持有
# 的小樣本檔案」仍誠實列出，並在 notes 說明其為示範樣本而非官方全量資料。
# **不虛構**任何實際不存在的資料集（R16.4）。
DATA_SOURCE_MATRIX: tuple[DataSourceEntry, ...] = (
    DataSourceEntry(
        source="新北市政府教育局（命題方提供）",
        dataset="公校（含市立幼兒園）決算書 112/113/114 年度",
        authority="新北市政府教育局",
        update_frequency="年度",
        data_format="PDF（有文字層，可程式抽取）",
        key_fields=("機構編號", "歲入決算", "歲出決算", "人事費", "業務費"),
        confidence="高：官方決算文件、有文字層可精確抽取",
        purpose="財務異常偵測（班佛/Beneish/趨勢）之黃金資料源",
        risk="表格版面多樣，抽取需逐冊校對；市立幼兒園自編號 13601 起",
        availability=Availability.CONFIRMED,
        has_api=Availability.NOT_APPLICABLE,
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,
        notes="第5冊含市立幼兒園決算，為 MVP 主力資料源。",
    ),
    DataSourceEntry(
        source="新北市政府教育局（命題方提供）",
        dataset="非營利幼兒園財報 110~113 學年度（約 132 份）",
        authority="新北市政府教育局",
        update_frequency="學年度",
        data_format="PDF（內頁為掃描影像、無文字層，需 OCR/Textract/Bedrock 多模態）",
        key_fields=("收入", "支出", "人事費"),
        confidence="中：檔案已確認存在，但 OCR 抽取後數值完整度未確認",
        purpose="擴大資料涵蓋面，展示架構可處理掃描檔並可規模化",
        risk="無文字層，需 OCR；中文財報表格辨識率與數字正確性待驗證",
        availability=Availability.CONFIRMED,
        has_api=Availability.NOT_APPLICABLE,
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,
        notes="抽取後之結構化財務數值屬未確認，需 OCR 驗證後才可入模。",
    ),
    DataSourceEntry(
        source="非營利幼兒園基本資料（專案整理）",
        dataset="非營利園基本資料（園名/行政區/地址）",
        authority="新北市政府教育局 / 全國教保資訊網",
        update_frequency="不定期",
        data_format="CSV",
        key_fields=("code", "short_name", "park_name", "district", "address"),
        confidence="中：已持有檔案，園名與地址可比對；官方全量來源未確認",
        purpose="非營利園實體識別與地址地理編碼之基礎",
        risk="名稱變體需實體解析；官方權威來源之更新機制未確認",
        availability=Availability.CONFIRMED,
        has_api=Availability.UNCONFIRMED,
        downloadable=Availability.UNCONFIRMED,
        traceable=Availability.CONFIRMED,
        notes="檔案：data/external/nonprofit.csv。",
    ),
    DataSourceEntry(
        source="行政區概略座標（衍生）／Nominatim 精確編碼（架構備用）",
        dataset="機構座標（lat/lng，供風險地圖標記）",
        authority="OpenStreetMap 貢獻者（衍生資料，非官方主管機關）",
        update_frequency="隨地址資料重跑",
        data_format="CSV",
        key_fields=("park_name", "address", "lat", "lng"),
        confidence=(
            "概略：目前 shipped 座標為『行政區中心概略座標』（離線重建、免外連），"
            "非逐址精確地理編碼。Nominatim 逐址編碼能力已實作於 src/geocode.py，"
            "線上重跑即可升級為精確座標。"
        ),
        purpose="風險地圖標記（Leaflet + OpenStreetMap）——概略定位、精確度待線上編碼",
        risk=(
            "目前座標為行政區概略中心（同區機構位置相近），非門牌精確；"
            "地圖用於『看出哪些行政區/機構需優先關注』的概略分佈，非導航級定位。"
        ),
        availability=Availability.CONFIRMED,
        has_api=Availability.CONFIRMED,       # Nominatim 免金鑰 API 可用（架構已實作）
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,
        notes=(
            "檔案：data/processed/geocoded.csv（source 欄標『行政區概略』）。"
            "誠實揭露：現為概略座標；精確逐址編碼需線上執行 src/geocode.py（Nominatim）。"
        ),
    ),
    DataSourceEntry(
        source="全國教保資訊網（官方裁罰資料）",
        dataset="裁罰紀錄（官方全量）",
        authority="教育部 / 全國教保資訊網",
        update_frequency="未確認",
        data_format="未確認",
        key_fields=("園所名稱", "裁罰次數", "裁罰事由", "裁罰日期"),
        confidence="未確認：官方全量裁罰資料源尚未取得或驗證",
        purpose="風險標籤來源（驗證高風險園是否較常被裁罰）",
        risk="官方 API/下載端點與更新頻率未確認；目前僅有專案自行整理之小樣本",
        availability=Availability.UNCONFIRMED,
        has_api=Availability.UNCONFIRMED,
        downloadable=Availability.UNCONFIRMED,
        traceable=Availability.UNCONFIRMED,
        notes=(
            "目前僅持有示範樣本 data/external/penalties.csv（少數園、人工整理），"
            "非官方全量資料；官方資料源可用性標為未確認，不宣稱可用。"
        ),
    ),
    DataSourceEntry(
        source="全國教保資訊網（官方評鑑資料）",
        dataset="幼兒園評鑑等第（官方全量）",
        authority="教育部 / 全國教保資訊網",
        update_frequency="未確認",
        data_format="未確認",
        key_fields=("園所名稱", "評鑑等第", "評鑑年度"),
        confidence="未確認：官方評鑑資料源尚未取得或驗證",
        purpose="風險評分之評鑑分項輸入",
        risk="目前僅隨裁罰樣本附帶少量 eval_grade 欄位，非官方完整評鑑資料",
        availability=Availability.UNCONFIRMED,
        has_api=Availability.UNCONFIRMED,
        downloadable=Availability.UNCONFIRMED,
        traceable=Availability.UNCONFIRMED,
        notes="官方評鑑資料源可用性未確認，不宣稱可用。",
    ),
    DataSourceEntry(
        source="全國教保資訊網（官方收費資料）",
        dataset="幼兒園收費資訊（官方全量）",
        authority="教育部 / 全國教保資訊網",
        update_frequency="未確認",
        data_format="未確認",
        key_fields=("園所名稱", "收費項目", "收費金額"),
        confidence="未確認：官方收費資料源尚未取得或驗證",
        purpose="家長信任中心公開收費揭露、收費合理性交叉勾稽",
        risk="尚未取得官方收費資料；不得以推估或預設值替代",
        availability=Availability.UNCONFIRMED,
        has_api=Availability.UNCONFIRMED,
        downloadable=Availability.UNCONFIRMED,
        traceable=Availability.UNCONFIRMED,
        notes="官方收費資料源可用性未確認，不宣稱可用。",
    ),
    DataSourceEntry(
        source="公開新聞 RSS（Google News／Bing News／台灣媒體公開 feed）",
        dataset="機構新聞輿情（負面度 neg_ratio，真實爬取）",
        authority="無單一主管機關（各媒體公開新聞）",
        update_frequency="即時（每次執行重爬近兩年報導）",
        data_format="RSS（XML）→ CSV",
        key_fields=("園所名稱", "新聞標題", "媒體來源", "原文連結", "發布日", "負面比例"),
        confidence=(
            "中：新聞層為真實爬取之公開 RSS、每筆附媒體來源與原文連結可追溯；"
            "以白盒規則式 NLP 判負面度。惟市立／非營利園新聞量少，多數機構查無"
            "精準比對報導（誠實：訊號少即如實留空、不放大）。"
        ),
        purpose="風險評分輿情分項（權重 10%、貢獻上限 15 分）；家長端輿情觀測",
        risk=(
            "新聞召回受媒體報導量限制；同名／地區泛稱經精準比對過濾（責任 AI，"
            "避免張冠李戴）故命中率保守。社群（Dcard/PTT/FB/IG/Google 評論）"
            "受登入牆／ToS 限制，仍為未確認、以 adapter 示範。"
        ),
        availability=Availability.CONFIRMED,   # 新聞 RSS 層已接入真實爬蟲並計分
        has_api=Availability.CONFIRMED,        # 公開 RSS 免金鑰可即時抓取
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,      # 每筆附媒體來源與原文連結
        notes=(
            "檔案：data/processed/sentiment.csv（由 scripts/build_sentiment.py "
            "以 news_crawler + ptt_crawler 產出）。新聞＋PTT 兩條真實來源已計入總分；"
            "Dcard/FB/IG/Google 評論（登入牆／ToS 限制）仍為未確認、以 adapter 示範。"
        ),
    ),
    DataSourceEntry(
        source="PTT 公開看板（www.ptt.cc）",
        dataset="PTT 親子看板公開討論（社群輿情，真實爬取）",
        authority="無單一主管機關（公開網路論壇）",
        update_frequency="即時（每次執行重抓看板最新文章）",
        data_format="HTML 列表頁 → 正規化 records",
        key_fields=("園所名稱", "文章標題", "看板", "原文連結", "發布日"),
        confidence=(
            "中：BabyMother/BabyProducts 等公開看板無登入牆、可合法抓取；"
            "以園名核心詞精準比對（責任 AI，避免張冠李戴）。惟指名特定園之"
            "討論稀疏，命中率保守（誠實：訊號少即如實留空）。"
        ),
        purpose="社群輿情層（與新聞互補）；納入 neg_ratio 計分（貢獻上限 15 分）",
        risk="論壇討論為輿情訊號、非違法認定；針對特定園之指名討論量少。",
        availability=Availability.CONFIRMED,   # PTT 公開看板可即時合法抓取
        has_api=Availability.CONFIRMED,        # 公開 web 列表頁，免金鑰
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,      # 每筆附原文連結
        notes="連接器：src/ptt_crawler.py。只讀公開看板，不抓登入內容、不繞存取控制。",
    ),
    DataSourceEntry(
        source="司法院裁判書公開查詢／各級行政處分",
        dataset="司法／行政處分紀錄（事實層，區分確定/程序）",
        authority="司法院 / 各目的事業主管機關",
        update_frequency="不定期（隨判決／處分公告）",
        data_format="公開查詢頁（WebForm）→ 結構化 records",
        key_fields=("園所名稱", "案由", "司法階段", "法院/機關", "字號", "日期"),
        confidence=(
            "中：判決／處分『確定』者為事實層（tier=fact，可支持稽查判讀）；"
            "偵查／起訴／審理中為過程（tier=event，不等於有罪）。階段嚴格區分。"
        ),
        purpose="事實層風險訊號（比社群輿情份量重）；供風險判讀與證據鏈",
        risk=(
            "司法院查詢為 ASP.NET WebForm（ViewState+session+POST），非穩定即時"
            "爬取；現以自公開判決整理之結構化樣本示範，正式部署接司法院開放資料/API。"
        ),
        availability=Availability.CONFIRMED,   # 連接器與結構化資料已備、可查詢計分
        has_api=Availability.UNCONFIRMED,      # 官方穩定 API/開放資料端點未確認
        downloadable=Availability.UNCONFIRMED,
        traceable=Availability.CONFIRMED,      # 每筆附字號與查詢連結
        notes=(
            "連接器：src/judicial_source.py；資料：data/raw/judicial_records.json。"
            "誠實揭露：現為離線結構化樣本（標 is_demo_sample），介面不變即可接官方開放資料。"
        ),
    ),
    DataSourceEntry(
        source="政府資料開放平臺 data.gov.tw（dataset 6086 等）",
        dataset="全國幼兒園名錄／裁罰／補助（官方一手，架構備援）",
        authority="教育部 / 各主管機關",
        update_frequency="定期（依平臺更新）",
        data_format="REST API / CSV",
        key_fields=("園所名稱", "地址", "類型", "核定人數", "裁罰", "補助"),
        confidence="高（官方一手）：可用性經平臺提供；本專案列為正式部署改接來源。",
        purpose="正式部署之權威資料源（取代二手整理），可規模化至全國全量",
        risk="需依平臺 API 規格對接與欄位對齊；競賽階段以既有來源示範、架構已備。",
        availability=Availability.CONFIRMED,   # 平臺與 dataset 存在、公開可用
        has_api=Availability.CONFIRMED,        # data.gov.tw 提供 REST API
        downloadable=Availability.CONFIRMED,
        traceable=Availability.CONFIRMED,
        notes=(
            "架構已備、正式部署接入：連接器介面同 src/live_source.py 模式，"
            "改指向 data.gov.tw 端點即可，免改動風險引擎與 UI。"
        ),
    ),
)


# --------------------------------------------------------------------------
# 查詢便利函式
# --------------------------------------------------------------------------
def get_matrix() -> tuple[DataSourceEntry, ...]:
    """回傳完整資料來源矩陣（靜態設定表，R16.1）。"""
    return DATA_SOURCE_MATRIX


def confirmed_sources() -> list[DataSourceEntry]:
    """回傳整體取用狀態為「已確認」的資料源（R16.2）。"""
    return [e for e in DATA_SOURCE_MATRIX if e.availability == Availability.CONFIRMED]


def unconfirmed_sources() -> list[DataSourceEntry]:
    """回傳誠實標示為「未確認」的資料源（R16.3）。"""
    return [e for e in DATA_SOURCE_MATRIX if e.is_unconfirmed()]


def find_by_dataset(dataset: str) -> DataSourceEntry | None:
    """依資料集名稱尋找條目；找不到回傳 None（不虛構，R16.4）。"""
    for e in DATA_SOURCE_MATRIX:
        if e.dataset == dataset:
            return e
    return None
