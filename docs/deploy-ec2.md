# EC2 部署指南 — Smart Watchdog 小小守護員

把兩個 Streamlit 服務部署到一台 EC2，以 systemd 常駐（開機自啟、當機自動重啟）：

| 服務 | 進入點 | 埠 | 對外網址 |
|---|---|---|---|
| 公務後台（Fiscalint 稽查預警） | `app/主頁.py` | 8601 | `http://<EC2 公有IP>:8601` |
| 公眾查詢網（安心找幼兒園） | `public/公開查詢.py` | 8602 | `http://<EC2 公有IP>:8602` |

> 本機對照啟動指令（部署後由 systemd 自動執行，不需手動下）：
> ```
> python -m streamlit run app/主頁.py --server.port 8601
> python -m streamlit run public/公開查詢.py --server.port 8602
> ```

---

## 1. 建立 EC2

- **AMI**：Amazon Linux 2023（腳本亦支援 Ubuntu）。
- **執行個體類型**：建議 `t3.small` 以上（Streamlit + pandas + sklearn/shap 記憶體吃得較兇，`t3.micro` 1GB 可能在載入 shap 時吃緊；預算有限可先 `t3.small`）。
- **金鑰對**：建立或選擇既有 key pair，供 SSH。
- **儲存**：8GB 以上（依賴含 shap/scikit-learn/PyMuPDF 較大，建議 16GB）。

## 2. Security Group（重要 — 主辦方指定的四組 IP）

建立入站規則（Inbound rules），**只對主辦方/評審來源 IP 開放** 8601 與 8602，避免對全世界開放：

| 類型 | 協定 | 埠範圍 | 來源 | 說明 |
|---|---|---|---|---|
| Custom TCP | TCP | 8601 | `60.250.71.45/32` | 公務後台 |
| Custom TCP | TCP | 8601 | `61.222.117.53/32` | 公務後台 |
| Custom TCP | TCP | 8601 | `59.125.121.41/32` | 公務後台 |
| Custom TCP | TCP | 8601 | `60.250.71.43/32` | 公務後台 |
| Custom TCP | TCP | 8602 | `60.250.71.45/32` | 公眾查詢網 |
| Custom TCP | TCP | 8602 | `61.222.117.53/32` | 公眾查詢網 |
| Custom TCP | TCP | 8602 | `59.125.121.41/32` | 公眾查詢網 |
| Custom TCP | TCP | 8602 | `60.250.71.43/32` | 公眾查詢網 |
| SSH | TCP | 22 | 你的辦公室/家用 IP | 管理用 |

> 每個 IP 後面記得加 `/32`（單一主機）。若要 demo 當天讓自己的筆電也能連，另外加一條你當下的對外 IP。
>
> **不建議**用 `0.0.0.0/0` 對外全開——這兩個系統含公務資料，對全網開放不符責任 AI/資料治理原則。

CLI 範例（把 `<SG-ID>` 換成你的 security group id）：

```bash
for ip in 60.250.71.45 61.222.117.53 59.125.121.41 60.250.71.43; do
  for port in 8601 8602; do
    aws ec2 authorize-security-group-ingress --group-id <SG-ID> \
      --protocol tcp --port $port --cidr ${ip}/32
  done
done
```

## 3. AWS 憑證（Bedrock）— 用 IAM Role，不要放金鑰

AI 研判會呼叫 Bedrock。**最安全**的做法是給 EC2 掛一個 IAM Role（instance profile），`boto3` 會自動取得不會過期的臨時憑證，`.env` 完全不需填 AWS 金鑰。

