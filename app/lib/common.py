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
    ("5_action",   "稽查行動",     "alert",     "pages/5_action.py"),
    ("6_forensic", "鑑識分析",     "case",      "pages/6_forensic.py"),
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
    .block-container {{ padding:var(--s5) var(--page-px) var(--s8); max-width:var(--page-max); }}
    /* Streamlit 垂直堆疊間距統一（元件間距）*/
    [data-testid="stVerticalBlock"] {{ gap:var(--comp-gap); }}

    #MainMenu, footer {{ visibility:hidden; }}
    [data-testid="stDecoration"] {{ display:none; }}
    [data-testid="stHeader"] {{ background:transparent; }}
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
    [data-testid="stSidebarNav"] {{ display:none; }}
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
      border-bottom:1px solid var(--border); padding-bottom:var(--s4); margin-bottom:var(--s6); gap:var(--s4); }}
    .sw-crumb {{ color:var(--muted); font-size:.74rem; letter-spacing:.04em; margin-bottom:6px; }}
    .sw-crumb b {{ color:var(--ink2); font-weight:500; }}
    .sw-ptitle {{ font-size:1.4rem; font-weight:700; color:var(--ink); line-height:1.25; }}
    .sw-psub {{ color:var(--muted); font-size:.82rem; margin-top:5px; line-height:1.4; }}
    .sw-meta {{ text-align:right; color:var(--muted); font-size:.72rem; line-height:1.8; white-space:nowrap; }}
    .sw-meta b {{ color:var(--ink2); font-weight:600; font-variant-numeric:tabular-nums; }}

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
    try:
        for frame in inspect.stack():
            fn = os.path.basename(frame.filename)
            for key, _disp, _ic, _page in NAV:
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
    側欄 = 品牌區 + 導覽 + System Status footer。
    導覽使用 Streamlit 原生 st.page_link()（單一導覽來源），
    由 Streamlit 內建 router 處理頁面切換，路徑保證與 page registry 一致，
    故不會出現 "Page not found"。視覺以 CSS（.sw-nav-native）貼齊原設計。
    每個 icon 以獨立 class 呈現（純 CSS mask），不動元件內部結構。
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

    # --- 2) 導覽（Streamlit 原生 page_link，單一來源）---
    with st.sidebar.container():
        for key, disp, ic, page in NAV:
            # label 前置一個對應 icon 的字元標記，交由 CSS 依 key 疊上線性 SVG。
            st.page_link(page, label=disp, icon=_NAV_EMOJI.get(key, "•"))

    # --- 3) System Status footer（HTML）---
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
    "主頁": "▪", "5_action": "▪", "6_forensic": "▪",
    "1_case": "▪", "2_map": "▪", "3_ai": "▪", "4_sentiment": "▪",
}


def setup_page(page_title, header_title, subtitle=None, layout="wide",
               module=None, crumb=None):
    """
    頁面初始化：set_page_config + 注入設計系統 + 品牌側欄 + Header/Breadcrumb。
    向後相容舊簽名（page_title/header_title/subtitle/layout）。
    module：麵包屑最後一節（預設用 header_title）。
    """
    st.set_page_config(page_title=page_title, page_icon=None, layout=layout,
                       initial_sidebar_state="auto")
    st.markdown(_css(), unsafe_allow_html=True)
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
    # 交叉指標關係因子（鑑識會計核心）
    if row.get("cross_unit_income_outlier"):
        ipc = row.get("income_per_child")
        z = row.get("income_per_child_z")
        ipc_txt = f"{float(ipc):,.0f} 元" if pd.notna(ipc) else "—"
        z_txt = f"{float(z):+.1f}σ" if pd.notna(z) else "—"
        factors.append(("單位幼兒收入偏離同儕",
                        "每生收入顯著高於同類型同儕，金流結構值得查核",
                        f"每生收入 = {ipc_txt}；偏離同儕 {z_txt}"))
    if row.get("cross_rev_exp_divergence"):
        gap = row.get("rev_exp_growth_gap")
        gap_txt = f"{float(gap):+.1f}" if pd.notna(gap) else "—"
        factors.append(("收入-支出成長背離",
                        "收入與支出的年度成長幅度明顯不同步，收支結構可能突變",
                        f"收入年增 − 支出年增 = {gap_txt} 個百分點"))

    pen = row.get("penalty_count")
    if pd.notna(pen) and int(pen) > 0:
        pcat = row.get("penalty_category")
        preason = row.get("penalty_reason")
        cat_txt = f"（{pcat}風險）" if isinstance(pcat, str) and pcat else ""
        why = f"已有 {int(pen)} 次裁罰{cat_txt}，屬已知風險標的"
        evidence = f"裁罰次數 = {int(pen)}"
        if isinstance(preason, str) and preason:
            evidence += f"；事由：{preason}"
        factors.append((f"既有裁罰紀錄{cat_txt}", why, evidence))

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
# 進階共用元件（12 項政府視角功能共用）
# 只負責呈現與純資料整形，計算仍在既有欄位上做，維持白盒子可解釋。
# ===========================================================================

