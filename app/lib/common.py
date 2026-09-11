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
import time

import pandas as pd
import streamlit as st

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
      --radius:6px; --radius-sm:4px;
      --page-px:40px;          /* 內容左右 padding（統一 grid 邊界）*/
      --page-max:1280px;       /* 內容最大寬 */
      --section-gap:var(--s6); /* 大區塊間距 32 */
      --sub-gap:var(--s5);     /* 次區塊間距 24 */
      --comp-gap:var(--s4);    /* 元件間距 16 */
      --card-pad:20px;         /* 卡片內距（統一）*/
      --control-h:38px;        /* 表單控制元件高度（統一）*/
      --table-row-h:40px;      /* 表格列高（統一）*/
      --sidebar-w:236px;
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
    /* 導覽項目左右內距對齊、上方留一點呼吸間距 */
    [data-testid="stSidebar"] [data-testid="stPageLink"] {{ margin:0 var(--s2) !important; }}
    /* 第一個導覽項與品牌區分隔線的間距：設為 16px（--s4），
       與 footer（.sw-side-foot）的 padding-top:16px 對稱，
       使「風險總覽上方」= 「輿情分析下方」的空間。 */
    [data-testid="stSidebar"] [data-testid="stPageLink"]:first-of-type {{ margin-top:var(--s4) !important; }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] a,
    [data-testid="stSidebar"] a[data-testid="stPageLink-NavLink"] {{
      display:flex !important; align-items:center; gap:10px; height:38px; padding:0 var(--s3) !important;
      border-radius:var(--radius-sm); color:{SIDEBAR_INK} !important; font-size:.88rem;
      text-decoration:none; margin:0 0 2px 0 !important; border-left:2px solid transparent;
      transition:background .16s ease; background:transparent !important; }}
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
      border:1px solid var(--border); border-radius:var(--radius); background:var(--surface); padding:6px; }}
    .stTabs [data-baseweb="tab-list"] {{ gap:2px; border-bottom:1px solid var(--border); }}
    .stTabs [data-baseweb="tab"] {{ font-size:.88rem; color:var(--ink2); padding:8px 14px; }}
    .stTabs [aria-selected="true"] {{ color:var(--primary) !important; }}
    .stTabs [data-baseweb="tab-highlight"] {{ background:var(--primary); }}

    /* ===== 頁面 Header + Breadcrumb（精準層級）===== */
    .sw-topbar {{ display:flex; align-items:flex-end; justify-content:space-between;
      border-bottom:1px solid var(--border); padding-bottom:var(--s3); margin-bottom:var(--s4); gap:var(--s4); }}
    .sw-crumb {{ color:var(--muted); font-size:.74rem; letter-spacing:.04em; margin-bottom:6px; }}
    .sw-crumb b {{ color:var(--ink2); font-weight:500; }}
    .sw-ptitle {{ font-size:1.4rem; font-weight:700; color:var(--ink); line-height:1.25; }}
    .sw-psub {{ color:var(--muted); font-size:.82rem; margin-top:5px; line-height:1.4; }}
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
      border-radius:var(--radius); overflow:hidden; }}
    .sw-stats .cell {{ flex:1 1 0; min-height:92px; padding:var(--card-pad); background:var(--surface);
      position:relative; display:flex; flex-direction:column; }}
    .sw-stats .cell.accent::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px;
      background:{RISK_BAR['high']}; }}
    .sw-stats .lab {{ color:var(--muted); font-size:.74rem; font-weight:500; letter-spacing:.02em;
      display:flex; align-items:center; gap:6px; min-height:16px; }}
    .sw-stats .val {{ color:var(--ink); font-size:1.7rem; font-weight:700; line-height:1.1; margin-top:auto;
      font-variant-numeric:tabular-nums; }}
    .sw-stats .val.risk {{ color:{RISK['high'][0]}; }}
    .sw-stats .sub {{ color:var(--muted); font-size:.72rem; margin-top:6px; min-height:14px; }}

    /* ===== Section Header：統一元件 ===== */
    .sw-section {{ display:flex; align-items:center; gap:var(--s2); margin:var(--section-gap) 0 var(--comp-gap);
      font-size:.92rem; font-weight:600; color:var(--ink); }}
    .sw-section svg {{ flex:0 0 16px; }}
    .sw-section .ln {{ flex:1; height:1px; background:var(--border); margin-left:2px; }}
    .sw-callout {{ border:1px solid var(--border); border-left:3px solid var(--primary);
      background:var(--surface); border-radius:var(--radius); padding:var(--s3) var(--s4);
      font-size:.86rem; color:var(--ink2); line-height:1.6; }}

    /* ===== 企業資料表：固定列高、細框、tabular ===== */
    .sw-table {{ width:100%; border-collapse:collapse; background:var(--surface);
      border:1px solid var(--border); border-radius:var(--radius); overflow:hidden;
      font-variant-numeric:tabular-nums; table-layout:auto; }}
    .sw-table thead th {{ background:var(--surface-alt); color:var(--muted); font-weight:600;
      font-size:.72rem; letter-spacing:.04em; padding:10px 14px; text-align:right; white-space:nowrap;
      border-bottom:1px solid var(--border-strong); }}
    .sw-table thead th.l {{ text-align:left; }}
    .sw-table tbody td {{ height:var(--table-row-h); padding:0 14px; text-align:right; font-size:.85rem;
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
    .sw-badge {{ display:inline-block; min-width:38px; text-align:center; padding:2px 10px;
      border-radius:var(--radius-sm); font-size:.76rem; font-weight:700; line-height:1.5;
      border:1px solid transparent; }}

    /* 卡片：統一內距，含等高變體 */
    .sw-panel {{ background:var(--surface); border:1px solid var(--border); border-radius:var(--radius);
      padding:var(--card-pad); }}
    .sw-panel.fill {{ height:100%; box-sizing:border-box; }}
    .sw-scorecard {{ background:var(--surface); border:1px solid var(--border); border-left:4px solid var(--primary);
      border-radius:var(--radius); padding:var(--card-pad); margin-bottom:var(--s4); }}

    /* Empty / Loading state */
    .sw-empty {{ border:1px dashed var(--border-strong); border-radius:var(--radius); background:var(--surface-alt);
      padding:var(--s6) var(--s5); text-align:center; color:var(--muted); font-size:.86rem; }}
    .sw-empty .ttl {{ color:var(--ink2); font-weight:600; font-size:.92rem; margin:var(--s2) 0 var(--s1); }}
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
          <div class='tag'>企業級鑑識會計風險情報平台</div>
        </div>
        <div class='sw-nav-native'></div>
        """,
        unsafe_allow_html=True,
    )

    # --- 2) 角色感知導覽（第一層授權）---
    # 未登入 → 不顯示任何導覽項目；已登入 → 只顯示該角色允許的頁面。
    current_role = auth.get_current_role()
    if current_role is not None:
        allowed_keys = set(permissions.get_role_navigation(current_role))
        with st.sidebar.container():
            for key, disp, ic, page in NAV_ALL:
                if key in allowed_keys:
                    st.page_link(page, label=disp, icon=_NAV_EMOJI.get(key, "▪"))

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
    "主頁": "▪", "1_case": "▪", "2_map": "▪", "3_ai": "▪", "4_sentiment": "▪",
    "6_governance": "▪",
}

# 完整導覽清單（公務後台）：在既有 NAV 之上補入案件調查（稽查員）與資料治理
# 權限矩陣（政府），供角色感知導覽依角色過濾。
# 家長信任中心已切分為獨立公眾查詢網（public/公開查詢.py），不再是公務後台頁面。
# 既有 NAV 不變（向後相容其他引用），角色過濾一律以 NAV_ALL 為來源。
NAV_ALL = NAV + [
    ("1_case",       "案件調查",         "case",      "pages/1_case.py"),
    ("6_governance", "資料治理權限矩陣", "shield",    "pages/6_governance.py"),
]
# NAV_ALL 可能因 1_case 已在 NAV（否）而重複；以 key 去重並保留首次出現順序。
_seen_keys = set()
_dedup = []
for _item in NAV_ALL:
    if _item[0] not in _seen_keys:
        _seen_keys.add(_item[0])
        _dedup.append(_item)
NAV_ALL = _dedup


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

    # RBAC 第二層授權：頁面級守衛（在渲染側欄與內容之前）。
    if allowed_roles is not None:
        auth.require_role(allowed_roles)

    _sidebar(_current_page_key())

    crumb_txt = crumb or "Fiscalint"
    module_txt = module or header_title
    sub = f"<div class='sw-psub'>{html.escape(subtitle)}</div>" if subtitle else ""

    # 登出：以查詢參數 ?logout=1 觸發（純 HTML 連結點擊），在此處理並清 session。
    if st.query_params.get("logout") == "1":
        auth.logout()
        try:
            del st.query_params["logout"]
        except Exception:
            st.query_params.clear()
        st.rerun()

    current_role = auth.get_current_role()

    # 帳號膠囊（角色 + 登出）：合併進 header 右側 sw-meta 區塊，成為 header 的一部分，
    # 避免與 header 橫幅成為兩個獨立區塊而重疊。已登入才顯示。
    acct_html = ""
    if current_role is not None:
        user = auth.get_current_user() or {}
        _usvg = (
            "<svg width='14' height='14' viewBox='0 0 24 24' fill='none' "
            f"stroke='{INK_MUTED}' stroke-width='1.7' stroke-linecap='round' "
            "stroke-linejoin='round'><circle cx='12' cy='8' r='4'/>"
            "<path d='M4 21a8 8 0 0 1 16 0'/></svg>"
        )
        acct_html = (
            f"<div class='sw-acctbar'>"
            f"<div class='sw-acct'>{_usvg}"
            f"<span class='sw-acct-role'>{html.escape(user.get('label', ''))}</span></div>"
            f"<a class='sw-acct sw-logout' href='?logout=1' target='_self'>登出</a>"
            f"</div>"
        )

    st.markdown(
        f"""
        <div class='sw-topbar'>
          <div>
            <div class='sw-crumb'>{html.escape(crumb_txt)} &nbsp;/&nbsp; <b>{html.escape(module_txt)}</b></div>
            <div class='sw-ptitle'>{html.escape(header_title)}</div>
            {sub}
          </div>
          <div class='sw-meta'>
            {acct_html}
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
        html_rows += (
            f"<div style='display:flex;gap:14px;padding:12px 0;"
            f"border-top:1px solid {BORDER};'>"
            f"<div style='flex:0 0 26px;height:26px;border-radius:5px;background:{SURFACE_SUNK};"
            f"color:{INK_2};font-weight:700;font-size:.82rem;display:flex;align-items:center;"
            f"justify-content:center;'>{i:02d}</div>"
            f"<div style='flex:1;'>"
            f"<div style='font-weight:600;color:{INK};font-size:.9rem;'>{html.escape(name)}</div>"
            f"<div style='color:{INK_2};font-size:.83rem;margin-top:2px;'>{html.escape(why)}</div>"
            f"<div style='color:{INK_MUTED};font-size:.76rem;margin-top:4px;'>"
            f"{icon('check', 13, INK_MUTED)} 證據：{html.escape(evidence)}</div>"
            f"</div></div>"
        )
    st.markdown(f"<div class='sw-panel' style='padding-top:2px;'>{html_rows}</div>",
                unsafe_allow_html=True)
    return len(factors)


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
    return df


# ===========================================================================
# 主動預警面板（Proactive Alert）— 事前主動示警
# ===========================================================================
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

    if not alerts:
        empty_state("目前無達預警門檻的機構",
                    "全體機構風險相對平穩，維持例行監測。", icon_name="shield")
        return

    rows = ""
    for a in alerts[:max_rows]:
        reason = a.reasons[0] if a.reasons else "綜合風險相對偏高"
        rows += (
            "<tr>"
            f"<td class='l'><span style='display:inline-block;width:8px;height:8px;"
            f"border-radius:50%;background:{a.color};margin-right:8px;'></span>"
            f"{html.escape(a.level)}</td>"
            f"<td class='l'>{html.escape(str(a.park_name))}</td>"
            f"<td>{a.risk_total:.1f}</td>"
            f"<td class='l' style='color:{INK_2};'>{html.escape(reason)}</td>"
            f"<td class='l' style='color:{INK_2};'>{html.escape(a.recommended_action)}</td>"
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
