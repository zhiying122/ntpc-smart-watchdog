"""
教保機構公開資訊查詢網（Public Trust Center）— 獨立公眾入口
============================================================================
小小守護員 Smart Watchdog Platform — 面向一般民眾／家長的**獨立**公眾查詢網。

系統切分（Network Segmentation，政府資安標準做法）：
--------------------------------------------------------------------------
本站與「公務後台（Fiscalint 稽查預警系統，app/主頁.py）」為**兩個完全獨立
的系統**，各自為獨立進入點、獨立執行程序、（生產環境）獨立網域與主機：

  - 公務後台：僅限授權公務人員（SSO / TW FidO），含風險分數、鑑識分析、
    AI 稽查報告、稽查派工等內部資訊。
  - 公眾查詢網（本站）：**無需登入**，只揭露「已去識別化的官方公開資訊」
    （基本資料、公私立別、收費、公開評鑑、公開裁罰），
    **絕不含任何內部風險分數／等級／排序**。

資料流：本站向共用「鑑識風險中台」（src/ 引擎 + data/）取數，但在**資料層**
即透過 permissions.authorize_dataframe(df, ROLE_PARENT) 移除所有風險欄位——
本站程式碼在記憶體中根本拿不到 risk_total，並非前端把分數算出來再隱藏。

責任 AI：風險（risk）不等於違法（illegality）。本站不對任何機構作違法、
舞弊、高風險之評價或標記，僅陳述可回溯官方公開資料之事實。

啟動：streamlit run public/公開查詢.py --server.port 8502
（與公務後台 app/主頁.py 使用不同 port，示範主機／網路隔離。）
"""
import html
import os
import sys
from datetime import date

import pandas as pd
import streamlit as st

# ---------------------------------------------------------------------------
# 路徑：本站可獨立執行，需能載入共用中台（src/）與家長端純邏輯（app/lib）。
# 僅取用「呈現無關的純邏輯」與「資料層去識別化投影」，不引入公務後台的登入/導覽。
# ---------------------------------------------------------------------------
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_LIB = os.path.join(ROOT, "app")
for _p in (ROOT, APP_LIB):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib import parent_portal as pp  # noqa: E402
from lib import permissions  # noqa: E402
from src.models import SourceRef  # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
LATEST_CSV = os.path.join(PROC, "kindergartens_latest.csv")


# ---------------------------------------------------------------------------
# 資料載入（本站獨立，不依賴公務後台的 common.require_data）
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner=False)
def _load_public_data() -> pd.DataFrame | None:
    if not os.path.exists(LATEST_CSV):
        return None
    df = pd.read_csv(LATEST_CSV)
    # 關鍵：資料層去識別化投影——移除所有 risk_*/score_* 等內部欄位。
    # 本站自此拿到的 DataFrame 根本不含 risk_total。
    return permissions.authorize_dataframe(df, permissions.ROLE_PARENT)


def _data_updated_at() -> str:
    if os.path.exists(LATEST_CSV):
        import time
        return time.strftime("%Y-%m-%d %H:%M",
                             time.localtime(os.path.getmtime(LATEST_CSV)))
    return "—"


