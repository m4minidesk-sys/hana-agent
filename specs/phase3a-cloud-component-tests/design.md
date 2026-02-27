# design.md — Phase 3a: クラウドコンポーネントテスト

**Feature**: Lambda Deployment Component Tests (TDD先行実装)  
**Branch**: `feat/phase3a-cloud-component-tests`  
**Parent Spec**: `specs/mock-coverage-cicd/requirements.md` (v2.2)  
**Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)

---

## 1. Architecture Overview

Phase 3aでは、Phase 6 (Issue #47) で実装予定のLambda Deploymentに対する**コンポーネントテストを先行実装**する。TDDアプローチに従い、インターフェース定義→テスト作成→stub実装の順で進める。

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Lambda Handler (src/yui/lambda_handler.py)                  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ handler(event, context) → dict                          │ │
│ │   ├── API Gateway proxy event → Slack Event変換        │ │
│ │   ├── EventBridge schedule event → heartbeat呼び出し   │ │
│ │   ├── Secrets Manager → token取得                      │ │
│ │   ├── Bedrock Converse API呼び出し                     │ │
│ │   └── Structured logging (JSON)                        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                          ↑
                          │ (stub/mock)
                          │
┌─────────────────────────────────────────────────────────────┐
│ Component Tests (tests/test_lambda_*.py)                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ test_lambda_handler.py         (15-20 tests)           │ │
│ │ test_lambda_secrets.py         (3-5 tests)             │ │
│ │ test_lambda_adapter_switch.py  (2-3 tests)             │ │
│ │ test_lambda_eventbridge.py     (2-3 tests)             │ │
│ │ test_lambda_layers.py          (2-3 tests)             │ │
│ │ test_lambda_logging.py         (2-3 tests)             │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Test Strategy

- **TDD Red→Green→Refactor**: 各FR-08-A項目ごとにサイクル実行
- **Stub/Mock優先**: 外部依存（boto3, Bedrock, Secrets Manager）は全てstub
- **Interface-First**: lambda_handler.pyは空実装（NotImplementedError）のみ
- **Black-Box Testing**: 公開インターフェースのみテスト（内部実装に依存しない）

---

## 2. Technology Selection

### 2.1 Test Framework

| Technology | Rationale |
|---|---|
| **pytest** | 既存テストスイートと統一。fixture機能でstub管理が容易 |
| **unittest.mock** | Python標準ライブラリ。autospec=True強制でtype-safe |
| **Faker** | 既存のtests/factories.pyと統合。リアルなテストデータ生成 |

### 2.2 Mock Strategy

| 対象 | Mock方法 | 理由 |
|---|---|---|
| boto3.client | `@patch("boto3.client")` | Secrets Manager/Bedrock呼び出しをstub |
| Lambda context | MagicMock | aws_request_id, get_remaining_time_in_millis()をstub |
| os.environ | `@patch.dict(os.environ)` | LAMBDA_RUNTIME環境変数の切り替えテスト |
| sys.path | 直接操作 | Lambda Layer用パス追加の検証 |
| logging | `@patch("logging.getLogger")` | structured log出力の検証 |

### 2.3 No External Dependencies

- 新規ライブラリ追加なし（既存のpytest, unittest.mock, Fakerのみ）
- AWS SDK呼び出しは全てstub（実際のAWS接続なし）
- テスト実行時間: 全体で ≤ 10秒（stub/mockのみなので高速）

---

## 3. API Interfaces

### 3.1 Lambda Handler Interface

```python
# src/yui/lambda_handler.py

from typing import Any

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler entry point.
    
    Args:
        event: API Gateway proxy event or EventBridge schedule event
            - API Gateway: {"httpMethod": "POST", "body": "{...}", "headers": {...}}
            - EventBridge: {"source": "aws.events", "detail-type": "Scheduled Event"}
        
        context: Lambda context object
            - aws_request_id: str
            - get_remaining_time_in_millis: () -> int
    
    Returns:
        dict: API Gateway proxy response format
            - statusCode: int
            - body: str (JSON)
            - headers: dict
    
    Raises:
        NotImplementedError: Phase 3aでは未実装（Phase 6で実装）
    """
    raise NotImplementedError("Phase 6で実装予定")
```

### 3.2 Test Interface Contracts

各テストファイルは以下のインターフェースをテストする:

#### test_lambda_handler.py
- `handler(challenge_event, context) → {"challenge": "xxx"}`
- `handler(event_callback, context) → {"statusCode": 200, "body": "..."}`
- `handler(invalid_signature, context) → {"statusCode": 401}`

#### test_lambda_secrets.py
- `_get_secret(secret_name) → dict` (内部関数、Phase 6で実装)

#### test_lambda_adapter_switch.py
- `_select_adapter(env) → "events_api" | "socket_mode"` (内部関数、Phase 6で実装)

#### test_lambda_eventbridge.py
- `handler(eventbridge_event, context) → {"statusCode": 200}`

#### test_lambda_layers.py
- `sys.path` に `/opt/python` が含まれることを検証

#### test_lambda_logging.py
- `handler()` 実行時にJSON形式のログが出力されることを検証

---

## 4. Data Models

### 4.1 Slack Events API Event Types

```python
# Slack url_verification event
{
    "type": "url_verification",
    "challenge": "3eZbrw1aBm2rZgRNFdxV2595E9CY3gmdALWMmHkvFXO7tYXAYM8P",
    "token": "Jhj5dZrVaK7ZwHHjRyZWjbDl"
}

# Slack event_callback event
{
    "type": "event_callback",
    "token": "XXYYZZ",
    "team_id": "TXXXXXXXX",
    "event": {
        "type": "app_mention",
        "user": "U061F7AUR",
        "text": "<@U0LAN0Z89> is it everything a river should be?",
        "ts": "1515449522.000016",
        "channel": "C0LAN2Q65"
    }
}
```

### 4.2 API Gateway Proxy Event

```python
{
    "httpMethod": "POST",
    "path": "/slack/events",
    "headers": {
        "X-Slack-Signature": "v0=...",
        "X-Slack-Request-Timestamp": "1531420618"
    },
    "body": "{\"type\": \"url_verification\", \"challenge\": \"...\"}"
}
```

### 4.3 EventBridge Schedule Event

```python
{
    "version": "0",
    "id": "53dc4d37-cffa-4f76-80c9-8b7d4a4d2eaa",
    "detail-type": "Scheduled Event",
    "source": "aws.events",
    "account": "123456789012",
    "time": "2015-10-08T16:53:06Z",
    "region": "us-east-1",
    "resources": ["arn:aws:events:us-east-1:123456789012:rule/my-schedule"],
    "detail": {}
}
```

### 4.4 Lambda Context

```python
class LambdaContext:
    aws_request_id: str
    log_group_name: str
    log_stream_name: str
    function_name: str
    memory_limit_in_mb: int
    function_version: str
    invoked_function_arn: str
    
    def get_remaining_time_in_millis(self) -> int:
        """Returns remaining execution time in milliseconds."""
        ...
```

---

## 5. Error Handling

### 5.1 Error Categories

| Error Type | HTTP Status | Handler Response | Test Coverage |
|---|---|---|---|
| Invalid Slack signature | 401 | `{"statusCode": 401, "body": "Unauthorized"}` | AC-3 |
| Malformed JSON body | 400 | `{"statusCode": 400, "body": "Bad Request"}` | AC-12 |
| Secrets Manager error | 500 | `{"statusCode": 500, "body": "Internal Error"}` | AC-6, AC-7 |
| Bedrock timeout | 200 | Slack error message返却 | AC-18 |
| Slack API 429 | 200 | リトライ後に成功 | AC-19 |
| Lambda timeout接近 | 200 | 早期終了 | AC-20 |

### 5.2 Error Handling Strategy

- **Graceful Degradation**: Bedrock/Slack APIエラー時もLambdaは正常終了（statusCode: 200）
- **Structured Error Logging**: 全エラーをJSON形式でCloudWatch Logsに記録
- **Retry Logic**: Slack API 429エラーは最大3回リトライ（exponential backoff）
- **Early Termination**: Lambda実行時間が残り10秒を切ったら処理を中断

### 5.3 Test Error Injection

```python
# Bedrock timeout injection
mock_bedrock.converse.side_effect = TimeoutError("Request timed out")

# Slack 429 injection
mock_slack.chat_postMessage.side_effect = [
    SlackApiError("rate_limited", response={"error": "rate_limited"}),
    SlackApiError("rate_limited", response={"error": "rate_limited"}),
    {"ok": True, "ts": "1234567890.123456"}  # 3回目で成功
]

# Lambda timeout injection
mock_context.get_remaining_time_in_millis.return_value = 5000  # 5秒残り
```

---

## 6. Security Considerations

### 6.1 Slack Request Verification

- **Signature Validation**: `X-Slack-Signature` ヘッダーの検証（AC-3）
- **Timestamp Check**: リプレイ攻撃防止（5分以内のリクエストのみ受付）
- **Test Coverage**: 不正署名、古いタイムスタンプのテストケース

### 6.2 Secrets Management

- **Secrets Manager**: Slackトークンは環境変数ではなくSecrets Managerから取得
- **IAM Permissions**: Lambda実行ロールに `secretsmanager:GetSecretValue` 権限必須
- **Test Coverage**: シークレット取得失敗時のエラーハンドリング（AC-6, AC-7）

### 6.3 Input Validation

- **JSON Parsing**: 不正なJSON bodyは400エラー（AC-12）
- **Event Type Check**: 未知のSlack event typeは無視（ログのみ）
- **Test Coverage**: 各種不正入力のテストケース

### 6.4 Lambda Layer Security

- **Path Isolation**: `/opt/python` のみをsys.pathに追加（AC-14）
- **Import Validation**: 必要なパッケージ（strands-agents, slack-bolt）のimport確認（AC-15）

---

## 7. Testing Strategy

### 7.1 TDD Workflow (per FR-08-A item)

1. **TODO List**: FR-08-A1〜A9から対象テストリスト作成
2. **Red**: テストファイル作成 → `pytest` 実行 → 全失敗（NotImplementedError）
3. **Green**: 最小限のstub実装でテスト通過
4. **Refactor**: テストコード・実装コードの整理

### 7.2 Test Naming Convention (goldbergyoni R1)

```
test_<module>__<scenario>__<expected_behavior>
```

例:
- `test_lambda_handler__challenge_event__returns_challenge_value`
- `test_lambda_secrets__nonexistent_secret__raises_error`
- `test_lambda_adapter__lambda_runtime_true__selects_events_api`

### 7.3 Test Structure (goldbergyoni R2: AAA)

```python
def test_lambda_handler__challenge_event__returns_challenge_value():
    # Arrange
    event = {"type": "url_verification", "challenge": "test123"}
    context = MagicMock(aws_request_id="req-123")
    
    # Act
    response = handler(event, context)
    
    # Assert
    assert response["challenge"] == "test123"
```

### 7.4 Test Markers

全テストに `@pytest.mark.component` マーカーを付与:

```python
import pytest

pytestmark = pytest.mark.component
```

### 7.5 Test Execution

```bash
# 全Lambda関連テスト実行
pytest tests/test_lambda_*.py -v

# 特定のテストファイルのみ
pytest tests/test_lambda_handler.py -v

# マーカー指定
pytest -m component tests/test_lambda_*.py
```

---

## 8. Implementation Phases

### Phase 1: Interface Definition (Red)
1. `src/yui/lambda_handler.py` 作成（空実装）
2. テストファイル6つ作成（全テスト失敗）

### Phase 2: Stub Implementation (Green)
3. 各テストファイルにstub/mock実装
4. 全テスト通過確認

### Phase 3: Refactoring
5. テストコードの重複削除
6. factories.py に Lambda用ファクトリ追加
7. conftest.py に共通fixtureを追加（必要に応じて）

---

## 9. Success Criteria

- [ ] テストファイル6つ作成済み（test_lambda_*.py）
- [ ] テスト件数 25+件
- [ ] `pytest tests/test_lambda_*.py -v` で全pass、0 skipped
- [ ] 全テストに `@pytest.mark.component` マーカー
- [ ] テスト実行時間 ≤ 10秒
- [ ] lambda_handler.py のインターフェース定義が存在
- [ ] R1テスト名（3パーツ）、R2 AAA構造、R17障害シナリオ準拠
- [ ] autospec=True 適用率100%（enforce_autospec fixtureで自動）

---

## 10. Out of Scope (Phase 6で実装)

- Lambda handler の実際の実装
- Bedrock Converse API の実際の呼び出し
- Secrets Manager の実際の呼び出し
- Slack Events API の実際の呼び出し
- Lambda Layer の実際のビルド・デプロイ
- CloudFormation テンプレート
- CI/CD パイプライン

---

## 11. References

- **goldbergyoni Test Best Practices**: R1 (3-part naming), R2 (AAA), R4 (black-box), R5 (stub/spy), R6 (Faker), R15 (no global seed), R17 (failure scenarios)
- **t-wada TDD Principles**: TW1 (TODO list), TW2 (Red-Green-Refactor), TW5 (structural decoupling), TW8 (test-first)
- **Parent Spec**: `specs/mock-coverage-cicd/requirements.md` (v2.2)
- **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
