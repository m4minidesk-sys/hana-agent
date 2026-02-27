# tasks.md — Phase 3a: クラウドコンポーネントテスト実装タスク

**Feature**: Lambda Deployment Component Tests (TDD先行実装)  
**Branch**: `feat/phase3a-cloud-component-tests`  
**Appetite**: 2.5日（仕様変更バッファ0.5日込み）

---

## TDD Workflow

各タスクは **Red → Green → Refactor** サイクルに従う:

1. **Red**: テスト作成 → 実行 → 失敗確認
2. **Green**: 最小限の実装でテスト通過
3. **Refactor**: コード整理・重複削除

---

## Implementation Tasks

### T1: Lambda handler インターフェース定義 (S)

**Complexity**: S (< 30min)  
**Dependencies**: なし  
**TDD Phase**: Red

**Files**:
- `src/yui/lambda_handler.py` (新規作成)

**Acceptance Criteria**:
- [ ] `handler(event, context) -> dict` 関数が定義されている
- [ ] docstringにAPI Gateway/EventBridge event形式を記載
- [ ] `raise NotImplementedError("Phase 6で実装予定")` で空実装
- [ ] type hints付き（`dict[str, Any]`, `Any`）

**Implementation**:
```python
# src/yui/lambda_handler.py
from typing import Any

def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler entry point.
    
    Args:
        event: API Gateway proxy event or EventBridge schedule event
        context: Lambda context object
    
    Returns:
        dict: API Gateway proxy response format
    
    Raises:
        NotImplementedError: Phase 6で実装予定
    """
    raise NotImplementedError("Phase 6で実装予定")
```

---

### T2: Lambda handler基本テスト作成 (M)

**Complexity**: M (30min-2h)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_handler.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A1 (AC-1, AC-2, AC-3, AC-4) のテストケース作成
- [ ] FR-08-A4 (AC-10) 状態汚染なしテスト作成
- [ ] FR-08-A5 (AC-11, AC-12) API Gateway変換テスト作成
- [ ] FR-08-A9 (AC-18, AC-19, AC-20) エラーハンドリングテスト作成
- [ ] 全テストに `@pytest.mark.component` マーカー
- [ ] R1 (3-part naming), R2 (AAA) 準拠
- [ ] 15-20件のテストケース

**Test Cases**:
```python
# tests/test_lambda_handler.py
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.component

# AC-1: url_verification challenge応答
def test_lambda_handler__challenge_event__returns_challenge_value():
    pass

# AC-2: event_callback処理
def test_lambda_handler__event_callback__invokes_bedrock_stub():
    pass

# AC-3: 不正署名拒否
def test_lambda_handler__invalid_signature__returns_401_unauthorized():
    pass

# AC-4: url_verification応答時間
def test_lambda_handler__challenge_response__completes_under_100ms():
    pass

# AC-10: 状態汚染なし
def test_lambda_handler__consecutive_calls__no_state_pollution():
    pass

# AC-11: API Gateway変換
def test_lambda_handler__api_gateway_event__converts_to_slack_event():
    pass

# AC-12: 不正JSON
def test_lambda_handler__invalid_json_body__returns_400_bad_request():
    pass

# AC-18: Bedrockタイムアウト
def test_lambda_handler__bedrock_timeout__returns_error_to_slack():
    pass

# AC-19: Slack 429リトライ
def test_lambda_handler__slack_429__retries_with_backoff():
    pass

# AC-20: Lambda timeout接近
def test_lambda_handler__remaining_time_low__terminates_early():
    pass
```

---

### T3: Secrets Manager テスト作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_secrets.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A2 (AC-5, AC-6, AC-7) のテストケース作成
- [ ] boto3.client("secretsmanager") のstub
- [ ] 3-5件のテストケース

**Test Cases**:
```python
# tests/test_lambda_secrets.py
import pytest
from unittest.mock import patch, MagicMock

pytestmark = pytest.mark.component

# AC-5: 正常取得
def test_lambda_secrets__valid_secret__returns_parsed_token():
    pass

# AC-6: シークレット未存在
def test_lambda_secrets__nonexistent_secret__raises_resource_not_found():
    pass

# AC-7: 権限エラー
def test_lambda_secrets__access_denied__raises_access_denied_exception():
    pass
```

---

### T4: Adapter切替テスト作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_adapter_switch.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A3 (AC-8, AC-9) のテストケース作成
- [ ] os.environ["LAMBDA_RUNTIME"] のstub
- [ ] 2-3件のテストケース

**Test Cases**:
```python
# tests/test_lambda_adapter_switch.py
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.component

# AC-8: LAMBDA_RUNTIME=true
def test_lambda_adapter__lambda_runtime_true__selects_events_api():
    pass

# AC-9: LAMBDA_RUNTIME未設定
def test_lambda_adapter__lambda_runtime_unset__selects_socket_mode():
    pass
```

---