# ---- 鑑識會計「紅旗」規則（單一定義來源，供紅旗清單／派工清單／稽查報告共用）----
# 每條規則：(代碼, 名稱, 判定函式(row)->bool, 說明函式(row)->str, 合理區間字串)
def _rf_ratio(r):
    v = r.get("expense_income_ratio")
    return pd.notna(v) and float(v) > 1.0


def _rf_benford(r):
    v = r.get("benford_mad")
    return pd.notna(v) and float(v) >= 0.015


def _rf_beneish(r):
    v = r.get("beneish_score")
    return pd.notna(v) and float(v) >= 40


def _rf_iforest(r):
    v = r.get("iforest_score")
    return pd.notna(v) and float(v) >= 60


def _rf_yoy(r):
    v = r.get("expense_yoy_pct")
    return pd.notna(v) and abs(float(v)) >= 20


def _rf_penalty(r):
    v = r.get("penalty_count")
    return pd.notna(v) and int(v) > 0


def _rf_unit_income(r):
    # 單位幼兒收入顯著偏離同儕（交叉指標關係規則）
    return bool(r.get("cross_unit_income_outlier"))


def _rf_rev_exp(r):
    # 收入-支出成長背離（交叉指標關係規則）
    return bool(r.get("cross_rev_exp_divergence"))


RED_FLAGS = [
    ("F1", "收支結構失衡",
     _rf_ratio,
     lambda r: f"支出為收入 {float(r['expense_income_ratio']):.2f} 倍",
     "收支比 ≤ 1.00"),
    ("F2", "數字分布異常（班佛定律）",
     _rf_benford,
     lambda r: f"首位數偏離度 MAD = {float(r['benford_mad']):.4f}",
     "MAD < 0.015"),
    ("F3", "盈餘操縱訊號（Beneish）",
     _rf_beneish,
     lambda r: f"Beneish 操縱分 = {float(r['beneish_score']):.1f}",
     "Beneish < 40"),
    ("F4", "多維財務離群（孤立森林）",
     _rf_iforest,
     lambda r: f"孤立森林異常分 = {float(r['iforest_score']):.1f}",
     "iForest < 60"),
    ("F5", "年度支出劇烈波動",
     _rf_yoy,
     lambda r: f"支出年增率 = {float(r['expense_yoy_pct']):.1f}%",
     "|年增率| < 20%"),
    ("F6", "既有裁罰紀錄",
     _rf_penalty,
     lambda r: f"裁罰次數 = {int(r['penalty_count'])}",
     "裁罰次數 = 0"),
    ("F7", "單位幼兒收入偏離同儕",
     _rf_unit_income,
     lambda r: (f"每生收入 {float(r['income_per_child']):,.0f} 元／偏離同儕 "
                f"{float(r['income_per_child_z']):+.1f}σ"),
     "同儕 ±1.5σ 內"),
    ("F8", "收入-支出成長背離",
     _rf_rev_exp,
     lambda r: f"收入年增 − 支出年增 = {float(r['rev_exp_growth_gap']):+.1f} 個百分點",
     "背離 < 25 個百分點"),
]


