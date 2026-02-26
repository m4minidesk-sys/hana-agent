# Yui Agent — デプロイ手順書

## 概要
Yui Agent をローカル Mac にデプロイするための標準手順。
AWS CloudFormation でインフラをプロビジョニングし、ローカルで Yui を起動する。

---

## Prerequisites

| 項目 | 要件 | 確認コマンド |
|---|---|---|
| macOS | 13.0+ (Ventura) | `sw_vers` |
| Python | 3.12+ | `python3 --version` |
| AWS CLI | v2 | `aws --version` |
| AWS権限 | CloudFormation + IAM + Bedrock | `aws sts get-caller-identity` |
| Bedrock Model Access | Claude Sonnet 有効化済み | AWS Console → Bedrock → Model access |
| Slack App | Bot Token + App Token取得済み | Slack API Dashboard |
| Kiro CLI (optional) | v1.20+ | `~/.local/bin/kiro-cli --version` |

---

## Step 1: AWS インフラ デプロイ

### 1.1 CFn スタック作成

```bash
# Clone repo
git clone https://github.com/m4minidesk-sys/yui-agent.git
cd yui-agent

# Deploy base stack
aws cloudformation deploy \
  --template-file cfn/yui-agent-base.yaml \
  --stack-name yui-agent-base-dev \
  --parameter-overrides \
    Environment=dev \
    BedrockRegion=us-east-1 \
    ContentFilterStrength=HIGH \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1
```

### 1.2 Output確認

```bash
aws cloudformation describe-stacks \
  --stack-name yui-agent-base-dev \
  --query 'Stacks[0].Outputs' \
  --output table \
  --region us-east-1
```

以下の値をメモ:
- `YuiAccessKeyId`
- `YuiSecretAccessKey`
- `GuardrailId`
- `GuardrailVersion`

### 1.3 Slack Secrets 更新

```bash
aws secretsmanager update-secret \
  --secret-id yui-agent/dev/slack \
  --secret-string '{"bot_token":"xoxb-YOUR-TOKEN","app_token":"xapp-YOUR-TOKEN"}' \
  --region us-east-1
```

---

## Step 2: ローカル環境セットアップ

### 2.1 Yui インストール

```bash
# Basic install
pip install yui-agent

# With meeting feature
pip install yui-agent[meeting]

# With all optional features
pip install yui-agent[all]
```

### 2.2 AWS認証設定

```bash
# AWS credentials for Yui user
aws configure --profile yui-dev
# Enter: AccessKeyId, SecretAccessKey, Region: us-east-1

# Set default profile
export AWS_PROFILE=yui-dev
```

### 2.3 Config作成

```bash
mkdir -p ~/.yui

cat > ~/.yui/config.yaml << 'EOF'
model:
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  region: us-east-1

guardrail:
  id: <GuardrailId from Step 1.2>
  version: <GuardrailVersion from Step 1.2>

slack:
  enabled: true

session:
  db_path: ~/.yui/sessions.db
  compaction_threshold: 50

heartbeat:
  enabled: true
  interval_minutes: 15
  active_hours:
    start: "07:00"
    end: "24:00"

tools:
  shell:
    allowlist: [ls, cat, head, tail, grep, find, wc, date, echo, pwd, git, python3, pip, npm]
    blocklist: [rm -rf /, sudo rm, mkfs, dd if=, shutdown, reboot]
  kiro:
    binary_path: ~/.local/bin/kiro-cli
    timeout: 300

workspace:
  base_dir: ~/.yui/workspace
EOF
```

### 2.4 Slack Token設定

```bash
cat > ~/.yui/.env << 'EOF'
SLACK_BOT_TOKEN=xoxb-YOUR-BOT-TOKEN
SLACK_APP_TOKEN=xapp-YOUR-APP-TOKEN
BYPASS_TOOL_CONSENT=true
EOF

chmod 600 ~/.yui/.env
```

---

## Step 3: 起動確認

### 3.1 CLI モード

```bash
yui
# Expected: "結（Yui）v0.1.0 — Type 'exit' to quit"
# Type: hello
# Expected: Bedrock response
```

### 3.2 Slack モード

```bash
yui --slack
# Expected: "⚡ Bolt app is running!"
# Test: @Yui hello in Slack
```

### 3.3 Daemon モード

```bash
yui daemon start
yui daemon status
# Expected: "running (pid: XXXX)"
```

---

## Step 4: E2E バリデーション

自動テストスクリプト:

```bash
./tests/test_deploy_e2e.sh
```

### 手動テストマトリクス

| # | テスト | 手順 | 期待結果 | Pass? |
|---|---|---|---|---|
| D-01 | CFn stack deployed | `aws cfn describe-stacks` | CREATE_COMPLETE | ☐ |
| D-02 | IAM user exists | `aws iam get-user --user-name yui-agent-dev` | user returned | ☐ |
| D-03 | Guardrail exists | `aws bedrock get-guardrail --guardrail-id <id>` | guardrail returned | ☐ |
| D-04 | Bedrock API responds | `yui` → "hello" | response received | ☐ |
| D-05 | Guardrail blocks | `yui` → harmful input | "blocked by safety" | ☐ |
| D-06 | CLI REPL works | `yui` | prompt appears | ☐ |
| D-07 | Slack connects | `yui --slack` | Socket Mode OK | ☐ |
| D-08 | Mention responds | @Yui hello | thread reply | ☐ |
| D-09 | Kiro delegates | ask Yui to code | Kiro output | ☐ |
| D-10 | Daemon runs | `yui daemon start/status` | running | ☐ |
| D-11 | Session persists | restart Yui, check history | history retained | ☐ |
| D-12 | Heartbeat fires | wait interval | HEARTBEAT.md processed | ☐ |
| D-13 | Stack teardown | `aws cfn delete-stack` | DELETE_COMPLETE | ☐ |

---

## Troubleshooting

| 症状 | 原因 | 対処 |
|---|---|---|
| `AccessDeniedException` | IAM権限不足 | CFn outputs確認、aws configure --profile確認 |
| `ModelNotReadyException` | Bedrock model access未有効化 | AWS Console → Bedrock → Model access で有効化 |
| `Socket Mode connection failed` | Slack token無効 | .env のトークン確認、App設定でSocket Mode有効確認 |
| `Guardrail not found` | GuardrailId設定ミス | `aws bedrock list-guardrails` で確認 |
| `Kiro CLI not found` | パス不正 | `ls ~/.local/bin/kiro-cli` 確認 |

---

## クリーンアップ

```bash
# Daemon停止
yui daemon stop

# CFnスタック削除（全リソース削除）
aws cloudformation delete-stack \
  --stack-name yui-agent-base-dev \
  --region us-east-1

# ローカル設定削除
rm -rf ~/.yui
```

---

## 変更履歴

| 日付 | 変更内容 |
|---|---|
| 2026-02-26 | 初版作成 |
