# Phase 2-3 Implementation Discovery Spec

## 概要
Phase 2残り + Phase 2.5 + Phase 3 の全残ACsを一括実装する。

---

## Phase 2 残り — AgentCore Cloud Tools 実接続

### AC-17: AgentCore Browser Tool
**SDK**: `bedrock_agentcore.tools.browser_client.BrowserClient`
- `BrowserClient` で cloud Chrome セッション作成
- `browser_session` コンテキストマネージャーでURL閲覧
- Strands `@tool` でラップして `web_browse(url: str) -> str` を実装
- 現在の stub (`agentcore.py`) を実SDK呼び出しに置換

### AC-18: AgentCore Memory
**SDK**: `bedrock_agentcore.memory.client.MemoryClient`
- Strands統合: `bedrock_agentcore.memory.integrations.strands.session_manager.AgentCoreMemorySessionManager`
- `MemoryClient` で memory store 作成 → store/retrieve
- 現在の stub を実SDK呼び出しに置換
- config.yaml に `memory.namespace` 追加

### AC-18a: AgentCore Code Interpreter
**SDK**: `bedrock_agentcore.tools.code_interpreter_client.CodeInterpreter`
- `CodeInterpreter` + `code_session` でサンドボックスPython実行
- Strands `@tool` でラップして `code_execute(code: str) -> str` を実装
- 現在の stub を実SDK呼び出しに置換

### AC-19: Kiro CLI timeout (>300s)
- 既存 `kiro_delegate` に `timeout=300` パラメータ追加
- `subprocess.TimeoutExpired` → graceful error message

### AC-19a: Kiro CLI missing at startup
- 既存 `agent.py` で `kiro_path.exists()` チェック済み
- ただし startup時にexitせずwarning止まり → exit code 1 に変更

---

## Phase 2.5 — Meeting Transcription & Minutes

### 依存パッケージ (pyproject.toml [meeting] extras)
- `mlx-whisper` — Apple Silicon Whisper
- `rumps` — macOS menu bar
- `pynput` — global hotkeys
- `pyaudio` or `sounddevice` — audio capture

### AC-40〜42: Core recording + Whisper
- `src/yui/meeting/recorder.py` — ScreenCaptureKit audio capture
- `src/yui/meeting/transcriber.py` — mlx-whisper リアルタイム transcription
- `yui meeting start/stop/status` CLI commands

### AC-43〜44: Audio sources
- ScreenCaptureKit for system audio (Zoom/Teams/Chime)
- Microphone mixing when `include_mic: true`

### AC-45〜47: Bedrock minutes generation
- `src/yui/meeting/minutes.py` — Bedrock Converse で議事録生成
- 保存先: `~/.yui/meetings/<meeting_id>/minutes.md`
- Slack通知: meeting.slack_notify config

### AC-48〜50: CLI commands
- `yui meeting list` — 過去の議事録一覧
- `yui meeting search "keyword"` — 全文検索
- Real-time analysis updates (60s interval)

### AC-51: Opt-in install
- `pip install yui-agent[meeting]` で追加依存

### AC-52〜61: Menu bar UI + Hotkeys
- rumps menu bar app
- pynput global hotkeys (⌘⇧R, ⌘⇧S, ⌘⇧M)
- Unix socket IPC (`~/.yui/yui.sock`)
- launchd auto-start

---

## Phase 3 — Guardrails + Heartbeat + Daemon + MCP

### AC-20: Bedrock Guardrails
**Strands SDK統合 (ゼロコード追加)**:
```python
BedrockModel(
    model_id=...,
    guardrail_id="<guardrail-id>",
    guardrail_version="DRAFT",
    guardrail_latest_message=False,  # full history (secure)
)
```
- AWS Bedrock Console で Guardrail 作成が必要 (hanさん側)
- config.yaml に `guardrail.id` / `guardrail.version` 追加
- 10ターンごとの full-history check (guardrail_latest_message=true 時)

### AC-21〜22: Heartbeat
- `src/yui/heartbeat.py` — HEARTBEAT.md 読み込み + SHA256 integrity
- `threading.Timer` で定期実行
- active_hours 制限
- 改竄検知 → Slack通知 + 停止

### AC-23〜25: Daemon (launchd)
- `src/yui/daemon.py` — `yui daemon start/stop/status`
- plist生成: `~/Library/LaunchAgents/com.yui.agent.plist`
- KeepAlive + ThrottleInterval(5s)
- RotatingFileHandler logging

### AC-25a〜25c: MCP Server Integration
- config.yaml の `mcp.servers` セクション
- 起動時に static MCP servers 接続
- `aws-outlook-mcp` for calendar/mail
- Dynamic MCP connection at runtime

### AC-26〜39: Error Handling (negative tests)
- E-01〜E-20 の全14エラーシナリオ
- pytest parametrize でネガティブテスト

---

## Implementation Order

1. **Phase 2残り** (AgentCore実接続) — 最も依存少ない
   - `agentcore.py` の stub → 実SDK
   - kiro_delegate timeout 追加
   - テスト追加
   
2. **Phase 3 Core** (Guardrails + Heartbeat + Daemon)
   - Guardrails: config追加のみ (SDK側で処理)
   - Heartbeat: 新規モジュール
   - Daemon: 新規モジュール + plist
   - エラーハンドリング: negative tests

3. **Phase 2.5** (Meeting) — 独立機能、最も大きい
   - 依存パッケージ多い
   - macOS固有API (ScreenCaptureKit)
   - 段階的に: recorder → transcriber → minutes → UI

4. **MCP** (AC-25a〜c) — Phase 3 の一部
   - Strands MCP統合調査が必要

---

## 技術検証済み事項
- ✅ `bedrock_agentcore` SDK インストール済み、API構造確認済み
- ✅ `BedrockModel` に `guardrail_id`/`guardrail_version` パラメータあり
- ✅ `AgentCoreMemorySessionManager` で Strands ↔ Memory 統合可能
- ✅ `BrowserClient` + `CodeInterpreter` のクラス構造確認済み
- 🟡 mlx-whisper 未インストール（Meeting phase で追加）
- 🟡 AWS Guardrail リソース未作成（hanさんの AWS Console 操作 or CFn）
- 🟡 MCP サーバーの Strands SDK 統合方法要調査