### T5: EventBridge テスト作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_eventbridge.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A6 (AC-13) のテストケース作成
- [ ] EventBridge schedule event形式のstub
- [ ] 2-3件のテストケース

**Test Cases**:
```python
# tests/test_lambda_eventbridge.py
import pytest
from unittest.mock import MagicMock, patch

pytestmark = pytest.mark.component

# AC-13: EventBridge → heartbeat
def test_lambda_eventbridge__schedule_event__calls_heartbeat():
    pass
```

---

### T6: Lambda Layer テスト作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_layers.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A7 (AC-14, AC-15) のテストケース作成
- [ ] sys.path操作の検証
- [ ] 2-3件のテストケース

**Test Cases**:
```python
# tests/test_lambda_layers.py
import pytest
import sys

pytestmark = pytest.mark.component

# AC-14: sys.pathに/opt/python追加
def test_lambda_layers__handler_init__adds_opt_python_to_syspath():
    pass

# AC-15: Layer内パッケージimport
def test_lambda_layers__layer_packages__import_succeeds():
    pass
```

---

### T7: Lambda logging テスト作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T1  
**TDD Phase**: Red → Green

**Files**:
- `tests/test_lambda_logging.py` (新規作成)

**Acceptance Criteria**:
- [ ] FR-08-A8 (AC-16, AC-17) のテストケース作成
- [ ] logging.getLogger() のstub
- [ ] JSON形式ログ出力の検証
- [ ] 2-3件のテストケース

**Test Cases**:
```python
# tests/test_lambda_logging.py
import pytest
from unittest.mock import patch, MagicMock
import json

pytestmark = pytest.mark.component

# AC-16: structured log (JSON)
def test_lambda_logging__handler_execution__outputs_json_log():
    pass

# AC-17: request_id含む
def test_lambda_logging__handler_execution__includes_request_id():
    pass
```

---

### T8: Lambda factories追加 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T2-T7  
**TDD Phase**: Refactor

**Files**:
- `tests/factories.py` (既存ファイルに追加)

**Acceptance Criteria**:
- [ ] `LambdaEventFactory` クラス追加
- [ ] `LambdaContextFactory` クラス追加
- [ ] Faker使用でリアルなテストデータ生成

**Implementation**:
```python
# tests/factories.py に追加

class LambdaEventFactory:
    """Factory for Lambda event dicts."""
    
    @staticmethod
    def api_gateway_event(body: str | None = None) -> dict:
        return {
            "httpMethod": "POST",
            "path": "/slack/events",
            "headers": {
                "X-Slack-Signature": f"v0={fake.sha256()}",
                "X-Slack-Request-Timestamp": str(fake.random_int(min=1700000000, max=1800000000)),
            },
            "body": body or fake.json(),
        }
    
    @staticmethod
    def eventbridge_event() -> dict:
        return {
            "version": "0",
            "id": fake.uuid4(),
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": fake.random_number(digits=12, fix_len=True),
            "time": fake.iso8601(),
            "region": fake.random_element(["us-east-1", "us-west-2"]),
            "resources": [f"arn:aws:events:us-east-1:{fake.random_number(digits=12)}:rule/my-schedule"],
            "detail": {},
        }
    
    @staticmethod
    def slack_challenge_event(challenge: str | None = None) -> dict:
        return {
            "type": "url_verification",
            "challenge": challenge or fake.sha256(),
            "token": fake.sha256(),
        }


class LambdaContextFactory:
    """Factory for Lambda context objects."""
    
    @staticmethod
    def create(
        aws_request_id: str | None = None,
        remaining_time_ms: int = 300000,
    ) -> MagicMock:
        context = MagicMock()
        context.aws_request_id = aws_request_id or fake.uuid4()
        context.log_group_name = f"/aws/lambda/{fake.word()}"
        context.log_stream_name = f"2024/01/01/[$LATEST]{fake.sha256()[:8]}"
        context.function_name = fake.word()
        context.memory_limit_in_mb = 512
        context.function_version = "$LATEST"
        context.invoked_function_arn = f"arn:aws:lambda:us-east-1:{fake.random_number(digits=12)}:function:{fake.word()}"
        context.get_remaining_time_in_millis.return_value = remaining_time_ms
        return context
```

---

### T9: テスト実装（stub/mock） (L)

**Complexity**: L (2h+)  
**Dependencies**: T2-T7  
**TDD Phase**: Green

**Files**:
- `tests/test_lambda_handler.py`
- `tests/test_lambda_secrets.py`
- `tests/test_lambda_adapter_switch.py`
- `tests/test_lambda_eventbridge.py`
- `tests/test_lambda_layers.py`
- `tests/test_lambda_logging.py`

**Acceptance Criteria**:
- [ ] 全テストケースにstub/mock実装
- [ ] `pytest tests/test_lambda_*.py -v` で全pass
- [ ] 0 skipped
- [ ] テスト実行時間 ≤ 10秒
- [ ] autospec=True 適用率100%

