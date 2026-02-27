# tasks.md — Phase 2c: autospec強制 + Contract Test

> **Feature**: feat/phase2c-autospec-contracts
> **Design**: specs/phase2c-autospec-contracts/design.md
> **Task Date**: 2026-02-27

---

## Implementation Tasks

### Task 1: autospec強制fixture実装 [S]

**File**: `tests/conftest.py`

**Action**:
- `enforce_autospec` autouse fixtureを追加
- `unittest.mock.patch`をラップしてautospec=Trueをデフォルト化
- `@pytest.mark.no_autospec`でオプトアウト可能にする

**Acceptance Criteria**:
- `pytest --fixtures` で `enforce_autospec` が表示される
- 既存テストが全pass（autospec適用後）

**Complexity**: S (< 30min)

**Code**:
```python
# tests/conftest.py に追加

import unittest.mock
from unittest.mock import patch

@pytest.fixture(autouse=True)
def enforce_autospec(request):
    """Force autospec=True for all unittest.mock.patch calls.
    
    Opt-out: @pytest.mark.no_autospec
    """
    if "no_autospec" in request.keywords:
        yield
        return
    
    original_patch = unittest.mock.patch
    
    def autospec_patch(target, *args, autospec=True, **kwargs):
        return original_patch(target, *args, autospec=autospec, **kwargs)
    
    with patch.object(unittest.mock, 'patch', autospec_patch):
        yield
```

---

### Task 2: autospec適用後のテスト修正 [M]

**Files**: `tests/test_*.py` (autospec適用で失敗するテストのみ)

**Action**:
- `pytest tests/ -m 'not integration and not e2e' --ignore=tests/test_meeting_*.py` を実行
- 失敗したテストを特定
- シグネチャ不一致を修正（mockの引数を実関数に合わせる）
- 修正不可能なテストには `@pytest.mark.no_autospec` を追加

**Acceptance Criteria**:
- 全テストがpass（0 failed, 0 error）
- 修正内容をコミットメッセージに記載

**Complexity**: M (30min-2h)

**Note**: 失敗率が20%を超える場合はautospec適用を一時停止して設計を再検討

---

### Task 3: Contract Test基盤構築 [S]

**Files**:
- `tests/contracts/__init__.py` (新規作成)
- `tests/contracts/conftest.py` (新規作成)

**Action**:
- `tests/contracts/` ディレクトリ作成
- 共通fixtureを実装（bedrock_client, slack_client, cfn_client）
- レスポンス構造検証ヘルパー `assert_schema_match()` を実装

**Acceptance Criteria**:
- `pytest tests/contracts/ --collect-only` が正常実行
- fixtureがAWS credentials未設定時に `pytest.skip()` を呼ぶ

**Complexity**: S (< 30min)

**Code**:
```python
# tests/contracts/conftest.py

import os
import boto3
import pytest
from slack_sdk import WebClient

@pytest.fixture
def bedrock_client():
    """Real Bedrock client for contract tests."""
    try:
        client = boto3.client("bedrock-runtime", region_name="us-east-1")
        # Test credentials
        client.list_foundation_models()
        return client
    except Exception:
        pytest.skip("AWS credentials not configured")

@pytest.fixture
def slack_client():
    """Real Slack client for contract tests."""
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        pytest.skip("SLACK_BOT_TOKEN not set")
    return WebClient(token=token)

@pytest.fixture
def cfn_client():
    """Real CloudFormation client for contract tests."""
    try:
        client = boto3.client("cloudformation", region_name="us-east-1")
        # Test credentials
        client.describe_stacks()
        return client
    except Exception:
        pytest.skip("AWS credentials not configured")

def assert_schema_match(response: dict, schema: dict) -> None:
    """Assert that response matches schema structure."""
    for key_path, expected_type in schema.items():
        keys = key_path.split(".")
        value = response
        for key in keys:
            if "[" in key:
                # Handle list indexing: "Stacks[0]"
                key_name, idx = key.split("[")
                idx = int(idx.rstrip("]"))
                value = value[key_name][idx]
            else:
                value = value[key]
        
        if expected_type == "datetime":
            from datetime import datetime
            assert isinstance(value, datetime), f"{key_path}: expected datetime, got {type(value)}"
        else:
            assert isinstance(value, expected_type), f"{key_path}: expected {expected_type}, got {type(value)}"
```

