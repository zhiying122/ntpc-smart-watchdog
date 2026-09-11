"""
A+ RBAC 角色權限架構 —「你是誰」（Mock Authentication + Session + 守衛）
=========================================================================
小小守護員 Smart Watchdog Platform — RBAC 第二層：身分驗證與頁面級守衛。

雙層授權：
  第一層（UI 導覽）：permissions.get_role_navigation — 不該看到的頁面在側欄消失。
  第二層（本模組）：require_role — 即使直接開頁面網址，角色不符也會被資料層擋下。

設計原則：
  - 純邏輯（authenticate / 帳密對映）**不依賴 streamlit**，可離線單元測試。
  - 需要呈現或存取 session 的函式（login / render_login / require_role…）
    才在函式內 import streamlit，避免純邏輯測試需要 Streamlit runtime。
  - 每次登入/登出/守衛觸發皆寫一筆 src.audit 的 AuditLog（append-only）。

Demo credentials only — not production authentication.
（Demo 帳密僅供競賽展示，非機密，刻意寫在程式碼中，不放 .env。）
"""
from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from typing import Iterable


# ---------------------------------------------------------------------------
# 載入既有純邏輯模組（app/lib 非套件；src 為套件）
# ---------------------------------------------------------------------------
def _load_lib_module(mod_name: str):
    """以檔案路徑載入 app/lib/<mod_name>.py（相容 Streamlit import 與測試）。"""
    try:
        from importlib import import_module
        return import_module(f"lib.{mod_name}")
    except Exception:
        pass
    _here = os.path.dirname(os.path.abspath(__file__))
    _path = os.path.join(_here, f"{mod_name}.py")
    _spec = importlib.util.spec_from_file_location(f"app_lib_{mod_name}", _path)
    _mod = importlib.util.module_from_spec(_spec)
    import sys as _sys
    _sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)
    return _mod


permissions = _load_lib_module("permissions")


def _load_audit():
    """載入 src.audit（含 AuditLog）。相容從專案根或測試載入。"""
    try:
        from src import audit as _a  # type: ignore
        return _a
    except Exception:
        pass
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import sys as _sys
    if _root not in _sys.path:
        _sys.path.insert(0, _root)
    from src import audit as _a  # type: ignore
    return _a


# ---------------------------------------------------------------------------
# Demo 帳號（非機密，僅供競賽展示）
# ---------------------------------------------------------------------------
# Demo credentials only — not production authentication.
# 帳號 → (密碼, 角色)。三組固定 Demo 帳號，對應 permissions 的三種角色。
_DEMO_CREDENTIALS: dict[str, tuple[str, str]] = {
    "government_demo": ("gov_demo", permissions.ROLE_GOV),
    "inspector_demo": ("inspect_demo", permissions.ROLE_INSPECTOR),
    "parent_demo": ("parent_demo", permissions.ROLE_PARENT),
}


# ---------------------------------------------------------------------------
# 純邏輯：身分驗證（不依賴 st.session_state，方便單元測試）
# ---------------------------------------------------------------------------
def authenticate(username: str, password: str) -> str | None:
    """驗證帳密，成功回傳角色字串，失敗回傳 None（純邏輯）。

    Demo credentials only — not production authentication.
    """
    if not isinstance(username, str) or not isinstance(password, str):
        return None
    entry = _DEMO_CREDENTIALS.get(username.strip())
    if entry is None:
        return None
    expected_pw, role = entry
    if password == expected_pw:
        return role
    return None


def demo_accounts() -> dict[str, str]:
    """回傳 {帳號: 角色} 對映（不含密碼），供 UI 說明使用。"""
    return {u: r for u, (_pw, r) in _DEMO_CREDENTIALS.items()}


# ---------------------------------------------------------------------------
# Session state 存取（需要 streamlit；在函式內 import）
# ---------------------------------------------------------------------------
_SESSION_ROLE = "auth_role"
_SESSION_USER = "auth_username"
_SESSION_LOGIN_TIME = "auth_login_time"
_SESSION_AUDIT = "auth_audit_log"


def _st():
    import streamlit as st  # 延遲 import：純邏輯測試不需 Streamlit runtime
    return st