**Implementation Notes**:
- boto3.client のstubは `@patch("boto3.client")` で統一
- Lambda context は `LambdaContextFactory.create()` で生成
- Slack event は `LambdaEventFactory` で生成
- エラー注入は `side_effect` で実装

---

### T10: テストコードリファクタリング (M)

**Complexity**: M (30min-2h)  
**Dependencies**: T9  
**TDD Phase**: Refactor

**Files**:
- `tests/test_lambda_*.py` (全6ファイル)
- `tests/conftest.py` (必要に応じて)

**Acceptance Criteria**:
- [ ] 重複コードをfixtureに抽出
- [ ] AAA構造の明確化（空行で区切り）
- [ ] テスト名がR1準拠（3パーツ）
- [ ] コメント削除（self-documenting code）

**Refactoring Targets**:
- boto3.client stub → conftest.py に `mock_lambda_boto3_client` fixture追加
- Lambda context stub → conftest.py に `mock_lambda_context` fixture追加
- 共通のassert関数 → tests/helpers.py に追加

---

## Test Tasks

### T11: 全テスト実行確認 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T10

**Command**:
```bash
pytest tests/test_lambda_*.py -v
```

**Acceptance Criteria**:
- [ ] 25+件のテストが全pass
- [ ] 0 skipped
- [ ] 0 failed
- [ ] テスト実行時間 ≤ 10秒

---

### T12: マーカー確認 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T10

**Command**:
```bash
pytest -m component tests/test_lambda_*.py -v
```

**Acceptance Criteria**:
- [ ] 全テストが `@pytest.mark.component` マーカー付き
- [ ] マーカー指定で全テスト実行される

---

### T13: autospec適用率確認 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T10

**Acceptance Criteria**:
- [ ] 全テストで `@patch(..., autospec=True)` が適用されている
- [ ] `enforce_autospec` fixtureで自動適用されている
- [ ] `@pytest.mark.no_autospec` マーカーなし

---

## Documentation Tasks

### T14: テストドキュメント更新 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T13

**Files**:
- `specs/phase3a-cloud-component-tests/design.md` (既存)
- `specs/phase3a-cloud-component-tests/tasks.md` (既存)

**Acceptance Criteria**:
- [ ] design.md の Success Criteria を全てチェック
- [ ] tasks.md の全タスクを完了マーク
- [ ] テスト件数、実行時間を記録

---

## Git Tasks

### T15: PR作成 (S)

**Complexity**: S (< 30min)  
**Dependencies**: T14

**Acceptance Criteria**:
- [ ] feature branch: `feat/phase3a-cloud-component-tests`
- [ ] base: `main`
- [ ] PR title: `feat: Phase 3a - Lambda component tests (TDD)`
- [ ] PR description に以下を記載:
  - テスト件数
  - テスト実行時間
  - FR-08-A1〜A9の達成状況
  - `closes #75` は**入れない**（全Phase完了後にclose）

---

## Task Summary

| Task | Complexity | Estimated Time | Dependencies |
|---|---|---|---|
| T1: Lambda handler interface | S | 15min | - |
| T2: Handler tests | M | 1.5h | T1 |
| T3: Secrets tests | S | 20min | T1 |
| T4: Adapter tests | S | 20min | T1 |
| T5: EventBridge tests | S | 20min | T1 |
| T6: Layer tests | S | 20min | T1 |
| T7: Logging tests | S | 20min | T1 |
| T8: Factories | S | 20min | T2-T7 |
| T9: Test implementation | L | 2h | T2-T7 |
| T10: Refactoring | M | 1h | T9 |
| T11: Test execution | S | 10min | T10 |
| T12: Marker check | S | 10min | T10 |
| T13: Autospec check | S | 10min | T10 |
| T14: Documentation | S | 15min | T13 |
| T15: PR creation | S | 15min | T14 |

**Total Estimated Time**: 7.5h (≈ 1日)  
**Appetite**: 2.5日（バッファ1.5日）

---

## Execution Order

1. **Day 1 Morning**: T1 → T2 → T3 → T4 → T5 → T6 → T7 (Red phase完了)
2. **Day 1 Afternoon**: T8 → T9 (Green phase完了)
3. **Day 2 Morning**: T10 → T11 → T12 → T13 (Refactor phase完了)
4. **Day 2 Afternoon**: T14 → T15 (Documentation & PR)

---

## Phase Completion Checklist

- [ ] テストファイル6つ作成済み
- [ ] テスト件数 25+件
- [ ] `pytest tests/test_lambda_*.py -v` で全pass、0 skipped
- [ ] 全テストに `@pytest.mark.component` マーカー
- [ ] テスト実行時間 ≤ 10秒
- [ ] lambda_handler.py のインターフェース定義が存在
- [ ] R1テスト名（3パーツ）、R2 AAA構造、R17障害シナリオ準拠
- [ ] autospec=True 適用率100%
- [ ] Kiroクロスレビュー APPROVE
