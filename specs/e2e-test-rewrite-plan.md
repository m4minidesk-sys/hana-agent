# E2E Test Rewrite Plan — fullspec

**目的**: 全993テストを mock排除 + skip排除 で全PASS (skip 0, fail 0) にする

## 現状分析

| 指標 | 値 |
|---|---|
| テスト総数 | 993 |
| PASSED | 937 |
| SKIPPED | 56 |
| FAILED | 0 |
| mockファイル数 | 35/46 |
| mock使用箇所 | 627 |

## スキップ理由の分類（56件）

| ファイル | Skip数 | 原因 | 依存 |
|---|---|---|---|
| `test_agentcore_e2e.py` | 24 | `AGENTCORE_ENDPOINT` env未設定 | AgentCore Runtime |
| `test_aya_yui_integration.py` | 9 | `AYA_BOT_TOKEN` env未設定 | AYA Slack token |
| `test_slack_live.py` | 7 | `YUI_SLACK_BOT_TOKEN` env未設定 | Slack API |
| `test_integration.py` | 7 | `YUI_AWS_E2E` env未設定 | Bedrock + Slack |
| `test_guardrails_e2e.py` | 4 | `YUI_TEST_GUARDRAIL_ID` env未設定 | Bedrock Guardrails |
| `test_cfn_validation.py` | 2 | `YUI_AWS_E2E` env未設定 | CloudFormation |
| `test_converse_errors.py` | 1 | `YUI_AWS_E2E` env未設定 | Bedrock |
| `test_kb_search.py` | 2 | `AWS_AVAILABLE` flag | Bedrock KB |

## 段階的テスト計画

### Phase T-1: ローカル純粋テスト（mock排除）— 所要時間: 30分
**対象**: mock使用しているが外部サービス不要の11ファイル

| ファイル | テスト数 | 依存 |
|---|---|---|
| `test_security.py` | 26 | subprocess (safe_shell) |
| `test_meeting_ipc.py` | 7 | Unix socket (ローカル) |
| `test_evaluator.py` | 11 | SQLite + ローカル |
| `test_conflict.py` | (確認) | ローカルロジック |
| `test_meeting_hotkeys.py` | 12 | pynput (ローカル) |
| `test_meeting_menubar.py` | 20 | rumps (ローカル) |
| `test_video_recorder.py` | 10 | ScreenCaptureKit (ローカルHW) |
| `test_meeting_recorder.py` | 6 | sounddevice (ローカルHW) |
| `test_meeting_transcriber.py` | 5 | mlx_whisper (ローカル) |
| `test_meeting_manager.py` | 8 | 上記の組合せ |
| `test_meeting_minutes.py` | 15 | Bedrock Converse |

**ゴール**: mock 0、skip 0、全PASS
**ブランチ**: `feat/e2e-phase-t1`
**検証**: `pytest tests/test_security.py tests/test_meeting_ipc.py ... -v`

### Phase T-2: AWS Bedrock テスト（mock排除 + skip排除）— 所要時間: 45分
**対象**: Bedrock API呼び出しのmock排除 + E2E skip解除

| ファイル | テスト数 | 依存 |
|---|---|---|
| `test_reflexion.py` | 8 | Bedrock Converse |
| `test_improver.py` | 6 | Bedrock Converse |
| `test_guardrails_e2e.py` | 4 | Bedrock Guardrails |
| `test_converse_errors.py` | (skip分) | Bedrock |
| `test_integration.py` (AWS部) | 3 | Bedrock |
| `test_generate_icon.py` | 12 | Bedrock Nova Canvas |
| `test_kb_search.py` | 12 | Bedrock KB + Web Search |
| `test_agentcore.py` | 8 | AgentCore SDK |
| `test_agentcore_e2e.py` | 24 | AgentCore Runtime |
| `test_cfn_validation.py` | 2 | CloudFormation |

**前提**: 環境変数 `YUI_AWS_E2E=1` 設定、Guardrail作成、AgentCore endpoint設定
**ゴール**: mock 0、skip 0、Bedrock実呼び出し
**ブランチ**: `feat/e2e-phase-t2`

### Phase T-3: Slack テスト（mock排除 + skip排除）— 所要時間: 30分
**対象**: Slack API mock排除 + live test skip解除

| ファイル | テスト数 | 依存 |
|---|---|---|
| `test_slack_e2e.py` | 24 | Slack API (実) |
| `test_slack_live.py` | 7 | Slack API (実) |
| `test_integration.py` (Slack部) | 2 | Slack API (実) |
| `test_aya_yui_integration.py` | 9 | AYA + Yui Slack |

**前提**: `YUI_SLACK_BOT_TOKEN`, `YUI_SLACK_APP_TOKEN` 設定済み
**ゴール**: mock 0、skip 0、#yui-test で実通信
**ブランチ**: `feat/e2e-phase-t3`

### Phase T-4: Kiro + Workshop テスト（mock排除）— 所要時間: 45分
**対象**: Kiro CLI + Playwright + Workshop系

| ファイル | テスト数 | 依存 |
|---|---|---|
| `test_kiro_tools.py` | 12 | Kiro CLI + Bedrock |
| `test_console_auth.py` | 8 | Playwright |
| `test_executor.py` | 15 | Playwright |
| `test_workshop_scraper.py` | 16 | Playwright |
| `test_workshop_planner.py` | 10 | Bedrock |
| `test_workshop_resource_manager.py` | 8 | ローカルFS |
| `test_workshop_runner.py` | 6 | Playwright + Bedrock |
| `test_workshop_cli.py` | 10 | 上記の組合せ |

**前提**: Playwright installed, Kiro CLI v1.26.2
**ゴール**: mock 0、skip 0、実Playwright実行
**ブランチ**: `feat/e2e-phase-t4`

### Phase T-5: MCP テスト（mock排除）— 所要時間: 15分
**対象**: MCP server integration

| ファイル | テスト数 | 依存 |
|---|---|---|
| `test_mcp.py` | 62 | MCP server (stdio/SSE/streamable) |

**ゴール**: mock 0、skip 0
**ブランチ**: `feat/e2e-phase-t5`

## 実行手順（各Phase共通）

1. ブランチ作成
2. 対象ファイルからmock排除 + skip排除
3. 必要な環境変数/依存を設定
4. `pytest <対象ファイル> -v --tb=short` で全PASS確認
5. commit + push
6. PR作成 + マージ
7. 次のPhaseへ

## 環境セットアップ（Phase開始前に必要）

```bash
# Phase T-2用
export YUI_AWS_E2E=1
# Guardrail作成（Bedrock Console or CFn）
# AgentCore endpoint設定

# Phase T-3用
# ~/.yui/.env に既に設定済み（SLACK_BOT_TOKEN, SLACK_APP_TOKEN）

# 全Phase共通: 依存パッケージ確認
pip install sounddevice mlx-whisper rumps pynput playwright
playwright install chromium
```

## 最終目標

```
993 passed, 0 skipped, 0 failed — 全テストが実サービスで通る
```