def get_audit_log():
    """取得模組級共享的 AuditLog 實例（存在 session_state，跨頁共用）。

    每個瀏覽器 session 一份 append-only 稽核軌跡；登入/登出/守衛皆寫入此處。
    """
    st = _st()
    audit = _load_audit()
    if _SESSION_AUDIT not in st.session_state:
        st.session_state[_SESSION_AUDIT] = audit.AuditLog()
    return st.session_state[_SESSION_AUDIT]


def _audit(actor: str, action: str, target: str) -> None:
    """寫一筆稽核紀錄（容錯：稽核失敗不得中斷登入流程）。"""
    try:
        log = get_audit_log()
        log.log(actor=actor or "anonymous", action=action,
                target=target or "-", ts=datetime.now(timezone.utc))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 登入 / 登出 / 狀態查詢
# ---------------------------------------------------------------------------
def login(role: str, username: str | None = None) -> None:
    """直接以角色登入（快速 Demo 用），寫入 session 並記稽核軌跡。"""
    st = _st()
    uname = username or f"{role}_demo"
    st.session_state[_SESSION_ROLE] = role
    st.session_state[_SESSION_USER] = uname
    st.session_state[_SESSION_LOGIN_TIME] = datetime.now(timezone.utc).isoformat()
    _audit(actor=uname, action="LOGIN", target=role)


def login_with_credentials(username: str, password: str) -> str | None:
    """以帳密登入：成功寫入 session 並回傳角色，失敗回傳 None 並記錄。"""
    role = authenticate(username, password)
    if role is None:
        _audit(actor=username or "unknown", action="LOGIN_FAILED",
               target="invalid_credentials")
        return None
    login(role, username=username.strip())
    return role


def logout() -> None:
    """清除登入 session（記一筆 LOGOUT）。"""
    st = _st()
    uname = st.session_state.get(_SESSION_USER, "anonymous")
    role = st.session_state.get(_SESSION_ROLE, "-")
    for key in (_SESSION_ROLE, _SESSION_USER, _SESSION_LOGIN_TIME):
        if key in st.session_state:
            del st.session_state[key]
    _audit(actor=uname, action="LOGOUT", target=role)


def is_authenticated() -> bool:
    """是否已登入（session 中有有效角色）。"""
    st = _st()
    return st.session_state.get(_SESSION_ROLE) in permissions.VALID_ROLES


def get_current_role() -> str | None:
    """回傳目前登入角色；未登入回傳 None。"""
    st = _st()
    role = st.session_state.get(_SESSION_ROLE)
    return role if role in permissions.VALID_ROLES else None


def get_current_user() -> dict | None:
    """回傳目前登入使用者資訊（role/username/login_time）；未登入回傳 None。"""
    st = _st()
    role = get_current_role()
    if role is None:
        return None
    return {
        "role": role,
        "username": st.session_state.get(_SESSION_USER),
        "login_time": st.session_state.get(_SESSION_LOGIN_TIME),
        "name": permissions.role_name(role),
        "emoji": permissions.role_emoji(role),
        "label": permissions.role_label(role),
    }


# ---------------------------------------------------------------------------
# 守衛：require_login / require_role
# ---------------------------------------------------------------------------
def require_login() -> None:
    """未登入時顯示登入畫面並停止頁面渲染（st.stop）。"""
    st = _st()
    if not is_authenticated():
        render_login()
        st.stop()


def require_role(allowed_roles: Iterable[str]) -> None:
    """頁面級守衛（雙層授權第二層）。

    - 未登入 → 導向登入畫面並 st.stop()。
    - 已登入但角色不在 allowed_roles → 顯示「存取遭拒」友善畫面、記 ACCESS_DENIED
      稽核軌跡並 st.stop()。
    - 通過 → 記一筆 VIEW 稽核軌跡後正常返回。
    """
    st = _st()
    allowed = set(allowed_roles)
    if not is_authenticated():
        render_login()
        st.stop()
        return
    role = get_current_role()
    if role not in allowed:
        user = get_current_user() or {}
        _audit(actor=user.get("username", "unknown"), action="ACCESS_DENIED",
               target=",".join(sorted(allowed)) or "-")
        _render_access_denied(allowed)
        st.stop()
        return
    # 通過守衛：記錄檢視行為。
    user = get_current_user() or {}
    _audit(actor=user.get("username", "unknown"), action="VIEW",
           target=",".join(sorted(allowed)) or "-")


