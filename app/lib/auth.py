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
    st.error("🚫 存取遭拒：此資訊不在您的資料授權範圍內")
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
    if st.button("↩ 返回並切換角色（登出）"):
        logout()
        st.rerun()


def render_login() -> None:
    """Demo 登入畫面：三個角色快速登入大按鈕 + 可展開的帳密登入表單。"""
    st = _st()

    st.markdown(
        """
        <div style="text-align:center;padding:8px 0 4px;">
          <div style="display:inline-block;background:#EAF0F6;color:#2C5D8F;
               font-size:.72rem;font-weight:700;letter-spacing:.08em;
               padding:4px 12px;border-radius:6px;">DEMO ENVIRONMENT</div>
          <h1 style="margin:14px 0 4px;font-size:1.6rem;color:#1F2733;">
            🛡️ Smart Watchdog 小小守護員</h1>
          <div style="color:#5A626D;font-size:.95rem;">教保機構智慧風險預警平台</div>
          <div style="color:#8A929C;font-size:.82rem;margin-top:8px;">
            請選擇角色進入對應的權限視角（RBAC 角色權限展示）</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(
            "<div style='text-align:center;font-size:2rem;'>🏛️</div>",
            unsafe_allow_html=True)
        if st.button("政府管理者 Demo", use_container_width=True, type="primary",
                     key="login_gov"):
            login(permissions.ROLE_GOV, username="government_demo")
            st.rerun()
        st.caption("全轄區風險決策、分派、模擬")
    with c2:
        st.markdown(
            "<div style='text-align:center;font-size:2rem;'>🔎</div>",
            unsafe_allow_html=True)
        if st.button("稽查人員 Demo", use_container_width=True, type="primary",
                     key="login_inspector"):
            login(permissions.ROLE_INSPECTOR, username="inspector_demo")
            st.rerun()
        st.caption("單一機構鑑識調查、證據鏈、AI Copilot")
    with c3:
        st.markdown(
            "<div style='text-align:center;font-size:2rem;'>👨‍👩‍👧</div>",
            unsafe_allow_html=True)
        if st.button("家長 Demo", use_container_width=True, type="primary",
                     key="login_parent"):
            login(permissions.ROLE_PARENT, username="parent_demo")
            st.rerun()
        st.caption("公開透明資訊查詢（不含任何風險分數）")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    with st.expander("使用帳號登入"):
        st.caption("Demo credentials only — not production authentication.")
        with st.form("credential_login"):
            username = st.text_input("帳號", placeholder="例如 government_demo")
            password = st.text_input("密碼", type="password")
            submitted = st.form_submit_button("登入")
        if submitted:
            role = login_with_credentials(username, password)
            if role is None:
                st.error("帳號或密碼錯誤，請確認 Demo 帳密。")
            else:
                st.success(f"登入成功：{permissions.role_label(role)}")
                st.rerun()

    st.markdown(
        "<div style='text-align:center;color:#AEB4BC;font-size:.72rem;margin-top:16px;'>"
        "Demo credentials only — not production authentication.</div>",
        unsafe_allow_html=True,
    )
