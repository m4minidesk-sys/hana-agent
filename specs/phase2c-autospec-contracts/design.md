# design.md — Phase 2c: autospec強制 + Contract Test

> **Feature**: feat/phase2c-autospec-contracts
> **Requirements**: specs/phase2c-autospec-contracts/requirements.md
> **Design Date**: 2026-02-27

---

## 1. Architecture Overview

Phase 2cは既存のテストインフラに2つの品質保証レイヤーを追加:

```
┌─────────────────────────────────────────────────────────────┐
│ Test Suite (pytest)                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: autospec強制 (conftest.py autouse fixture)        │
│   → すべてのmockにautospec=Trueを適用                       │
│   → シグネチャ不一致を実行時に検出                          │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Contract Tests (tests/contracts/)                 │
│   → mockと実APIの構造整合性を検証                           │
│   → 障害シナリオ（timeout/503/429）を検証                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Mock Drift Detection (scripts/check_mock_drift.py)│
│   → 週次CI実行でmock/実API乖離を検出                        │
│   → GitHub Issue自動生成（dry-runモード対応）               │
└─────────────────────────────────────────────────────────────┘
```

**設計原則**:
- **最小侵襲**: 既存テストコードへの変更を最小化（autospecはfixtureで透過的に適用）
- **段階的適用**: autospec適用で失敗するテストは個別に修正（一括変更しない）
- **独立実行**: Contract Testは`-m integration`で分離実行可能
- **ゼロ依存**: 外部ライブラリ追加なし（unittest.mock + pytest標準機能のみ）

---

## 2. Technology Selection

### 2.1 autospec強制メカニズム

**選択**: pytest autouse fixture + `unittest.mock.patch` wrapper

**理由**:
- pytest標準機能のみで実装可能（外部ライブラリ不要）
- 既存テストコードの変更不要（透過的に適用）
- テスト単位でオプトアウト可能（`@pytest.mark.no_autospec`で無効化）

**代替案と却下理由**:
- ❌ `pytest-mock` plugin: 外部依存追加（親spec OUT-OF-SCOPE）
- ❌ 全テストファイルを手動修正: 変更量大・リスク高

**実装方法**:
```python
# tests/conftest.py
@pytest.fixture(autouse=True)
def enforce_autospec(request):
    """Force autospec=True for all unittest.mock.patch calls."""
    if "no_autospec" in request.keywords:
        yield
        return
    
    original_patch = unittest.mock.patch
    
    def autospec_patch(target, *args, autospec=True, **kwargs):
        return original_patch(target, *args, autospec=autospec, **kwargs)
    
    with patch.object(unittest.mock, 'patch', autospec_patch):
        yield
```

### 2.2 Contract Test実装

**選択**: stub + 実API呼び出し + 構造比較

**理由**:
- R5（stub/spy優先）に準拠
- 実APIレスポンスの構造をstubと比較することで乖離を検出
- `@pytest.mark.integration`で分離実行可能

**テスト構造**:
```python
# AAA構造（R2）
def test_bedrock_converse__normal_response__returns_valid_message_structure():
    # Arrange
    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    request = {...}
    
    # Act
    response = client.converse(**request)
    
    # Assert
    assert "output" in response
    assert "message" in response["output"]
    assert "content" in response["output"]["message"]
    assert isinstance(response["output"]["message"]["content"], list)
```

### 2.3 Mock Drift Detection

**選択**: Python script + boto3/slack_sdk実API呼び出し + JSON schema比較

**理由**:
- CI週次実行可能（独立スクリプト）
- dry-runモードで手動検証可能
- GitHub Issue作成用の出力フォーマット生成

**検出ロジック**:
1. 既存テストからmockレスポンス構造を抽出（AST解析）
2. 実APIを呼び出してレスポンス構造を取得
3. キー構造を比較（型チェックは行わない — 構造のみ）
4. 乖離があればIssue本文を生成

---

## 3. API Interfaces

### 3.1 autospec fixture

```python
# tests/conftest.py

@pytest.fixture(autouse=True)
def enforce_autospec(request):
    """Force autospec=True for all unittest.mock.patch calls.
    
    Opt-out: @pytest.mark.no_autospec
    """
    ...
```

### 3.2 Contract Test共通fixture

```python
# tests/contracts/conftest.py

@pytest.fixture
def bedrock_client():
    """Real Bedrock client for contract tests."""
    return boto3.client("bedrock-runtime", region_name="us-east-1")

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
    return boto3.client("cloudformation", region_name="us-east-1")
```

### 3.3 Mock Drift Script CLI

