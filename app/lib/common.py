"""
Fiscalint 設計系統與共用元件（企業級風險情報平台）
============================================================
設計語氣：Institutional / Analytical / Trustworthy。
中性石墨骨架佔 90%，五階風險語意色只用於風險相關元素。
Border 優先於 Shadow、小圓角、8px spacing、等寬數字。

本檔為唯一的設計來源：所有頁面共用 token、CSS、shell、元件。
只負責「呈現」，不含任何商業/計算邏輯。資料契約見 docs/data-dictionary.md。
"""
import html
import os
import re
import time

import pandas as pd
import streamlit as st

# 載入專案根目錄的 .env（AWS 憑證 / Bedrock 設定）。
# 程式一律用 os.environ 讀值（禁止寫死金鑰）；此處僅負責把 .env 匯入環境。
# 用 try/except 包住：未安裝 python-dotenv 或無 .env 時，不影響 app 啟動
# （Bedrock 未設定時 src/ai_report.py 會自動退化為 fallback）。
try:
    from dotenv import load_dotenv

    _ENV_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        ".env",
    )
    load_dotenv(_ENV_PATH)
except Exception:  # noqa: BLE001 - dotenv 缺失不應阻擋啟動
    pass

# RBAC：角色感知導覽（第一層授權）與身分驗證守衛（第二層授權）。
# 這兩個模組為 app/lib 內的同儕模組；common 只在需要時使用其純函式與守衛。
from lib import auth  # noqa: E402
from lib import permissions  # noqa: E402

# ---------------------------------------------------------------------------
# 專案路徑
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROC = os.path.join(ROOT, "data", "processed")
LATEST_CSV = os.path.join(PROC, "kindergartens_latest.csv")
FULL_CSV = os.path.join(PROC, "kindergartens.csv")
ROSTER_CSV = os.path.join(PROC, "kindergartens_roster.csv")  # 全市涵蓋層（廣度）

# ===========================================================================
# 設計 Tokens
# ===========================================================================
# ---- 結構（中性骨架，佔畫面 90%）----
BG = "#F4F5F7"            # 應用底色
SURFACE = "#FFFFFF"       # 面板／表格底
SURFACE_ALT = "#F8F9FB"   # 次層面板（斑馬紋、表頭）
SURFACE_SUNK = "#EEF0F3"  # 內凹區（軌道、輸入框）
SIDEBAR_BG = "#1C2530"    # 側欄：深石墨（品牌骨架，唯一的深色區）
SIDEBAR_INK = "#C6CDD6"   # 側欄文字
SIDEBAR_INK_DIM = "#7E8794"
SIDEBAR_ACTIVE = "#232F3D"
PRIMARY = "#2C5D8F"       # 主互動色（沉穩藍，非鮮豔）
PRIMARY_SOFT = "#EAF0F6"

INK = "#1F2733"           # text-primary
INK_2 = "#5A626D"         # text-secondary
INK_MUTED = "#8A929C"     # text-muted
FAINT = "#AEB4BC"         # 無資料
BORDER = "#C7CDD6"        # 主框線（加深，提升卡片/表格輪廓清晰度）
BORDER_STRONG = "#B4BBC5" # 強框線（表頭分隔、輸入框，較主框線再深一階）

# ---- 五階風險語意色（僅用於風險元素）----
# key: 英文語意層；(前景深字色, 淺底色, 框線色)
RISK = {
    "critical": ("#8C2A22", "#F3DEDB", "#D8AAA3"),
    "high":     ("#B0453A", "#F6E2DD", "#DFB1A8"),
    "medium":   ("#9A7212", "#F3E9CF", "#D8C48C"),
    "low":      ("#4E6E8E", "#E6EDF4", "#B4C6D8"),
    "normal":   ("#3F6B54", "#E2EDE6", "#AECBBA"),
}
RISK_BAR = {
    "critical": "#9E3229", "high": "#BC4B3E", "medium": "#B58A1E",
    "low": "#5A7A99", "normal": "#4E7A63",
}

# ---- 中文三階 → 企業五階的對映（現有資料只有 高/中/低，向後相容）----
LEVEL_TO_RISK = {"高": "high", "中": "medium", "低": "normal"}

# ---- 向後相容：舊頁面仍以中文 key 取用，保留這些對映 ----
LEVEL_COLOR = {k: RISK[LEVEL_TO_RISK[k]][0] for k in ("高", "中", "低")}
LEVEL_BG = {k: RISK[LEVEL_TO_RISK[k]][1] for k in ("高", "中", "低")}
LEVEL_BORDER = {k: RISK[LEVEL_TO_RISK[k]][2] for k in ("高", "中", "低")}
LEVEL_BAR = {k: RISK_BAR[LEVEL_TO_RISK[k]] for k in ("高", "中", "低")}
# 舊 token 別名（其他頁面 import 用）
STRUCT = SIDEBAR_BG
PANEL = SURFACE
LINE = BORDER
LINE_STRONG = BORDER_STRONG
LINE_SOFT = "#F0F1F3"
MUTED = INK_MUTED
ACCENT = PRIMARY

# 評鑑等第語意色（沿用五階邏輯：優偏綠、良中性、乙偏黃、差偏紅）
GRADE_STYLE = {
    "優": (RISK["normal"][0], RISK["normal"][1]),
    "甲": (RISK["normal"][0], RISK["normal"][1]),
    "良": ("#4E5763", "#E9EBEE"),
    "乙": (RISK["medium"][0], RISK["medium"][1]),
    "丙": (RISK["high"][0], RISK["high"][1]),
    "待改進": (RISK["high"][0], RISK["high"][1]),
    "不通過": (RISK["critical"][0], RISK["critical"][1]),
}

RADAR_DIMS = [
    ("score_financial", "財務異常"),
    ("score_penalty", "裁罰紀錄"),
    ("score_eval", "評鑑結果"),
]

# ---------------------------------------------------------------------------
# 導覽定義（單一導覽來源 / Single Source of Navigation）
# ---------------------------------------------------------------------------
# 本專案採「舊式 pages/ multipage 架構」。導覽一律用 Streamlit 原生 st.page_link()
# 產生，交由 Streamlit 內建 router 處理，路徑必然與 page registry 一致，
# 因此不會出現 "Page not found"。
#
# page 欄位＝相對於 entry point（app/主頁.py）的「檔案路徑」，非 URL slug，
# 也非 Python module path。這是 st.page_link() 唯一正確的頁面指定方式：
#   主頁          -> "主頁.py"（entry point 本身）
#   pages/1_case  -> "pages/1_case.py"
# key 僅用於「目前頁面 active 標示」，以檔名關鍵字比對。
#
# NAV item: (key, 側欄顯示名, icon, page 檔案路徑)
NAV = [
    ("主頁",       "風險總覽",     "dashboard", "主頁.py"),
    ("1_case",     "案件調查",     "case",      "pages/1_case.py"),
    ("2_map",      "風險地圖",     "map",       "pages/2_map.py"),
    ("3_ai",       "AI 決策支援",  "ai",        "pages/3_ai.py"),
    ("4_sentiment", "輿情分析",    "sentiment", "pages/4_sentiment.py"),
]

# ---------------------------------------------------------------------------
# 線性 SVG 圖示（單一風格，stroke 一致；角色是辨識非裝飾）
# ---------------------------------------------------------------------------
_ICON = {
    "dashboard": "<rect x='3' y='3' width='7' height='9' rx='1'/><rect x='14' y='3' width='7' height='5' rx='1'/><rect x='14' y='12' width='7' height='9' rx='1'/><rect x='3' y='16' width='7' height='5' rx='1'/>",
    "case": "<path d='M9 3h6l1 3H8z'/><rect x='4' y='6' width='16' height='15' rx='2'/><path d='M8 11h8M8 15h5'/>",
    "map": "<path d='M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2z'/><path d='M9 4v14M15 6v14'/>",
    "ai": "<circle cx='12' cy='12' r='8'/><path d='M12 8v4l3 2'/>",
    "sentiment": "<path d='M4 5h16v11H8l-4 4z'/><path d='M9 10h.01M15 10h.01M9 13c1 1 5 1 6 0'/>",
    "shield": "<path d='M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z'/>",
    "clock": "<circle cx='12' cy='12' r='9'/><path d='M12 7v5l3 2'/>",
    "alert": "<path d='M12 3 2 20h20z'/><path d='M12 9v5M12 17h.01'/>",
    "check": "<circle cx='12' cy='12' r='9'/><path d='m8 12 3 3 5-6'/>",
}


def icon(name, size=16, color="currentColor", stroke=1.6):
    body = _ICON.get(name, "")
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' "
            f"stroke='{color}' stroke-width='{stroke}' stroke-linecap='round' "
            f"stroke-linejoin='round' style='vertical-align:middle;'>{body}</svg>")


# ===========================================================================
# 資料載入（唯讀，不改任何邏輯）
# ===========================================================================
@st.cache_data(show_spinner=False)
def load_latest():
    if not os.path.exists(LATEST_CSV):
        return None
    return pd.read_csv(LATEST_CSV)


@st.cache_data(show_spinner=False)
def load_full():
    if not os.path.exists(FULL_CSV):
        return None
    return pd.read_csv(FULL_CSV)


@st.cache_data(show_spinner=False)
def load_roster():
    """全市涵蓋層（廣度）：全新北市立案幼兒園名冊。

    每列一間機構，含 data_status 欄位：
      - "scored"：已具真實鑑識會計風險分（深度層，與 latest 對應）。
      - "roster_only"：僅基本資料（名稱/類型/行政區/地址/電話），風險欄位空，
        待接入財務資料。
    檔案不存在時回傳 None（頁面應優雅退化，不影響既有 61 間分析功能）。
    由 scripts/fetch_ntpc_roster.py 從新北市政府資料開放平台產生。
    """
    if not os.path.exists(ROSTER_CSV):
        return None
    return pd.read_csv(ROSTER_CSV)


PENALTY_CSV = os.path.join(ROOT, "data", "external", "ntpc_penalty.csv")


@st.cache_data(show_spinner=False)
def load_penalty():
    """真實裁罰紀錄（全國教保資訊網主管機關裁罰，已正式納入風險分計算）。

    來源：全國教保資訊網裁罰查詢（scripts/fetch_ntpc_penalty.py 抓取）。
    每列一間曾受裁罰之機構，含縣市/鄉鎮/設立別/電話/核定人數/營運狀態。
    檔案不存在時回傳 None（頁面應優雅退化）。
    """
    if not os.path.exists(PENALTY_CSV):
        return None
    return pd.read_csv(PENALTY_CSV)


def _norm_park_name(name):
    """園名正規化（去括號附註與雜訊），供裁罰紀錄跨資料源比對。"""
    import re as _re
    s = "" if pd.isna(name) else str(name).strip()
    s = _re.sub(r"[（(].*?[）)]", "", s)
    for junk in ("新北市政府", "新北市", "私立", "市立", "立", "　", " "):
        s = s.replace(junk, "")
    return s.strip()


@st.cache_data(show_spinner=False)
def penalty_lookup():
    """回傳 {正規化園名: 裁罰紀錄dict}，供各頁快速查詢某機構是否有裁罰。"""
    pen = load_penalty()
    if pen is None or len(pen) == 0:
        return {}
    lut = {}
    for _, r in pen.iterrows():
        lut[_norm_park_name(r.get("park_name"))] = r.to_dict()
    return lut


def penalty_for(park_name):
    """查某機構的真實裁罰紀錄；無則回 None。"""
    return penalty_lookup().get(_norm_park_name(park_name))


NONPROFIT_FIN_CSV = os.path.join(
    ROOT, "data", "processed", "nonprofit_financials_bedrock.csv")


@st.cache_data(show_spinner=False)
def load_nonprofit_financials():
    """非營利園真實財務（AWS Bedrock 視覺抽取自財報 PDF，已納入財務鑑識與風險計算）。

    每列一間非營利園之收入/支出/餘絀決算數，附抽取信心（high=勾稽通過）。
    已正式整合至 financials.csv 與風險模型計算。
    """
    if not os.path.exists(NONPROFIT_FIN_CSV):
        return None
    return pd.read_csv(NONPROFIT_FIN_CSV)


