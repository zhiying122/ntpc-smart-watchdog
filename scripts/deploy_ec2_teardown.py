"""
EC2 部署清理：終止 EC2 並（可選）移除相關資源，停止計費
========================================================
Demo 結束後執行，避免 EC2 持續計費。預設只終止 EC2 執行個體；
加 --all 連同 Security Group / Key Pair / IAM Role 一併清除。

用法：
    python scripts/deploy_ec2_teardown.py         # 只終止 EC2
    python scripts/deploy_ec2_teardown.py --all    # 全部清除
"""
import os
import sys

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
TAG_NAME = "sw-streamlit-demo"
SG_NAME = "sw-ec2-sg"
KEY_NAME = "sw-ec2-key"
ROLE_NAME = "sw-ec2-bedrock-role"
PROFILE_NAME = "sw-ec2-bedrock-profile"
POLICY_NAME = "sw-bedrock-textract-inline"


def main():
    full = "--all" in sys.argv
    ec2 = boto3.client("ec2", region_name=REGION)

    # 終止所有 sw-streamlit-demo 標籤的執行個體
    desc = ec2.describe_instances(
        Filters=[
            {"Name": "tag:Name", "Values": [TAG_NAME]},
            {"Name": "instance-state-name",
             "Values": ["pending", "running", "stopping", "stopped"]},
        ]
    )
    ids = [i["InstanceId"]
           for r in desc["Reservations"] for i in r["Instances"]]
    if ids:
        ec2.terminate_instances(InstanceIds=ids)
        print(f"終止 EC2: {ids}（停止計費）")
        ec2.get_waiter("instance_terminated").wait(InstanceIds=ids)
        print("EC2 已終止。")
    else:
        print("沒有找到執行中的 sw-streamlit-demo 執行個體。")

    if not full:
        print("\n（僅終止 EC2。若要連 SG/KeyPair/IAM 一併清除，加 --all）")
        return

    # SG
    try:
        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "group-name", "Values": [SG_NAME]}])
        for sg in sgs["SecurityGroups"]:
            ec2.delete_security_group(GroupId=sg["GroupId"])
            print(f"刪除 Security Group: {sg['GroupId']}")
    except ClientError as e:
        print("SG 清除:", e.response["Error"]["Code"])

    # Key pair
    try:
        ec2.delete_key_pair(KeyName=KEY_NAME)
        print(f"刪除 key pair: {KEY_NAME}")
    except ClientError as e:
        print("key pair 清除:", e.response["Error"]["Code"])

    # IAM role + instance profile
    iam = boto3.client("iam", region_name=REGION)
    try:
        iam.remove_role_from_instance_profile(
            InstanceProfileName=PROFILE_NAME, RoleName=ROLE_NAME)
    except ClientError:
        pass
    try:
        iam.delete_instance_profile(InstanceProfileName=PROFILE_NAME)
        print(f"刪除 instance profile: {PROFILE_NAME}")
    except ClientError as e:
        print("profile 清除:", e.response["Error"]["Code"])
    try:
        iam.delete_role_policy(RoleName=ROLE_NAME, PolicyName=POLICY_NAME)
        iam.delete_role(RoleName=ROLE_NAME)
        print(f"刪除 role: {ROLE_NAME}")
    except ClientError as e:
        print("role 清除:", e.response["Error"]["Code"])

    print("\n全部清除完成。")


if __name__ == "__main__":
    main()
