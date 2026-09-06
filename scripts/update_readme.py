"""
README 自動更新工具
--------------------------------
掃描專案結構，自動更新 README.md 裡標記區塊之間的內容。
在 README.md 中用下列標記包住要自動維護的區段：

    <!-- AUTO-STRUCTURE:START -->
    ...(自動產生的內容)...
    <!-- AUTO-STRUCTURE:END -->

用法：
    python scripts/update_readme.py
"""
import os
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README = os.path.join(ROOT, "README.md")

START = "<!-- AUTO-STRUCTURE:START -->"
END = "<!-- AUTO-STRUCTURE:END -->"

# 掃描時忽略的資料夾
IGNORE_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
               ".kiro", "E_教育局-資料集", "E_教育局-命題文件", ".pytest_cache"}


def build_tree(base, prefix=""):
    lines = []
    try:
        entries = sorted(
            [e for e in os.scandir(base) if e.name not in IGNORE_DIRS
             and not e.name.startswith(".")],
            key=lambda e: (not e.is_dir(), e.name.lower())
        )
    except OSError:
        return lines
    for i, entry in enumerate(entries):
        connector = "└── " if i == len(entries) - 1 else "├── "
        lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.extend(build_tree(entry.path, prefix + extension))
    return lines


def count_files_by_ext():
    counts = {}
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            ext = os.path.splitext(f)[1].lower() or "(無副檔名)"
            counts[ext] = counts.get(ext, 0) + 1
    return counts


def generate_block():
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).strftime("%Y-%m-%d %H:%M")
    tree = "\n".join(build_tree(ROOT))
    counts = count_files_by_ext()
    count_lines = "\n".join(
        f"- `{ext}`：{n} 個" for ext, n in sorted(counts.items(), key=lambda x: -x[1])
    )
    return (
        f"{START}\n"
        f"> 本區塊由 `scripts/update_readme.py` 自動維護，最後更新：{now} (UTC+8)\n\n"
        f"### 專案結構\n```\nntpc-smart-watchdog/\n{tree}\n```\n\n"
        f"### 檔案統計\n{count_lines}\n"
        f"{END}"
    )


def main():
    block = generate_block()
    if not os.path.exists(README):
        with open(README, "w", encoding="utf-8") as f:
            f.write("# 小小守護員 Smart Watchdog\n\n" + block + "\n")
        print("[OK] README.md 不存在，已建立並寫入自動區塊。")
        return

    with open(README, "r", encoding="utf-8") as f:
        content = f.read()

    if START in content and END in content:
        pre = content.split(START)[0]
        post = content.split(END)[1]
        new_content = pre + block + post
    else:
        # 沒有標記就附加到檔尾
        new_content = content.rstrip() + "\n\n## 專案概況（自動產生）\n\n" + block + "\n"

    if new_content != content:
        with open(README, "w", encoding="utf-8") as f:
            f.write(new_content)
        print("[OK] README.md 自動區塊已更新。")
    else:
        print("[i] README.md 無需更新。")


if __name__ == "__main__":
    main()
