# requirements.md — Phase 2c: autospec強制 + Contract Test

> **親spec**: `specs/mock-coverage-cicd/requirements.md` (v2.2)
> **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
> **Phase**: 2c（テストインフラspec内の連番）
> **Appetite**: 1.5日
> **テスト思想**: goldbergyoni (R5, R17) + t-wada TDD原則準拠

---

## 1. 背景

Phase 0-2b完了済み：
- マーカー5種定義 + CI/CD構築（PR #77）
- 共通fixture + factories + helpers（PR #78）
- mockカバレッジ分析 + CFn mockテスト（PR #79）
- skip全件解消 + CI integrationジョブ（PR #80）

Phase 2cではmock品質の強化として以下を実施:
1. **autospec強制** — mockの型安全性を実行時に検知
2. **Contract Test** — mockと実APIの整合性を検証

---

## 2. 要求仕様

### FR-05-2: autospec=True強制

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-1 | `tests/conftest.py` にautouse fixtureで `unittest.mock.patch` のデフォルトを `autospec=True` に設定 | `pytest --fixtures` でautospec強制fixtureが表示される |
| AC-2 | 既存テストがautospec適用後も全pass | `pytest tests/ -m 'not integration and not e2e' --ignore=tests/test_meeting_*.py` で0 failedかつ0 error |
| AC-3 | autospecで検出されるシグネチャ不一致があれば修正 | 修正内容をコミットメッセージに記載 |

**注意:** autospecはR5（stub/spy優先）と両立する。autospec=シグネチャ安全性、stub/spy=検証方法。

### FR-05-3: mock driftスクリプト

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-4 | `scripts/check_mock_drift.py` を作成 | `python scripts/check_mock_drift.py` が正常実行可能 |
| AC-5 | 主要API（Bedrock Converse, Slack API, boto3 CFn）のmockレスポンス構造と実APIスキーマを比較 | 乖離検出時にGitHub Issue作成用の出力（タイトル+本文）を生成 |
| AC-6 | CIで週次実行可能（`-m integration` 不要の独立スクリプト） | `--dry-run` オプションでIssue作成せずに結果表示 |

### FR-05-4: Contract Test 30+件

| ID | 要求 | 受入基準 |
|---|---|---|
| AC-7 | `tests/contracts/` ディレクトリ作成 | ディレクトリ構造: `tests/contracts/test_bedrock_contract.py`, `test_slack_contract.py`, `test_boto3_contract.py` |
| AC-8 | Bedrock Converse API Contract Test 10+件 | 正常レスポンス構造、エラーレスポンス構造、ストリームレスポンス、タイムアウト（R17）、503エラー（R17）、レートリミット（R17）を検証 |
| AC-9 | Slack API Contract Test 10+件 | chat.postMessage、reactions.add、conversations.history のレスポンス構造＋429 rate limit（R17）＋遅延レスポンス（R17）を検証 |
| AC-10 | boto3 (CFn/Lambda/SecretsManager) Contract Test 10+件 | CFn describe_stacks、Lambda invoke、SecretsManager get_secret_value のレスポンス構造＋AccessDenied＋ResourceNotFound（R17）を検証 |
| AC-11 | 全Contract Testに `@pytest.mark.integration` マーカー | `pytest tests/contracts/ -m integration` で全件実行可能 |
| AC-12 | R17障害シナリオ: 各API最低1件のタイムアウト/503/遅延テスト | タイムアウト（stubで遅延注入）、503（stub応答）、遅延レスポンス（stub + time.sleep mock）|

### テスト名規則（R1: 3パーツ構成）

```
test_{API名}__{条件/シナリオ}__{期待結果}

例:
test_bedrock_converse__normal_response__returns_valid_message_structure
test_bedrock_converse__timeout_30s__raises_read_timeout_error
test_slack_post_message__rate_limited_429__retries_after_delay
test_cfn_describe_stacks__nonexistent_stack__raises_client_error
test_secrets_manager_get__access_denied__raises_permission_error
```

### AAA構造（R2）

全テストは Arrange → Act → Assert を空行で分離すること。

---

## 3. 技術的制約

- Python 3.12+ / pytest / unittest.mock
- 外部ライブラリ追加不可（moto, responses等は使わない — 親specのOUT-OF-SCOPE）
- autospec適用で既存テストのfail率が20%を超える場合はPhase 0 spikeの結果を参照して判断
- テスト実行時間: Contract Test全体で ≤ 30秒

---

## 4. gitルール

- Feature branch: `feat/phase2c-autospec-contracts`
- base: `main`
- squash merge
- PRに `closes #75` は入れない（#75は全Phase完了後にclose）

---

## 5. ファイル構成（期待）

```
tests/
├── conftest.py          # autospec強制fixture追加
├── contracts/
│   ├── __init__.py
│   ├── conftest.py      # contract test共通fixture
│   ├── test_bedrock_contract.py
│   ├── test_slack_contract.py
│   └── test_boto3_contract.py
scripts/
└── check_mock_drift.py
```
