"""
AWS Bedrock 連通性檢查
========================
部署 AWS 環境後，用這支腳本確認「憑證 / Region / 模型開通 / 實際呼叫」四關全通。
不寫死任何金鑰，一律從專案根目錄的 .env 讀取（os.environ）。

用法：
    python scripts/check_bedrock.py

四個檢查步驟：
    1) .env 是否讀到必要環境變數（含臨時憑證的 SESSION_TOKEN）
    2) STS 確認憑證有效、抓到帳號身分
    3) 列出 Bedrock 可用模型，確認目標模型已在此 Region 開通
    4) 實際呼叫一次 src/ai_report.generate_report()，確認端到端可產出報告
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"))
except Exception:
    print("! 未安裝 python-dotenv 或載入失敗，改用系統環境變數。")


def _mask(value):
    if not value:
        return "(未設定)"
    return value[:4] + "..." + value[-4:] if len(value) > 8 else "****"


def step1_env():
    print("\n[1/4] 檢查 .env 環境變數")
    region = os.environ.get("BEDROCK_REGION") or os.environ.get("AWS_DEFAULT_REGION")
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    ak = os.environ.get("AWS_ACCESS_KEY_ID")
    sk = os.environ.get("AWS_SECRET_ACCESS_KEY")
    token = os.environ.get("AWS_SESSION_TOKEN")

    print(f"  AWS_ACCESS_KEY_ID      = {_mask(ak)}")
    print(f"  AWS_SECRET_ACCESS_KEY  = {_mask(sk)}")
    print(f"  AWS_SESSION_TOKEN      = {'(已設定)' if token else '(未設定，臨時憑證通常需要)'}")
    print(f"  Region                 = {region or '(未設定)'}")
    print(f"  BEDROCK_MODEL_ID       = {model_id or '(未設定)'}")

    if not ak or not sk:
        print("  X 缺少 AWS 金鑰。請從 Workshop Studio「Get AWS CLI credentials」複製到 .env。")
        return False
    if not region:
        print("  X 缺少 Region。請在 .env 設 BEDROCK_REGION=us-west-2。")
        return False
    print("  OK")
    return True


def step2_sts():
    print("\n[2/4] 確認憑證有效（STS get-caller-identity）")
    try:
        import boto3
        region = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")
        ident = boto3.client("sts", region_name=region).get_caller_identity()
        print(f"  Account = {ident['Account']}")
        print(f"  ARN     = {ident['Arn']}")
        print("  OK")
        return True
    except Exception as e:
        print(f"  X 憑證無效或過期：{type(e).__name__}: {e}")
        print("  → 臨時憑證會過期，請重新從 Workshop Studio 取得並更新 .env。")
        return False


def step3_models():
    print("\n[3/4] 列出 Bedrock 可用模型並確認目標模型已開通")
    region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-west-2"))
    model_id = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
    try:
        import boto3
        client = boto3.client("bedrock", region_name=region)
        resp = client.list_foundation_models()
        ids = [m["modelId"] for m in resp.get("modelSummaries", [])]
        claude = [i for i in ids if "claude" in i.lower()]
        print(f"  此 Region 共 {len(ids)} 個模型，其中 Claude 系列 {len(claude)} 個：")
        for i in claude[:10]:
            print(f"    - {i}")
        # 目標可能是 inference profile（us./global. 前綴），需另查 profile 清單。
        is_profile = model_id.startswith(("us.", "global.", "apac.", "eu."))
        matched = False
        if is_profile:
            profiles = [
                p["inferenceProfileId"]
                for p in client.list_inference_profiles().get(
                    "inferenceProfileSummaries", []
                )
            ]
            matched = model_id in profiles
            if matched:
                print(f"  OK 目標為 inference profile：{model_id}（已在此 Region 提供）。")
        else:
            base_model = model_id.split(":")[0]
            matched = any(base_model in i for i in ids)
            if matched:
                print(f"  OK 目標模型 {model_id} 存在於此 Region。")
        if not matched:
            print(f"  ! 目標 {model_id} 不在清單。可能未開通或 Region 不符。")
            print("    → 到 Bedrock console → Model access 開通，或改用清單中的 ID。")
            print("    → 註：本環境 Claude 僅支援 inference profile，需加 us. 前綴。")
        return True
    except Exception as e:
        print(f"  X 無法列出模型：{type(e).__name__}: {e}")
        print("    → 確認 IAM 有 bedrock:ListFoundationModels 權限，且 Region 正確。")
        return False


def step4_invoke():
    print("\n[4/4] 端到端呼叫 src/ai_report.generate_report()")
    sample = {
        "park_name": "示範幼兒園",
        "district": "板橋區",
        "park_type": "私立",
        "risk_total": 78.5,
        "risk_level": "高",
        "score_financial": 40,
        "score_penalty": 30,
        "score_eval": 8,
        "expense_income_ratio": 1.12,
        "benford_mad": 0.021,
        "beneish_score": 45,
        "iforest_score": 0.7,
        "expense_yoy_pct": 35,
        "penalty_count": 2,
        "eval_grade": "丙",
    }
    try:
        from src.ai_report import generate_report
        text, source = generate_report(sample, prefer_bedrock=True)
        print(f"  來源：{source}")
        print("  報告內容：")
        print("  " + text.replace("\n", "\n  "))
        if source == "bedrock":
            print("\n  OK Bedrock 真的被呼叫成功了。")
        else:
            print("\n  ! 用了 fallback（規則式範本）。若你預期用 Bedrock，")
            print("    回頭看步驟 1-3 哪一關沒過。Demo 仍可正常運作。")
        return True
    except Exception as e:
        print(f"  X 呼叫失敗：{type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("AWS Bedrock 連通性檢查 — Smart Watchdog")
    print("=" * 60)
    ok = step1_env()
    if ok:
        step2_sts()
        step3_models()
    step4_invoke()
    print("\n完成。若步驟 4 顯示 source=bedrock 即代表 AWS 環境部署成功。")