```bash
# 基本実行（dry-run）
python scripts/check_mock_drift.py --dry-run

# Issue作成モード（CI用）
python scripts/check_mock_drift.py --create-issue

# 特定APIのみチェック
python scripts/check_mock_drift.py --api bedrock --dry-run
```

**出力フォーマット**:
```
=== Mock Drift Detection Report ===
Date: 2026-02-27T21:56:00+09:00

[DRIFT DETECTED] Bedrock Converse API
  Mock: tests/conftest.py:mock_bedrock_client
  Missing keys in mock: ["metrics", "trace"]
  Extra keys in mock: []
  
[OK] Slack chat.postMessage
[OK] CloudFormation describe_stacks

--- GitHub Issue Template ---
Title: [Mock Drift] Bedrock Converse API structure mismatch
Body:
## Summary
Mock response structure in `tests/conftest.py:mock_bedrock_client` is out of sync with real API.

## Missing Keys
- `metrics`
- `trace`

## Action Required
Update mock fixture to match current API schema.
```

---

## 4. Data Models

### 4.1 Contract Test Response Validation

各APIのレスポンス構造を検証するための最小スキーマ:

```python
# Bedrock Converse API
BEDROCK_RESPONSE_SCHEMA = {
    "output": dict,
    "output.message": dict,
    "output.message.content": list,
    "usage": dict,
    "usage.inputTokens": int,
    "usage.outputTokens": int,
    "stopReason": str,
}

# Slack chat.postMessage
SLACK_POST_MESSAGE_SCHEMA = {
    "ok": bool,
    "ts": str,
    "channel": str,
}

# CloudFormation describe_stacks
CFN_DESCRIBE_STACKS_SCHEMA = {
    "Stacks": list,
    "Stacks[0].StackName": str,
    "Stacks[0].StackStatus": str,
    "Stacks[0].CreationTime": "datetime",
}
```

**検証ヘルパー**:
```python
def assert_schema_match(response: dict, schema: dict) -> None:
    """Assert that response matches schema structure."""
    for key_path, expected_type in schema.items():
        value = _get_nested(response, key_path)
        assert isinstance(value, expected_type), \
            f"{key_path}: expected {expected_type}, got {type(value)}"
```

---

## 5. Error Handling

### 5.1 autospec適用時のエラー

**問題**: 既存テストがautospec適用後に失敗する可能性

**対策**:
1. `@pytest.mark.no_autospec`でオプトアウト可能
2. 失敗したテストは個別に修正（一括変更しない）
3. 修正内容をコミットメッセージに記録

**典型的な失敗パターン**:
```python
# Before (autospec無し)
mock_func.return_value = "result"
mock_func("wrong_arg")  # 実行時エラーなし

# After (autospec有り)
mock_func.return_value = "result"
mock_func("wrong_arg")  # TypeError: 引数が実関数と一致しない
```

### 5.2 Contract Test実行時のエラー

**問題**: 実API呼び出しが失敗する可能性（認証エラー、レート制限、ネットワークエラー）

**対策**:
- AWS credentials未設定 → `pytest.skip()`
- Slack token未設定 → `pytest.skip()`
- レート制限 → exponential backoff + retry（最大3回）
- タイムアウト → `pytest.fail()` with clear message

**実装例**:
```python
@pytest.mark.integration
def test_bedrock_converse__normal_response__returns_valid_message_structure(bedrock_client):
    # Arrange
    try:
        request = {...}
        
        # Act
        response = bedrock_client.converse(**request)
        
    except ClientError as e:
        if e.response["Error"]["Code"] == "UnrecognizedClientException":
            pytest.skip("AWS credentials not configured")
        raise
    
    # Assert
    assert_schema_match(response, BEDROCK_RESPONSE_SCHEMA)
```

### 5.3 Mock Drift Script実行時のエラー

**問題**: 実API呼び出し失敗、AST解析失敗

**対策**:
- API呼び出し失敗 → エラーログ出力 + 該当APIをスキップ
- AST解析失敗 → ファイル名とエラー内容を出力 + 処理継続
- 全API失敗 → exit code 1

---

## 6. Security Considerations

### 6.1 Contract Test実行時の認証情報

**リスク**: 実API呼び出しに必要な認証情報（AWS credentials, Slack token）がCI環境に必要

**対策**:
- CI環境では読み取り専用のIAM roleを使用
- Slack tokenはtest workspace専用のbot token
- Contract Testは`-m integration`で分離実行（デフォルトでは実行しない）

