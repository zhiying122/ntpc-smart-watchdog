# push 後自動部署到 EC2（GitHub Actions self-hosted runner）

目標：每次 push 到 `main`，EC2（`18.236.246.233`）就自動拉最新程式碼、重裝依賴、
重啟兩個 Streamlit 服務（公務後台 :8601、公眾查詢網 :8602）。

原理：在 **EC2 那台 Linux 機器上**安裝一個 GitHub Actions self-hosted runner。
push 觸發 `.github/workflows/deploy.yml`，runner 在 EC2 上直接執行 `deploy/setup_ec2.sh`
完成部署——不需要 SSH、不需要在 GitHub 存私鑰。

> ⚠️ runner 要裝在 **AWS EC2**，不是你的 Windows 開發機。以下指令全部在 SSH 進 EC2 後執行。

---

## 步驟 0：SSH 進 EC2

```bash
ssh -i <你的金鑰.pem> ec2-user@18.236.246.233
# Ubuntu 系的 AMI 使用者是 ubuntu：ssh -i <金鑰.pem> ubuntu@18.236.246.233
```

## 步驟 1：確認程式碼已在 EC2 上（runner 會用到 deploy/setup_ec2.sh）

```bash
# 若還沒 clone：
git clone https://github.com/zhiying122/ntpc-smart-watchdog.git
cd ntpc-smart-watchdog
# 若已 clone 過：
cd ntpc-smart-watchdog && git pull
```

## 步驟 2：取得註冊 token（在瀏覽器）

到 GitHub repo：
`Settings → Actions → Runners → New self-hosted runner → Linux / x64`

頁面會給你一組指令與一次性 token（`--token AXXX...`）。**token 幾分鐘後過期**，取得後盡快用。

## 步驟 3：在 EC2 上安裝 runner

依 GitHub 頁面給的版本號執行（下面是範例，版本以頁面為準）：

```bash
# 建議把 runner 裝在使用者家目錄，與程式碼分開
cd ~
mkdir -p actions-runner && cd actions-runner

curl -o actions-runner-linux-x64-2.337.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.337.0/actions-runner-linux-x64-2.337.0.tar.gz
tar xzf ./actions-runner-linux-x64-2.337.0.tar.gz

# 用 GitHub 頁面給你的 token 註冊（把 <TOKEN> 換成頁面上的）
./config.sh --url https://github.com/zhiying122/ntpc-smart-watchdog --token <TOKEN>
```

`config.sh` 會問幾個問題，直接按 Enter 用預設即可：
- runner group：`Default`
- runner name：預設（例如主機名）
- **labels：直接 Enter**（保留預設 `self-hosted`，workflow 就是用這個標籤）
- work folder：`_work`

## 步驟 4：把 runner 裝成開機自啟服務（重要，別用 ./run.sh）

`./run.sh` 只在前景跑，你一登出就停。用內建的 service 安裝成 systemd 常駐：

```bash
sudo ./svc.sh install
sudo ./svc.sh start
sudo ./svc.sh status     # 應顯示 active (running)
```

## 步驟 5：讓 runner 使用者能用 sudo 免密碼（部署腳本需要）

`deploy/setup_ec2.sh` 會用 `sudo`（安裝套件、寫 systemd、重啟服務）。非互動的 runner
不能停下來輸入密碼，所以要給免密碼 sudo。runner 預設以安裝它的使用者身分執行
（例如 `ec2-user`）：

```bash
# 把 ec2-user 換成你實際的使用者（用 id -un 可查）
echo "$(id -un) ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/gha-runner
sudo chmod 440 /etc/sudoers.d/gha-runner
```

> 安全備註：這給了 runner 使用者完整免密碼 sudo。因為 runner 只跑你自己 repo `main`
> 分支的 workflow（見下方「安全」段），風險可控。若要更嚴謹，可只放行特定指令。

## 步驟 6：驗證

在 GitHub `Settings → Actions → Runners` 應看到你的 runner 是綠點 **Idle**。
接著推一個 commit 到 `main`（或到 `Actions → 部署到 EC2 → Run workflow` 手動觸發），
到 Actions 頁看 `deploy` job 是否綠勾。成功後：

```bash
sudo systemctl status watchdog-gov      # active (running)
sudo systemctl status watchdog-public
curl -I http://localhost:8601           # 200
curl -I http://localhost:8602
```

---

## 日常使用

- **改程式 → push 到 main → 自動部署。** 不用再手動 SSH 進去跑腳本。
- 想手動重部署：GitHub `Actions → 部署到 EC2 → Run workflow`。
- 只改文件（`docs/`、`*.md`、`.kiro/`）不會觸發部署（workflow 的 `paths-ignore`）。

## 疑難排解

| 症狀 | 處理 |
|---|---|
| Actions 卡在 queued 不動 | runner 沒在線：`sudo ./svc.sh status`，必要時 `sudo ./svc.sh start` |
| 部署失敗、log 出現 sudo 要密碼 | 沒設步驟 5 的免密碼 sudo |
| 服務起不來 | `sudo journalctl -u watchdog-gov -n 50 --no-pager` 看錯誤 |
| 頁面連不上但服務 active | EC2 Security Group 沒對來源 IP 開 8601/8602（見 docs/deploy-ec2.md） |

## 安全

- runner 跑在**你自己的 EC2** 上，執行 repo 的 workflow 程式碼。
- 本 workflow 只在 push 到 `main` 或手動觸發時執行；請確保 `main` 只由你/隊友合併。
- 若日後把 repo 開成公開並接受外部 PR，**務必**在 repo 設定關閉「Fork PR 自動跑 workflow」，
  避免外部人在你的 runner 上跑任意程式。
- 別把真實 `.env` 提交進 git（`.gitignore` 已排除）；AWS 憑證優先用 IAM Role。