def red_flags_for(row):
    """回傳該機構觸發的紅旗清單 [(code, name, detail, normal_range, triggered_bool), ...]，含未觸發的。"""
    out = []
    for code, name, test, detail_fn, normal in RED_FLAGS:
        try:
            hit = bool(test(row))
        except Exception:
            hit = False
        detail = ""
        if hit:
            try:
                detail = detail_fn(row)
            except Exception:
                detail = ""
        out.append((code, name, detail, normal, hit))
    return out


def red_flag_count(row):
    return sum(1 for *_r, hit in red_flags_for(row) if hit)


def red_flag_checklist(row):
    """紅旗檢核清單（白盒子）：逐條列出觸發／正常 + 數值 + 合理區間。"""
    rows_html = ""
    for code, name, detail, normal, hit in red_flags_for(row):
        if hit:
            mark = (f"<span class='sw-badge' style='background:{RISK['high'][1]};"
                    f"color:{RISK['high'][0]};border-color:{RISK['high'][2]};'>觸發</span>")
            detail_txt = html.escape(detail)
        else:
            mark = (f"<span class='sw-badge' style='background:{RISK['normal'][1]};"
                    f"color:{RISK['normal'][0]};border-color:{RISK['normal'][2]};'>正常</span>")
            detail_txt = "<span class='sw-na'>—</span>"
        rows_html += (
            "<tr>"
            f"<td class='l sw-rank'>{code}</td>"
            f"<td class='l'>{html.escape(name)}</td>"
            f"<td class='l'>{mark}</td>"
            f"<td class='l'>{detail_txt}</td>"
            f"<td class='l' style='color:{INK_MUTED};'>{html.escape(normal)}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>代碼</th><th class='l'>鑑識規則</th><th class='l'>判定</th>"
        "<th class='l'>實際數值</th><th class='l'>合理區間</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )


# ---- 同儕比較（Peer Benchmarking）----
def peer_compare(df, row, metrics=None):
    """
    與「同類型（公校/非營利）」同儕比較各財務比率，標出偏離幾個標準差。
    metrics: [(col, label, higher_is_worse_bool, fmt), ...]
    """
    if metrics is None:
        metrics = [
            ("income_per_child", "每生單位收入", True, lambda v: f"{v:,.0f}"),
            ("expense_income_ratio", "收支比", True, lambda v: f"{v:.3f}"),
            ("benford_mad", "班佛偏離度", True, lambda v: f"{v:.4f}"),
            ("beneish_score", "Beneish 操縱分", True, lambda v: f"{v:.1f}"),
            ("iforest_score", "孤立森林異常分", True, lambda v: f"{v:.1f}"),
            ("score_financial", "財務異常分", True, lambda v: f"{v:.1f}"),
        ]
    peers = df[df["park_type"] == row["park_type"]]
    rows_html = ""
    for col, label, worse_high, fmt in metrics:
        if col not in df.columns:
            continue
        series = pd.to_numeric(peers[col], errors="coerce").dropna()
        v = row.get(col)
        if pd.isna(v) or len(series) < 3:
            continue
        v = float(v)
        med = float(series.median())
        std = float(series.std(ddof=0)) or 1e-9
        z = (v - med) / std
        # 偏離方向的風險語意
        deviated_worse = (z >= 1) if worse_high else (z <= -1)
        c = RISK["high"][0] if deviated_worse else INK_2
        # z 條（以 med 為中心，±3σ 映射到 0-100%）
        pct = max(0, min((z + 3) / 6 * 100, 100))
        bar_c = RISK_BAR["high"] if deviated_worse else PRIMARY
        z_txt = f"{z:+.1f}σ"
        rows_html += (
            "<tr>"
            f"<td class='l'>{html.escape(label)}</td>"
            f"<td style='color:{c};font-weight:600;'>{fmt(v)}</td>"
            f"<td>{fmt(med)}</td>"
            "<td>"
            "<span class='sw-bar-wrap'>"
            f"<span class='sw-bar-num' style='color:{c};'>{z_txt}</span>"
            "<span class='sw-bar-track' style='width:80px;position:relative;'>"
            f"<span style='position:absolute;left:50%;top:0;bottom:0;width:1px;background:{BORDER_STRONG};'></span>"
            f"<span class='sw-bar-fill' style='width:{pct:.0f}%;background:{bar_c};'></span>"
            "</span></span>"
            "</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>財務指標</th><th>本機構</th><th>同儕中位數</th>"
        "<th>偏離度（越右偏離越大）</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='margin-top:8px;color:{INK_MUTED};font-size:.8rem;'>"
        f"同儕範圍：{html.escape(str(row['park_type']))}類機構共 {len(peers)} 間。"
        f"偏離度以中位數為中心、標準差為單位（σ）；紅色代表偏離達 1σ 以上且方向偏風險端。</div>",
        unsafe_allow_html=True,
    )


# ---- 風險變化 / 惡化榜（跨年度）----
def build_delta(latest, full):
    """
    計算每間機構「最新年度 vs 前一年度」的總風險分變化。
    回傳 DataFrame: park_name, district, risk_total, prev_total, delta, risk_level。
    無前一年度者 delta 為 NaN。
    """
    if full is None or "risk_total" not in full.columns:
        base = latest.copy()
        base["prev_total"] = pd.NA
        base["delta"] = pd.NA
        return base
    recs = []
    for name, g in full.sort_values("year").groupby("park_name"):
        g = g.dropna(subset=["risk_total"])
        if len(g) == 0:
            continue
        cur = g.iloc[-1]
        prev_total = float(g.iloc[-2]["risk_total"]) if len(g) >= 2 else None
        recs.append({
            "park_name": name,
            "cur_total": float(cur["risk_total"]),
            "prev_total": prev_total,
        })
    dd = pd.DataFrame(recs)
    merged = latest.merge(dd, on="park_name", how="left")
    merged["delta"] = merged["cur_total"] - merged["prev_total"]
    return merged


def deterioration_board(latest, full, n=8):
    """本期惡化榜：風險分較前一年度上升最多的機構（事前主動示警）。"""
    m = build_delta(latest, full)
    worse = m.dropna(subset=["delta"])
    worse = worse[worse["delta"] > 0].sort_values("delta", ascending=False).head(n)
    if len(worse) == 0:
        empty_state("本期無明顯惡化機構", "所有機構風險分較前一年度持平或下降。", "check")
        return
    rows_html = ""
    for _, r in worse.iterrows():
        d = float(r["delta"])
        rows_html += (
            "<tr>"
            f"<td class='l'>{html.escape(str(r['park_name']))}</td>"
            f"<td class='l'>{html.escape(str(r['district']))}</td>"
            f"<td>{float(r['prev_total']):.1f}</td>"
            f"<td>{float(r['cur_total']):.1f}</td>"
            f"<td style='color:{RISK['high'][0]};font-weight:700;'>▲ {d:.1f}</td>"
            f"<td class='l'>{badge(r['risk_level'])}</td>"
            "</tr>"
        )
    st.markdown(
        "<table class='sw-table'><thead><tr>"
        "<th class='l'>機構名稱</th><th class='l'>行政區</th>"
        "<th>前期分</th><th>本期分</th><th>變化</th><th class='l'>現等級</th>"
        f"</tr></thead><tbody>{rows_html}</tbody></table>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div style='margin-top:8px;color:{INK_MUTED};font-size:.8rem;'>"
        "「事前主動示警」核心：變化量比絕對分更具預警意義，"
        "風險快速上升的機構應優先關注即使目前尚未達高風險。</div>",
        unsafe_allow_html=True,
    )


# ---- 裁罰預測驗證（模型可信度：高分園是否確實較常被裁罰）----
def penalty_validation(df, threshold=None):
    """
    以既有裁罰紀錄驗證風險分的鑑別力：
    - 若風險分能鑑別，則「高分組」的裁罰率應顯著高於「低分組」。
    回傳 dict 統計，供頁面畫圖與說明。
    """
    d = df.copy()
    d["has_penalty"] = pd.to_numeric(d["penalty_count"], errors="coerce").fillna(0) > 0
    if threshold is None:
        threshold = float(d["risk_total"].median())
    high = d[d["risk_total"] >= threshold]
    low = d[d["risk_total"] < threshold]
    def rate(x):
        return (x["has_penalty"].mean() * 100) if len(x) else 0.0
    # 混淆矩陣：把「高分」視為模型預測正例、「有裁罰」視為實際正例
    tp = int(((d["risk_total"] >= threshold) & d["has_penalty"]).sum())
    fp = int(((d["risk_total"] >= threshold) & ~d["has_penalty"]).sum())
    fn = int(((d["risk_total"] < threshold) & d["has_penalty"]).sum())
    tn = int(((d["risk_total"] < threshold) & ~d["has_penalty"]).sum())
    precision = tp / (tp + fp) * 100 if (tp + fp) else 0.0
    recall = tp / (tp + fn) * 100 if (tp + fn) else 0.0
    return {
        "threshold": threshold,
        "high_n": len(high), "low_n": len(low),
        "high_rate": rate(high), "low_rate": rate(low),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall,
        "total_penalized": int(d["has_penalty"].sum()),
    }


def confusion_matrix_html(stats):
    """把裁罰驗證的混淆矩陣畫成 2x2 表。"""
    def cell(v, good):
        c = RISK["normal"][0] if good else INK_2
        return f"<td style='text-align:center;font-weight:700;font-size:1.1rem;color:{c};'>{v}</td>"
    return (
        "<table class='sw-table' style='max-width:460px;'>"
        "<thead><tr><th class='l'></th>"
        "<th style='text-align:center;'>實際有裁罰</th>"
        "<th style='text-align:center;'>實際無裁罰</th></tr></thead><tbody>"
        f"<tr><td class='l'>模型判高風險</td>{cell(stats['tp'], True)}{cell(stats['fp'], False)}</tr>"
        f"<tr><td class='l'>模型判低風險</td>{cell(stats['fn'], False)}{cell(stats['tn'], True)}</tr>"
        "</tbody></table>"
    )


# ---- 稽查派工卡（單列，供派工清單使用）----
def dispatch_reason(row):
    """為派工清單產生「為何要查」的白話理由（取觸發紅旗的前幾條）。"""
    flags = []
    for code, name, _d, _n, hit in red_flags_for(row):
        if not hit:
            continue
        # 裁罰紅旗補上主類別，讓「為何要查」更具體（收費/人力/安全…）
        if code == "F6":
            cat = row.get("penalty_category")
            if isinstance(cat, str) and cat:
                name = f"{name}（{cat}風險）"
        flags.append(name)
    if not flags:
        return "綜合風險分偏高，建議一併複核"
    return "、".join(flags[:3])


def audit_focus(row):
    """依觸發紅旗給出建議查核重點。"""
    focus = []
    fset = {c for c, _n, _d, _nr, hit in red_flags_for(row) if hit}
    if "F1" in fset:
        focus.append("支出憑證與採購核銷")
    if "F5" in fset:
        focus.append("人事費與大額支出明細")
    if "F2" in fset or "F3" in fset:
        focus.append("原始帳冊與明細分類帳")
    if "F6" in fset:
        # 依裁罰主類別給出對應查核重點（比「前次裁罰改善情形」更精準）
        focus.append(_penalty_focus(row))
    if "F7" in fset:
        focus.append("收入金流結構與每生收費合理性")
    if "F8" in fset:
        focus.append("收入與支出年度變動原因說明")
    if not focus:
        focus.append("財務報表與收費作業")
    return "、".join(dict.fromkeys(focus))


# 裁罰主類別 → 建議查核重點（與 src/penalty_nlp.py 的 focus 對齊）
_PENALTY_FOCUS_MAP = {
    "安全": "建物公共安全與設施檢查",
    "收費": "收費備查與退費、收據憑證",
    "人力": "教保人員資格與師生比",
    "教保": "教保服務內容與餐點衛生",
    "行政": "文件申報與限期改善情形",
    "未分類": "裁罰事由與改善情形",
}


def _penalty_focus(row):
    """依 penalty_category 欄位給裁罰查核重點；缺欄位時回退到通用說法。"""
    cat = row.get("penalty_category")
    if isinstance(cat, str) and cat in _PENALTY_FOCUS_MAP:
        return _PENALTY_FOCUS_MAP[cat]
    return "前次裁罰改善情形"
