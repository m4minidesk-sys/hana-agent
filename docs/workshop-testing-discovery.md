# Phase 4: AWS Workshop Auto-Execution Testing — Discovery Spec

## 概要
Yui Agent の新機能として、AWS Workshop Studio のワークショップコンテンツを
自動的に実行・検証する機能を追加する。

ワークショップ作者がコンテンツを公開する前に、「手順通りにやったら本当に動くか」を
AIエージェントが自動でウォークスルーし、テスト結果をレポートする。

## ユースケース

### Primary: ワークショップ品質保証（QA）
- ワークショップ作者 → コンテンツ作成 → Yui に自動テスト依頼
- Yui がワークショップの手順をステップバイステップで実行
- 各ステップの成功/失敗を記録
- テスト結果レポートを生成

### Secondary: ワークショップ定期回帰テスト
- 既存ワークショップがAWSサービス更新で壊れてないか定期チェック
- CronやEventBridgeで週次実行
- 失敗検知 → Slack通知

---

## アーキテクチャ

```
┌─────────────────────────────────────────────────┐
│                 Yui Workshop Tester              │
│                                                  │
│  ┌──────────┐  ┌───────────┐  ┌──────────────┐ │
│  │ Content  │  │  Step     │  │  Executor    │ │
│  │ Parser   │→│ Planner   │→│ (CLI/Browser)│ │
│  │          │  │           │  │              │ │
│  └──────────┘  └───────────┘  └──────────────┘ │
│       ↑                             ↑           │
│  ┌──────────┐                ┌──────────────┐  │
│  │Workshop  │                │  AWS Account │  │
│  │ Content  │                │  (temporary) │  │
│  │(MD/HTML) │                │              │  │
│  └──────────┘                └──────────────┘  │
└─────────────────────────────────────────────────┘
```

### コンポーネント

| # | コンポーネント | 役割 | 実装 |
|---|---|---|---|
| 1 | Content Parser | ワークショップMD/HTMLからステップ抽出 | Python + BedrockでLLM解析 |
| 2 | Step Planner | ステップを実行可能なアクションに変換 | Bedrock Converse |
| 3 | CLI Executor | AWS CLI / shell コマンド実行 | subprocess + safe_shell |
| 4 | Browser Executor | Console操作の自動化 | AgentCore Browser or Playwright |
| 5 | CFn Provisioner | テスト環境の自動構築/削除 | boto3 CloudFormation |
| 6 | Validator | 期待結果との照合 | Bedrock + AWS SDK checks |
| 7 | Reporter | テスト結果レポート生成 | Markdown + Slack通知 |

---

## ワークフロー

### 1. テスト開始
```bash
yui workshop test <workshop-url-or-path> [--account <account-id>] [--cleanup]
```

### 2. コンテンツ取得
- Workshop Studio URL → スクレイピング（ブラウザ自動化）
- GitHub URL → `git clone` or API fetch
- ローカルパス → 直接読み込み

### 3. ステップ解析（LLM）
Bedrockに全コンテンツを送り、構造化ステップを抽出:
```json
{
  "workshop": "Building Serverless Apps",
  "steps": [
    {
      "id": 1,
      "title": "Deploy the base infrastructure",
      "type": "cfn_deploy",
      "action": "aws cloudformation deploy --template-file template.yaml ...",
      "expected": "Stack CREATE_COMPLETE",
      "timeout_seconds": 300
    },
    {
      "id": 2,
      "title": "Verify the Lambda function",
      "type": "cli_check",
      "action": "aws lambda get-function --function-name MyFunction",
      "expected": "Function exists with runtime python3.12",
      "timeout_seconds": 30
    },
    {
      "id": 3,
      "title": "Test the API endpoint",
      "type": "http_test",
      "action": "curl -s https://{api-id}.execute-api.us-east-1.amazonaws.com/prod/",
      "expected": "HTTP 200, response contains 'Hello'",
      "timeout_seconds": 30
    }
  ]
}
```

### 4. ステップ実行
各ステップを順次実行:
- `cfn_deploy` → CloudFormation stack create/update
- `cli_check` → AWS CLI コマンド実行 + 出力検証
- `console_check` → ブラウザでConsole画面を確認（AgentCore Browser）
- `http_test` → HTTP リクエスト + レスポンス検証
- `code_run` → Cloud9/ローカルでコード実行
- `manual_step` → LLMが判断: スキップまたは代替実行

### 5. 結果検証
各ステップの出力をBedrockで判定:
- ✅ PASS: 期待通りの結果
- ❌ FAIL: 期待と異なる結果（エラーメッセージ付き）
- ⏭ SKIP: 手動ステップ（Console画面操作等）
- ⏱ TIMEOUT: 実行タイムアウト