def nonprofit_financials_for(park_id):
    """查某非營利園的真實財務（以 park_id 對應）；無則回 None。"""
    df = load_nonprofit_financials()
    if df is None or len(df) == 0:
        return None
    hit = df[df["park_id"].astype(str) == str(park_id)]
    return hit.iloc[0].to_dict() if len(hit) else None


MOE_YEARLY_CSV = os.path.join(ROOT, "data", "external", "moe_ntpc_yearly.csv")


@st.cache_data(show_spinner=False)
def load_moe_yearly():
    """新北市幼兒園逐年概況（教育部統計處開放資料）；無檔時回 None。"""
    if not os.path.exists(MOE_YEARLY_CSV):
        return None
    return pd.read_csv(MOE_YEARLY_CSV)


def city_trend_chart():
    """全市幼兒園逐年概況趨勢：園數 / 幼生數 / 教師數（雙軸趨勢折線）。

    資料來源為教育部統計處官方開放資料（全市總量，非單園）。展現宏觀趨勢與
    「系統可持續接入官方開放資料」的可規模化性，與單園鑑識分析互補。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    d = load_moe_yearly()
    if d is None or len(d) < 2:
        empty_state("尚無全市概況統計", "執行 scripts/fetch_moe_stats.py 取得教育部統計處資料。")
        return

    years = [f"{int(y)}" for y in d["學年度"]]
    fig = make_subplots(specs=[[{"secondary_y": True}]])

    # 1. 幼生數（面積折線，右軸）：以沉穩藍與柔和漸層呈現總體規模趨勢，避免巨大長條遮蔽
    if "幼生總數" in d.columns:
        fig.add_trace(go.Scatter(
            x=years, y=d["幼生總數"], name="幼生總數（人）", mode="lines+markers",
            line=dict(color=PRIMARY, width=3),
            marker=dict(size=7, color=PRIMARY),
            fill="tozeroy", fillcolor="rgba(47, 109, 181, 0.08)",
            hovertemplate="%{x} 學年｜幼生 <b>%{y:,}</b> 人<extra></extra>",
        ), secondary_y=True)

    # 2. 教師數（折線，左軸）：綠色折線標示師資走勢
    if "教師總數" in d.columns:
        fig.add_trace(go.Scatter(
            x=years, y=d["教師總數"], name="教師總數（人）", mode="lines+markers",
            line=dict(color=RISK_BAR["low"], width=2.5, dash="dash"),
            marker=dict(size=6, color=RISK_BAR["low"]),
            hovertemplate="%{x} 學年｜教師 <b>%{y:,}</b> 人<extra></extra>",
        ), secondary_y=False)

    # 3. 園數（折線，左軸）：深色實線標示立案機構總數
    if "園數總數" in d.columns:
        fig.add_trace(go.Scatter(
            x=years, y=d["園數總數"], name="園數總數（間）", mode="lines+markers",
            line=dict(color=INK, width=2.5),
            marker=dict(size=7, color=INK),
            hovertemplate="%{x} 學年｜園數 <b>%{y:,}</b> 間<extra></extra>",
        ), secondary_y=False)

    _plotly_layout(fig, height=360)
    fig.update_layout(
        margin=dict(l=54, r=54, t=46, b=64),
        legend=dict(orientation="h", yanchor="bottom", y=1.03, xanchor="left", x=0,
                    font=dict(size=11, color=INK_2)),
    )
    fig.update_yaxes(title="園數（間）/ 教師數（人）", secondary_y=False, range=[0, 2600])
    fig.update_yaxes(title="幼生數（人）", secondary_y=True, range=[0, 100000])
    fig.update_xaxes(
        title="學年度",
        tickmode="array",
        tickvals=years,
        ticktext=[f"{y}學年" for y in years],
        tickfont=dict(size=11, color=INK_2),
        automargin=True,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def roster_coverage():
    """回傳全市涵蓋統計 dict（供總覽 KPI）；無 roster 檔時回 None。"""
    r = load_roster()
    if r is None or len(r) == 0:
        return None
    n_total = len(r)
    # 與實際深度評分母體（latest.csv）嚴格對齊，確保上下 KPI 數字閉環
    latest_df = load_latest()
    if latest_df is not None and len(latest_df) > 0:
        n_scored = len(latest_df)
    else:
        n_scored = int((r["data_status"] == "scored").sum())
    return {
        "total": n_total,
        "scored": n_scored,
        "roster_only": n_total - n_scored,
        "districts": int(r["district"].dropna().nunique()),
    }


def data_updated_at():
    """資料檔實際更新時間（不寫死）。"""
    if os.path.exists(LATEST_CSV):
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(LATEST_CSV)))
    return "—"


# ---- 格式化與風險對映 ----
def risk_key(level):
    """中文等級 → 企業五階 key。"""
    return LEVEL_TO_RISK.get(str(level), "normal")


def level_color(level):
    return LEVEL_COLOR.get(str(level), INK_MUTED)


def level_bg(level):
    return LEVEL_BG.get(str(level), SURFACE_SUNK)


def level_badge(level):
    return f"{level}風險"


def fmt_money(v):
    if pd.isna(v):
        return "—"
    return f"{v/10000:,.0f} 萬"


def fmt_pct(v, digits=1):
    if pd.isna(v):
        return "—"
    return f"{v:.{digits}f}%"


def hex_rgba(hex_color, alpha=0.18):
    """將 6 碼 hex 色碼（如 #B0453A）轉為 rgba() 字串，供 Plotly fillcolor 使用。

    Plotly 的 fillcolor 不接受 8 碼 hex（#RRGGBBAA），需用 rgba() 表達透明度。
    alpha 介於 0–1。非合法 6 碼 hex 時回傳原值（安全退化）。
    """
    s = str(hex_color).strip()
    if s.startswith("#"):
        s = s[1:]
    if len(s) != 6:
        return str(hex_color)
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
    except ValueError:
        return str(hex_color)
    a = max(0.0, min(float(alpha), 1.0))
    return f"rgba({r},{g},{b},{a})"


# ===========================================================================
# 全域 CSS
# ===========================================================================
def _css():
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap');

    :root {{
      --bg:{BG}; --surface:{SURFACE}; --surface-alt:{SURFACE_ALT}; --surface-sunk:{SURFACE_SUNK};
      --primary:{PRIMARY}; --primary-soft:{PRIMARY_SOFT};
      --ink:{INK}; --ink2:{INK_2}; --muted:{INK_MUTED}; --faint:{FAINT};
      --border:{BORDER}; --border-strong:{BORDER_STRONG};
      /* 8px spacing system */
      --s1:4px; --s2:8px; --s3:12px; --s4:16px; --s5:24px; --s6:32px; --s7:40px; --s8:48px;
      /* 統一尺寸規範 */
      --radius:8px; --radius-sm:5px;
      --page-px:48px;          /* 內容左右 padding（加大，提升呼吸感）*/
      --page-max:1320px;       /* 內容最大寬 */
      --section-gap:44px;      /* 大區塊間距（拉開，降低報表壅擠感）*/
      --sub-gap:var(--s5);     /* 次區塊間距 24 */
      --comp-gap:18px;         /* 元件間距（略加大）*/
      --card-pad:22px;         /* 卡片內距（統一，略加大）*/
      --control-h:40px;        /* 表單控制元件高度（統一）*/
      --table-row-h:46px;      /* 表格列高（加高，更好讀、更不擠）*/
      --sidebar-w:248px;
    }}

    html, body, [class*="css"], .stApp {{
      font-family:'Inter','Noto Sans TC','Microsoft JhengHei',sans-serif; color:var(--ink); }}
    .stApp {{ background:var(--bg);
      font-feature-settings:'tnum' 1; font-variant-numeric:tabular-nums; }}
    /* 統一 grid：所有 section 共用同一左右邊界與最大寬 */
    .block-container {{ padding:var(--s2) var(--page-px) var(--s8); max-width:var(--page-max); }}
    /* Streamlit 垂直堆疊間距統一（元件間距）*/
    [data-testid="stVerticalBlock"] {{ gap:var(--comp-gap); }}

    #MainMenu, footer {{ visibility:hidden; }}
    [data-testid="stDecoration"] {{ display:none; }}
    /* 頂部 Streamlit header 條歸零高度，消除頁面最上方的空白留白 */
    [data-testid="stHeader"] {{ background:transparent; height:0 !important; min-height:0 !important; }}
    [data-testid="stSidebarCollapsedControl"] {{ visibility:visible !important; display:flex !important; }}

    h1,h2,h3,h4 {{ color:var(--ink); font-weight:600; letter-spacing:.01em; }}

    /* ===== 側欄：深石墨品牌骨架（pixel-level 對齊）===== */
    /* 側欄背景色（不影響寬度）*/
    [data-testid="stSidebar"] {{ background:{SIDEBAR_BG}; border-right:none; }}
    /* 最小寬度只在「展開時」生效；收合時交還給 Streamlit（寬度 0），
       否則 min-width !important 會把收合後的側欄硬撐開，留下深色空白條。 */
    [data-testid="stSidebar"][aria-expanded="true"] {{ min-width:var(--sidebar-w) !important; }}
    /* 收合狀態：確保完全塌陷、不佔版面、不顯示深色殘影 */
    [data-testid="stSidebar"][aria-expanded="false"] {{
      min-width:0 !important; width:0 !important; margin-left:0 !important;
      overflow:hidden; border-right:none !important; }}
    [data-testid="stSidebar"][aria-expanded="false"] * {{ visibility:hidden; }}
    [data-testid="stSidebar"] > div:first-child {{ display:flex; flex-direction:column; height:100%; }}
    [data-testid="stSidebar"] * {{ color:{SIDEBAR_INK}; }}
    [data-testid="stSidebarNav"] {{ display:none !important; }}
    /* 清掉側欄容器與內容區的頂部預設留白 */
    [data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ padding:0 !important; }}
    [data-testid="stSidebar"] > div:first-child {{ padding-top:0 !important; }}
    /* Sidebar header：保留一列高度容納「收合按鈕（»）」，按鈕靠右，
       不再壓成 0，否則按鈕會浮到品牌區、與 logo 重疊。 */
    [data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{
      height:auto !important; min-height:0 !important;
      padding:6px 8px 0 !important; display:flex; justify-content:flex-end; align-items:center;
      background:transparent; }}
    /* 收合按鈕：融入深色側欄，低調不搶眼 */
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button,
    [data-testid="stSidebar"] [data-testid="stBaseButton-headerNoPadding"] {{
      color:{SIDEBAR_INK_DIM} !important; background:transparent !important; border:none !important; }}
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] button:hover {{
      color:#F1F4F7 !important; background:rgba(255,255,255,.06) !important; }}
    [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] svg {{ fill:currentColor !important; }}
    section[data-testid="stSidebar"] .block-container {{ padding-top:0 !important; }}
    /* 品牌區：header 之下，頂部只留少量間距（header 已佔一列） */
    .sw-brand {{ padding:var(--s2) var(--s4) var(--s4); border-bottom:1px solid rgba(255,255,255,.08); }}
    .sw-brand .logo {{ display:flex; align-items:center; gap:var(--s2); }}
    .sw-brand .name {{ font-size:1.18rem; font-weight:700; color:#F1F4F7; letter-spacing:.03em;
      line-height:1; }}
    .sw-brand .tag {{ color:{SIDEBAR_INK_DIM}; font-size:.72rem; margin-top:8px;
      letter-spacing:.02em; line-height:1.4; }}
    .sw-nav {{ padding:var(--s3) var(--s2); }}
    /* 導覽項目：完全等高、icon 固定寬對齊、文字 baseline 一致 */
    .sw-nav a {{ display:flex; align-items:center; gap:var(--s3); height:38px; padding:0 var(--s3);
      border-radius:var(--radius-sm); color:{SIDEBAR_INK}; font-size:.88rem; text-decoration:none;
      margin-bottom:2px; border-left:2px solid transparent; transition:background .16s ease; }}
    .sw-nav a:hover {{ background:rgba(255,255,255,.06); color:#F1F4F7; }}
    .sw-nav a.active {{ background:{SIDEBAR_ACTIVE}; color:#fff; border-left:2px solid {PRIMARY}; }}
    .sw-nav a svg {{ opacity:.85; flex:0 0 18px; width:18px; }}
    .sw-nav a span {{ line-height:1; }}

    /* ===== 原生 st.page_link 導覽（單一導覽來源）：外觀貼齊 .sw-nav a ===== */
    /* 佔位 div 不佔高度，避免品牌區與導覽之間出現空隙 */
    .sw-nav-native {{ height:0; margin:0; padding:0; line-height:0; }}
    /* 側欄各區塊（品牌 markdown / 導覽 container / footer）之間收緊：
       覆蓋全域 16px 的 vertical block gap，改為 2px，消除品牌區到導覽的大空隙。 */
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap:2px !important; }}
    /* 側欄各 element-container 也去掉多餘上下 margin */
    [data-testid="stSidebar"] [data-testid="stElementContainer"] {{ margin:0 !important; }}
    /* 導覽項目左右內距對齊 */
    [data-testid="stSidebar"] [data-testid="stPageLink"] {{ margin:0 var(--s2) !important; }}
    /* 分組標題（行政作業系統式檔案櫃分區）：小型全大寫石墨副標，
       與 System Status footer 的區塊標題（.stt-h）同一語彙，維持側欄一致性。
       組間拉開（上距 22px）、標題與其下第一個項目留 8px，同組內項目維持緊湊，
       建立「組內緊湊、組間分明」的清楚節奏。 */
    [data-testid="stSidebar"] .sw-navgrp {{
      color:{SIDEBAR_INK_DIM}; font-size:.68rem; font-weight:700;
      letter-spacing:.12em; text-transform:uppercase;
      margin:22px 14px 8px !important; padding:0; line-height:1.2; }}
    /* 第一個分組標題緊貼品牌分隔線下方，間距略收。 */
    [data-testid="stSidebar"] .sw-navgrp:first-of-type {{ margin-top:14px !important; }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] a,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
      display:flex !important; align-items:center; gap:11px; height:38px; padding:0 12px !important;
      border-radius:var(--radius-sm); color:{SIDEBAR_INK} !important; font-size:.885rem;
      text-decoration:none; margin:0 !important; border-left:2px solid transparent;
      transition:background .16s ease, color .16s ease; background:transparent !important; }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] a:hover,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"]:hover {{
      background:rgba(255,255,255,.06) !important; color:#F1F4F7 !important; }}
    /* active：Streamlit 對目前頁面加 aria-current="page" */
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"],
    [data-testid="stSidebar"] [data-testid="stPageLink"] a[aria-current="page"] {{
      background:{SIDEBAR_ACTIVE} !important; color:#fff !important;
      border-left:2px solid {PRIMARY} !important; }}
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] p,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"][aria-current="page"] span {{
      color:#fff !important; }}
    /* 文字（label） */
    [data-testid="stSidebar"] [data-testid="stPageLink"] p {{
      color:inherit !important; font-size:.88rem !important; line-height:1 !important; margin:0 !important;
      font-weight:400 !important; }}
    /* 佔位 icon（▪）：縮小成小色點，對齊原 svg 的 18px 欄位 */
    [data-testid="stSidebar"] [data-testid="stPageLink"] [data-testid="stIconMaterial"],
    [data-testid="stSidebar"] [data-testid="stPageLink"] span[role="img"] {{
      color:{SIDEBAR_INK_DIM} !important; font-size:12px !important; width:18px; flex:0 0 18px;
      text-align:center; opacity:.7; }}

    /* System Status footer（企業式）*/
    .sw-side-foot {{ margin-top:auto; padding:var(--s4); border-top:1px solid rgba(255,255,255,.08); }}
    .sw-side-foot .stt-h {{ color:{SIDEBAR_INK_DIM}; font-size:.66rem; font-weight:600;
      letter-spacing:.12em; text-transform:uppercase; margin-bottom:10px; }}
    .sw-side-foot .stt-row {{ margin-bottom:10px; }}
    .sw-side-foot .stt-k {{ color:{SIDEBAR_INK_DIM}; font-size:.68rem; letter-spacing:.02em; }}
    .sw-side-foot .stt-v {{ color:{SIDEBAR_INK}; font-size:.78rem; margin-top:2px;
      font-variant-numeric:tabular-nums; }}
    .sw-status {{ display:inline-flex; align-items:center; gap:6px; color:{SIDEBAR_INK}; font-size:.78rem; }}
    /* 運作中指示燈：淺綠色 + 脈動綠光（呼吸效果），表示系統 live 運作 */
    .sw-status .dot {{ width:7px; height:7px; border-radius:50%; background:#4ADE80;
      position:relative; flex:0 0 7px;
      box-shadow:0 0 0 0 #4ADE80;
      animation:swStatusPulse 1.8s ease-in-out infinite; }}
    @keyframes swStatusPulse {{
      0%   {{ box-shadow:0 0 0 0 rgba(74,222,128,.55); opacity:1; }}
      70%  {{ box-shadow:0 0 0 6px rgba(74,222,128,0); opacity:.75; }}
      100% {{ box-shadow:0 0 0 0 rgba(74,222,128,0); opacity:1; }}
    }}

    /* ===== 按鈕（統一高度）===== */
    .stButton>button, .stDownloadButton>button {{
      border-radius:var(--radius); border:1px solid var(--border-strong); background:var(--surface);
      color:var(--ink); font-weight:500; box-shadow:none; transition:all .16s ease; min-height:var(--control-h); }}
    .stButton>button:hover, .stDownloadButton>button:hover {{
      border-color:var(--primary); color:var(--primary); }}
    .stButton>button[kind="primary"] {{ background:var(--primary); border-color:var(--primary); color:#fff; }}

    /* ===== 表單控制元件：統一高度/radius/font ===== */
    [data-baseweb="select"]>div {{ border-radius:var(--radius) !important; border:1px solid var(--border) !important;
      background:var(--surface) !important; min-height:var(--control-h); box-shadow:none !important; }}
    [data-baseweb="select"]>div:focus-within {{ border-color:var(--primary) !important; }}
    /* label 與 input 間距一致 */
    [data-testid="stWidgetLabel"] {{ margin-bottom:6px; }}
    [data-testid="stWidgetLabel"] p {{ color:var(--muted) !important; font-size:.75rem !important;
      font-weight:500 !important; letter-spacing:.02em; }}
    /* 多選 chip：統一尺寸、不過胖 */
    [data-baseweb="tag"], [data-baseweb="tag"] > span, span[data-baseweb="tag"] {{
      background-color:#EDEEEF !important; background-image:none !important;
      border:1px solid var(--border-strong) !important; border-radius:var(--radius-sm) !important;
      color:#5A616B !important; height:22px !important; }}
    [data-baseweb="tag"] span, [data-baseweb="tag"] div {{ color:#5A616B !important; font-size:.78rem !important; }}
    [data-baseweb="tag"] svg {{ fill:var(--faint) !important; color:var(--faint) !important; }}
    .stSlider [data-baseweb="slider"] div[role="slider"] {{ background:var(--primary); }}

    /* ===== pills 多選（機構類型 / 風險等級）：膠囊按鈕，取代會出現 "No results" 的 multiselect ===== */
    [data-testid="stPills"] {{ gap:6px; }}
    [data-testid="stPills"] button {{
      min-height:var(--control-h) !important; border-radius:999px !important;
      border:1px solid var(--border) !important; background:var(--surface) !important;
      color:var(--ink2) !important; font-size:.82rem !important; font-weight:500 !important;
      padding:0 14px !important; box-shadow:none !important; transition:all .14s ease; }}
    [data-testid="stPills"] button:hover {{
      border-color:var(--primary) !important; color:var(--primary) !important; }}
    /* 選中狀態：主色底白字（Streamlit 對選中 pill 加 aria-checked/aria-pressed）*/
    [data-testid="stPills"] button[aria-checked="true"],
    [data-testid="stPills"] button[aria-pressed="true"],
    [data-testid="stPills"] button[kind="pillsActive"] {{
      background:var(--primary) !important; border-color:var(--primary) !important;
      color:#fff !important; }}
    [data-testid="stPills"] button[aria-checked="true"] p,
    [data-testid="stPills"] button[aria-pressed="true"] p {{ color:#fff !important; }}

    /* ===== expander / alert / tabs / chart ===== */
    [data-testid="stExpander"] {{ border:1px solid var(--border); border-radius:var(--radius); box-shadow:none; background:var(--surface); }}
    [data-testid="stExpander"] summary {{ font-weight:500; }}
    [data-testid="stAlert"] {{ border-radius:var(--radius); }}
    [data-testid="stPlotlyChart"], [data-testid="stVegaLiteChart"] {{
      border:1px solid var(--border) !important; border-radius:var(--radius) !important;
      background:var(--surface) !important; padding:0 !important;
      box-shadow:0 1px 2px rgba(28,37,48,.04) !important;
      overflow:hidden !important; box-sizing:border-box !important; }}
    [data-testid="stPlotlyChart"] *, [data-testid="stVegaLiteChart"] * {{
      box-sizing:border-box; }}
    [data-testid="stPlotlyChart"] > div,
    [data-testid="stPlotlyChart"] .js-plotly-plot,
    [data-testid="stPlotlyChart"] .plot-container,
    [data-testid="stPlotlyChart"] .svg-container {{
      border-radius:var(--radius) !important; overflow:hidden !important; }}
    [data-testid="stPlotlyChart"] .modebar-container {{
      display:none !important; }}
    iframe[title="streamlit_folium.st_folium"] {{
      border:1px solid var(--border) !important; border-radius:var(--radius) !important;
      overflow:hidden !important; box-shadow:0 1px 2px rgba(28,37,48,.04) !important;
      box-sizing:border-box !important; }}
    .stTabs [data-baseweb="tab-list"] {{ gap:2px; border-bottom:1px solid var(--border); }}
    .stTabs [data-baseweb="tab"] {{ font-size:.88rem; color:var(--ink2); padding:8px 14px; }}
    .stTabs [aria-selected="true"] {{ color:var(--primary) !important; }}
    .stTabs [data-baseweb="tab-highlight"] {{ background:var(--primary); }}

    /* ===== 頁面 Header + Breadcrumb（精準層級）===== */
    .sw-topbar {{ display:flex; align-items:flex-end; justify-content:space-between;
      border-bottom:1px solid var(--border); padding-bottom:var(--s4); margin-bottom:var(--s5); gap:var(--s4); }}
    .sw-crumb {{ color:var(--muted); font-size:.74rem; letter-spacing:.04em; margin-bottom:8px; }}
    .sw-crumb b {{ color:var(--ink2); font-weight:500; }}
    .sw-ptitle {{ font-size:1.6rem; font-weight:700; color:var(--ink); line-height:1.2;
      letter-spacing:.005em; }}
    .sw-psub {{ color:var(--ink2); font-size:.86rem; margin-top:7px; line-height:1.5;
      max-width:820px; }}
    .sw-meta {{ text-align:right; color:var(--muted); font-size:.72rem; line-height:1.8; white-space:nowrap; }}
    .sw-meta b {{ color:var(--ink2); font-weight:600; font-variant-numeric:tabular-nums; }}
    /* 右上角帳號區：目前登入角色（登出按鈕於下方以 Streamlit 元件呈現） */
    /* 帳號列：角色膠囊 + 登出膠囊，同形狀、緊鄰並排、靠右。 */
    .sw-acctbar {{ display:flex; align-items:center; justify-content:flex-end;
      gap:8px; margin-bottom:8px; }}
    .sw-acct {{ display:inline-flex; align-items:center; gap:6px; justify-content:center;
      height:32px; padding:0 14px; border:1px solid var(--border-strong);
      border-radius:999px; background:var(--surface); white-space:nowrap;
      box-sizing:border-box; text-decoration:none; }}
    .sw-acct-role {{ color:var(--ink); font-size:.78rem; font-weight:600; }}
    /* 登出：與角色膠囊同形狀的可點擊連結；hover 變主色。 */
    .sw-logout {{ color:var(--ink2); font-size:.78rem; font-weight:600; cursor:pointer;
      transition:all .14s ease; }}
    .sw-logout:hover {{ border-color:var(--primary); color:var(--primary); }}

    /* ===== KPI stat：四格等寬等高、baseline 一致 ===== */
    .sw-stats {{ display:flex; gap:1px; background:var(--border); border:1px solid var(--border);
      border-radius:var(--radius); overflow:hidden;
      box-shadow:0 1px 2px rgba(28,37,48,.04); }}
    .sw-stats .cell {{ flex:1 1 0; min-height:108px; padding:20px 22px; background:var(--surface);
      position:relative; display:flex; flex-direction:column; }}
    .sw-stats .cell.accent::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
      background:{RISK_BAR['high']}; }}
    .sw-stats .lab {{ color:var(--muted); font-size:.76rem; font-weight:500; letter-spacing:.03em;
      display:flex; align-items:center; gap:6px; min-height:16px; }}
    .sw-stats .val {{ color:var(--ink); font-size:2rem; font-weight:700; line-height:1.05; margin-top:auto;
      font-variant-numeric:tabular-nums; letter-spacing:-.01em; }}
    .sw-stats .val.risk {{ color:{RISK['high'][0]}; }}
    .sw-stats .sub {{ color:var(--muted); font-size:.73rem; margin-top:8px; min-height:14px;
      line-height:1.4; }}

    /* ===== Section Header：統一元件 ===== */
    .sw-section {{ display:flex; align-items:center; gap:10px; margin:var(--section-gap) 0 var(--comp-gap);
      font-size:1rem; font-weight:600; color:var(--ink); letter-spacing:.01em; }}
    .sw-section svg {{ flex:0 0 16px; }}
    .sw-section .ln {{ flex:1; height:1px; background:var(--border); margin-left:4px; }}
    .sw-callout {{ border:1px solid var(--border); border-left:3px solid var(--primary);
      background:var(--surface); border-radius:var(--radius); padding:14px 18px;
      font-size:.87rem; color:var(--ink2); line-height:1.7;
      box-shadow:0 1px 2px rgba(28,37,48,.04); }}

    /* ===== 企業資料表：固定列高、細框、tabular ===== */
    .sw-table {{ width:100%; border-collapse:separate; border-spacing:0; background:var(--surface);
      border:1px solid var(--border); border-radius:var(--radius); overflow:hidden;
      font-variant-numeric:tabular-nums; table-layout:auto;
      box-shadow:0 1px 2px rgba(28,37,48,.04); }}
    .sw-table thead th {{ background:var(--surface-alt); color:var(--muted); font-weight:600;
      font-size:.73rem; letter-spacing:.05em; padding:13px 16px; text-align:right; white-space:nowrap;
      border-bottom:1px solid var(--border-strong); }}
    .sw-table thead th.l {{ text-align:left; }}
    .sw-table tbody td {{ height:var(--table-row-h); padding:0 16px; text-align:right; font-size:.875rem;
      font-weight:400; border-top:1px solid var(--surface-sunk); color:var(--ink2); white-space:nowrap;
      font-variant-numeric:tabular-nums; vertical-align:middle; }}
    .sw-table tbody td.l {{ text-align:left; color:var(--ink); }}
    .sw-table tbody tr:nth-child(even) {{ background:var(--surface-alt); }}
    .sw-table tbody tr:hover {{ background:var(--primary-soft); }}
    .sw-rank {{ color:var(--faint); font-weight:600; }}
    .sw-na {{ color:var(--faint); }}

    /* 風險分內嵌長條 */
    .sw-bar-wrap {{ display:inline-flex; align-items:center; gap:var(--s2); justify-content:flex-end; min-width:128px; }}
    .sw-bar-num {{ font-weight:700; font-size:.94rem; width:46px; text-align:right; font-variant-numeric:tabular-nums; }}
    .sw-bar-track {{ width:64px; height:6px; background:var(--surface-sunk); border-radius:2px; overflow:hidden; }}
    .sw-bar-fill {{ height:100%; border-radius:2px; }}

    /* badge：固定尺寸一致 */
    .sw-badge {{ display:inline-block; min-width:40px; text-align:center; padding:3px 11px;
      border-radius:999px; font-size:.75rem; font-weight:600; line-height:1.5;
      border:1px solid transparent; letter-spacing:.02em; }}

    /* 卡片：統一內距，含等高變體 */
    .sw-panel {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
      padding:var(--card-pad); box-shadow:0 1px 2px rgba(28,37,48,.04); }}
    .sw-panel.fill {{ height:100%; box-sizing:border-box; }}
    .sw-scorecard {{ background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--primary);
      border-radius:var(--radius); padding:var(--card-pad); margin-bottom:var(--s4);
      box-shadow:0 1px 2px rgba(28,37,48,.04); }}

    /* ===== 稽查決策條（行動優先 / 互動回饋）===== */
    .sw-decisionbar {{ background:var(--surface); border:1px solid var(--border);
      border-left:4px solid var(--primary); border-radius:var(--radius);
      padding:16px 20px; margin:10px 0 4px;
      display:flex; align-items:center; justify-content:space-between; gap:20px;
      flex-wrap:wrap; transition:box-shadow .18s ease, border-color .18s ease; }}
    .sw-decisionbar:hover {{ box-shadow:0 2px 10px rgba(28,37,48,.08); }}
    .sw-db-verdict {{ flex:1 1 320px; min-width:280px; }}
    .sw-db-eyebrow {{ color:var(--muted); font-size:.72rem; font-weight:600;
      letter-spacing:.08em; text-transform:uppercase; display:flex; align-items:center;
      gap:6px; margin-bottom:6px; }}
    .sw-db-headline {{ color:var(--ink); font-size:1.02rem; font-weight:600;
      line-height:1.5; }}
    .sw-db-sub {{ color:var(--ink2); font-size:.82rem; margin-top:4px; line-height:1.5; }}
    /* 當前狀態徽章：狀態切換時色彩即時變化，給予清楚的視覺回饋 */
    .sw-statuspill {{ display:inline-flex; align-items:center; gap:7px;
      padding:5px 14px; border-radius:999px; font-size:.82rem; font-weight:700;
      border:1px solid transparent; transition:all .2s ease; white-space:nowrap; }}
    .sw-statuspill .dot {{ width:8px; height:8px; border-radius:50%; flex:0 0 8px; }}
    /* 決策按鈕列：把「下決定」放在使用者視線最先到達處 */
    .sw-db-actions {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}

    /* 決策條內的 Streamlit 按鈕：加大、hover 上浮、明確可點回饋 */
    .sw-decision-scope .stButton>button {{ min-height:42px; padding:0 18px;
      font-weight:600; font-size:.9rem; transition:all .16s ease; }}
    .sw-decision-scope .stButton>button:hover {{ transform:translateY(-1px);
      box-shadow:0 3px 10px rgba(28,37,48,.12); }}
    .sw-decision-scope .stButton>button:active {{ transform:translateY(0); }}

    /* Empty / Loading state */
    .sw-empty {{ border:1px dashed var(--border-strong); border-radius:var(--radius); background:var(--surface-alt);
      padding:40px var(--s5); text-align:center; color:var(--muted); font-size:.86rem; line-height:1.6; }}
    .sw-empty .ttl {{ color:var(--ink2); font-weight:600; font-size:.94rem; margin:10px 0 var(--s1); }}
    @keyframes swpulse {{ 0%{{opacity:.55}}50%{{opacity:1}}100%{{opacity:.55}} }}
    .sw-skel {{ height:12px; border-radius:3px; background:var(--surface-sunk); animation:swpulse 1.4s infinite; }}

    /* 響應式：窄螢幕收縮 padding，避免爆版 */
    @media (max-width:1200px) {{
      :root {{ --page-px:24px; }}
      .sw-stats {{ flex-wrap:wrap; }}
      .sw-stats .cell {{ flex:1 1 46%; }}
    }}
    </style>
    """


