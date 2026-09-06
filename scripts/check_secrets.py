"""
上傳前機密檢查工具 (Pre-commit Secret Scanner)
----------------------------------------------------
用途：在 git push 到 GitHub 前，掃描即將上傳的檔案裡
      有沒有不小心留下 AWS 金鑰、API Token、密碼等機密資訊。

用法：
    python scripts/check_secrets.py

會檢查 git 追蹤中(staged/tracked)的檔案，找出可疑內容。
若發現疑似機密，會列出來並以非零狀態碼結束。
"""
import re
import subprocess
import sys

# 可疑機密的正則樣式：說明 -> 樣式
PATTERNS = {
    "AWS Access Key ID": re.compile(r"AKIA[0-9A-Z]{16}"),
    "AWS Secret Access Key": re.compile(r"(?i)aws.{0,20}secret.{0,20}['\"][0-9a-zA-Z/+]{40}['\"]"),
    "私鑰檔開頭 (PRIVATE KEY)": re.compile(r"-----BEGIN (RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "一般 API Token/Key 賦值": re.compile(r"(?i)(api[_-]?key|api[_-]?token|secret|password|passwd)\s*[=:]\s*['\"][^'\"]{8,}['\"]"),
    "Bearer Token": re.compile(r"(?i)bearer\s+[a-z0-9\-_\.]{20,}"),
}

# 這些檔案本來就是「範本」，允許出現 placeholder，跳過
ALLOWLIST = {".env.example", "scripts/check_secrets.py"}

# 這些是明顯的假值/範本值，出現時不算違規
PLACEHOLDER_HINTS = ("your_", "_here", "example", "xxxx", "placeholder", "changeme")


def get_tracked_files():
    """取得 git 追蹤中的所有檔案清單。"""
    try:
        out = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, check=True, encoding="utf-8"
        )
        return [f for f in out.stdout.splitlines() if f.strip()]
    except Exception as e:
        print(f"[!] 無法讀取 git 追蹤清單：{e}")
        return []


def looks_like_placeholder(line: str) -> bool:
    low = line.lower()
    return any(hint in low for hint in PLACEHOLDER_HINTS)


def scan():
    files = get_tracked_files()
    if not files:
        print("[i] git 目前沒有追蹤任何檔案，無需檢查。")
        return 0

    findings = []
    for path in files:
        if path in ALLOWLIST:
            continue
        # 只掃文字檔，略過二進位/PDF/圖片
        if path.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".gif",
                                  ".zip", ".exe", ".parquet", ".sqlite", ".db")):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if looks_like_placeholder(line):
                        continue
                    for label, pattern in PATTERNS.items():
                        if pattern.search(line):
                            findings.append((path, lineno, label, line.strip()[:100]))
        except (OSError, UnicodeDecodeError):
            continue

    if findings:
        print("=" * 60)
        print("[X] 危險！偵測到疑似機密資訊，請勿上傳：")
        print("=" * 60)
        for path, lineno, label, snippet in findings:
            print(f"  檔案: {path}:{lineno}")
            print(f"  類型: {label}")
            print(f"  內容: {snippet}")
            print("-" * 60)
        print(f"共發現 {len(findings)} 處。請移到 .env 或改用環境變數後再上傳。")
        return 1

    print("[OK] 未發現機密資訊，可以安全上傳。")
    return 0


if __name__ == "__main__":
    sys.exit(scan())