---

### Task 4: Bedrock Contract Test実装 [M]

**File**: `tests/contracts/test_bedrock_contract.py` (新規作成)

**Action**:
- 10+件のContract Testを実装
- 正常レスポンス構造検証（3件）
- エラーレスポンス構造検証（3件）
- 障害シナリオ（timeout/503/rate limit）検証（4件）
- 全テストに `@pytest.mark.integration` マーカー

**Acceptance Criteria**:
- `pytest tests/contracts/test_bedrock_contract.py -m integration` で全pass
- テスト名がR1規則に準拠（3パーツ構成）
- AAA構造（R2）に準拠

**Complexity**: M (30min-2h)

**Test Cases**:
1. `test_bedrock_converse__normal_response__returns_valid_message_structure`
2. `test_bedrock_converse__with_system_prompt__includes_system_in_request`
3. `test_bedrock_converse__streaming_response__yields_content_blocks`
4. `test_bedrock_converse__invalid_model_id__raises_validation_exception`
5. `test_bedrock_converse__throttling_error__raises_throttling_exception`
6. `test_bedrock_converse__access_denied__raises_access_denied_exception`
7. `test_bedrock_converse__timeout_30s__raises_read_timeout_error` (stub)
8. `test_bedrock_converse__503_service_unavailable__raises_service_exception` (stub)
9. `test_bedrock_converse__rate_limited__retries_with_backoff` (stub)
10. `test_bedrock_converse__usage_metrics__returns_token_counts`

---

### Task 5: Slack Contract Test実装 [M]

**File**: `tests/contracts/test_slack_contract.py` (新規作成)

**Action**:
- 10+件のContract Testを実装
- chat.postMessage正常系（3件）
- reactions.add正常系（2件）
- conversations.history正常系（2件）
- 障害シナリオ（429 rate limit/遅延レスポンス）検証（3件）
- 全テストに `@pytest.mark.integration` マーカー

**Acceptance Criteria**:
- `pytest tests/contracts/test_slack_contract.py -m integration` で全pass
- テスト名がR1規則に準拠
- AAA構造（R2）に準拠

**Complexity**: M (30min-2h)

**Test Cases**:
1. `test_slack_post_message__normal_text__returns_ts_and_channel`
2. `test_slack_post_message__with_blocks__returns_valid_response`
3. `test_slack_post_message__thread_reply__includes_thread_ts`
4. `test_slack_reactions_add__valid_emoji__returns_ok_true`
5. `test_slack_reactions_add__invalid_emoji__raises_invalid_name_error`
6. `test_slack_conversations_history__recent_messages__returns_message_list`
7. `test_slack_conversations_history__with_limit__respects_limit_param`
8. `test_slack_post_message__rate_limited_429__retries_after_delay` (stub)
9. `test_slack_post_message__slow_response_5s__completes_successfully` (stub)
10. `test_slack_auth_test__valid_token__returns_user_and_team_info`

---

### Task 6: boto3 Contract Test実装 [M]

**File**: `tests/contracts/test_boto3_contract.py` (新規作成)

**Action**:
- 10+件のContract Testを実装
- CloudFormation describe_stacks（3件）
- Lambda invoke（3件）
- SecretsManager get_secret_value（2件）
- 障害シナリオ（AccessDenied/ResourceNotFound）検証（2件）
- 全テストに `@pytest.mark.integration` マーカー

**Acceptance Criteria**:
- `pytest tests/contracts/test_boto3_contract.py -m integration` で全pass
- テスト名がR1規則に準拠
- AAA構造（R2）に準拠

**Complexity**: M (30min-2h)

