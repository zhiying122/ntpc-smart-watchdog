#!/usr/bin/env bash
# ============================================================================
# Smart Watchdog — EC2 一鍵部署腳本
# ----------------------------------------------------------------------------
# 在全新的 Amazon Linux 2023 / Ubuntu EC2 上，安裝系統相依、建立 venv、
# 安裝 Python 依賴，並以 systemd 常駐兩個 Streamlit 服務：
#   - 公務後台   app/主頁.py        → :8601
#   - 公眾查詢網 public/公開查詢.py → :8602
#
# 用法（於 EC2 上）：
#   git clone https://github.com/zhiying122/ntpc-smart-watchdog.git
#   cd ntpc-smart-watchdog
#   bash deploy/setup_ec2.sh
#
# 冪等：可重複執行（再次執行＝更新程式碼 + 重裝依賴 + 重啟服務）。
# 環境變數：AWS 憑證建議改用 IAM Role（見 docs/deploy-ec2.md），
#           不要把 .env 的金鑰硬塞進 repo。
# ============================================================================
set -euo pipefail

# --- 專案根目錄（腳本位於 <root>/deploy/）---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUN_USER="$(id -un)"
RUN_GROUP="$(id -gn)"
VENV="${PROJECT_DIR}/.venv"

echo "==> 專案目錄：${PROJECT_DIR}"
echo "==> 執行使用者：${RUN_USER}:${RUN_GROUP}"

# --- 1. 系統套件（Python3、venv、pip、tesseract 中文 OCR、git）---
echo "==> 安裝系統相依套件…"
if command -v dnf >/dev/null 2>&1; then
    # Amazon Linux 2023 / RHEL 系
    # 核心套件（一定要有）：python3 / pip / git。
    sudo dnf install -y python3 python3-pip git || true
    # tesseract（OCR，非必要）：AL2023 預設 repo 可能沒有此套件，逐個嘗試、
    # 裝不到也不影響儀表板啟動（OCR 僅供非營利園掃描財報抽取，屬離線批次工具）。
    sudo dnf install -y tesseract tesseract-langpack-chi_tra 2>/dev/null \
        || echo "!! 略過 tesseract（此環境 repo 無此套件；OCR 為離線工具，不影響儀表板）。"
elif command -v apt-get >/dev/null 2>&1; then
    # Ubuntu / Debian 系
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip git tesseract-ocr tesseract-ocr-chi-tra || true
else
    echo "!! 未知的套件管理器，請手動安裝 python3/venv/pip/git/tesseract。"
fi

# --- 2. 更新程式碼（若已是 git repo）---
if [ -d "${PROJECT_DIR}/.git" ]; then
    echo "==> 更新程式碼（git pull）…"
    git -C "${PROJECT_DIR}" pull --ff-only || echo "!! git pull 略過（可能有本地變更）。"
fi

# --- 3. 建立 / 更新 Python 虛擬環境 ---
echo "==> 建立虛擬環境 ${VENV} …"
python3 -m venv "${VENV}"
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
python -m pip install --upgrade pip wheel
echo "==> 安裝 Python 依賴（requirements.txt）…"
pip install -r "${PROJECT_DIR}/requirements.txt"
deactivate

# --- 4. 產生 systemd service（動態填入實際使用者與路徑）---
echo "==> 安裝 systemd 服務…"
render_service() {
    # $1 = 來源範本，$2 = 目標檔名
    sed -e "s#/home/ec2-user/ntpc-smart-watchdog#${PROJECT_DIR}#g" \
        -e "s#^User=ec2-user#User=${RUN_USER}#g" \
        -e "s#^Group=ec2-user#Group=${RUN_GROUP}#g" \
        "$1" | sudo tee "$2" >/dev/null
}
render_service "${PROJECT_DIR}/deploy/watchdog-gov.service"    /etc/systemd/system/watchdog-gov.service
render_service "${PROJECT_DIR}/deploy/watchdog-public.service" /etc/systemd/system/watchdog-public.service

# --- 5. 啟用並啟動服務（開機自啟 + 當機自動重啟）---
echo "==> 啟用並啟動服務…"
sudo systemctl daemon-reload
sudo systemctl enable  watchdog-gov.service watchdog-public.service
sudo systemctl restart watchdog-gov.service watchdog-public.service

echo ""
echo "============================================================"
echo " 部署完成 ✅"
echo "   公務後台   ： http://<EC2 公有IP>:8601"
echo "   公眾查詢網 ： http://<EC2 公有IP>:8602"
echo ""
echo " 常用指令："
echo "   sudo systemctl status  watchdog-gov     # 查看狀態"
echo "   sudo journalctl -u watchdog-gov -f       # 追 log"
echo "   sudo systemctl restart watchdog-public   # 重啟"
echo ""
echo " ⚠️ 別忘了在 EC2 Security Group 對這四組 IP 開放 8601/8602："
echo "    60.250.71.45  61.222.117.53  59.125.121.41  60.250.71.43"
echo "============================================================"