# ---------------------------------------------------------------------------
# 呈現：登入畫面 / 存取遭拒（需要 streamlit）
# ---------------------------------------------------------------------------
def _render_access_denied(allowed: Iterable[str]) -> None:
    """存取遭拒畫面（呼應 modes 的 access denied 精神，不揭露任何風險資訊）。"""
    st = _st()
    user = get_current_user() or {}
    allowed_labels = "、".join(permissions.role_label(r) for r in allowed)
    st.error("存取遭拒：此資訊不在您的資料授權範圍內")
    st.markdown(
        f"""
        <div style="border:1px solid #D8AAA3;background:#F3DEDB;border-radius:6px;
             padding:16px 20px;color:#8C2A22;line-height:1.8;">
          <div style="font-weight:700;font-size:1rem;">存取遭拒（Access Denied）</div>
          <div style="margin-top:6px;color:#5A626D;">
            您目前的角色為 <b>{user.get('label', '未登入')}</b>，
            此頁面僅開放給：<b>{allowed_labels}</b>。<br>
            權限在資料層控管——不屬於您職責範圍的風險資訊，
            系統不會提供，並非前端隱藏。
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("返回並切換角色（登出）"):
        logout()
        st.rerun()


def _login_svg(name: str, size: int = 24, color: str = "#2C5D8F",
               stroke: float = 1.6) -> str:
    """登入畫面用的線性 SVG 圖示（政府/企業級，取代 emoji）。"""
    paths = {
        "shield": "<path d='M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z'/>",
        # 政府：機關建物（列柱 + 山牆）
        "gov": ("<path d='M3 9 12 4l9 5'/><path d='M4 9h16'/>"
                "<path d='M6 9v8M10 9v8M14 9v8M18 9v8'/><path d='M3 21h18'/>"),
        # 稽查：放大鏡（調查）
        "inspect": "<circle cx='11' cy='11' r='6'/><path d='m20 20-3.5-3.5'/>",
        # 家長：兩人（社群/家庭）
        "parent": ("<circle cx='9' cy='8' r='3'/><path d='M3 20a6 6 0 0 1 12 0'/>"
                   "<path d='M16 6a3 3 0 0 1 0 6'/><path d='M17 14a6 6 0 0 1 4 6'/>"),
    }
    body = paths.get(name, "")
    return (f"<svg width='{size}' height='{size}' viewBox='0 0 24 24' fill='none' "
            f"stroke='{color}' stroke-width='{stroke}' stroke-linecap='round' "
            f"stroke-linejoin='round'>{body}</svg>")


# 登入畫面用來隱藏 Streamlit 內建的英文檔名導覽（1_case → "case"…），
# 並注入政府/企業級的登入版面樣式。未登入時側欄不需任何導覽。
_LOGIN_CSS = """
<style>
/* 登入畫面：完全隱藏側欄（登入前不需任何導覽，避免出現一塊深色空白），
   並隱藏 Streamlit 預設英文檔名導覽、收合按鈕與右上角工具列（Deploy 等）。 */
[data-testid="stSidebar"] { display:none !important; }
[data-testid="stSidebarNav"] { display:none !important; }
[data-testid="stSidebarCollapsedControl"] { display:none !important; }
[data-testid="stToolbar"], [data-testid="stDecoration"],
#MainMenu, footer { display:none !important; visibility:hidden; }
/* 登入畫面背景：極淡的中性藍 → 白的柔和漸層。
   關鍵：只讓最外層 .stApp 畫一次「固定於視窗」的漸層，其餘容器全部透明，
   避免多層各自漸層疊加而出現色階斷層／分界線。 */
.stApp {
  background:linear-gradient(180deg, #EDF3FA 0%, #F5F8FC 45%, #FFFFFF 100%)
             fixed !important; }
[data-testid="stAppViewContainer"], [data-testid="stMain"],
[data-testid="stHeader"],
.stApp [data-testid="stAppViewContainer"] > .main {
  background:transparent !important; }
[data-testid="stHeader"] { height:0 !important; }
/* 內容區：頂端貼齊、置中收窄（登入畫面較窄，角色卡不撐滿整個視窗）、適度上留白 */
.stApp [data-testid="stAppViewContainer"] > .main .block-container,
.stApp [data-testid="stMain"] .block-container {
  padding-top:40px !important; background:transparent !important;
  max-width:860px !important; margin:0 auto !important; }
.login-wrap { max-width:820px; margin:12px auto 0; }
/* Logo 圓形淡藍底，襯托盾牌，增加識別感 */
.login-logo { width:56px; height:56px; border-radius:50%;
  background:#E6EFF8; display:inline-flex; align-items:center;
  justify-content:center; margin-bottom:6px; }
.login-title { margin:12px 0 2px; font-size:1.7rem; font-weight:700;
  color:#16202B; letter-spacing:.02em; }
.login-sub { color:#4E5763; font-size:.95rem; }
.login-hint { color:#8A929C; font-size:.8rem; margin-top:8px; }
.login-divider { height:1px;
  background:linear-gradient(90deg, transparent, #D3DCE6 20%, #D3DCE6 80%, transparent);
  margin:26px 0 18px; }
.login-sec { color:#5A626D; font-size:.76rem; font-weight:700;
  letter-spacing:.1em; margin-bottom:4px; }
/* 角色卡：現代簡潔——較大圓角 + 適度陰影（懸浮感）+ hover 微互動。
   固定等高，使三張卡與其下的按鈕在同一水平線對齊。 */
.role-card { border:1px solid #DCE3EC; border-top:3px solid #2C5D8F;
  border-radius:10px; background:#FFFFFF; padding:22px 20px 18px;
  box-sizing:border-box; margin-bottom:14px; height:214px;
  box-shadow:0 2px 6px rgba(28,52,84,.06), 0 6px 20px rgba(28,52,84,.05);
  transition:box-shadow .18s ease, transform .18s ease; }
.role-card:hover { box-shadow:0 4px 10px rgba(28,52,84,.10),
  0 12px 28px rgba(28,52,84,.08); transform:translateY(-2px); }
.role-card .ico { width:44px; height:44px; border-radius:10px;
  background:#EAF1F9; display:flex; align-items:center; justify-content:center;
  margin-bottom:14px; }
.role-card .rname { font-size:1.05rem; font-weight:700; color:#1F2733; }
.role-card .rdesc { color:#5A626D; font-size:.8rem; line-height:1.6;
  margin-top:8px; }

/* ---- 深藍強調按鈕：進入按鈕更醒目、圓角一致、hover 加深 ---- */
.stButton > button {
  min-height:46px; font-weight:600; border-radius:8px !important;
  background:#2C5D8F !important; border:1px solid #2C5D8F !important;
  color:#FFFFFF !important;
  box-shadow:0 2px 6px rgba(44,93,143,.18); transition:all .16s ease; }
.stButton > button:hover {
  background:#244E79 !important; border-color:#244E79 !important;
  box-shadow:0 4px 12px rgba(44,93,143,.28); }
/* 「改用帳號登入」expander：白底、圓角、與上方角色區明顯分隔 */
[data-testid="stExpander"] { margin-top:24px !important; border-radius:10px;
  border:1px solid #DCE3EC; background:rgba(255,255,255,.7); }

/* ---- 公務入口門面（Government Portal）---- */
.gov-topbar { max-width:520px; margin:0 auto 8px; text-align:center;
  font-size:.82rem; color:#5A626D; letter-spacing:.02em; }
.gov-portal { max-width:520px; margin:8px auto 0; }
.gov-card { border:1px solid #D3DCE6; border-top:3px solid #2C5D8F;
  border-radius:10px; background:#FFFFFF; padding:26px 30px 24px;
  box-shadow:0 2px 6px rgba(28,52,84,.06), 0 8px 24px rgba(28,52,84,.05); }
.gov-card .sec { color:#5A626D; font-size:.74rem; font-weight:700;
  letter-spacing:.1em; margin:2px 0 10px; }
.gov-sso-note { color:#6B7280; font-size:.78rem; line-height:1.7;
  margin-top:2px; }
.gov-secbanner { max-width:520px; margin:16px auto 0; text-align:center;
  color:#4E7A63; font-size:.78rem; }
.gov-secbanner .lock { color:#2C5D8F; }
</style>
"""


def render_login() -> None:
    """Demo 登入畫面（政府/企業級，無 emoji）：三張角色卡 + 帳密登入表單。"""
    st = _st()

    st.markdown(_LOGIN_CSS, unsafe_allow_html=True)

    # ---- 公務入口門面（政府級單一登入，非「選擇角色」）----
    st.markdown(
        f"""
        <div class="gov-topbar">新北市政府教育局　·　教保機構監理數位平台</div>
        <div class="login-wrap" style="text-align:center;">
          <div class="login-logo">{_login_svg('shield', 28, '#2C5D8F', 1.7)}</div>
          <div class="login-title">Fiscalint</div>
          <div class="login-sub">教保機構智慧風險預警管理系統（公務入口）</div>
          <div class="login-hint">本系統為公務內部系統，僅限授權公務人員登入使用</div>
          <div class="login-divider"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- 公務帳號登入（實際走既有帳密驗證；SSO/TW FidO 為生產環境架構）----
    portal_l, portal_c, portal_r = st.columns([1, 2.2, 1])
    with portal_c:
        st.markdown("<div class='gov-card'>", unsafe_allow_html=True)
        st.markdown("<div class='sec'>公務帳號登入</div>", unsafe_allow_html=True)
        with st.form("gov_credential_login"):
            username = st.text_input(
                "公務識別碼 / 員工編號",
                placeholder="請輸入公務帳號")
            password = st.text_input("密碼", type="password")
            submitted = st.form_submit_button("登入", use_container_width=True)
        if submitted:
            role = login_with_credentials(username, password)
            if role is None:
                st.error("帳號或密碼錯誤，請確認公務帳號。")
            elif role == permissions.ROLE_PARENT:
                # 公務入口不接受家長角色（家長端為獨立公眾查詢網）。
                _audit(actor=username or "unknown", action="ACCESS_DENIED",
                       target="parent_role_on_gov_portal")
                logout()
                st.error("此為公務入口，家長／民眾請改用「公開查詢網」。")
            else:
                st.success(
                    "登入成功，系統依權限自動導向對應工作區："
                    f"{permissions.role_label(role)}")
                st.rerun()
        st.markdown(
            "<div class='gov-sso-note'>"
            "本系統於生產環境對接「新北市政府單一登入（SSO）」與「行動自然人憑證"
            "（TW FidO）」進行身分識別；登入後由後端解析職權代碼自動分流（科長 →"
            "全轄區戰情室、稽查人員 → 稽查工作台），使用者無需亦無權自選角色。"
            "現為競賽驗證環境，暫以公務帳號模擬 SSO 身分交換。</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        # ---- 競賽驗證環境：SSO 身分模擬（誠實標示，非生產功能）----
        with st.expander("競賽驗證環境：模擬 SSO 身分登入"):
            st.caption(
                "以下為競賽驗證用之身分模擬，對應生產環境由 SSO/TW FidO 解出的"
                "公務職權。生產環境無此手動選擇；此處僅供評審快速檢視兩種公務視角。")
            sim_gov, sim_ins = st.columns(2)
            with sim_gov:
                if st.button("模擬：局處決策者（科長）", use_container_width=True,
                             key="sim_login_gov"):
                    login(permissions.ROLE_GOV, username="government_demo")
                    st.rerun()
            with sim_ins:
                if st.button("模擬：第一線稽查人員", use_container_width=True,
                             key="sim_login_inspector"):
                    login(permissions.ROLE_INSPECTOR, username="inspector_demo")
                    st.rerun()

    st.markdown(
        "<div class='gov-secbanner'><span class='lock'>&#128274;</span> "
        "本系統已落實 RBAC 角色權限控管與資料層授權（權限在資料層控管，"
        "非前端隱藏）；所有登入、存取與判定操作皆寫入不可竄改稽核軌跡。</div>",
        unsafe_allow_html=True,
    )