**Test Cases**:
1. `test_cfn_describe_stacks__existing_stack__returns_stack_details`
2. `test_cfn_describe_stacks__nonexistent_stack__raises_validation_error`
3. `test_cfn_describe_stacks__multiple_stacks__returns_list_of_stacks`
4. `test_lambda_invoke__sync_invocation__returns_payload_and_status`
5. `test_lambda_invoke__async_invocation__returns_202_status`
6. `test_lambda_invoke__nonexistent_function__raises_resource_not_found`
7. `test_secrets_manager_get__valid_secret__returns_secret_string`
8. `test_secrets_manager_get__nonexistent_secret__raises_resource_not_found`
9. `test_secrets_manager_get__access_denied__raises_access_denied_exception`
10. `test_cfn_describe_stacks__timeout_10s__raises_endpoint_connection_error` (stub)

---

### Task 7: Mock Drift Script実装 [L]

**File**: `scripts/check_mock_drift.py` (新規作成)

**Action**:
- CLI引数パース（--dry-run, --create-issue, --api）
- 既存テストからmockレスポンス構造を抽出（AST解析）
- 実APIを呼び出してレスポンス構造を取得
- 構造比較（キーの有無のみ、型チェックなし）
- 乖離検出時にGitHub Issue本文生成
- エラーハンドリング（API呼び出し失敗、AST解析失敗）

**Acceptance Criteria**:
- `python scripts/check_mock_drift.py --dry-run` が正常実行
- 乖離検出時にIssue本文が出力される
- API呼び出し失敗時にエラーログ出力 + 処理継続

**Complexity**: L (2h+)

**Code Structure**:
```python
#!/usr/bin/env python3
"""Mock drift detection script for yui-agent.

Usage:
    python scripts/check_mock_drift.py --dry-run
    python scripts/check_mock_drift.py --create-issue
    python scripts/check_mock_drift.py --api bedrock --dry-run
"""

import argparse
import ast
import json
from pathlib import Path

def extract_mock_structure(test_file: Path) -> dict:
    """Extract mock response structure from test file using AST."""
    ...

def get_real_api_structure(api_name: str) -> dict:
    """Call real API and extract response structure."""
    ...

def compare_structures(mock: dict, real: dict) -> dict:
    """Compare mock and real structures, return drift report."""
    ...

def generate_issue_body(drift_report: dict) -> str:
    """Generate GitHub Issue body from drift report."""
    ...

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--create-issue", action="store_true")
    parser.add_argument("--api", choices=["bedrock", "slack", "boto3"])
    args = parser.parse_args()
    
    # Implementation
    ...

if __name__ == "__main__":
    main()
```

---

### Task 8: pyproject.toml更新 [S]

**File**: `pyproject.toml`

**Action**:
- `no_autospec` マーカーを追加

**Acceptance Criteria**:
- `pytest --markers` で `no_autospec` が表示される

**Complexity**: S (< 30min)

**Code**:
```toml
[tool.pytest.ini_options]
markers = [
    # ... existing markers ...
    "no_autospec: Disable autospec enforcement for this test",
]
```

---

## Test Tasks

### Test Task 1: autospec fixture動作確認 [S]

**File**: `tests/test_conftest.py` (新規作成)

**Action**:
- `enforce_autospec` fixtureが正しく動作することを確認
- autospec適用時にシグネチャ不一致が検出されることを確認
- `@pytest.mark.no_autospec` でオプトアウト可能なことを確認

**Complexity**: S (< 30min)

**Test Cases**:
```python
def test_enforce_autospec__signature_mismatch__raises_type_error():
    """autospec適用時にシグネチャ不一致が検出される."""
    # Arrange
    def real_func(a: int, b: int) -> int:
        return a + b
    
    # Act & Assert
    with patch("__main__.real_func") as mock_func:
        with pytest.raises(TypeError):
            mock_func("wrong", "args")  # autospecでエラー

@pytest.mark.no_autospec
def test_no_autospec_marker__signature_mismatch__no_error():
    """@pytest.mark.no_autospecでオプトアウト可能."""
    # Arrange
    def real_func(a: int, b: int) -> int:
        return a + b
    
    # Act
    with patch("__main__.real_func") as mock_func:
        mock_func("wrong", "args")  # エラーなし
    
    # Assert
    mock_func.assert_called_once()
```

---

### Test Task 2: Contract Test実行時間測定 [S]

**Action**:
- `pytest tests/contracts/ -m integration --durations=0` を実行
- 全Contract Test実行時間が30秒以内であることを確認
- 30秒を超える場合は最も遅いテストを特定して最適化