**IAM Policy例**:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "cloudformation:DescribeStacks",
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "*"
    }
  ]
}
```

### 6.2 Mock Drift Script実行時の認証情報

**リスク**: 週次CI実行時に実APIを呼び出すため、認証情報が必要

**対策**:
- GitHub Actions secretsに認証情報を保存
- dry-runモードではAPI呼び出しをスキップ（mockレスポンスのみ解析）

### 6.3 テストデータの機密性

**リスク**: Contract Testで実APIを呼び出す際、機密データが含まれる可能性

**対策**:
- テスト用のダミーデータのみ使用（Faker生成）
- レスポンスログには機密情報を含めない（構造のみ検証）

---

## 7. Implementation Notes

### 7.1 autospec適用の段階的ロールアウト

1. **Phase 1**: autouse fixtureを追加（デフォルトで無効）
2. **Phase 2**: 既存テストを実行してautospec互換性を確認
3. **Phase 3**: 失敗したテストを個別に修正
4. **Phase 4**: autouse fixtureをデフォルトで有効化

### 7.2 Contract Test実行時間の最適化

**目標**: 全Contract Test（30+件）を30秒以内に実行

**最適化手法**:
- 並列実行: `pytest -n auto`（pytest-xdist）は使わない（外部依存）
- API呼び出し最小化: 1テストケース = 1 API呼び出し
- レスポンスキャッシュ: 同一リクエストは1回のみ実行（session-scoped fixture）

**実装例**:
```python
@pytest.fixture(scope="session")
def bedrock_normal_response():
    """Cache normal Bedrock response for multiple tests."""
    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    return client.converse(...)
```

### 7.3 Mock Drift Detection実行頻度

**推奨**: 週次（月曜日 9:00 JST）

**理由**:
- API変更は頻繁ではない（月1-2回程度）
- 毎日実行するとAPI呼び出しコストが増加
- 週次で十分な検出精度

**GitHub Actions設定例**:
```yaml
on:
  schedule:
    - cron: '0 0 * * 1'  # 毎週月曜日 00:00 UTC (09:00 JST)
```

---

## 8. Testing Strategy

### 8.1 autospec fixtureのテスト

- ✅ autospecが適用されることを確認
- ✅ `@pytest.mark.no_autospec`でオプトアウト可能
- ✅ 既存テストが全pass

### 8.2 Contract Testのテスト

- ✅ 各API正常系レスポンス構造検証
- ✅ 各APIエラーレスポンス構造検証
- ✅ 障害シナリオ（timeout/503/429）検証
- ✅ 実行時間 ≤ 30秒

### 8.3 Mock Drift Scriptのテスト

- ✅ dry-runモードで実行可能
- ✅ 乖離検出時にIssue本文生成
- ✅ API呼び出し失敗時にエラーハンドリング

---

## 9. Rollback Plan

**autospec適用後に既存テストが大量に失敗した場合**:

1. autouse fixtureを一時的に無効化（`autouse=False`に変更）
2. 失敗したテストをリスト化
3. 失敗原因を分析（シグネチャ不一致 vs バグ）
4. 修正方針を決定（個別修正 vs autospec無効化）

**Contract Test実行時間が30秒を超えた場合**:

1. 最も時間がかかるテストを特定（`pytest --durations=10`）
2. レスポンスキャッシュを追加
3. それでも超える場合はテスト件数を削減（優先度の低いテストを削除）

**Mock Drift Script実行時にAPI呼び出しエラーが頻発する場合**:

1. エラーログを確認（認証エラー vs レート制限 vs ネットワークエラー）
2. 認証情報を再設定
3. レート制限の場合はretry間隔を延長
4. それでも解決しない場合はスクリプトを一時的に無効化

---

## 10. Success Metrics

| Metric | Target | Measurement |
|---|---|---|
| autospec適用後のテスト成功率 | ≥ 80% | `pytest tests/ -m 'not integration and not e2e' --ignore=tests/test_meeting_*.py` |
| Contract Test実行時間 | ≤ 30秒 | `pytest tests/contracts/ -m integration --durations=0` |
| Mock Drift検出精度 | 100%（乖離があれば必ず検出） | 手動でAPI変更を加えてスクリプト実行 |
| CI実行時間増加 | ≤ 5秒（autospec fixtureのオーバーヘッド） | GitHub Actions実行時間比較 |

---

## 11. Future Enhancements (Out of Scope)

- Contract Testの自動生成（OpenAPI specから生成）
- Mock Drift Scriptの自動修正（乖離検出時にmockを自動更新）
- autospec適用率のメトリクス収集（何%のmockがautospec適用済みか）
