"""pytest 共用設定：確保專案根目錄在 sys.path，使 `import src.xxx` 可用。"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