### 6. レポート生成
```markdown
# Workshop Test Report — 2026-02-26

## Workshop: Building Serverless Apps
## Source: https://catalog.workshops.aws/serverless/en-US

### Summary
- Total Steps: 15
- Passed: 12 ✅
- Failed: 2 ❌
- Skipped: 1 ⏭
- Duration: 23m 45s
- AWS Cost (estimated): $0.42

### Failed Steps
| # | Step | Error |
|---|---|---|
| 7 | Deploy API Gateway | CFn CREATE_FAILED: IAM role not found |
| 11 | Test WebSocket | Connection timeout after 30s |

### Recommendations
1. Step 7: IAM role ARN in template.yaml references deleted role
2. Step 11: WebSocket URL has changed, update docs
```

### 7. クリーンアップ
- `--cleanup` フラグ時: テスト用CFnスタック全削除
- リソース一覧をレポートに記載

---

## Step Types

| Type | 説明 | Executor |
|---|---|---|
| `cfn_deploy` | CloudFormation スタック作成/更新 | boto3 CFn |
| `cli_command` | AWS CLI コマンド実行 | subprocess |
| `cli_check` | CLI出力の検証 | subprocess + LLM判定 |
| `http_test` | HTTP エンドポイントテスト | requests/curl |
| `console_navigate` | AWS Console画面操作 | AgentCore Browser |
| `console_verify` | Console画面の状態確認 | AgentCore Browser + LLM |
| `code_run` | コード実行（Python/Node等） | subprocess or CodeInterpreter |
| `code_deploy` | SAM/CDK/Serverless deploy | subprocess |
| `manual_step` | 手動操作（LLM判断でスキップ/代替） | — |
| `wait` | リソース準備待ち | time.sleep + ポーリング |

---

## Config

```yaml
workshop:
  test:
    aws_account_id: ""  # テスト用AWSアカウント
    region: us-east-1
    cleanup_after_test: true
    timeout_per_step_seconds: 300
    max_total_duration_minutes: 60
    max_cost_usd: 5.0  # コストガード
    browser_enabled: true  # Console検証有効
    parallel_steps: false  # ステップ並列実行（将来）
  report:
    format: markdown
    slack_notify: true
    slack_channel: ""
    save_path: ~/.yui/workshop-tests/
```

---

## ACs (Acceptance Criteria)

| # | AC | 内容 |
|---|---|---|
| AC-70 | Workshop content parsing | ワークショップMD/HTMLからステップ抽出 |
| AC-71 | Step planning | ステップを実行可能アクションに変換 |
| AC-72 | CLI execution | AWS CLIコマンドの自動実行 |
| AC-73 | CFn deploy/delete | CloudFormationスタック自動管理 |
| AC-74 | HTTP testing | APIエンドポイントの自動テスト |
| AC-75 | Result validation | LLMによる結果判定（PASS/FAIL/SKIP） |
| AC-76 | Test report | 構造化テストレポート生成 |
| AC-77 | Slack notification | テスト結果のSlack通知 |
| AC-78 | Cleanup | テスト後のAWSリソース自動削除 |
| AC-79 | Cost guard | コスト上限超過時のテスト中断 |
| AC-80 | CLI entry point | `yui workshop test <url>` コマンド |
| AC-81 | Timeout handling | ステップ/全体タイムアウト |
| AC-82 | Console verification | ブラウザでのConsole画面検証（AgentCore Browser） |
| AC-83 | Regression mode | 定期回帰テスト（cron/EventBridge） |

---

## 依存関係

| 依存 | 用途 | Phase |
|---|---|---|
| Bedrock Converse | ステップ解析 + 結果判定 | 4 |
| AgentCore Browser | Console画面操作 | 4 (opt) |
| boto3 CloudFormation | スタック管理 | 4 |
| requests | HTTP テスト | 4 |
| Workshop Studio API | コンテンツ取得 | 4 (if available) |

---

## 実装計画

| サブフェーズ | 内容 | 見積 |
|---|---|---|
| 4a | Content Parser + Step Planner | 1日 |
| 4b | CLI/CFn Executor + Validator | 1日 |
| 4c | Reporter + Slack通知 | 0.5日 |
| 4d | Browser Executor (Console検証) | 1日 |
| 4e | Regression mode + Cost guard | 0.5日 |

---

## Open Questions (hanさん確認待ち)
1. Workshop Studioのコンテンツ取得方法（URL直接 or GitHub or ローカル）
2. テスト用AWSアカウントの準備方法（専用アカウント? Workshop Studio Event?）
3. Console操作検証の要否
4. 対象ワークショップのジャンル