**Complexity**: S (< 30min)

---

### Test Task 3: Mock Drift Script動作確認 [M]

**Action**:
- `python scripts/check_mock_drift.py --dry-run` を実行
- 既存mockと実APIの構造が一致することを確認
- 手動でmockを変更して乖離検出が動作することを確認
- Issue本文が正しく生成されることを確認

**Complexity**: M (30min-2h)

---

## Documentation Tasks

### Doc Task 1: README更新 [S]

**File**: `README.md`

**Action**:
- Phase 2c完了を記載
- Contract Test実行方法を追加
- Mock Drift Script使用方法を追加

**Complexity**: S (< 30min)

**Content**:
```markdown
## Testing

### Unit/Component Tests
```bash
pytest tests/ -m 'not integration and not e2e'
```

### Contract Tests (requires AWS credentials)
```bash
pytest tests/contracts/ -m integration
```

### Mock Drift Detection
```bash
# Dry-run mode
python scripts/check_mock_drift.py --dry-run

# Create GitHub Issue (CI only)
python scripts/check_mock_drift.py --create-issue
```
```

---

### Doc Task 2: specs/phase2c-autospec-contracts/COMPLETION.md作成 [S]

**File**: `specs/phase2c-autospec-contracts/COMPLETION.md` (新規作成)

**Action**:
- Phase 2c完了報告を記載
- 実装内容サマリー
- テスト結果（autospec適用率、Contract Test件数、実行時間）
- 既知の問題・制限事項

**Complexity**: S (< 30min)

**Template**:
```markdown
# COMPLETION.md — Phase 2c: autospec強制 + Contract Test

**Completion Date**: 2026-02-XX
**PR**: #XX

## Summary

Phase 2c完了。autospec強制 + Contract Test 30+件 + Mock Drift Script実装。

## Implementation

- ✅ autospec強制fixture（tests/conftest.py）
- ✅ Contract Test 30+件（tests/contracts/）
- ✅ Mock Drift Script（scripts/check_mock_drift.py）

## Test Results

- autospec適用率: XX% (XX/XX tests)
- Contract Test件数: XX件
- Contract Test実行時間: XX秒
- Mock Drift検出: 0件（乖離なし）

## Known Issues

- なし

## Next Steps

- Phase 3: Guardrails + Heartbeat + Daemon
```

---

## Task Execution Order

1. **Task 8** (pyproject.toml更新) — 他のタスクの前提条件
2. **Task 1** (autospec fixture実装) — 基盤構築
3. **Test Task 1** (autospec fixture動作確認) — Task 1の検証
4. **Task 2** (autospec適用後のテスト修正) — 既存テストの互換性確保
5. **Task 3** (Contract Test基盤構築) — Contract Testの前提条件
6. **Task 4** (Bedrock Contract Test実装) — 並行実行可能
7. **Task 5** (Slack Contract Test実装) — 並行実行可能
8. **Task 6** (boto3 Contract Test実装) — 並行実行可能
9. **Test Task 2** (Contract Test実行時間測定) — Task 4-6の検証
10. **Task 7** (Mock Drift Script実装) — 独立タスク
11. **Test Task 3** (Mock Drift Script動作確認) — Task 7の検証
12. **Doc Task 1** (README更新) — 最終タスク
13. **Doc Task 2** (COMPLETION.md作成) — 最終タスク

---

## Total Effort Estimate

- Implementation: 3 S + 4 M + 1 L = ~6-8 hours
- Testing: 2 S + 1 M = ~1.5-2 hours
- Documentation: 2 S = ~1 hour

**Total**: ~8.5-11 hours (1.5日以内 — Appetite達成可能)

---

## Risk Mitigation

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| autospec適用で既存テスト大量失敗 | Medium | High | Task 2で個別修正、失敗率20%超えたら一時停止 |
| Contract Test実行時間が30秒超過 | Low | Medium | レスポンスキャッシュ追加、テスト件数削減 |
| Mock Drift Script実装が複雑化 | Medium | Medium | AST解析を簡略化、最小限の構造比較のみ |
| AWS credentials未設定でCI失敗 | Low | Low | pytest.skip()で回避、CI環境に認証情報設定 |