# ===========================================================================
# Shell：側欄品牌 + 導覽 + Header/Breadcrumb
# ===========================================================================
def _current_page_key():
    """
    判斷目前正在執行哪一個頁面（供導覽 active 標示）。
    以「呼叫堆疊中最靠近使用者頁面的來源檔名」比對 NAV key。
    每個頁面腳本檔名皆含唯一關鍵字（主頁.py / 1_case.py / 2_map.py ...），
    因此以檔名關鍵字比對即可，跨平台（Windows 反斜線路徑亦適用）。
    """
    import inspect
    nav_source = NAV_ALL if "NAV_ALL" in globals() else NAV
    try:
        for frame in inspect.stack():
            fn = os.path.basename(frame.filename)
            for key, _disp, _ic, _page in nav_source:
                # 主頁：entry point 檔名為「主頁.py」
                if key == "主頁":
                    if fn == "主頁.py":
                        return "主頁"
                # 其他頁：檔名關鍵字（如 1_case）出現在檔名中
                elif key in fn:
                    return key
    except Exception:
        pass
    return "主頁"


def _sidebar(active_key):
    """
    側欄 = 品牌區 + 角色感知導覽 + 使用者/登出 + System Status footer。

    RBAC 第一層授權（UI 導覽）：只顯示 permissions.get_role_navigation(current_role)
    允許的頁面——不該看到的頁面在 UI 直接消失。未登入時側欄不顯示任何導覽。
    導覽仍用 Streamlit 原生 st.page_link()（單一導覽來源），CSS class 不變。
    """
    # --- 1) 品牌區（HTML）---
    st.sidebar.markdown(
        f"""
        <div class='sw-brand'>
          <div class='logo'>{icon('shield', 22, '#5FA0DB')}
            <span class='name'>Fiscalint</span></div>
          <div class='tag'>教保機構監理作業系統</div>
        </div>
        <div class='sw-nav-native'></div>
        """,
        unsafe_allow_html=True,
    )

    # --- 2) 導覽（公務後台無登入、無角色）：依行政職能分組顯示所有公務頁面 ---
    # 公務後台為政府內部系統，所有頁面對公務人員一律開放；家長端已切分為獨立
    # 公眾查詢網（public/公開查詢.py），不在此導覽中。
    # 分組（NAV_GROUPS）只影響呈現順序與分組標題，不新增／不刪除任何頁面。
    # 重點：在 `with st.sidebar.container()` 區塊內，一律用「不帶 sidebar. 前綴」
    # 的 st.markdown / st.page_link。若在此區塊內呼叫 st.sidebar.markdown，會跳出
    # 容器、掛到側欄根層而破壞順序（先前分組標題全擠到底部的原因）。用容器內
    # 相對 API 即可讓「分組標題 → 該組頁面」依序、成組排列。
    with st.sidebar.container():
        for grp_title, keys in NAV_GROUPS:
            st.markdown(
                f"<div class='sw-navgrp'>{html.escape(grp_title)}</div>",
                unsafe_allow_html=True,
            )
            for key in keys:
                item = _NAV_BY_KEY.get(key)
                if not item:
                    continue
                _k, disp, _ic, page = item
                # page_link 在離線測試環境（AppTest 無 page registry）會丟
                # KeyError('url_pathname')；容錯以確保導覽失敗不中斷整頁渲染。
                try:
                    st.page_link(page, label=disp, icon=_NAV_EMOJI.get(key, "▪"))
                except Exception:  # noqa: BLE001
                    pass

    # --- 3) 目前登入角色 + 登出：已移至右上角 header（見 _render_topbar_account）---

    # --- 4) System Status footer（HTML）---
    st.sidebar.markdown(
        f"""
        <div class='sw-side-foot'>
          <div class='stt-h'>System Status</div>
          <div class='stt-row'><div class='sw-status'><span class='dot'></span>Operational</div></div>
          <div class='stt-row'><div class='stt-k'>Last Updated</div>
            <div class='stt-v'>{data_updated_at()}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# 導覽項目的 icon（用單色圓點 emoji 佔位，實際外觀由 CSS 控制；
# st.page_link 的 icon 僅接受單一 emoji 或 Material 圖示，這裡用中性符號）。
_NAV_EMOJI = {
    "主頁": "▪", "1_case": "▪", "2_map": "▪", "5_dispatch": "▪",
    "7_integration": "▪", "3_ai": "▪", "4_sentiment": "▪", "6_governance": "▪",
    "8_health": "▪",
}

# 完整導覽清單（公務後台）：在既有 NAV 之上補入案件調查（稽查員）與資料治理
# 權限矩陣（政府），供角色感知導覽依角色過濾。
# 家長信任中心已切分為獨立公眾查詢網（public/公開查詢.py），不再是公務後台頁面。
# 既有 NAV 不變（向後相容其他引用），角色過濾一律以 NAV_ALL 為來源。
NAV_ALL = NAV + [
    ("1_case",        "案件調查",         "case",      "pages/1_case.py"),
    ("5_dispatch",    "派工決策台",       "case",      "pages/5_dispatch.py"),
    ("7_integration", "資料整合中心",     "dashboard", "pages/7_integration.py"),
    ("6_governance",  "資料治理權限矩陣", "shield",    "pages/6_governance.py"),
    ("9_public_preview", "民眾端預覽",    "check",     "pages/9_public_preview.py"),
    ("8_health",      "系統健康檢查",     "shield",    "pages/8_health.py"),
]
# NAV_ALL 可能因 1_case 已在 NAV（否）而重複；以 key 去重並保留首次出現順序。
_seen_keys = set()
_dedup = []
for _item in NAV_ALL:
    if _item[0] not in _seen_keys:
        _seen_keys.add(_item[0])
        _dedup.append(_item)
NAV_ALL = _dedup

# ---------------------------------------------------------------------------
# 側欄導覽分組（行政作業系統式）：把平列導覽依「行政職能」分區並加分組標題，
# 讓側欄一眼看出「監理總覽 / 案件作業 / 分析工具 / 系統」的檔案櫃結構，
# 貼近政府機關內部系統的資訊架構。分組只影響「呈現順序與標題」，不新增、
# 不刪除任何頁面（頁面本身完全不變），故功能零更動。
#
# NAV_GROUPS: [(分組標題, [該組的 nav key（順序即顯示順序）]), ...]
NAV_GROUPS = [
    ("監理總覽",  ["主頁", "2_map"]),
    ("案件作業",  ["1_case", "5_dispatch"]),
    ("分析工具",  ["3_ai", "4_sentiment"]),
    ("系統管理",  ["7_integration", "6_governance", "8_health"]),
]
# 以 key 快速取回完整 nav item（key -> (key, disp, icon, page)）。
_NAV_BY_KEY = {item[0]: item for item in NAV_ALL}


def setup_page(page_title, header_title, subtitle=None, layout="wide",
               module=None, crumb=None, allowed_roles=None):
    """
    頁面初始化：set_page_config + 注入設計系統 + 品牌側欄 + Header/Breadcrumb。
    向後相容舊簽名（page_title/header_title/subtitle/layout）。
    module：麵包屑最後一節（預設用 header_title）。

    RBAC（allowed_roles）：
      - 若提供 allowed_roles（角色字串清單），先做頁面級守衛（第二層授權）：
        未登入 → 顯示登入畫面並 st.stop()；已登入但角色不符 → 顯示「存取遭拒」
        畫面並 st.stop()。
      - 預設 None 時維持舊行為（向後相容，不破壞尚未加守衛的頁面）。
    """
    st.set_page_config(page_title=page_title, page_icon=None, layout=layout,
                       initial_sidebar_state="auto")
    st.markdown(_css(), unsafe_allow_html=True)

    # 公務後台（8601）為政府內部系統，不設登入牆與角色守衛。
    # allowed_roles 參數保留於簽名以向後相容既有頁面呼叫，但不再觸發守衛。
    _ = allowed_roles

    _sidebar(_current_page_key())

    crumb_txt = crumb or "Fiscalint"
    module_txt = module or header_title
    sub = f"<div class='sw-psub'>{html.escape(subtitle)}</div>" if subtitle else ""

    st.markdown(
        f"""
        <div class='sw-topbar'>
          <div>
            <div class='sw-crumb'>{html.escape(crumb_txt)} &nbsp;/&nbsp; <b>{html.escape(module_txt)}</b></div>
            <div class='sw-ptitle'>{html.escape(header_title)}</div>
            {sub}
          </div>
          <div class='sw-meta'>
            <div>資料更新　<b>{data_updated_at()}</b></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ===========================================================================
# 共用 HTML 元件
# ===========================================================================
def section(title, icon_name=None):
    ic = (icon(icon_name, 16, INK_2) + " ") if icon_name else ""
    st.markdown(f"<div class='sw-section'>{ic}<span>{html.escape(title)}</span>"
                f"<span class='ln'></span></div>", unsafe_allow_html=True)


def callout(text, tone="info"):
    st.markdown(f"<div class='sw-callout'>{text}</div>", unsafe_allow_html=True)


def empty_state(title, desc="", icon_name="clock"):
    st.markdown(
        f"<div class='sw-empty'>{icon(icon_name, 22, FAINT)}"
        f"<div class='ttl'>{html.escape(title)}</div>"
        f"<div>{html.escape(desc)}</div></div>",
        unsafe_allow_html=True,
    )


def kpi_band(items):
    """相容舊簽名：items=[(label, value, is_risk_bool?), ...]。企業級 stat 帶。"""
    cells = ""
    for it in items:
        lab, val = it[0], it[1]
        risk = it[2] if len(it) > 2 else False
        sub = it[3] if len(it) > 3 else ""
        cell_cls = "cell accent" if risk else "cell"
        val_cls = "val risk" if risk else "val"
        sub_html = f"<div class='sub'>{html.escape(str(sub))}</div>" if sub else ""
        cells += (f"<div class='{cell_cls}'><div class='lab'>{html.escape(str(lab))}</div>"
                  f"<div class='{val_cls}'>{html.escape(str(val))}</div>{sub_html}</div>")
    st.markdown(f"<div class='sw-stats'>{cells}</div>", unsafe_allow_html=True)


def badge(level):
    """風險等級色塊 badge（中文等級）。"""
    c = level_color(level)
    bg = level_bg(level)
    bd = LEVEL_BORDER.get(str(level), "#CBD0D6")
    return (f"<span class='sw-badge' style='background:{bg};color:{c};"
            f"border-color:{bd};'>{html.escape(str(level))}</span>")


def grade_badge(grade):
    g = "" if grade is None else str(grade).strip()
    if g == "" or g == "nan":
        return "<span class='sw-na'>—</span>"
    if g in GRADE_STYLE:
        fg, bg = GRADE_STYLE[g]
        return (f"<span class='sw-badge' style='background:{bg};color:{fg};"
                f"border-color:{fg}33;'>{html.escape(g)}</span>")
    return f"<span>{html.escape(g)}</span>"


def score_bar(value, level, vmax=100):
    c = level_color(level)
    bar = LEVEL_BAR.get(str(level), c)
    pct = max(0, min(float(value) / vmax * 100, 100))
    return (f"<span class='sw-bar-wrap'>"
            f"<span class='sw-bar-num' style='color:{c};'>{value:.1f}</span>"
            f"<span class='sw-bar-track'>"
            f"<span class='sw-bar-fill' style='width:{pct:.0f}%;background:{bar};'></span>"
            f"</span></span>")


def dot(color, label):
    return (f"<span style='display:inline-flex;align-items:center;gap:6px;'>"
            f"<span style='width:9px;height:9px;border-radius:50%;background:{color};"
            f"display:inline-block;'></span>{html.escape(label)}</span>")


def risk_distribution(counts_by_level, total):
    """
    風險分布橫條（第二層）：高/中/低各一條，長度＝占比。用風險色，非彩色圓餅。
    counts_by_level: dict {'高':n,'中':n,'低':n}
    """
    rows = ""
    for lv in ("高", "中", "低"):
        n = int(counts_by_level.get(lv, 0))
        pct = (n / total * 100) if total else 0
        c = level_color(lv)
        bar = LEVEL_BAR.get(lv, c)
        rows += (
            f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:8px;'>"
            f"<div style='width:74px;color:{c};font-weight:600;font-size:.82rem;'>"
            f"{badge(lv)}</div>"
            f"<div style='flex:1;height:10px;background:{SURFACE_SUNK};border-radius:2px;overflow:hidden;'>"
            f"<div style='width:{pct:.0f}%;height:100%;background:{bar};border-radius:2px;'></div></div>"
            f"<div style='width:96px;text-align:right;color:{INK_2};font-size:.84rem;"
            f"font-variant-numeric:tabular-nums;'>{n} 間　({pct:.0f}%)</div>"
            f"</div>"
        )
    st.markdown(f"<div class='sw-panel fill'>{rows}</div>", unsafe_allow_html=True)


def priority_cases(df, n=5):
    """
    優先案件（第三層之上的精選）：列出風險最高的前 n 間，含主要風險訊號。
    誠實地由現有分項與指標推導風險訊號，不造假。
    """
    top = df.sort_values("risk_total", ascending=False).head(n)
    rows = ""
    for _, r in top.iterrows():
        signals = []
        if r.get("penalty_count", 0) and int(r["penalty_count"]) > 0:
            signals.append(f"裁罰 {int(r['penalty_count'])} 次")
        if r.get("expense_income_ratio", 0) and r["expense_income_ratio"] > 1:
            signals.append(f"收支比 {r['expense_income_ratio']:.2f}")
        if r.get("score_financial", 0) >= 40:
            signals.append("財務指標異常")
        if not signals:
            signals.append("綜合分數偏高")
        sig_txt = "、".join(signals[:3])
        c = level_color(r["risk_level"])
        rows += (
            "<tr>"
            f"<td class='l'>{html.escape(str(r['park_name']))}</td>"
            f"<td class='l'>{html.escape(str(r['district']))}</td>"
            f"<td>{score_bar(r['risk_total'], r['risk_level'])}</td>"
            f"<td class='l'>{badge(r['risk_level'])}</td>"
            f"<td class='l' style='color:{INK_2};'>{html.escape(sig_txt)}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>機構名稱</th><th class='l'>行政區</th><th>總風險分</th>"
        "<th class='l'>等級</th><th class='l'>主要風險訊號</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )


def render_ranking_table(view):
    """企業資料表：排名表（微型長條 + 色塊 badge + tabular 數字）。"""
    head = (
        "<tr>"
        "<th class='l'>#</th><th class='l'>機構名稱</th><th class='l'>行政區</th>"
        "<th>總風險分</th><th class='l'>等級</th>"
        "<th>財務分</th><th>裁罰分</th><th>評鑑分</th>"
        "<th>收支比</th><th>裁罰次數</th><th class='l'>評鑑等第</th>"
        "</tr>"
    )
    rows = ""
    for i, r in view.iterrows():
        rows += (
            "<tr>"
            f"<td class='l sw-rank'>{i+1}</td>"
            f"<td class='l'>{html.escape(str(r['park_name']))}</td>"
            f"<td class='l'>{html.escape(str(r['district']))}</td>"
            f"<td>{score_bar(r['risk_total'], r['risk_level'])}</td>"
            f"<td class='l'>{badge(r['risk_level'])}</td>"
            f"<td>{r['score_financial']:.1f}</td>"
            f"<td>{r['score_penalty']:.0f}</td>"
            f"<td>{r['score_eval']:.0f}</td>"
            f"<td>{r['expense_income_ratio']:.3f}</td>"
            f"<td>{int(r['penalty_count'])}</td>"
            f"<td class='l'>{grade_badge(r.get('eval_grade'))}</td>"
            "</tr>"
        )
    st.markdown(f"<table class='sw-table'><thead>{head}</thead><tbody>{rows}</tbody></table>",
                unsafe_allow_html=True)


def case_header(row):
    """案件標頭：Case ID / 機構 / 行政區 / 等級 / 總分，一橫排（Forensic Workspace 頂部）。"""
    c = level_color(row["risk_level"])
    bg = level_bg(row["risk_level"])
    cid = html.escape(str(row.get("park_id", "—")))
    st.markdown(
        f"""
        <div class='sw-panel' style='border-left:4px solid {c};display:flex;
             align-items:center;justify-content:space-between;gap:20px;flex-wrap:wrap;'>
          <div>
            <div style='color:{INK_MUTED};font-size:.74rem;letter-spacing:.03em;'>
              案件編號 {cid}　·　{html.escape(str(row['district']))}　·　{html.escape(str(row['park_type']))}</div>
            <div style='font-size:1.35rem;font-weight:700;color:{INK};margin-top:2px;'>
              {html.escape(str(row['park_name']))}</div>
          </div>
          <div style='text-align:right;'>
            <div style='color:{INK_MUTED};font-size:.74rem;'>總風險分</div>
            <div style='font-size:2.4rem;font-weight:700;color:{c};line-height:1;
                 font-variant-numeric:tabular-nums;'>{row['risk_total']:.1f}
              <span style='font-size:.9rem;color:{INK_MUTED};font-weight:500;'>/100</span></div>
            <div style='margin-top:4px;'>{badge(row['risk_level'])}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _one_line_verdict(row):
    """由現有鑑識指標推導「一句話結論」，供決策條快速呈現（不造假）。

    取最能代表風險的因子組合成一句話；無顯著因子時回中性訊息。
    """
    parts = []
    ratio = row.get("expense_income_ratio")
    if pd.notna(ratio) and ratio > 1:
        parts.append(f"收支比 {ratio:.2f}（入不敷出）")
    pen = row.get("penalty_count")
    if pd.notna(pen) and int(pen) > 0:
        parts.append(f"{int(pen)} 次裁罰紀錄")
    mad = row.get("benford_mad")
    if pd.notna(mad) and mad >= 0.015:
        parts.append("班佛定律數字分布異常")
    yoy = row.get("expense_yoy_pct")
    if pd.notna(yoy) and abs(yoy) >= 20:
        parts.append(f"支出年變動 {yoy:.0f}%")
    if not parts:
        return "各項鑑識指標均在常態範圍，未偵測到顯著風險因子。"
    head = "、".join(parts[:2])
    tail = f"（另有 {len(parts) - 2} 項）" if len(parts) > 2 else ""
    return f"主要風險訊號：{head}{tail}。"


def status_pill(status_key, label):
    """當前案件狀態徽章（依狀態語意色即時配色）。"""
    fg, bg, bd = RISK.get(status_key, RISK["medium"])
    return (f"<span class='sw-statuspill' style='background:{bg};color:{fg};"
            f"border-color:{bd};'><span class='dot' style='background:{fg};'></span>"
            f"{html.escape(str(label))}</span>")


def status_banner(record):
    """當前案件狀態大橫幅（決策條上方）：一眼看出目前狀態，狀態變更後顏色即變。

    record：case_status.CaseRecord。已結案者以較飽和的語意色底強調，並附
    「最後更新」時間與操作者，讓「案子到哪了」清楚可見。
    """
    risk_key = record.status_risk_key()
    label = record.status_label()
    fg, bg, bd = RISK.get(risk_key, RISK["medium"])
    is_closed = record.status in {"closed_confirmed", "closed_dismissed"}
    meta = ""
    if record.updated_at:
        who = f"　·　{html.escape(record.actor)}" if record.actor else ""
        meta = (f"<div style='color:{INK_MUTED};font-size:.76rem;margin-top:2px;'>"
                f"最後更新 {html.escape(record.updated_at)}{who}</div>")
    tag = "已結案" if is_closed else "處理中"
    tag_color = fg if is_closed else INK_MUTED
    # 重要：組成「單行、無前導縮排」的 HTML 再輸出。Streamlit 的 Markdown 解析器
    # 會把縮排 ≥4 空白的行當成程式碼區塊，導致 HTML 標籤（如 </div>）以純文字漏出。
    banner = (
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"gap:16px;flex-wrap:wrap;background:{bg};border:1px solid {bd};"
        f"border-left:5px solid {fg};border-radius:8px;padding:14px 20px;"
        f"margin:6px 0 10px;'>"
        f"<div style='display:flex;align-items:center;gap:14px;'>"
        f"<span style='width:12px;height:12px;border-radius:50%;background:{fg};"
        f"flex:0 0 12px;'></span>"
        f"<div>"
        f"<div style='color:{INK_MUTED};font-size:.72rem;font-weight:600;"
        f"letter-spacing:.08em;'>目前案件狀態</div>"
        f"<div style='color:{fg};font-size:1.35rem;font-weight:700;line-height:1.2;"
        f"margin-top:2px;'>{html.escape(label)}</div>"
        f"{meta}"
        f"</div></div>"
        f"<div style='color:{tag_color};font-size:.8rem;font-weight:700;"
        f"border:1px solid {tag_color}55;border-radius:999px;padding:4px 14px;'>{tag}</div>"
        f"</div>"
    )
    st.markdown(banner, unsafe_allow_html=True)


def decision_bar(row, record, decisions):
    """
    互動式稽查決策條（行動優先）：一句話結論 + 當前狀態徽章 + 決策按鈕列。

    放在案件標頭正下方，讓稽查官「先做決定、證據往下支撐」。
    本函式只負責渲染上半部（結論 + 狀態）與按鈕容器的 CSS scope；決策按鈕
    本身由頁面用 st.columns + st.button 呈現（才能接 session 與持久化）。

    參數：
      row：機構資料列。
      record：case_status.CaseRecord（目前狀態）。
      decisions：要顯示的決策標籤序列（供頁面產生按鈕，此處僅用於註記）。
    回傳：一句話結論字串（頁面可重用）。
    """
    verdict = _one_line_verdict(row)
    pill = status_pill(record.status_risk_key(), record.status_label())
    updated = (f"　·　最後更新 {html.escape(record.updated_at)}"
               if record.updated_at else "")
    st.markdown(
        f"""
        <div class='sw-decisionbar'>
          <div class='sw-db-verdict'>
            <div class='sw-db-eyebrow'>{icon('ai', 14, INK_MUTED)} AI 研判摘要</div>
            <div class='sw-db-headline'>{html.escape(verdict)}</div>
            <div class='sw-db-sub'>目前狀態：{pill}{updated}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return verdict


def risk_factors(row):
    """
    風險因子清單（AI Decision Support 核心）：編號因子 → 可追溯證據數值。
    誠實地由現有指標推導，不造假。回傳因子數。
    """
    factors = []
    ratio = row.get("expense_income_ratio")
    if pd.notna(ratio) and ratio > 1:
        factors.append(("收支結構失衡",
                        f"支出為收入的 {ratio:.2f} 倍，呈現入不敷出",
                        f"收支比 = {ratio:.3f}"))
    yoy = row.get("expense_yoy_pct")
    if pd.notna(yoy) and abs(yoy) >= 20:
        factors.append(("年度支出波動異常",
                        f"支出較前一年度變動 {yoy:.0f}%，偏離常態",
                        f"支出年增率 = {yoy:.1f}%"))
    mad = row.get("benford_mad")
    if pd.notna(mad) and mad >= 0.015:
        factors.append(("數字分布異常（班佛定律）",
                        "首位數分布偏離自然律，具人為調整嫌疑",
                        f"班佛偏離度 MAD = {mad:.5f}"))
    beneish = row.get("beneish_score")
    if pd.notna(beneish) and beneish >= 40:
        factors.append(("盈餘操縱訊號（Beneish）",
                        "收支成長背離或應計項目異常",
                        f"Beneish 操縱分 = {beneish:.1f}"))
    iforest = row.get("iforest_score")
    if pd.notna(iforest) and iforest >= 60:
        factors.append(("多維財務異常（孤立森林）",
                        "多項財務特徵綜合判定為離群",
                        f"孤立森林異常分 = {iforest:.1f}"))
    pen = row.get("penalty_count")
    if pd.notna(pen) and int(pen) > 0:
        factors.append(("既有裁罰紀錄",
                        f"已有 {int(pen)} 次裁罰，屬已知風險標的",
                        f"裁罰次數 = {int(pen)}"))

    if not factors:
        empty_state("未偵測到顯著風險因子",
                    "各項鑑識指標均在常態範圍，維持常態管理即可。", "check")
        return 0

    html_rows = ""
    for i, (name, why, evidence) in enumerate(factors, start=1):
        border_top = f"border-top:1px solid {BORDER};" if i > 1 else ""
        html_rows += (
            f"<div style='display:flex;align-items:center;justify-content:space-between;"
            f"gap:20px;padding:15px 0;{border_top}'>"
            f"<div style='display:flex;align-items:flex-start;gap:14px;flex:1;'>"
            f"<div style='flex:0 0 28px;height:28px;border-radius:6px;background:{SURFACE_SUNK};"
            f"color:{INK_2};font-weight:700;font-size:.82rem;display:flex;align-items:center;"
            f"justify-content:center;margin-top:1px;'>{i:02d}</div>"
            f"<div>"
            f"<div style='font-weight:600;color:{INK};font-size:.92rem;'>{html.escape(name)}</div>"
            f"<div style='color:{INK_2};font-size:.84rem;margin-top:2px;line-height:1.5;'>{html.escape(why)}</div>"
            f"</div></div>"
            f"<div style='flex:0 0 auto;background:{SURFACE_ALT};border:1px solid {BORDER};"
            f"border-radius:20px;padding:6px 14px;color:{INK};font-size:.82rem;"
            f"display:flex;align-items:center;gap:6px;font-variant-numeric:tabular-nums;'>"
            f"<span style='color:{PRIMARY};font-weight:700;'>✓</span> 證據：{html.escape(evidence)}</div>"
            f"</div>"
        )
    st.markdown(f"<div class='sw-panel' style='padding:4px 20px;'>{html_rows}</div>",
                unsafe_allow_html=True)
    return len(factors)


_DISTRICT_RE = re.compile(r"(?:新北市)?([\u4e00-\u9fff]{1,3}區)")


def _fill_district(df):
    """補齊缺漏的行政區，避免表格/圖表出現 nan。

    多數列的 district 已由資料管線填妥；少數（如國小附設幼兒園、部分非營利園）
    在 latest 檔缺值。依序以下列來源回填，全程可解釋、不臆造：
      1. 全市名冊 kindergartens_roster.csv（依 park_id 對應官方行政區）。
      2. 機構名稱中內含的「XX區」字樣（如「新北市板橋區板橋國小附幼」→ 板橋區）。
    仍無法判定者填「未分類」，讓畫面明確而非顯示 nan。
    """
    if "district" not in df.columns:
        return df
    df = df.copy()

    roster = load_roster()
    if roster is not None and "park_id" in df.columns and "park_id" in roster.columns:
        ref = (roster.dropna(subset=["district"])
               .drop_duplicates("park_id")
               .set_index("park_id")["district"])
        missing = df["district"].isna() | (df["district"].astype(str).str.strip() == "")
        df.loc[missing, "district"] = df.loc[missing, "park_id"].map(ref)

    def _from_name(row):
        if pd.notna(row["district"]) and str(row["district"]).strip():
            return row["district"]
        m = _DISTRICT_RE.search(str(row.get("park_name", "")))
        return m.group(1) if m else "未分類"

    df["district"] = df.apply(_from_name, axis=1)
    return df


def require_data():
    df = load_latest()
    if df is None or len(df) == 0:
        st.error("找不到資料檔 data/processed/kindergartens_latest.csv。")
        st.info(
            "請先產生資料：\n\n"
            "- 用假資料開發：python scripts/make_mock_data.py\n"
            "- 或由風險引擎產出真資料：python -m src.risk_score"
        )
        st.stop()
    return _fill_district(df)


# ===========================================================================
# 主動預警面板（Proactive Alert）— 事前主動示警
# ===========================================================================
@st.cache_data(show_spinner=False, ttl=600)
def live_dataset_cached(city="新北市", timeout=25):
    """帶 10 分鐘 TTL 快取的動態資料串接（供「進頁自動抓」使用）。

    以 @st.cache_data 包住 src.live_source.load_live_dataset：
      - 同一 session 內 10 分鐘只實際連外抓一次 → 進頁自動顯示即時數字、
        又不會每次 rerun 都重抓拖慢畫面。
      - load_live_dataset 本身已含離線備援（抓失敗退回本地快取，不崩）。
    回傳 (summary_dict | None)。summary 結構與整合中心原本 session 版一致。
    """
    try:
        from src import live_source as _ls
        from src import penalty_match as _pm
    except Exception:
        return None
    try:
        ds = _ls.load_live_dataset(city=city, timeout=timeout)
    except Exception:  # noqa: BLE001 - 抓取任何錯誤都不得中斷頁面
        return None
    if ds is None or not (ds.institutions or ds.penalties):
        return None
    try:
        matches = _pm.match_penalties(ds.penalties, ds.institutions)
        summaries = _pm.summarize_by_institution(matches)
        n_high = sum(1 for m in matches if m.confidence == _pm.HIGH)
        top = sorted(summaries.values(), key=lambda s: s.confirmed_count,
                     reverse=True)[:8]
    except Exception:  # noqa: BLE001
        matches, summaries, n_high, top = [], {}, 0, []
    return {
        "inst": len(ds.institutions),
        "pen": len(ds.penalties),
        "is_live": ds.is_live,
        "inst_at": ds.institutions_status.fetched_at,
        "pen_at": ds.penalties_status.fetched_at,
        "inst_fallback": ds.institutions_status.used_fallback,
        "pen_fallback": ds.penalties_status.used_fallback,
        "inst_err": ds.institutions_status.error,
        "pen_err": ds.penalties_status.error,
        "sample_inst": [
            {"機構名稱": i.park_name, "行政區": i.district,
             "核定人數": i.count_approved, "月費": i.monthly}
            for i in ds.institutions[:8]
        ],
        "sample_pen": [
            {"受處分對象別": p.subject_type, "對象": p.subject,
             "日期": p.date, "處分": p.punishment}
            for p in ds.penalties[:8]
        ],
        "match_total": len(matches),
        "match_high": n_high,
        "match_pending": len(matches) - n_high,
        "match_institutions": len(summaries),
        "match_top": [
            {"機構名稱": s.park_name, "確認裁罰數（高信心）": s.confirmed_count,
             "待人工確認": s.pending_count}
            for s in top if s.confirmed_count > 0
        ],
    }


def _load_alert_module():
    """載入 src.alert（純邏輯預警層）。相容從專案根或測試載入。"""
    try:
        from src import alert as _a  # type: ignore
        return _a
    except Exception:
        import importlib
        import sys as _sys
        if ROOT not in _sys.path:
            _sys.path.insert(0, ROOT)
        return importlib.import_module("src.alert")


def active_alert_panel(df, max_rows=8):
    """政府戰情室「主動示警」面板：以相對門檻自動列出需立即派查／需追蹤的機構。

    對齊題目核心「事前主動示警」：系統不等人工翻報表，主動把落在紅色警報
    （相對最高風險，建議立即派查）與橘色預警（接近門檻的緩衝區，建議主動
    追蹤）的機構推到最前面，每筆附觸發原因與建議行動。門檻採相對基準
    （百分位 + 同儕標準差），任何分數分布下都穩定運作，見 src/alert.py。
    """
    alert = _load_alert_module()
    try:
        alerts = alert.active_alerts(df)
        summary = alert.alert_summary(df)
    except Exception as exc:  # 預警失敗不得中斷主頁其餘內容
        empty_state("主動示警暫時無法產生", f"預警評估發生問題：{html.escape(str(exc))}",
                    icon_name="alert")
        return

    n_crit = summary.get(alert.CRITICAL_ALERT, 0)
    n_watch = summary.get(alert.WATCHLIST, 0)

    st.markdown(
        f"<div style='color:{INK_2};font-size:.86rem;margin:2px 0 12px;'>"
        f"系統依相對風險基準（百分位＋同儕標準差）主動掃描全體機構，"
        f"自動示警 <b style='color:{RISK_BAR['high']};'>{n_crit}</b> 間建議立即派查、"
        f"<b style='color:{RISK_BAR['medium']};'>{n_watch}</b> 間建議納入追蹤。"
        f"此為事前預警：接近門檻者提前示警，不必等惡化跨線才被動發現。</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='color:{FAINT};font-size:.78rem;margin:-6px 0 12px;"
        f"padding-left:10px;border-left:2px solid {BORDER};'>"
        f"定義說明：上方 KPI 卡「高風險機構」採<b>絕對分級</b>（風險分 ≥ 70），"
        f"為固定政策門檻；本區「主動示警」採<b>相對百分位法</b>（同儕分布 + 標準差），"
        f"用於事前預警。兩者定義不同，數字不一致屬預期，非計算錯誤。</div>",
        unsafe_allow_html=True,
    )

    if not alerts:
        empty_state("目前無達預警門檻的機構",
                    "全體機構風險相對平穩，維持例行監測。", icon_name="shield")
        return

    # 「主要觸發原因」與「建議行動」為多字內容，覆寫表格預設的 nowrap／固定列高
    # 讓文字完整換行顯示，不被截斷。
    wrap_td = (
        f"white-space:normal;height:auto;line-height:1.5;"
        f"padding-top:9px;padding-bottom:9px;color:{INK_2};vertical-align:top;"
    )
    rows = ""
    for a in alerts[:max_rows]:
        reason = "；".join(a.reasons) if a.reasons else "綜合風險相對偏高"
        rows += (
            "<tr>"
            f"<td class='l' style='vertical-align:top;'>"
            f"<span style='display:inline-block;width:8px;height:8px;"
            f"border-radius:50%;background:{a.color};margin-right:8px;'></span>"
            f"{html.escape(a.level)}</td>"
            f"<td class='l' style='vertical-align:top;'>{html.escape(str(a.park_name))}</td>"
            f"<td style='vertical-align:top;'>{a.risk_total:.1f}</td>"
            f"<td class='l' style='{wrap_td}min-width:200px;'>{html.escape(reason)}</td>"
            f"<td class='l' style='{wrap_td}min-width:280px;'>"
            f"{html.escape(a.recommended_action)}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>預警等級</th><th class='l'>機構名稱</th><th>風險分</th>"
        "<th class='l'>主要觸發原因</th><th class='l'>建議行動</th>"
        f"</tr></thead><tbody>{rows}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='margin-top:8px;color:{FAINT};font-size:.78rem;'>"
        f"門檻為相對基準（非寫死絕對分數），可規模化：資料每次更新後由排程／"
        f"資料管線重新評估，即構成隨資料自動更新的即時預警系統。</div>",
        unsafe_allow_html=True,
    )


# ===========================================================================
# 工作台待處理面板（Worklist）— 把「報表型示警」改造成「行政工作台」
# ---------------------------------------------------------------------------
# 設計目標（對齊行政作業系統 / Case Management 語彙）：
#   讓行政人員一進首頁想的是「我今天要處理哪幾件事」，而非「好多數據」。
#   頂部呈現「今日待處理 N 件」+ 狀態分頁 chips（全部／待研判／建議派查／
#   調查中）；下方為精簡可操作清單：狀態徽章｜機構｜風險分｜主要原因｜查看。
#   「查看」以 st.page_link 帶 ?park= 跳到既有案件調查頁（1_case.py），
#   不新增任何計算邏輯——純呈現＋既有頁面跳轉。
# ===========================================================================
def worklist_panel(df, max_rows=12):
    """首頁工作台待處理清單（可依狀態 chips 過濾、逐案跳轉查看）。

    狀態來源：case_status（跨頁共用之案件生命週期）。尚未有任何處置動作者
    預設為「待研判（pending）」。清單依風險分由高至低排序（風險高者先處理）。
    """
    from lib import case_status  # 延遲載入，避免頂層循環相依

    records = case_status.load_all()

    def _status_of(eid):
        eid = str(eid)
        return records[eid].status if eid in records else "pending"

    # 組工作清單（含狀態），依風險分高→低（先處理高風險）。
    work = df.copy()
    work["_status"] = work["park_id"].map(_status_of)
    work = work.sort_values("risk_total", ascending=False).reset_index(drop=True)

    # 未結案者才進「待處理」（結案的移出收件匣，但仍可於案件管理查閱）。
    pending_mask = ~work["_status"].isin(list(case_status.CLOSED_STATUSES))
    todo = work[pending_mask]

    n_todo = len(todo)
    n_pending = int((todo["_status"] == "pending").sum())
    n_dispatch = int((todo["_status"] == "dispatch").sum())
    n_investigating = int((todo["_status"] == "investigating").sum())

    # 頂部：今日待處理標題 + 狀態統計。
    st.markdown(
        f"<div style='display:flex;align-items:baseline;gap:12px;margin:2px 0 12px;'>"
        f"<span style='font-size:1.15rem;font-weight:700;color:{INK};'>今日待處理</span>"
        f"<span style='color:{INK_2};font-size:.9rem;'>共 <b style='color:{RISK_BAR['high']};"
        f"font-size:1.05rem;'>{n_todo}</b> 件需要處理</span></div>",
        unsafe_allow_html=True,
    )

    # 狀態分頁 chips（用 pills：既有樣式，選一個過濾清單）。
    chip_opts = [
        f"全部（{n_todo}）",
        f"待研判（{n_pending}）",
        f"建議派查（{n_dispatch}）",
        f"調查中（{n_investigating}）",
    ]
    chip_to_status = {
        chip_opts[0]: None, chip_opts[1]: "pending",
        chip_opts[2]: "dispatch", chip_opts[3]: "investigating",
    }
    sel = st.pills("狀態篩選", chip_opts, selection_mode="single",
                   default=chip_opts[0], label_visibility="collapsed",
                   key="worklist_chip")
    sel_status = chip_to_status.get(sel or chip_opts[0])

    view = todo if sel_status is None else todo[todo["_status"] == sel_status]

    if len(view) == 0:
        empty_state("目前此狀態沒有待處理案件",
                    "切換上方狀態分頁查看其他案件，或前往案件調查頁處理。", "check")
        return

    # 可操作清單：狀態｜機構｜風險｜主要原因｜查看（跳轉案件調查頁）。
    # 用 st.columns 逐列渲染，才能在每列放置可點的 page_link。
    hdr = st.columns([0.9, 2.4, 0.9, 3.0, 0.9])
    for c, t in zip(hdr, ["狀態", "機構名稱", "風險分", "主要風險原因", ""]):
        c.markdown(f"<div style='color:{INK_MUTED};font-size:.72rem;font-weight:600;"
                   f"letter-spacing:.04em;padding-bottom:4px;"
                   f"border-bottom:1px solid {BORDER_STRONG};'>{t}</div>",
                   unsafe_allow_html=True)

    for _, r in view.head(max_rows).iterrows():
        eid = str(r["park_id"])
        status_key = _status_of(eid)
        label, risk_key = case_status.STATUS_META.get(status_key, ("待研判", "medium"))
        fg, bg, bd = RISK.get(risk_key, RISK["medium"])
        reasons = []
        try:
            reasons = _load_alert_module().reasons_for_row(r)
        except Exception:  # noqa: BLE001
            pass
        reason_txt = "；".join(reasons[:2]) if reasons else "綜合風險相對偏高"
        lvl = r["risk_level"]

        cols = st.columns([0.9, 2.4, 0.9, 3.0, 0.9])
        cols[0].markdown(
            f"<div style='padding-top:8px;'><span class='sw-badge' "
            f"style='background:{bg};color:{fg};border-color:{bd};'>{label}</span></div>",
            unsafe_allow_html=True)
        cols[1].markdown(
            f"<div style='padding-top:8px;color:{INK};font-size:.88rem;'>"
            f"{html.escape(str(r['park_name']))}</div>"
            f"<div style='color:{INK_MUTED};font-size:.74rem;'>"
            f"{html.escape(str(r.get('district') or '—'))}</div>",
            unsafe_allow_html=True)
        cols[2].markdown(
            f"<div style='padding-top:8px;font-weight:700;color:{level_color(lvl)};"
            f"font-variant-numeric:tabular-nums;'>{r['risk_total']:.1f}</div>",
            unsafe_allow_html=True)
        cols[3].markdown(
            f"<div style='padding-top:8px;color:{INK_2};font-size:.82rem;line-height:1.5;'>"
            f"{html.escape(reason_txt)}</div>",
            unsafe_allow_html=True)
        with cols[4]:
            st.markdown("<div style='padding-top:4px;'></div>", unsafe_allow_html=True)
            try:
                st.page_link("pages/1_case.py", label="查看 →",
                             query_params={"park": str(r["park_name"])})
            except TypeError:
                # 舊版 Streamlit page_link 無 query_params 參數時的退化：
                # 仍提供連結但不帶參數（使用者可在案件頁自行選案件）。
                try:
                    st.page_link("pages/1_case.py", label="查看 →")
                except Exception:  # noqa: BLE001
                    pass
            except Exception:  # noqa: BLE001
                pass
        st.markdown(
            f"<div style='height:1px;background:{LINE_SOFT};margin:2px 0;'></div>",
            unsafe_allow_html=True)

    if len(view) > max_rows:
        st.caption(f"顯示前 {max_rows} 件（風險高者優先）。完整清單見下方「機構風險排名」。")


# ===========================================================================
# 互動式圖表（Plotly）：對齊政府級動態儀表板（hover 詳情 / 堆疊+趨勢雙軸）
# ---------------------------------------------------------------------------
# 設計原則（對齊 steering 反 AI 生成風）：
#   - 沿用中性石墨骨架 + 五階風險語意色，不用彩色/漸層/發光。
#   - 互動只做「hover 顯示詳情」與「堆疊分項組成」——政府稽查員每天真的會用的
#     互動，非炫技動畫。
#   - 白色底、細框、tabular 數字、Inter/Noto Sans TC 字體，與既有 CSS 一致。
# ===========================================================================
_PLOTLY_FONT = "Inter, Noto Sans TC, Microsoft JhengHei"


def _plotly_layout(fig, height=300, title=None):
    """套用統一的中性專業版面（透明底、細格線、無圖例外框、自適應卡片）。"""
    has_legend = getattr(fig.layout, "showlegend", None) is not False
    fig.update_layout(
        height=height,
        margin=dict(l=54, r=28, t=44 if (title or has_legend) else 20, b=46),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=_PLOTLY_FONT, size=12, color=INK),
        # title 永遠給 dict（未傳時 text=""）：避免部分 Plotly/Streamlit 版本把
        # title=None 渲染成字面 "undefined"（曾出現在全市趨勢圖左上角）。
        title=dict(text=title or "", font=dict(size=13, color=INK)),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=BORDER,
                        font=dict(family=_PLOTLY_FONT, size=12, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                    font=dict(size=11, color=INK_2)),
    )
    fig.update_xaxes(gridcolor=SURFACE_SUNK, linecolor=BORDER, zeroline=False,
                     tickfont=dict(size=11, color=INK_MUTED), automargin=True)
    fig.update_yaxes(gridcolor=SURFACE_SUNK, linecolor=BORDER, zeroline=False,
                     tickfont=dict(size=11, color=INK_MUTED), automargin=True)
    return fig


def risk_distribution_interactive(counts_by_level, total):
    """互動式風險分布橫條（hover 顯示間數與占比）。取代靜態 HTML 版。"""
    import plotly.graph_objects as go

    levels = ["高", "中", "低"]
    ns = [int(counts_by_level.get(lv, 0)) for lv in levels]
    pcts = [(n / total * 100) if total else 0 for n in ns]
    colors = [RISK_BAR[LEVEL_TO_RISK[lv]] for lv in levels]

    fig = go.Figure(go.Bar(
        x=ns, y=[f"{lv}風險" for lv in levels], orientation="h",
        marker=dict(color=colors),
        text=[f"{n} 間（{p:.0f}%）" for n, p in zip(ns, pcts)],
        textposition="outside",
        textfont=dict(size=12, color=INK),
        hovertemplate="%{y}：<b>%{x} 間</b>（占 %{customdata:.0f}%）<extra></extra>",
        customdata=pcts,
    ))
    fig.update_layout(showlegend=False)
    _plotly_layout(fig, height=220)
    fig.update_layout(margin=dict(l=54, r=32, t=18, b=38))
    fig.update_xaxes(title=None, range=[0, max(ns) * 1.35 if ns and max(ns) else 1], automargin=True)
    fig.update_yaxes(autorange="reversed", automargin=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def risk_composition_by_district(df, top_n=12):
    """各行政區風險分項堆疊長條（財務/裁罰/評鑑），hover 顯示分項拆解。

    對齊 statedu「堆疊長條表達組成」：每一區一根柱，堆疊三個可解釋分項的
    加權貢獻，稽查員 hover 即見「這一區的高風險是財務還是裁罰造成」。
    """
    import plotly.graph_objects as go

    if "district" not in df.columns:
        empty_state("無行政區資料", "資料未含行政區欄位，無法繪製分區組成。")
        return

    w = {"financial": 0.50, "penalty": 0.34, "eval": 0.16}
    g = df.copy()
    for k, col in (("financial", "score_financial"), ("penalty", "score_penalty"),
                   ("eval", "score_eval")):
        g[f"c_{k}"] = g[col].fillna(0) * w[k]
    agg = (g.groupby("district")[["c_financial", "c_penalty", "c_eval", "risk_total"]]
             .mean().sort_values("risk_total", ascending=False).head(top_n))

    districts = agg.index.tolist()
    parts = [("c_financial", "財務異常", RISK_BAR["high"]),
             ("c_penalty", "裁罰紀錄", RISK_BAR["medium"]),
             ("c_eval", "評鑑結果", RISK_BAR["low"])]

    fig = go.Figure()
    for col, label, color in parts:
        fig.add_trace(go.Bar(
            x=districts, y=agg[col], name=label, marker=dict(color=color),
            hovertemplate=f"%{{x}}｜{label}貢獻：<b>%{{y:.1f}}</b> 分<extra></extra>",
        ))
    fig.update_layout(barmode="stack")
    _plotly_layout(fig, height=320)
    fig.update_layout(margin=dict(l=54, r=28, t=44, b=48))
    fig.update_yaxes(title="平均風險分（分項貢獻堆疊）", automargin=True)
    fig.update_xaxes(automargin=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def risk_trend_chart(full_df, park_name):
    """單一機構歷年趨勢：分項堆疊長條 + 總分折線雙軸（對齊 statedu 雙軸樣式）。

    hover 顯示該年的分項拆解與總分，讓稽查員看見「哪一年惡化、由哪個分項推升」。
    full_df：多年度全量資料（每園每年一列）；park_name：目標機構。
    """
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    if full_df is None or "year" not in full_df.columns:
        empty_state("無多年度資料", "此機構缺跨年度資料，無法繪製歷年趨勢。")
        return
    sub = (full_df[full_df["park_name"] == park_name]
           .sort_values("year")) if "park_name" in full_df.columns else None
    if sub is None or len(sub) < 2:
        empty_state("跨年度資料不足", "此機構可取得年度少於 2 年，暫不繪製趨勢。")
        return

    years = [f"{int(y)}" for y in sub["year"]]
    w = {"financial": 0.50, "penalty": 0.34, "eval": 0.16}
    parts = [("score_financial", "財務異常", RISK_BAR["high"], w["financial"]),
             ("score_penalty", "裁罰紀錄", RISK_BAR["medium"], w["penalty"]),
             ("score_eval", "評鑑結果", RISK_BAR["low"], w["eval"])]

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    for col, label, color, weight in parts:
        vals = (sub[col].fillna(0) * weight) if col in sub.columns else [0] * len(sub)
        fig.add_trace(go.Bar(
            x=years, y=vals, name=label, marker=dict(color=color),
            hovertemplate=f"%{{x}} 學年｜{label}貢獻 <b>%{{y:.1f}}</b><extra></extra>",
        ), secondary_y=False)
    if "risk_total" in sub.columns:
        fig.add_trace(go.Scatter(
            x=years, y=sub["risk_total"], name="總風險分", mode="lines+markers",
            line=dict(color=INK, width=2.5), marker=dict(size=8, color=INK),
            hovertemplate="%{x} 學年｜總風險分 <b>%{y:.1f}</b><extra></extra>",
        ), secondary_y=True)
    fig.update_layout(barmode="stack")
    _plotly_layout(fig, height=340)
    fig.update_layout(margin=dict(l=54, r=54, t=44, b=48))
    fig.update_yaxes(title="分項貢獻", secondary_y=False, automargin=True)
    fig.update_yaxes(title="總風險分", secondary_y=True, range=[0, 100], automargin=True)
    fig.update_xaxes(automargin=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def validation_panel(df):
    """模型鑑別力驗證面板（回應評審「模型準不準／權重為何」）。

    以官方裁罰紀錄為高風險標籤，實證比較「系統判定高風險分組 vs 對照組」的
    裁罰率與平均裁罰次數，並呈現風險分數與裁罰的關聯係數。這張圖直接回答：
      - 分數準不準？（高分組裁罰率是否顯著高於對照組）
      - 裁罰權重為何合理？（權重反映裁罰與高風險的實際關聯強度，非主觀設定）

    誠實揭露：抽樣示範、裁罰為弱標籤、風險不等於違法（皆由 validation 模組附帶）。
    """
    import plotly.graph_objects as go

    try:
        from src.validation import validate_against_penalties
    except Exception:
        empty_state("驗證模組不可用", "無法載入 src/validation.py。")
        return

    result = validate_against_penalties(df)

    if result.n_penalized == 0:
        empty_state(
            "尚無官方裁罰標籤可供驗證",
            "目前抽樣中無任何園具官方裁罰紀錄；接入全國教保資訊網官方全量裁罰"
            "資料後，此處將自動產出「高分園是否較常被裁罰」的驗證結果。",
            icon_name="check",
        )
        return

    # ---- 指標帶：lift / 相關係數 / 兩組裁罰率 ----
    lift_txt = f"{result.lift}×" if result.lift is not None else "對照組無裁罰"
    r_txt = f"{result.point_biserial_r}" if result.point_biserial_r is not None else "—"
    kpi_band([
        ("高分組裁罰率", f"{result.high.penalty_rate_pct}%", True,
         f"高風險分組 {result.high.n} 間"),
        ("對照組裁罰率", f"{result.control.penalty_rate_pct}%", False,
         f"中／低風險 {result.control.n} 間"),
        ("裁罰率提升倍數", lift_txt, False, "高分組 ÷ 對照組"),
        ("分數—裁罰關聯 r", r_txt, False, "點二系列相關（越接近 1 越一致）"),
    ])

    # ---- 對比長條：兩組裁罰率 ----
    groups = [result.high.label, result.control.label]
    rates = [result.high.penalty_rate_pct, result.control.penalty_rate_pct]
    colors = [RISK_BAR["high"], RISK_BAR["low"]]
    fig = go.Figure(go.Bar(
        x=groups, y=rates, marker=dict(color=colors),
        text=[f"{v}%" for v in rates], textposition="outside",
        textfont=dict(size=13, color=INK),
        hovertemplate="%{x}<br>官方裁罰率 <b>%{y}%</b><extra></extra>",
    ))
    fig.update_layout(showlegend=False)
    _plotly_layout(fig, height=280,
                   title="系統判定高風險分組 vs 對照組：官方裁罰率對比")
    fig.update_layout(margin=dict(l=54, r=32, t=44, b=46))
    fig.update_yaxes(title="曾被官方裁罰的園占比 (%)",
                     range=[0, max(rates) * 1.3 if max(rates) else 1], automargin=True)
    fig.update_xaxes(automargin=True)
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # ---- 結論與權重依據 ----
    st.markdown(
        f"<div class='sw-scorecard'>"
        f"<div style='font-weight:600;color:{INK};margin-bottom:6px;'>結論</div>"
        f"<div style='color:{INK};line-height:1.9;font-size:.92rem;'>"
        f"{result.interpretation}</div>"
        f"<div style='font-weight:600;color:{INK};margin:12px 0 6px;'>"
        f"裁罰權重的實證依據</div>"
        f"<div style='color:{INK_2};line-height:1.9;font-size:.9rem;'>"
        f"{result.weight_justification}</div>"
        f"<div style='color:{INK_MUTED};font-size:.78rem;margin-top:12px;"
        f"border-top:1px solid {LINE_SOFT};padding-top:8px;'>"
        f"{result.not_illegality_notice}</div></div>",
        unsafe_allow_html=True,
    )
