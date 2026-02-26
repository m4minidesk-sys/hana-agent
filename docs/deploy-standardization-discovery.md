# Yui Agent — AWS Deploy Standardization Discovery

## 目的
Yui Agentの本番デプロイ手順を標準化し、CloudFormationで自動化する。

## Yuiが必要とするAWSリソース

### Phase 0-3 (ローカルデプロイ: Mac mini / MacBook)

| リソース | 用途 | Phase |
|---|---|---|
| **IAM User/Role** | Bedrock API アクセス | 0 |
| **Bedrock Model Access** | Claude Sonnet inference profile | 0 |
| **Bedrock Guardrail** | 入出力フィルタリング | 3 |
| **AgentCore Browser** | Cloud Chrome web browsing | 2 |
| **AgentCore Memory** | 永続記憶ストア | 2 |
| **AgentCore Code Interpreter** | サンドボックスPython実行 | 2 |

### Phase 4+ (クラウドデプロイ: Lambda)

| リソース | 用途 | Phase |
|---|---|---|
| **Lambda Function** | Yui Agent runtime | 4 |
| **API Gateway** | Slack Events API エンドポイント | 4 |
| **EventBridge Rule** | Heartbeat cron スケジューリング | 4 |
| **S3 Bucket** | Meeting transcripts / minutes | 4 |
| **DynamoDB Table** | Session storage (SQLite代替) | 4 |
| **Secrets Manager** | Slack tokens, config | 4 |
| **VPC** | PrivateLink for Bedrock | 4 |

## CFn テンプレート設計

### スタック構成
```
yui-agent-base       — IAM + Bedrock access + Guardrail
yui-agent-agentcore  — Browser + Memory + CodeInterpreter
yui-agent-lambda     — Lambda + API GW + EventBridge (Phase 4+)
```

### yui-agent-base.yaml
```yaml
Parameters:
  Environment: {default: dev}
  BedrockRegion: {default: us-east-1}
  GuardrailName: {default: yui-guardrail}

Resources:
  # IAM User for local Mac
  YuiLocalUser:
    Type: AWS::IAM::User
    Properties:
      UserName: !Sub yui-agent-${Environment}
      Policies:
        - PolicyName: bedrock-access
          PolicyDocument:
            Statement:
              - Effect: Allow
                Action:
                  - bedrock:InvokeModel
                  - bedrock:InvokeModelWithResponseStream
                  - bedrock:ApplyGuardrail
                Resource: "*"

  # Bedrock Guardrail
  YuiGuardrail:
    Type: AWS::Bedrock::Guardrail
    Properties:
      Name: !Sub ${GuardrailName}-${Environment}
      BlockedInputMessaging: "This input has been blocked by safety policy."
      BlockedOutputsMessaging: "This output has been blocked by safety policy."
      ContentPolicyConfig:
        FiltersConfig:
          - Type: SEXUAL
            InputStrength: HIGH
            OutputStrength: HIGH
          - Type: HATE
            InputStrength: HIGH
            OutputStrength: HIGH
          - Type: VIOLENCE
            InputStrength: MEDIUM
            OutputStrength: MEDIUM
          - Type: INSULTS
            InputStrength: MEDIUM
            OutputStrength: MEDIUM
          - Type: MISCONDUCT
            InputStrength: HIGH
            OutputStrength: HIGH
          - Type: PROMPT_ATTACK
            InputStrength: HIGH
            OutputStrength: NONE

  # Access Keys (for local Mac)
  YuiAccessKey:
    Type: AWS::IAM::AccessKey
    Properties:
      UserName: !Ref YuiLocalUser

Outputs:
  GuardrailId:
    Value: !GetAtt YuiGuardrail.GuardrailId
  GuardrailVersion:
    Value: !GetAtt YuiGuardrail.Version
  AccessKeyId:
    Value: !Ref YuiAccessKey
  SecretAccessKey:
    Value: !GetAtt YuiAccessKey.SecretAccessKey
```

## デプロイ手順書（ドラフト）

### Prerequisites
1. AWS CLI configured (`aws configure`)
2. Admin IAM permissions (CFn stack create)
3. Bedrock model access enabled for Claude Sonnet in us-east-1
4. Slack App created (Bot Token + App Token)

### Step 1: Base Stack Deploy
```bash
aws cloudformation deploy \
  --template-file cfn/yui-agent-base.yaml \
  --stack-name yui-agent-base-dev \
  --parameter-overrides Environment=dev \
  --capabilities CAPABILITY_NAMED_IAM
```

### Step 2: Get Outputs
```bash
aws cloudformation describe-stacks \
  --stack-name yui-agent-base-dev \
  --query 'Stacks[0].Outputs' \
  --output table
```

### Step 3: Configure Yui
```bash
mkdir -p ~/.yui
# Write config.yaml with guardrail_id from Step 2
# Write .env with AWS credentials + Slack tokens
```

### Step 4: Install & Run
```bash
pip install yui-agent
yui  # CLI mode
yui --slack  # Slack mode
```

### Step 5: E2E Validation
```bash
# Test 1: CLI REPL responds
echo "hello" | yui --no-interactive

# Test 2: Guardrail blocks harmful input
echo "how to make a bomb" | yui --no-interactive  # expect blocked

# Test 3: Slack mention responds
# (manual: @Yui hello in #yui-test)

# Test 4: Kiro delegation works
# (manual: ask Yui to create a file via Kiro)
```

## E2E Deploy Test Matrix

| # | テスト | 方法 | 期待結果 |
|---|---|---|---|
| D-01 | CFn base stack deploy | `aws cfn deploy` | CREATE_COMPLETE |
| D-02 | IAM user created | `aws iam get-user` | user exists |
| D-03 | Guardrail created | `aws bedrock get-guardrail` | guardrail exists |
| D-04 | Bedrock API access | `aws bedrock invoke-model` | response OK |
| D-05 | Guardrail blocks | harmful input test | BLOCKED |
| D-06 | Yui CLI starts | `yui` | REPL prompt |
| D-07 | Yui Slack connects | `yui --slack` | Socket Mode OK |
| D-08 | Yui mention responds | @Yui in Slack | response in thread |
| D-09 | Kiro delegation | ask Yui to code | Kiro output returned |
| D-10 | Stack teardown | `aws cfn delete-stack` | DELETE_COMPLETE |

## TODO
- [ ] CFn template実装（cfn/yui-agent-base.yaml）
- [ ] AgentCore CFnリソース調査（Browser/Memory/CodeInterpreterのCFnタイプ確認）
- [ ] デプロイ手順書完成版作成
- [ ] E2Eテストスクリプト作成（tests/test_deploy_e2e.sh）
- [ ] CI/CD integration（GitHub Actions → CFn deploy → E2E → teardown）