1. IAM → 建立 Role，信任實體選 **EC2**。
2. 附掛可呼叫 Bedrock 的權限（最小權限範例）：
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["bedrock:InvokeModel"],
       "Resource": "*"
     }]
   }
   ```
3. EC2 → 執行個體 → 動作 → 安全性 → **修改 IAM 角色** → 掛上該 Role。
4. 到 Bedrock console 的「Model access」開通你要用的模型（`.env.example` 預設 `us.anthropic.claude-sonnet-4-5-20250929-v1:0`，區域 `us-west-2`）。

> 沒掛 Role 也能跑——`src/ai_report.py` 偵測不到憑證會自動退回「規則式範本」，Demo 一定有東西出來。但要展示真 Bedrock 生成，就掛 Role。

`.env` 只需放非 AWS 的設定（若有用到）：

```bash
cp .env.example .env
# 用 IAM Role 時，AWS_ACCESS_KEY_ID 等留空即可；只確認 BEDROCK_MODEL_ID / BEDROCK_REGION 正確。
```

## 4. 部署

SSH 進 EC2 後：

```bash
git clone https://github.com/zhiying122/ntpc-smart-watchdog.git
cd ntpc-smart-watchdog
bash deploy/setup_ec2.sh
```

腳本會自動：安裝系統套件（含 tesseract 中文 OCR）→ 建 `.venv` → 裝 `requirements.txt` → 產生並啟用兩個 systemd 服務 → 啟動。

> 若你的 EC2 使用者不是 `ec2-user`（例如 Ubuntu 的 `ubuntu`），腳本會**自動**以當前使用者與實際路徑填入 service 檔，不需手改。

## 5. 驗證

```bash
sudo systemctl status watchdog-gov      # 應為 active (running)
sudo systemctl status watchdog-public
curl -I http://localhost:8601           # 應回 200
curl -I http://localhost:8602
```

瀏覽器開 `http://<EC2 公有IP>:8601` 與 `:8602`（需從 Security Group 允許的 IP 連）。

## 6. 更新程式碼（改版重部署）

```bash
cd ntpc-smart-watchdog
bash deploy/setup_ec2.sh   # 冪等：pull + 重裝依賴 + 重啟服務
```

或只重啟（沒改依賴時）：

```bash
git pull
sudo systemctl restart watchdog-gov watchdog-public
```

## 7. 常用維運指令

```bash
# 追即時 log（含 Streamlit 輸出、Python 例外）
sudo journalctl -u watchdog-gov -f
sudo journalctl -u watchdog-public -f

# 重啟 / 停止 / 啟動
sudo systemctl restart watchdog-gov
sudo systemctl stop    watchdog-public
sudo systemctl start   watchdog-public

# 停用開機自啟
sudo systemctl disable watchdog-gov watchdog-public
```

## 8. 疑難排解

| 症狀 | 可能原因 / 解法 |
|---|---|
| 瀏覽器連不上 | Security Group 沒開該埠給你的來源 IP；或服務沒起來（看 `systemctl status`）。 |
| `status` 顯示 failed | `journalctl -u <service> -n 50` 看錯誤。常見：venv 路徑、依賴沒裝完、埠被占用。 |
| 記憶體不足被 OOM kill | 換 `t3.small`/`t3.medium`；shap 載入吃記憶體。 |
| AI 研判顯示「規則式範本」 | 未偵測到 Bedrock 憑證/模型未開通 → 掛 IAM Role + Bedrock Model access。功能不受影響，只是沒用到真模型。 |
| 中文 OCR 失敗 | 確認 `tesseract-langpack-chi_tra`（AL2023）/ `tesseract-ocr-chi-tra`（Ubuntu）已裝。 |
| `.env` 沒生效 | service 用 `EnvironmentFile=-.../.env`；確認檔案在專案根、格式為 `KEY=value`（無 `export`）。 |

## 安全備註

- **絕不**把真實 `.env`（含任何金鑰）提交進 git（`.gitignore` 已排除）。上 GitHub 前跑 `python scripts/check_secrets.py`。
- AWS 憑證優先用 IAM Role，其次才是環境變數。
- 8601/8602 僅對指定 IP 開放，不對 `0.0.0.0/0`。
