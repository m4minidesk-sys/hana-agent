# 結（Yui）— 完全セットアップガイド

このガイドでは、Yui Agent をゼロから動かすまでの全手順を解説します。
CLI REPL → Slack連携 → オプション機能（Meeting/Workshop）の順に進めます。

---

## 0. Prerequisites（前提条件）

| 項目 | 要件 | 確認コマンド | インストール |
|------|------|-------------|------------|
| macOS | 13.0+ (Ventura) | `sw_vers` | — |
| Python | 3.12+（推奨: 3.13） | `python3 --version` | `brew install python@3.13` |
| AWS CLI | v2 | `aws --version` | `brew install awscli` |
| Git | 最新 | `git --version` | `brew install git` |
| Kiro CLI（任意） | v1.20+ | `~/.local/bin/kiro-cli --version` | [Kiro公式サイト](https://kiro.dev) |

> **一括インストール**: `brew install python@3.13 awscli git`

---

## 1. リポジトリのクローン + インストール

```bash
# Clone
git clone https://github.com/m4minidesk-sys/yui-agent.git
cd yui-agent

# 仮想環境
python3.13 -m venv .venv
source .venv/bin/activate

# コアインストール
pip install -e .

# 確認
python -c "import yui; print('OK')"
```

### オプション依存（必要に応じて追加）

```bash
# Meeting（MTG書き起こし・議事録）
pip install -e ".[meeting]"

# Workshop Testing（AWS Console自動テスト）
pip install -e ".[workshop]"

# Menu Bar UI + Hotkeys（macOSメニューバー）
pip install -e ".[ui,hotkey]"

# 開発用
pip install -e ".[dev]"

# 全部入り
pip install -e ".[meeting,workshop,ui,hotkey,dev]"
```

---

## 2. AWS 認証設定

Bedrock（LLM）へのアクセスに AWS 認証情報が必要です。

### 方法 A: AWS CLI プロファイル（推奨）

```bash
aws configure
# → Access Key ID, Secret Access Key, Region (us-east-1) を入力

# 確認
aws sts get-caller-identity
```

### 方法 B: 環境変数

```bash
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1
```

### 方法 C: IAM Identity Center (SSO)

```bash
aws configure sso
aws sso login --profile your-profile
```

### Bedrock モデルアクセス確認

```bash
# Claude Sonnet が有効か確認
aws bedrock list-foundation-models --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `claude`)].modelId' \
  --output text
```

> ⚠️ モデルが表示されない場合: AWS Console → Bedrock → Model access → Claude Sonnet を有効化

---

## 3. 設定ファイル

```bash
# ディレクトリ作成
mkdir -p ~/.yui/workspace

# 設定ファイルコピー
cp config.yaml.example ~/.yui/config.yaml

# ワークスペースファイルコピー
cp workspace/*.md ~/.yui/workspace/
```

### config.yaml の主要設定

```yaml
model:
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0  # Bedrock inference profile ID
  region: us-east-1
  max_tokens: 4096

tools:
  shell:
    allowlist:       # 実行許可コマンド
      - ls
      - cat
      - grep
      - find
      - python3
      - kiro-cli
      - brew
    blocklist:       # ブロックパターン
      - "rm -rf /"
      - "rm -rf ~"
      - sudo
    timeout_seconds: 30

  file:
    workspace_root: ~/.yui/workspace
```

---

## 4. CLI REPL 起動（Phase 0）

```bash
source .venv/bin/activate
python -m yui
```

正常起動時:
```
結（Yui） v0.1.0 — Your Unified Intelligence
Type your message or Ctrl+D to exit

You: 
```

### 基本操作

```
You: カレントディレクトリのファイルを一覧して
You: README.md を読んで
You: この Python ファイルの 10行目を修正して
```

| キー | 動作 |
|------|------|
| `↑` / `↓` | コマンド履歴 |
| `Ctrl+D` | 終了 |
| `Ctrl+C` | 入力キャンセル |

---

## 5. Slack 連携（Phase 1）

### 5.1 Slack App 作成

1. https://api.slack.com/apps → **「Create New App」** → **「From an app manifest」**
2. ワークスペースを選択
3. YAML タブに `slack-manifest.yaml` の内容を貼り付け
4. **「Create」** をクリック

### 5.2 Socket Mode 有効化

1. **Socket Mode** メニュー → **「Enable Socket Mode」** をオン
2. App-Level Token を生成:
   - Token Name: `yui-socket`
   - Scope: `connections:write`
   - **「Generate」** → `xapp-` トークンをコピー

### 5.3 Event Subscriptions

1. **Event Subscriptions** → **「Enable Events」** をオン
2. **Subscribe to bot events** に追加:
   - `app_mention` — @Yui メンション
   - `message.im` — DM メッセージ
   - `message.channels` — チャンネルメッセージ（任意）
   - `message.groups` — プライベートチャンネル（任意）

### 5.4 Bot OAuth Scopes

**OAuth & Permissions** → **Bot Token Scopes**:

| スコープ | 用途 |
|---------|------|
| `app_mentions:read` | @Yui メンション受信 |
| `channels:history` | パブリックチャンネル読み取り |
| `channels:read` | チャンネル情報取得 |
| `chat:write` | メッセージ送信 |
| `groups:history` | プライベートチャンネル読み取り |
| `groups:read` | プライベートチャンネル情報 |
| `im:history` | DM 読み取り |
| `im:read` | DM 情報取得 |
| `im:write` | DM 送信 |
| `mpim:history` | グループDM 読み取り |
| `mpim:read` | グループDM 情報 |
| `reactions:read` | リアクション読み取り |
| `reactions:write` | リアクション追加 |
| `files:read` | ファイル読み取り |
| `users:read` | ユーザー情報取得 |

### 5.5 App インストール + トークン保存

1. **Install App** → **「Install to Workspace」** → **「Allow」**
2. **Bot User OAuth Token**（`xoxb-`）をコピー
3. `.env` ファイルに保存:

```bash
# ~/.yui/.env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
```

### 5.6 Slack モード起動

```bash
source .venv/bin/activate
python -m yui --slack

# または config.yaml で:
# slack:
#   enabled: true
```

### 5.7 動作確認

1. Slack でチャンネルに Yui を招待: `/invite @Yui`
2. `@Yui hello` とメンション
3. Yui がスレッドで応答すれば成功！ 🎉

---

## 6. AWS インフラ デプロイ（本番向け）

Guardrails + IAM ロール + Secrets Manager を CloudFormation で構築します。

```bash
# CFn スタック作成
aws cloudformation deploy \
  --template-file cfn/yui-agent-base.yaml \
  --stack-name yui-agent-base-dev \
  --parameter-overrides \
    Environment=dev \
    BedrockRegion=us-east-1 \
    ContentFilterStrength=HIGH \
  --capabilities CAPABILITY_NAMED_IAM \
  --region us-east-1

# Output確認
aws cloudformation describe-stacks \
  --stack-name yui-agent-base-dev \
  --query 'Stacks[0].Outputs' \
  --output table
```

### Secrets Manager にトークン保存

```bash
# CFn Output から Secret ARN を取得
SECRET_ARN=$(aws cloudformation describe-stacks \
  --stack-name yui-agent-base-dev \
  --query 'Stacks[0].Outputs[?OutputKey==`SlackTokenSecretArn`].OutputValue' \
  --output text)

# トークンを保存
aws secretsmanager put-secret-value \
  --secret-id $SECRET_ARN \
  --secret-string '{"bot_token":"xoxb-...","app_token":"xapp-..."}'
```

### config.yaml を本番向けに更新

```yaml
# Guardrail ID を追加
guardrails:
  guardrail_id: <CFn Output の GuardrailId>
  guardrail_version: DRAFT
```

---

## 7. デーモン化（launchd）

常駐起動でバックグラウンド実行:

```bash
# デーモンインストール
yui daemon install

# 起動
yui daemon start

# 状態確認
yui daemon status

# 停止
yui daemon stop

# アンインストール
yui daemon uninstall
```

plist は `~/Library/LaunchAgents/dev.yui.agent.plist` にインストールされます。

---

## 8. MCP サーバー連携

外部ツールを MCP プロトコルで動的追加:

```yaml
# config.yaml
mcp:
  servers:
    outlook:
      transport: stdio
      command: "aws-outlook-mcp"
      enabled: true
    custom-server:
      transport: sse
      url: "http://localhost:8080/sse"
      enabled: true
```

```bash
# 接続確認
yui mcp list

# 手動接続/切断
yui mcp connect outlook
yui mcp disconnect outlook
```

---

## 9. Meeting（MTG書き起こし）※オプション

```bash
# 依存インストール
pip install -e ".[meeting]"

# 使い方
yui meeting start     # 録音+書き起こし開始
yui meeting stop      # 停止 → 自動議事録生成
yui meeting status    # 会議情報
yui meeting list      # 過去の会議一覧
```

### メニューバー UI（macOS）

```bash
pip install -e ".[ui,hotkey]"
yui menubar           # メニューバーアイコン起動

# ホットキー:
# ⌘⇧R — 録音開始/停止
# ⌘⇧S — ステータス表示
# ⌘⇧M — ミュート切替
```

---

## 10. Workshop Testing ※オプション

```bash
# 依存インストール
pip install -e ".[workshop]"

# Playwright ブラウザインストール
playwright install chromium

# Workshop テスト実行
yui workshop test <workshop-studio-url> --record --cleanup

# ドライラン（実行せず解析のみ）
yui workshop test <url> --dry-run

# 過去のテスト一覧
yui workshop list-tests

# レポート表示
yui workshop show-report <test-id>
```

Workshop Testing には AWS Console へのログイン情報が必要:

```bash
# ~/.yui/.env に追加
YUI_CONSOLE_PASSWORD=your_console_password
```

```yaml
# config.yaml
workshop:
  test:
    console_auth:
      method: iam_user        # iam_user | federation | sso
      account_id: "123456789012"
      username: "workshop-test-user"
```

---

## トラブルシューティング

| エラー | 原因 | 解決 |
|--------|------|------|
| `ModuleNotFoundError: No module named 'yui'` | インストール未完了 | `pip install -e .` |
| `NoCredentialsError` | AWS認証未設定 | `aws configure` |
| `command 'xxx' is not in the allowlist` | コマンド制限 | config.yaml の allowlist に追加 |
| `command blocked by security policy` | blocklist に該当 | config.yaml の blocklist を確認 |
| `ConfigError: Invalid YAML` | config.yaml 構文エラー | `cp config.yaml.example ~/.yui/config.yaml` |
| `slack_bolt.errors.BoltError: token must be xoxb-` | Bot Token 誤り | `xoxb-` で始まるか確認 |
| `Connection to Slack failed` | App Token 誤り | `xapp-` で始まるか確認 / Socket Mode 有効か |
| `not_in_channel` | Yui 未招待 | `/invite @Yui` |
| `missing_scope` | OAuth スコープ不足 | OAuth & Permissions で追加 → 再インストール |
| Playwright 未インストール | Workshop 依存 | `pip install -e ".[workshop]" && playwright install chromium` |
| `No audio device found` | マイク未接続 | System Preferences → Sound で確認 |

---

## ディレクトリ構成

```
~/.yui/
├── config.yaml          # メイン設定ファイル
├── .env                 # シークレット（SLACK_BOT_TOKEN 等）
├── .yui_history         # REPL 入力履歴（自動生成）
├── sessions/            # SQLite セッションDB（自動生成）
├── workshop-tests/      # Workshop テスト結果（自動生成）
│   └── {test-id}/
│       ├── report.md
│       ├── videos/
│       └── screenshots/
└── workspace/
    ├── AGENTS.md        # エージェント行動ルール
    ├── SOUL.md          # エージェントペルソナ
    └── MEMORY.md        # 長期記憶
```

---

## 関連ドキュメント

| ドキュメント | 内容 |
|-------------|------|
| `README.md` | プロジェクト概要 |
| `requirements.md` | 要件定義書 |
| `cfn/yui-agent-base.yaml` | CloudFormation テンプレート |
| `slack-manifest.yaml` | Slack App マニフェスト |
| `docs/workshop-testing-discovery.md` | Workshop Testing 設計書 |
