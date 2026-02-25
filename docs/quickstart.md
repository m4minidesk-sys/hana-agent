# 結（Yui）Quick Start Guide

## Prerequisites

| 要件 | バージョン | 確認コマンド |
|------|-----------|------------|
| Python | 3.12+ (推奨: 3.13) | `python3 --version` |
| pip | 最新 | `pip --version` |
| AWS CLI | v2 | `aws --version` |
| AWS credentials | Bedrock アクセス権限付き | `aws sts get-caller-identity` |
| Git | 最新 | `git --version` |

> **Note**: macOS の場合 `brew install python@3.13 awscli git` で一括インストール可能。

## 1. リポジトリのクローン

```bash
git clone https://github.com/m4minidesk-sys/yui-agent.git
cd yui-agent
```

## 2. 仮想環境の作成 + インストール

```bash
# venv 作成
python3.13 -m venv .venv
source .venv/bin/activate

# editable install
pip install -e .
```

インストール確認:
```bash
python -c "import yui; print(yui.__version__)"
# → 0.1.0
```

## 3. 設定ファイルのセットアップ

```bash
# config ディレクトリ + workspace 作成
mkdir -p ~/.yui/workspace

# 設定ファイルコピー
cp config.yaml.example ~/.yui/config.yaml

# デフォルトの AGENTS.md / SOUL.md コピー
cp workspace/*.md ~/.yui/workspace/
```

### config.yaml の主要設定

```yaml
model:
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0  # Bedrock モデルID
  region: us-east-1                                      # AWS リージョン
  max_tokens: 4096                                       # 最大トークン数

tools:
  shell:
    allowlist:       # 実行を許可するコマンド（base name で判定）
      - ls
      - cat
      - grep
      - find
      - python3
      - kiro-cli
      - brew
    blocklist:       # ブロックするパターン（部分一致）
      - "rm -rf /"
      - "rm -rf ~"
      - sudo
      # ... (全18パターン)
    timeout_seconds: 30

  file:
    workspace_root: ~/.yui/workspace  # ファイル操作のルート
```

## 4. AWS 認証の設定

Bedrock へのアクセスに AWS 認証情報が必要です。

```bash
# 方法 A: AWS CLI プロファイル（推奨）
aws configure
# → Access Key ID, Secret Access Key, Region (us-east-1) を入力

# 方法 B: 環境変数
export AWS_ACCESS_KEY_ID=your_key
export AWS_SECRET_ACCESS_KEY=your_secret
export AWS_DEFAULT_REGION=us-east-1

# 方法 C: IAM Identity Center (SSO)
aws configure sso
aws sso login --profile your-profile
```

認証確認:
```bash
aws sts get-caller-identity
# → アカウントID + ARN が表示されればOK

# Bedrock アクセス確認
aws bedrock list-foundation-models --region us-east-1 --query 'modelSummaries[?contains(modelId, `claude`)].modelId' --output text
```

## 5. 起動

```bash
# venv を有効化（新しいターミナルを開いた場合）
cd /path/to/yui-agent
source .venv/bin/activate

# REPL 起動
python -m yui
```

正常起動時の出力:
```
結（Yui） v0.1.0 — Your Unified Intelligence
Type your message or Ctrl+D to exit

You: 
```

## 6. 基本的な使い方

```
You: カレントディレクトリのファイルを一覧して
Yui: [ls を実行して結果を表示]

You: README.md を読んで
Yui: [file_read で内容を表示]

You: この Python ファイルの 10行目を修正して
Yui: [editor で該当行を編集]
```

### キーボードショートカット

| キー | 動作 |
|------|------|
| `↑` / `↓` | コマンド履歴のナビゲーション |
| `Ctrl+D` | 終了 (Goodbye!) |
| `Ctrl+C` | 現在の入力をキャンセル（REPL は継続） |

## Troubleshooting

### `ModuleNotFoundError: No module named 'yui'`
```bash
# editable install をやり直す
source .venv/bin/activate
pip install -e .
```

### `botocore.exceptions.NoCredentialsError`
```bash
# AWS 認証情報を設定
aws configure
# または環境変数を確認
echo $AWS_ACCESS_KEY_ID
```

### `Error: command 'xxx' is not in the allowlist`
```bash
# ~/.yui/config.yaml の tools.shell.allowlist にコマンドを追加
```

### `Error: command blocked by security policy`
```bash
# blocklist に含まれる危険パターンが検出された
# ~/.yui/config.yaml の tools.shell.blocklist を確認
```

### `ConfigError: Invalid YAML in ...`
```bash
# config.yaml の構文エラー。テンプレからやり直す:
cp config.yaml.example ~/.yui/config.yaml
```

## ディレクトリ構成

```
~/.yui/
├── config.yaml          # メイン設定ファイル
├── .yui_history         # REPL 入力履歴（自動生成）
└── workspace/
    ├── AGENTS.md        # エージェント行動ルール
    └── SOUL.md          # エージェントペルソナ
```

## 次のステップ

- **AGENTS.md をカスタマイズ**: エージェントの行動ルールを自分好みに
- **SOUL.md をカスタマイズ**: エージェントのペルソナ・口調を設定
- **config.yaml を調整**: allowlist にプロジェクトで使うコマンドを追加
- **Phase 1 (Slack連携)**: `slack-manifest.yaml` でSlack App作成 → Socket Mode で接続