# ---------------------------------------------------------------------------
# 頁面設定與樣式（公眾網：清爽、可信、無任何風險視覺）
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="教保機構公開資訊查詢網",
    page_icon=None,
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;700&display=swap');
    html, body, [class*="css"], .stApp {
      font-family:'Noto Sans TC','Microsoft JhengHei',sans-serif; color:#26303B; }
    .stApp { background:#F7F8FA; }
    #MainMenu, footer, [data-testid="stDecoration"] { visibility:hidden; }
    [data-testid="stHeader"] { height:0 !important; background:transparent; }
    [data-testid="stSidebar"] { display:none !important; }
    .pub-topbar { color:#5A626D; font-size:.82rem; letter-spacing:.02em;
      margin-bottom:6px; }
    .pub-title { font-size:1.55rem; font-weight:700; color:#16202B; margin:2px 0; }
    .pub-sub { color:#4E5763; font-size:.92rem; line-height:1.7; }
    .pub-note { background:#EAF1F9; border:1px solid #CFE0F1; border-radius:8px;
      padding:12px 16px; color:#33475B; font-size:.84rem; line-height:1.7;
      margin:14px 0 4px; }
    .pub-table { width:100%; border-collapse:collapse; margin-top:8px;
      background:#fff; border:1px solid #D3DCE6; border-radius:8px; overflow:hidden; }
    .pub-table th, .pub-table td { text-align:left; padding:12px 14px;
      border-bottom:1px solid #E6EAF0; font-size:.9rem; vertical-align:top; }
    .pub-table th { background:#F1F4F8; color:#5A626D; font-weight:700;
      font-size:.8rem; letter-spacing:.04em; }
    .pub-table tr:last-child td { border-bottom:none; }
    .pub-label { font-weight:600; white-space:nowrap; color:#1F2733; }
    .pub-na { color:#9AA1AB; }
    .pub-stale { color:#B58A1E; font-weight:600; margin-left:8px; }
    .pub-meta { color:#8A929C; font-size:.76rem; margin-top:4px; }
    .pub-foot { color:#8A929C; font-size:.78rem; margin-top:18px; line-height:1.7; }
    a { color:#2C5D8F; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="pub-topbar">新北市政府教育局　·　公開資料服務</div>
    <div class="pub-title">教保機構公開資訊查詢網</div>
    <div class="pub-sub">提供教保機構之公開透明資訊查詢。本站資料皆取自官方公開資料，
    每一欄位標註來源與最後更新時間。本站不提供任何風險評分或評價。</div>
    """,
    unsafe_allow_html=True,
)

df = _load_public_data()
if df is None or len(df) == 0:
    st.error("目前無可查詢的公開資料。")
    st.stop()

# 二次防禦：斷言本站資料層確實不含任何風險欄位（責任 AI 不變式）。
_leaked = [c for c in df.columns if pp.is_risk_field(c)]
assert not _leaked, f"公眾網不得含風險欄位，發現：{_leaked}"

# ---------------------------------------------------------------------------
# 選機構
# ---------------------------------------------------------------------------
names = sorted(df["park_name"].dropna().unique().tolist())
qp = st.query_params.get("park")
default_idx = names.index(qp) if qp in names else 0
park = st.selectbox("選擇教保機構", names, index=default_idx)

row = df[df["park_name"] == park].iloc[0].to_dict()

# ---------------------------------------------------------------------------
# 組裝官方來源（每欄位附連結與最後更新時間）
# ---------------------------------------------------------------------------
_updated = date.today()
_authority = "新北市政府教育局"
_dataset = "全國教保資訊網 / 新北市幼兒教育資源網（公開資料）"
_url = "https://www.ece.moe.edu.tw/"

field_sources: dict[str, SourceRef] = {
    "basic_info": SourceRef(dataset=_dataset, authority=_authority,
                            url=_url, last_updated=_updated),
    "ownership": SourceRef(dataset=_dataset, authority=_authority,
                           url=_url, last_updated=_updated),
}
if not pd.isna(row.get("eval_grade")) and str(row.get("eval_grade")).strip():
    field_sources["public_eval"] = SourceRef(
        dataset="幼兒園基礎評鑑結果（公開）", authority=_authority,
        url=_url, last_updated=_updated,
    )

# ---------------------------------------------------------------------------
# 收費資訊（方案 A）：以決算實收學費總額呈現，並標清楚語意避免家長誤解。
# 說明：tuition_actual 為「該園該決算年度全園實收學費總額」，非「每名幼兒收費」。
# 直接顯示金額會被誤讀為個人繳費，故明確標註為全園決算總額，並附年度。
# 資料來源：地方教育發展基金決算書（公開）。
# ---------------------------------------------------------------------------
_tuition = row.get("tuition_actual")
if _tuition is not None and not pd.isna(_tuition):
    try:
        _tuition_wan = float(_tuition) / 10000.0
        _year = row.get("year")
        _year_txt = f"{int(_year)} 年度" if _year is not None and not pd.isna(_year) else "最新決算年度"
        row["tuition_info"] = (
            f"{_year_txt}全園實收學費總額約 {_tuition_wan:,.0f} 萬元"
            f"（決算數；非每名幼兒收費，實際各項收退費依主管機關公告與契約為準）"
        )
        field_sources["tuition_info"] = SourceRef(
            dataset="地方教育發展基金決算書（公開）", authority=_authority,
            url=_url, last_updated=_updated,
        )
    except (TypeError, ValueError):
        pass

# ---------------------------------------------------------------------------
# 委由呈現無關模組計算公開檢視與揭露欄位（與公務後台共用同一份純邏輯）
# ---------------------------------------------------------------------------
view = pp.build_public_view(row, field_sources, reference=_updated)
basic_info = {
    "機構名稱": view.park_name or pp.NO_PUBLIC_DATA_LABEL,
    "行政區": row.get("district") or pp.NO_PUBLIC_DATA_LABEL,
}
fields = pp.build_disclosure_fields(view, basic_info=basic_info, reference=_updated)


def _fmt_value(f):
    if not f.has_data:
        return pp.NO_PUBLIC_DATA_LABEL
    v = f.value
    if isinstance(v, dict):
        return "　".join(f"{k}：{val}" for k, val in v.items())
    if isinstance(v, (list, tuple)):
        return "；".join(str(x) for x in v)
    return str(v)


st.markdown(
    "<div class='pub-note'>本頁僅呈現可回溯至官方公開資料之事實，每一欄位皆標註"
    "來源與最後更新時間。本平台不對任何機構作違法、舞弊或高風險之評價。</div>",
    unsafe_allow_html=True,
)

rows_html = []
for f in fields:
    val_txt = html.escape(_fmt_value(f))
    if f.has_data:
        meta_parts = []
        if f.source_url:
            meta_parts.append(
                f"<a href='{html.escape(f.source_url)}' target='_blank' "
                f"rel='noopener'>官方來源</a>")
        if f.source_last_updated:
            meta_parts.append(f"最後更新：{f.source_last_updated.isoformat()}")
        if f.source is not None:
            meta_parts.append(html.escape(f.source.authority))
        meta = "　·　".join(meta_parts)
        stale = ""
        if f.stale_notice:
            stale = f"<span class='pub-stale'>注意：{html.escape(f.stale_notice)}</span>"
        val_cell = f"{val_txt}{stale}<div class='pub-meta'>{meta}</div>"
    else:
        val_cell = f"<span class='pub-na'>{val_txt}</span>"
    rows_html.append(
        f"<tr><td class='pub-label'>{html.escape(f.label)}</td>"
        f"<td>{val_cell}</td></tr>")

st.markdown(
    "<table class='pub-table'><thead><tr>"
    "<th>揭露欄位</th><th>內容 · 官方來源 · 時效</th>"
    "</tr></thead><tbody>" + "".join(rows_html) + "</tbody></table>",
    unsafe_allow_html=True,
)

st.markdown(
    f"""
    <div class="pub-foot">
    資料來源為官方公開資料集；「查無公開資料」表示該欄位目前無對應官方公開來源，
    並非機構有無問題之判斷。本站不呈現任何內部風險分數或等級。<br>
    本站為獨立公眾查詢網，與教育局內部稽查系統採網路與主機隔離。<br>
    資料最後更新：{_data_updated_at()}
    </div>
    """,
    unsafe_allow_html=True,
)
