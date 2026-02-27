# requirements.md — Phase 3a: クラウドコンポーネントテスト

> **親spec**: `specs/mock-coverage-cicd/requirements.md` (v2.2)
> **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
> **Phase**: 3a（テストインフラspec独自連番 — yui-agent本体Phase番号とは別体系）
> **Appetite**: 2.5日（仕様変更バッファ0.5日込み）
> **テスト思想**: goldbergyoni (R1-R28) + t-wada TDD原則 (TW1-TW8) 準拠
> **TDD**: Red→Green→Refactorサイクル必須。テスト先行で実装。

---

## 1. 背景

Phase 2cまでの成果:
- 777 unit/component tests (autospec適用率100%)
- 30 contract tests (Bedrock/Slack/boto3)
- CI green (PR #77-#81)
- skip 0

Phase 3aでは **Lambda Deployment (Issue #47, Phase 6)** のコンポーネントテストをmock/stubベースで先行実装する。
lambda_handler.py は未実装だが、Slack Events API形式の入出力仕様は確定しているため、外部インターフェーステストを先行で書ける。

**重要**: lambda_handler.py は本Phaseでは**テスト対象のインターフェース定義のみ**作成する。実装はPhase 6で行う。

---

## 2. TDDアプローチ

本Phaseは t-wada TDD原則に厳密に従う:

1. **TODOリスト作成** → FR-08-A1〜A9から対象テストリスト作成
2. **Red**: テストファイル作成 → lambda_handler.pyのインターフェース定義（空実装）→ テスト実行 → 全失敗
3. **Green**: 最小限のstub実装でテスト通過
4. **Refactor**: テストコード・実装コードの整理

各FR-08-A項目ごとに Red→Green→Refactor を繰り返す。

---

## 3. 要求仕様

### FR-08-A1: Lambda handler リクエストパース+レスポンス生成テスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-1 | Slack Events API challenge応答テスト | `{"type": "url_verification", "challenge": "xxx"}` → `{"challenge": "xxx"}` レスポンス返却 |
| AC-2 | Slack Events API event_callback処理テスト | `{"type": "event_callback", "event": {...}}` → Bedrock呼び出しstub経由でレスポンス生成 |
| AC-3 | 不正リクエスト拒否テスト | 署名検証失敗 → 401 Unauthorized |
| AC-4 | url_verification応答時間 ≤100ms | Bedrock呼び出しなしの同期応答（stub環境で計測） |

### FR-08-A2: Secrets Manager トークン取得stubテスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-5 | 正常取得 | stubされたboto3がシークレット値を返す → handler内で正しくパース |
| AC-6 | シークレット未存在 | ResourceNotFoundError → 適切なエラーハンドリング |
| AC-7 | 権限エラー | AccessDeniedException → 適切なエラーハンドリング |

### FR-08-A3: Socket Mode ↔ Events API 切替ロジックテスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-8 | LAMBDA_RUNTIME=true → Events APIアダプタ選択 | 環境変数stubで検証 |
| AC-9 | LAMBDA_RUNTIME未設定 → Socket Modeアダプタ選択 | 環境変数stubで検証 |

### FR-08-A4: Lambda handler状態汚染なしテスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-10 | 2回連続呼び出しで同一結果 | 同一handler関数を同じ入力で2回呼び出し → 2回目も正確な結果（R4ブラックボックス） |

### FR-08-A5: API Gateway イベント→Slack Event変換

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-11 | API GW proxy event → Slack Event変換 | `{"httpMethod": "POST", "body": "{...}"}` → Slackイベント構造体 |
| AC-12 | 不正JSON body → 400エラー | パース失敗時の適切なエラーレスポンス |

### FR-08-A6: EventBridge cronトリガーテスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-13 | EventBridgeスケジュールイベント → heartbeat処理呼び出し | stubされたheartbeat関数の呼び出し確認 |

### FR-08-A7: Lambda Layer依存解決テスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-14 | sys.pathにLayer用パスが追加されること | handler初期化時に `/opt/python` がsys.pathに含まれる |
| AC-15 | Layer内パッケージのimportが成功すること | strands-agents, slack-bolt等のimportをstubで検証 |

### FR-08-A8: Lambda handler ログ出力テスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-16 | structured log（JSON形式）出力 | handler実行時にJSON形式のログがstdoutに出力される |
| AC-17 | request_idがログに含まれる | Lambda contextのrequest_idがログ内に存在 |

### FR-08-A9: Lambda handler エラーハンドリングテスト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-18 | Bedrock APIタイムアウト → graceful degradation | stubでタイムアウト注入 → エラーメッセージをSlackに返却 |
| AC-19 | Slack API 429 rate limit → リトライ（テストコード内、最大3回） | stubで429応答 → リトライロジック検証 |
| AC-20 | Lambda実行時間上限接近 → 早期終了 | remaining_time_in_millis stubで検証 |

---

## 4. テストファイル構成

```
tests/
├── test_lambda_handler.py          # FR-08-A1, A4, A5, A9 (15-20件)
├── test_lambda_secrets.py          # FR-08-A2 (3-5件)
├── test_lambda_adapter_switch.py   # FR-08-A3 (2-3件)
├── test_lambda_eventbridge.py      # FR-08-A6 (2-3件)
├── test_lambda_layers.py           # FR-08-A7 (2-3件)
├── test_lambda_logging.py          # FR-08-A8 (2-3件)
```

### テスト名パターン例（R1: 3パーツ）

```
test_lambda_handler__challenge_event__returns_challenge_value
test_lambda_handler__invalid_signature__returns_401_unauthorized
test_lambda_handler__event_callback__invokes_bedrock_stub
test_lambda_handler__consecutive_calls__no_state_pollution
test_lambda_secrets__valid_secret__returns_parsed_token
test_lambda_secrets__nonexistent_secret__raises_error
test_lambda_adapter__lambda_runtime_true__selects_events_api
test_lambda_eventbridge__schedule_event__calls_heartbeat
test_lambda_layers__handler_init__adds_opt_python_to_syspath
test_lambda_logging__handler_execution__outputs_json_with_request_id
test_lambda_handler__bedrock_timeout__returns_error_to_slack
test_lambda_handler__slack_429__retries_with_backoff
test_lambda_handler__remaining_time_low__terminates_early
```

---

## 5. 技術的制約

- Python 3.12+ / pytest / unittest.mock
- **lambda_handler.py のインターフェースのみ定義（空実装）** — 実装はPhase 6
- 外部ライブラリ追加不可
- pytest.skip() / skipif / importorskip 全面禁止
- 全テストに `@pytest.mark.component` マーカー
- テスト実行時間: 全体で ≤ 10秒（stub/mockのみなので高速）

---

## 6. lambda_handler.py インターフェース定義

```python
# src/yui/lambda_handler.py — Phase 3aではインターフェースのみ
# 実装はPhase 6 (Issue #47) で行う

def handler(event: dict, context) -> dict:
    """Lambda handler entry point.
    
    Args:
        event: API Gateway proxy event or EventBridge schedule event
        context: Lambda context object (aws_request_id, get_remaining_time_in_millis)
    
    Returns:
        dict: API Gateway proxy response format
    """
    raise NotImplementedError("Phase 6で実装予定")
```

---

## 7. gitルール

- Feature branch: `feat/phase3a-cloud-component-tests`
- base: `main`
- squash merge
- PRに `closes #75` は入れない（全Phase完了後にclose）

---

## 8. Phase完了判定基準

- [ ] テストファイル6つ作成済み
- [ ] テスト件数 25+件
- [ ] `pytest tests/test_lambda_*.py -v` で全pass、0 skipped
- [ ] 全テストに `@pytest.mark.component` マーカー
- [ ] テスト実行時間 ≤ 10秒
- [ ] lambda_handler.py のインターフェース定義が存在
- [ ] R1テスト名（3パーツ）、R2 AAA構造、R17障害シナリオ準拠
- [ ] Kiroクロスレビュー APPROVE
