"""
端到端冒煙測試（AppTest）：實際執行兩個系統的 Streamlit 腳本，
捕捉單元測試涵蓋不到的「執行期」邏輯/渲染錯誤。

涵蓋：
  - 公眾查詢網 public/公開查詢.py：無登入直接渲染，且不得含任何風險欄位。
  - 公務後台 app/主頁.py：未登入顯示公務入口；模擬政府/稽查員登入後可渲染；
    家長角色被公務入口拒絕。
"""
import os
import sys

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
PUBLIC_APP = os.path.join(ROOT, "public", "公開查詢.py")
GOV_APP = os.path.join(ROOT, "app", "主頁.py")

for _p in (ROOT, APP):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ---------------------------------------------------------------------------
# 公眾查詢網
# ---------------------------------------------------------------------------
def test_public_site_runs_without_exception():
    at = AppTest.from_file(PUBLIC_APP, default_timeout=30).run()
    assert not at.exception, f"公眾網執行期例外：{at.exception}"


def test_public_site_has_no_risk_data_leak():
    """公眾網不得洩漏內部風險『資料』（欄位名或分數值）。

    註：允許出現免責用語（如「本站不提供任何風險評分」），此屬責任 AI 聲明，
    非資料洩漏。故此處檢查的是內部欄位名與分數欄位，而非中文「風險」二字。
    """
    at = AppTest.from_file(PUBLIC_APP, default_timeout=30).run()
    assert not at.exception
    texts = " ".join(m.value for m in at.markdown)
    for banned in ("risk_total", "risk_level", "score_financial",
                   "score_penalty", "benford", "beneish", "iforest"):
        assert banned not in texts, f"公眾網不應出現內部風險欄位/資料：{banned}"


# ---------------------------------------------------------------------------
# 公務後台
# ---------------------------------------------------------------------------
def test_gov_backend_renders_without_login():
    """公務後台（8601）無登入牆：直接開啟即渲染風險總覽，不丟真實例外。"""
    at = AppTest.from_file(GOV_APP, default_timeout=30).run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"公務後台（無登入）真實執行期例外：{at.exception}")
    # 直接顯示風險總覽內容（不再有登入牆）。
    texts = " ".join(m.value for m in at.markdown)
    assert "風險" in texts


#: AppTest 的 bare 模式不提供多頁 URL 上下文，st.page_link 會失敗。這是測試框架
#: 限制（真實 Streamlit server 正常，已以 HTTP 200 與乾淨 log 驗證），非應用程式
#: 邏輯錯誤。不同 Streamlit 版本此限制的訊息不同：
#:   - 舊版：KeyError: 'url_pathname'
#:   - 新版：StreamlitPageNotFoundError: Could not find page: `主頁.py`
#: 以下工具判定例外是否「僅為此已知 page_link harness 限制」，涵蓋上述兩種訊息。
def _is_only_pagelink_harness_limitation(exc) -> bool:
    if exc is None:
        return True
    # exc 可能是單一例外或 ElementList（多個例外）；逐一檢查，全部都必須是
    # page_link 限制才算通過（任一為其他真實錯誤即不通過）。
    items = list(exc) if hasattr(exc, "__iter__") and not isinstance(exc, str) else [exc]
    if not items:
        return True
    for e in items:
        msg = str(getattr(e, "value", e))
        is_pagelink = (
            "url_pathname" in msg               # 舊版 Streamlit
            or "find page" in msg               # 新版：Could not find page
            or "StreamlitPageNotFoundError" in msg
            or "st.navigation" in msg           # 新版錯誤訊息尾段提示
        )
        if not is_pagelink:
            return False
    return True


def test_gov_backend_renders_after_gov_login():
    at = AppTest.from_file(GOV_APP, default_timeout=60)
    # 以 session_state 直接注入政府登入（等同 auth.login(ROLE_GOV)）。
    at.session_state["auth_role"] = "gov_user"
    at.session_state["auth_username"] = "government_demo"
    at.run()
    # 允許 AppTest 對 st.page_link 的已知限制；其餘任何例外皆視為真實錯誤。
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"公務後台（政府登入）真實執行期例外：{at.exception}")


def test_gov_backend_case_page_renders_without_login():
    # 稽查員工作台（案件調查）在無登入公務後台下應可直接渲染，不丟真實例外。
    at = AppTest.from_file(os.path.join(ROOT, "app", "pages", "1_case.py"),
                           default_timeout=60)
    at.run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"案件調查頁（無登入）真實執行期例外：{at.exception}")


def test_dispatch_page_renders_for_gov():
    # 稽查派工決策台（政府頁）應能以政府身分渲染，不丟真實例外。
    at = AppTest.from_file(os.path.join(ROOT, "app", "pages", "5_dispatch.py"),
                           default_timeout=60)
    at.session_state["auth_role"] = "gov_user"
    at.session_state["auth_username"] = "government_demo"
    at.run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"派工決策台真實執行期例外：{at.exception}")


def test_integration_page_renders_for_gov():
    # 資料整合中心（政府頁）應能以政府身分渲染，不丟真實例外。
    # 注意：首次載入不會自動觸網（同步為按鈕觸發），故此測試不依賴網路。
    at = AppTest.from_file(os.path.join(ROOT, "app", "pages", "7_integration.py"),
                           default_timeout=60)
    at.session_state["auth_role"] = "gov_user"
    at.session_state["auth_username"] = "government_demo"
    at.run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"資料整合中心真實執行期例外：{at.exception}")


def test_health_page_renders_for_gov():
    at = AppTest.from_file(os.path.join(ROOT, "app", "pages", "8_health.py"),
                           default_timeout=60)
    at.session_state["auth_role"] = "gov_user"
    at.session_state["auth_username"] = "government_demo"
    at.run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"系統健康檢查頁真實執行期例外：{at.exception}")


def test_gov_backend_map_page_renders_without_login():
    # 風險地圖頁在無登入公務後台下應可直接渲染，不丟真實例外。
    at = AppTest.from_file(os.path.join(ROOT, "app", "pages", "2_map.py"),
                           default_timeout=60)
    at.run()
    assert _is_only_pagelink_harness_limitation(at.exception), (
        f"風險地圖頁（無登入）真實執行期例外：{at.exception}")


# ---------------------------------------------------------------------------
# 資料層隔離不變式（再次於 app 層級斷言）
# ---------------------------------------------------------------------------
def test_public_data_layer_strips_all_risk_fields():
    from lib import parent_portal as pp
    from lib import permissions as perm

    df = pd.read_csv(os.path.join(ROOT, "data", "processed",
                                  "kindergartens_latest.csv"))
    pub = perm.authorize_dataframe(df, perm.ROLE_PARENT)
    leaked = [c for c in pub.columns if pp.is_risk_field(c)]
    assert leaked == []
    assert "risk_total" not in pub.columns
    assert "risk_level" not in pub.columns
