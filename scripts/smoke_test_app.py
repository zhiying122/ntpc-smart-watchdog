"""
儀表板煙霧測試：用 Streamlit AppTest 實際跑每一頁，確認不會拋例外。
不需開瀏覽器，CI/本地都能跑。
用法：python scripts/smoke_test_app.py
"""
import os
import sys

from streamlit.testing.v1 import AppTest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")

PAGES = [
    ("主頁（排名表）", os.path.join(APP, "主頁.py")),
    ("單園詳情", os.path.join(APP, "pages", "1_單園詳情.py")),
    ("風險地圖", os.path.join(APP, "pages", "2_風險地圖.py")),
    ("AI稽查建議", os.path.join(APP, "pages", "3_AI稽查建議.py")),
    ("輿情分析", os.path.join(APP, "pages", "4_輿情分析.py")),
]

failed = 0
for name, path in PAGES:
    try:
        at = AppTest.from_file(path, default_timeout=60)
        at.run()
        if at.exception:
            failed += 1
            msgs = [str(e.value) for e in at.exception]
            print(f"[FAIL] {name}: {msgs}")
        else:
            n_err = len(at.error)
            status = "OK" if n_err == 0 else f"OK(有{n_err}個st.error提示)"
            print(f"[{status}] {name}")
    except Exception as e:  # noqa: BLE001
        failed += 1
        print(f"[CRASH] {name}: {type(e).__name__}: {e}")

print(f"\n結果：{len(PAGES)-failed}/{len(PAGES)} 頁通過")
sys.exit(1 if failed else 0)
