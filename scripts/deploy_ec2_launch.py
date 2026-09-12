"""
EC2 部署步驟 2：Key Pair + Security Group + 開 EC2（含自動部署）
================================================================
遵守競賽規範：
  - 規範 3：Security Group 不對外全開，SSH(22)/Streamlit(8501) 僅開放本機公網 IP。
  - 規範 6：部署於 us-west-2。
  - EC2 機型限 Standard/T 系列 → t3.small。
  - 掛載 sw-ec2-bedrock-profile（步驟 1 建立），以 IAM Role 呼叫 Bedrock（不過期）。

EC2 開機時透過 user-data 自動：安裝 Python → git clone → pip install →
以 systemd 常駐跑 Streamlit（port 8501）。

冪等：同名 key pair / SG 已存在則沿用。EC2 每次執行都會新開一台（自行留意數量）。

用法：
    python scripts/deploy_ec2_launch.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    pass

import urllib.request

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
KEY_NAME = "sw-ec2-key"
KEY_FILE = os.path.join(ROOT, "sw-ec2-key.pem")
SG_NAME = "sw-ec2-sg"
PROFILE_NAME = "sw-ec2-bedrock-profile"
INSTANCE_TYPE = "t3.small"
GITHUB_REPO = "https://github.com/zhiying122/ntpc-smart-watchdog.git"
TAG_NAME = "sw-streamlit-demo"

# EC2 開機自動部署腳本（Amazon Linux 2023）。
# 注意：不含任何金鑰——Bedrock 憑證由掛載的 IAM Role 自動提供。
USER_DATA = f"""#!/bin/bash
set -x
dnf update -y
dnf install -y python3.11 python3.11-pip git
cd /home/ec2-user
git clone {GITHUB_REPO} app_repo
cd app_repo
python3.11 -m pip install -r requirements.txt
# 以 IAM Role 提供 Bedrock 憑證；只需設定 region 與模型 ID。
cat > /home/ec2-user/app_repo/.env <<EOF
AWS_DEFAULT_REGION={REGION}
BEDROCK_REGION={REGION}
BEDROCK_MODEL_ID=us.anthropic.claude-sonnet-4-5-20250929-v1:0
EOF
chown -R ec2-user:ec2-user /home/ec2-user/app_repo
# systemd 常駐 Streamlit
cat > /etc/systemd/system/streamlit.service <<EOF
[Unit]
Description=Smart Watchdog Streamlit
After=network.target
[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/app_repo
ExecStart=/usr/bin/python3.11 -m streamlit run app/主頁.py --server.port 8501 --server.address 0.0.0.0 --server.headless true
Restart=always
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable streamlit
systemctl start streamlit
"""


def my_ip():
    ip = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=10).read()
    return ip.decode().strip()


def main():
    ec2 = boto3.client("ec2", region_name=REGION)
    ip = my_ip()
    cidr = f"{ip}/32"
    print(f"本機公網 IP: {ip} → Security Group 僅開放 {cidr}")

    # 1) Key pair（冪等）
    try:
        kp = ec2.create_key_pair(KeyName=KEY_NAME)
        with open(KEY_FILE, "w") as f:
            f.write(kp["KeyMaterial"])
        print(f"[1] 建立 key pair 並存檔: {KEY_FILE}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidKeyPair.Duplicate":
            print(f"[1] key pair 已存在，沿用: {KEY_NAME}"
                  f"（若無 .pem 檔需先刪除再重建）")
        else:
            raise

    # 2) Security Group（冪等）
    try:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])
        vpc_id = vpcs["Vpcs"][0]["VpcId"]
        sg = ec2.create_security_group(
            GroupName=SG_NAME, Description="Smart Watchdog demo SG (IP-restricted)",
            VpcId=vpc_id,
        )
        sg_id = sg["GroupId"]
        print(f"[2] 建立 Security Group: {sg_id}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "InvalidGroup.Duplicate":
            sgs = ec2.describe_security_groups(
                Filters=[{"Name": "group-name", "Values": [SG_NAME]}])
            sg_id = sgs["SecurityGroups"][0]["GroupId"]
            print(f"[2] Security Group 已存在，沿用: {sg_id}")
        else:
            raise

    # 3) 授權規則：僅本機 IP 可連 22 與 8501（規範 3：不全開）
    for port in (22, 8501):
        try:
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp", "FromPort": port, "ToPort": port,
                    "IpRanges": [{"CidrIp": cidr, "Description": "my-ip only"}],
                }],
            )
            print(f"[3] 開放 port {port} 給 {cidr}")
        except ClientError as e:
            if e.response["Error"]["Code"] == "InvalidPermission.Duplicate":
                print(f"[3] port {port} 規則已存在")
            else:
                raise

    # 4) 取最新 Amazon Linux 2023 AMI
    ssm = boto3.client("ssm", region_name=REGION)
    ami = ssm.get_parameter(
        Name="/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
    )["Parameter"]["Value"]
    print(f"[4] AMI: {ami}")

    # 5) 開 EC2
    resp = ec2.run_instances(
        ImageId=ami, InstanceType=INSTANCE_TYPE, MinCount=1, MaxCount=1,
        KeyName=KEY_NAME, SecurityGroupIds=[sg_id],
        IamInstanceProfile={"Name": PROFILE_NAME},
        UserData=USER_DATA,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [{"Key": "Name", "Value": TAG_NAME}],
        }],
    )
    iid = resp["Instances"][0]["InstanceId"]
    print(f"[5] EC2 已啟動: {iid}（等待取得公網 IP…）")

    ec2.get_waiter("instance_running").wait(InstanceIds=[iid])
    desc = ec2.describe_instances(InstanceIds=[iid])
    pub_ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress")

    print("\n" + "=" * 55)
    print(f"Instance ID : {iid}")
    print(f"公網 IP     : {pub_ip}")
    print(f"Demo 網址   : http://{pub_ip}:8501")
    print(f"SSH         : ssh -i {KEY_FILE} ec2-user@{pub_ip}")
    print("=" * 55)
    print("注意：app 在開機後需 3-5 分鐘完成安裝才會上線。")
    print(f"停止計費：python scripts/deploy_ec2_teardown.py 或於 console 終止 {iid}")


if __name__ == "__main__":
    main()
