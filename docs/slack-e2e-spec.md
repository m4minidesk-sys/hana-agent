# Slack E2E Test — fullspec requirements

## 概要
Yui Agent の Slack 統合テストを網羅的に作成する。
mock ベースの unit test + 実 Slack API の integration test 両方。

## テストカテゴリ

### Category A: Mock-based Slack tests (常時実行可能)
Slack API呼び出しを全てmock。CI/CD で毎回実行。

### Category B: Live Slack tests (YUI_TEST_SLACK=1)
実際の Slack API を使うテスト。手動トリガー。

---

## Test Scenarios

### A. Mock-based Unit Tests (test_slack_e2e.py)

| # | テスト名 | AC | 内容 |
|---|---|---|---|
| SE-01 | test_mention_triggers_response | AC-10 | @mention → agent呼び出し → say()でスレッド返信 |
| SE-02 | test_dm_triggers_response | AC-11 | DM → agent呼び出し → say()で返信 |
| SE-03 | test_thread_reply | AC-10 | thread_ts付きメッセージ → 同スレッドに返信 |
| SE-04 | test_reaction_lifecycle | - | eyes → agent処理 → white_check_mark |
| SE-05 | test_already_reacted_ignored | - | reactions_add が already_reacted → エラーにならない |
| SE-06 | test_concurrent_requests_lock | AC-09 | 2つの同時リクエスト → Lock で直列化 |
| SE-07 | test_lock_timeout_processing_msg | - | Lock取得タイムアウト → "処理中" メッセージ |
| SE-08 | test_session_persistence | AC-12 | メッセージ → SessionManager に保存 |
| SE-09 | test_session_compaction_trigger | AC-13 | threshold超え → compact_session 呼び出し |
| SE-10 | test_bot_message_skip | - | subtype付きメッセージ → 無視 |
| SE-11 | test_dedup_mention_in_dm | - | bot_user_id含むDMメッセージ → handle_dm スキップ |
| SE-12 | test_agent_error_handling | - | agent例外 → エラーメッセージ投稿 |
| SE-13 | test_agent_result_to_string | - | AgentResult → str() 変換して投稿 |
| SE-14 | test_token_load_priority | AC-09 | env > .env > config の優先順位 |
| SE-15 | test_missing_tokens_error | - | トークンなし → ValueError |
| SE-16 | test_mpim_mention_single_response | - | グループDMでmention → 1回だけ応答 |
| SE-17 | test_socket_mode_startup | AC-09 | SocketModeHandler.start() が呼ばれる |
| SE-18 | test_compaction_summary_format | AC-14 | compact後のsummary形式確認 |

### B. Live Slack Integration Tests (test_slack_live.py, YUI_TEST_SLACK=1)

| # | テスト名 | AC | 内容 |
|---|---|---|---|
| SL-01 | test_slack_auth | AC-09 | auth.test → bot info返却 |
| SL-02 | test_post_message | - | チャンネルに投稿 → メッセージ確認 |
| SL-03 | test_add_reaction | - | reaction追加 → 成功 |
| SL-04 | test_thread_reply | AC-10 | スレッドに返信 → thread_ts付き |
| SL-05 | test_conversations_info | - | チャンネル情報取得 |
| SL-06 | test_users_info | - | ユーザー情報取得 |

---

## 実装方針
- `handle_mention` / `handle_dm` / `_safe_react` を個別テスト可能な関数に抽出
- 現在の `run_slack()` 内のクロージャを、テスタブルなクラスメソッドにリファクタ
- `SlackHandler` クラスを新設し、イベントハンドラをメソッドとして公開
