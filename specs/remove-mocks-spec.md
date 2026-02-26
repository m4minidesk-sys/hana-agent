# Mock排除 一括変換 — Kiro委任用spec

## 目的
全テストファイルから `unittest.mock` (MagicMock, @patch, Mock) を完全排除し、
実サービス/実環境で全テストが通るように書き換える。

## 完了済み
- `test_safe_shell.py` — 27 tests, mock 0
- `test_git_tool.py` — 19 tests, mock 0
- `test_security.py` — 26 tests, mock 0 (新規作成済み)
- `test_real_execution.py` — 書き換え不要（元々mock-free）

## 残りのファイル一覧（33ファイル）

### カテゴリ1: ローカル実行可能（外部サービス不要）
- `test_config.py` — config load/validate は実ファイルで可能
- `test_session.py` — SQLite は tmp_path で実行可能
- `test_cli.py` — REPL は stdin mock 必要 → stdin redirect で対応
- `test_meeting_ipc.py` — Unix socket で実行可能

### カテゴリ2: AWS Bedrock 実呼び出し
- `test_agent.py` — BedrockModel を実呼び出し
- `test_converse_errors.py` — エラーハンドリングは実BedrockErrorHandler
- `test_error_handling.py` — 実SessionManager + 実config
- `test_guardrails_e2e.py` — 実Bedrock Guardrails API

### カテゴリ3: Slack 実呼び出し
- `test_slack_adapter.py` — 実token読み込み
- `test_slack_e2e.py` — 実Slack API呼び出し

### カテゴリ4: Kiro CLI 実呼び出し
- `test_kiro_delegate.py` — 実kiro-cli呼び出し
- `test_kiro_tools.py` — 実Kiro CLI + Reflexion

### カテゴリ5: Workshop/Meeting (ハードウェア依存)
- `test_executor.py` — Playwright 必須
- `test_workshop_*.py` (5 files) — Playwright + Bedrock
- `test_meeting_*.py` (6 files) — Whisper/ScreenCaptureKit/sounddevice
- `test_console_auth.py` — Playwright
- `test_video_recorder.py` — ScreenCaptureKit

### カテゴリ6: MCP/Autonomy
- `test_mcp.py` — MCP server 実接続
- `test_reflexion.py` — 実BedrockModel
- `test_evaluator.py` — SQLite + 実呼び出し
- `test_improver.py` — 実BedrockModel
- `test_conflict.py` — 実BedrockModel (if exists)

### カテゴリ7: その他
- `test_agentcore.py` — AgentCore SDK
- `test_agentcore_e2e.py` — AgentCore 実API
- `test_kb_search.py` — Bedrock KB + Brave Search
- `test_cfn_validation.py` — CloudFormation template
- `test_generate_icon.py` — Bedrock Nova Canvas

## 変換ルール

1. `from unittest.mock import ...` → 削除
2. `@patch(...)` → 削除。テスト内で実オブジェクトを使う
3. `MagicMock()` → 実オブジェクト/fixture
4. `mock_xxx.return_value = ...` → 実呼び出し
5. `mock_xxx.assert_called_once()` → 実結果の assert に置き換え

## ハードウェア依存の対処

ハードウェア不在時は `pytest.importorskip` または `pytest.mark.skipif` で:
```python
pytest.importorskip("sounddevice")  # Meeting
pytest.importorskip("playwright")   # Workshop
```

## AWS/Slack 依存の対処

環境変数なしでも skip せず、**実際に呼ぶ**:
- AWS: `~/.aws/credentials` から認証（Mac miniにある）
- Slack: `~/.yui/.env` からトークン読み込み
- Bedrock: `us.anthropic.claude-sonnet-4-20250514-v1:0`
- Kiro: `~/.local/bin/kiro-cli`

## テスト実行

```bash
cd /Users/m4mac/.openclaw/workspace/yui-agent
source .venv/bin/activate
python -m pytest tests/ -v --tb=short
```

全テストが PASS すること。skip は最小限（ハードウェア不在のみ）。
