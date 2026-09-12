"""
EC2 部署步驟 1：建立 IAM Role + Instance Profile（供 EC2 呼叫 Bedrock）
========================================================================
讓 EC2 以 IAM Role（instance profile）身分自動取得「不會過期」的臨時憑證，
呼叫 Bedrock 與 Textract。遵守競賽規範：僅授予專案直接相關之必要權限。

資源命名一律以 sw- 前綴，方便事後辨識與清理。
冪等：若資源已存在則沿用，不重複建立。

用法：
    python scripts/deploy_ec2_setup_role.py
"""
import json
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

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
ROLE_NAME = "sw-ec2-bedrock-role"
PROFILE_NAME = "sw-ec2-bedrock-profile"
POLICY_NAME = "sw-bedrock-textract-inline"

TRUST_POLICY = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Principal": {"Service": "ec2.amazonaws.com"},
        "Action": "sts:AssumeRole",
    }],
}

# 僅授予專案直接相關之必要權限（Bedrock 生成報告 + Textract OCR）。
PERMISSION_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockInvoke",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels",
                "bedrock:ListInferenceProfiles",
            ],
            "Resource": "*",
        },
        {
            "Sid": "TextractRead",
            "Effect": "Allow",
            "Action": [
                "textract:AnalyzeDocument",
                "textract:DetectDocumentText",
            ],
            "Resource": "*",
        },
    ],
}


def main():
    iam = boto3.client("iam", region_name=REGION)

    # 1) 建 role（冪等）
    try:
        iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(TRUST_POLICY),
            Description="Smart Watchdog EC2 role for Bedrock/Textract (hackathon)",
        )
        print(f"[1] 建立 role: {ROLE_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"[1] role 已存在，沿用: {ROLE_NAME}")
        else:
            raise

    # 2) 附加 inline policy（冪等：put 為覆寫語意）
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(PERMISSION_POLICY),
    )
    print(f"[2] 附加權限政策: {POLICY_NAME}（Bedrock + Textract）")

    # 3) 建 instance profile（冪等）
    try:
        iam.create_instance_profile(InstanceProfileName=PROFILE_NAME)
        print(f"[3] 建立 instance profile: {PROFILE_NAME}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"[3] instance profile 已存在，沿用: {PROFILE_NAME}")
        else:
            raise

    # 4) 把 role 放進 instance profile（冪等：已存在則略過）
    prof = iam.get_instance_profile(InstanceProfileName=PROFILE_NAME)
    roles_in = [r["RoleName"] for r in prof["InstanceProfile"]["Roles"]]
    if ROLE_NAME not in roles_in:
        iam.add_role_to_instance_profile(
            InstanceProfileName=PROFILE_NAME, RoleName=ROLE_NAME
        )
        print(f"[4] 將 role 加入 instance profile")
        time.sleep(8)  # IAM 傳播需要時間
    else:
        print(f"[4] role 已在 instance profile 中")

    arn = prof["InstanceProfile"]["Arn"]
    print("\n完成。Instance Profile ARN:")
    print(f"  {arn}")
    print(f"\n下一步：開 EC2 時以 --iam-instance-profile Name={PROFILE_NAME} 掛載。")


if __name__ == "__main__":
    main()
