# Slack App セットアップガイド — 結（Yui）

## 概要

Yui は **Socket Mode** で Slack と接続します。これはアウトバウンド WebSocket 接続のみ（公開URLやngrok不要）で、企業ファイアウォール内でも動作します。

## 1. Slack App の作成

### 方法 A: マニフェストから作成（推奨・30秒）

1. https://api.slack.com/apps にアクセス
2. **「Create New App」** → **「From an app manifest」** を選択
3. ワークスペースを選択
4. YAML タブに `slack-manifest.yaml` の内容を貼り付け
5. **「Create」** をクリック

### 方法 B: 手動作成

1. https://api.slack.com/apps → **「Create New App」** → **「From scratch」**
2. App Name: `Yui` / ワークスペースを選択
3. 以下のセクションで設定を追加

## 2. Bot OAuth Scopes の設定

**OAuth & Permissions** → **Bot Token Scopes** に以下を追加:

| スコープ | 用途 |
|---------|------|
| `app_mentions:read` | @Yui メンションの受信 |
| `channels:history` | パブリックチャンネルのメッセージ読み取り |
| `channels:read` | チャンネル情報取得 |
| `chat:write` | メッセージ送信 |
| `groups:history` | プライベートチャンネルのメッセージ読み取り |
| `groups:read` | プライベートチャンネル情報取得 |
| `im:history` | DM 読み取り |
| `im:read` | DM 情報取得 |
| `im:write` | DM 送信 |
| `mpim:history` | グループDM 読み取り |
| `mpim:read` | グループDM 情報取得 |
| `reactions:read` | リアクション読み取り |
| `reactions:write` | リアクション追加 |
| `files:read` | ファイル読み取り |
| `users:read` | ユーザー情報取得 |

## 3. Socket Mode の有効化

1. **Socket Mode** メニューへ移動
2. **「Enable Socket Mode」** をオンにする
3. App-Level Token を生成:
   - Token Name: `yui-socket`
   - Scope: `connections:write`
   - **「Generate」** をクリック
   - 表示されたトークン（`xapp-` で始まる）をコピー

## 4. Event Subscriptions

1. **Event Subscriptions** → **「Enable Events」** をオンにする
2. **Subscribe to bot events** に以下を追加:
   - `app_mention` — @Yui メンション
   - `message.im` — DM メッセージ
   - `message.channels` — チャンネルメッセージ（オプション）
   - `message.groups` — プライベートチャンネル（オプション）

## 5. App のインストール

1. **Install App** メニューへ移動
2. **「Install to Workspace」** をクリック
3. 権限を確認して **「Allow」**
4. **Bot User OAuth Token**（`xoxb-` で始まる）をコピー

## 6. トークンの設定

### `.env` ファイルに保存（推奨）

```bash
# ~/.yui/.env
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
```

### 環境変数で渡す

```bash
export SLACK_BOT_TOKEN=xoxb-your-bot-token
export SLACK_APP_TOKEN=xapp-your-app-token
```

### config.yaml に記載（非推奨 — トークンがファイルに残る）

```yaml
slack:
  bot_token: xoxb-your-bot-token
  app_token: xapp-your-app-token
```

## 7. 動作確認

```bash
# Yui を起動
source .venv/bin/activate
python -m yui

# Slack で確認:
# 1. Yui をチャンネルに招待: /invite @Yui
# 2. @Yui hello とメンション
# 3. Yui がスレッドで応答すればOK!
```

## トラブルシューティング

### `slack_bolt.errors.BoltError: token must be xoxb-...`
→ Bot Token が正しくない。`xoxb-` で始まるトークンを確認。

### `Connection to Slack failed`
→ App-Level Token（`xapp-`）を確認。Socket Mode が有効か確認。

### `not_in_channel`
→ `/invite @Yui` でチャンネルに招待してからメンション。

### `missing_scope`
→ 不足しているスコープを OAuth & Permissions で追加 → App を再インストール。

### 管理者承認が必要と表示される
→ 多くの企業ワークスペースは App 承認制。管理者にリクエストが自動送信される。
Socket Mode の特徴（公開URL不要、アウトバウンド接続のみ）を説明すると承認されやすい。

## セキュリティ

- **Socket Mode = アウトバウンド WebSocket のみ**: インバウンド接続なし、公開URL不要
- **トークンは `.env` に保管**: git にコミットしない（`.gitignore` に含む）
- **Bot Token のスコープは最小権限**: 必要なスコープのみ付与
- **App-Level Token は `connections:write` のみ**: 最小スコープ
