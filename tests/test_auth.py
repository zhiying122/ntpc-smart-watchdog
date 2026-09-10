"""
RBAC 身分驗證單元測試（app/lib/auth.py）
==========================================
只測「純邏輯」，不測需要 Streamlit runtime 的呈現函式（render_login 等）。

驗證：
  - authenticate 三組 Demo 帳號正確；錯誤帳密回 None。
  - login / logout / get_current_role 的 session 行為（以 dict 模擬 session_state，
    並注入假的 streamlit 物件，使純邏輯與 Streamlit runtime 解耦）。

本模組位於 app/lib/（非 src 套件），沿用 tests/test_modes.py 的 importlib
file-path 載入方式。auth.py 的純邏輯（authenticate）不依賴 st.session_state；
session 相關函式透過 auth._st() 取得 streamlit，故測試以假物件替換之。
"""
import importlib.util
import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_AUTH_PATH = os.path.join(_ROOT, "app", "lib", "auth.py")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_spec = importlib.util.spec_from_file_location("app_lib_auth", _AUTH_PATH)
auth = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = auth
_spec.loader.exec_module(auth)


# ---------------------------------------------------------------------------
# 假的 streamlit：僅提供 session_state（dict）與 stop/rerun 空實作，
# 使 login/logout/get_current_role 等 session 邏輯可離線單元測試。
# ---------------------------------------------------------------------------
class _FakeStop(Exception):
    pass


class _FakeStreamlit:
    def __init__(self):
        self.session_state = {}

    def stop(self):
        raise _FakeStop()

    def rerun(self):
        pass


@pytest.fixture
def fake_st(monkeypatch):
    fst = _FakeStreamlit()
    monkeypatch.setattr(auth, "_st", lambda: fst)
    return fst


# ===========================================================================
# authenticate — 純邏輯，不需 fake_st
# ===========================================================================
@pytest.mark.parametrize(
    "username, password, expected",
    [
        ("government_demo", "gov_demo", "gov_user"),
        ("inspector_demo", "inspect_demo", "inspector"),
        ("parent_demo", "parent_demo", "parent_user"),
    ],
)
def test_authenticate_valid_credentials(username, password, expected):
    assert auth.authenticate(username, password) == expected


@pytest.mark.parametrize(
    "username, password",
    [
        ("government_demo", "wrong_password"),
        ("inspector_demo", ""),
        ("unknown_user", "gov_demo"),
        ("", ""),
        ("parent_demo", "gov_demo"),  # 對的帳號、錯的密碼
    ],
)
def test_authenticate_invalid_credentials_return_none(username, password):
    assert auth.authenticate(username, password) is None


def test_authenticate_non_string_returns_none():
    assert auth.authenticate(None, None) is None
    assert auth.authenticate(123, 456) is None


def test_authenticate_username_whitespace_tolerant():
    # 帳號前後空白應被容忍（strip）。
    assert auth.authenticate("  government_demo  ", "gov_demo") == "gov_user"


def test_demo_accounts_mapping():
    accounts = auth.demo_accounts()
    assert accounts["government_demo"] == "gov_user"
    assert accounts["inspector_demo"] == "inspector"
    assert accounts["parent_demo"] == "parent_user"


# ===========================================================================
# login / logout / get_current_role — session 行為（以 fake_st 模擬）
# ===========================================================================
def test_initial_state_not_authenticated(fake_st):
    assert auth.is_authenticated() is False
    assert auth.get_current_role() is None
    assert auth.get_current_user() is None


def test_login_sets_session_role(fake_st):
    auth.login("gov_user", username="government_demo")
    assert auth.is_authenticated() is True
    assert auth.get_current_role() == "gov_user"
    user = auth.get_current_user()
    assert user["role"] == "gov_user"
    assert user["username"] == "government_demo"
    assert user["login_time"] is not None


def test_logout_clears_session(fake_st):
    auth.login("inspector", username="inspector_demo")
    assert auth.is_authenticated() is True
    auth.logout()
    assert auth.is_authenticated() is False
    assert auth.get_current_role() is None


def test_login_with_credentials_success(fake_st):
    role = auth.login_with_credentials("parent_demo", "parent_demo")
    assert role == "parent_user"
    assert auth.get_current_role() == "parent_user"


def test_login_with_credentials_failure_does_not_authenticate(fake_st):
    role = auth.login_with_credentials("parent_demo", "bad")
    assert role is None
    assert auth.is_authenticated() is False


def test_switching_roles_updates_session(fake_st):
    auth.login("gov_user", username="government_demo")
    assert auth.get_current_role() == "gov_user"
    auth.login("parent_user", username="parent_demo")
    assert auth.get_current_role() == "parent_user"


# ===========================================================================
# Audit Log — 登入/登出寫入稽核軌跡
# ===========================================================================
def test_login_writes_audit_entry(fake_st):
    auth.login("gov_user", username="government_demo")
    log = auth.get_audit_log()
    entries = log.query_audit()
    assert any(e.action == "LOGIN" and e.actor == "government_demo" for e in entries)


def test_logout_writes_audit_entry(fake_st):
    auth.login("gov_user", username="government_demo")
    auth.logout()
    log = auth.get_audit_log()
    entries = log.query_audit()
    assert any(e.action == "LOGOUT" for e in entries)


def test_failed_login_writes_audit_entry(fake_st):
    auth.login_with_credentials("parent_demo", "wrong")
    log = auth.get_audit_log()
    entries = log.query_audit()
    assert any(e.action == "LOGIN_FAILED" for e in entries)


# ===========================================================================
# require_role — 頁面級守衛（雙層授權第二層）
# ===========================================================================
def test_require_role_denies_wrong_role(fake_st, monkeypatch):
    # 避免呼叫真正的呈現函式（需要 streamlit widget）；以空實作替換。
    monkeypatch.setattr(auth, "_render_access_denied", lambda allowed: None)
    monkeypatch.setattr(auth, "render_login", lambda: None)
    auth.login("parent_user", username="parent_demo")
    # 家長嘗試存取僅限政府的頁面 → 應觸發 st.stop()。
    with pytest.raises(_FakeStop):
        auth.require_role(["gov_user"])
    # 稽核軌跡應記錄 ACCESS_DENIED。
    entries = auth.get_audit_log().query_audit()
    assert any(e.action == "ACCESS_DENIED" for e in entries)


def test_require_role_allows_correct_role(fake_st, monkeypatch):
    monkeypatch.setattr(auth, "_render_access_denied", lambda allowed: None)
    monkeypatch.setattr(auth, "render_login", lambda: None)
    auth.login("gov_user", username="government_demo")
    # 政府存取政府頁 → 不應 st.stop()。
    auth.require_role(["gov_user"])
    entries = auth.get_audit_log().query_audit()
    assert any(e.action == "VIEW" for e in entries)


def test_require_role_unauthenticated_triggers_login(fake_st, monkeypatch):
    monkeypatch.setattr(auth, "render_login", lambda: None)
    with pytest.raises(_FakeStop):
        auth.require_role(["gov_user"])
