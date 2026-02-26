# requirements.md — mockカバレッジ100% + CI/CD自動化

> **Discovery**: `specs/mock-coverage-cicd/discovery.md`
> **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
> **方針**: mockは資産。全廃ではなく最大活用。
> **Appetite**: 11.5日

---

## 1. 背景と目的

### 背景
yui-agentは967テスト/46ファイルの既存テスト資産を持つが、以下の問題がある：
- テスト分類なし（unit/component/integration/e2eが混在）
- CI/CDパイプラインなし（テストが自動実行されない）
- mockなしファイル9個、skipテスト56件
- mockと実APIの整合性チェックなし
- 過去破棄されたテスト資産（7ファイル/400行）が未活用

### 目的
1. **外部依存分離率100%** — 全テストで外部依存（AWS/Slack/I/O）がmockで分離されている
2. **CI/CD自動化** — 全PRで自動テスト実行、PRマージゲートとしてテスト必須
3. **mock自動化** — mock生成・更新・品質検証の仕組みを構築
4. **テストカバレッジ85%以上** — 段階的に達成（70→80→85%）

---

## 2. スコープ

### IN-SCOPE
- pytestマーカー定義（unit/component/integration/e2e/security）
- GitHub Actions CI/CDパイプライン構築
- mockなし9ファイルへのmock追加
- 旧テスト7ファイル復旧・統合
- skip 48件のmock化解消（E2E 8件はoptional）
- conftest.py共通mock fixture集約
- mock生成スクリプト（`scripts/generate_mock_fixtures.py`）
- autospec強制
- 簡易Contract Testing（週次）
- CI mock品質検証（unused/重複/使用率）
- mock factory pattern + テストヘルパー
- tests/README.md（fixture一覧+サンプル）

### OUT-OF-SCOPE
- テスト名3パーツ構成リネーム（Phase 5で別途対応）
- AAA構造への全面書き換え（Phase 5で別途対応）
- faker/factory_boy導入（Phase 5で別途対応）
- E2Eテスト本格整備（Slack/Workshop/Meeting）
- moto, responses等の外部mockライブラリ導入

---

## 3. 要求仕様

### FR-01: テスト分類基盤

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-01-1 | `tests/conftest.py` にpytestマーカー5種を定義 | `pytest --markers` で unit/component/integration/e2e/security が表示 |
| FR-01-2 | `pyproject.toml` の `[tool.pytest.ini_options]` にマーカー登録 | マーカー未登録の警告が0件 |
| FR-01-3 | 既存46テストファイルにマーカー付与 | 全ファイルに適切なマーカーが付与されている |

### FR-02: mock共通基盤

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-02-1 | `tests/conftest.py` に共通mock fixture 10+個を定義 | `mock_bedrock_client`, `mock_slack_client`, `mock_open_file` 等が定義 |
| FR-02-2 | fixture命名規則: `mock_{service}_client` / `mock_{module}_factory` | 全fixtureが命名規則に準拠 |
| FR-02-3 | fixtureスコープ戦略: session(認証系)/module(API)/function(状態変更) | 各fixtureに適切なscope指定 |
| FR-02-4 | `tests/factories.py` にmock response factory定義 | `BedrockResponseFactory`, `SlackResponseFactory` が利用可能 |
| FR-02-5 | `tests/helpers.py` にテストヘルパー関数定義 | `assert_bedrock_called_with_model()` 等が利用可能 |

### FR-03: mockカバレッジ100%

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-03-1 | mockなし9ファイルに外部依存mockを追加 | 9ファイル全てでmock使用、全テストpass |
| FR-03-2 | 旧テスト7ファイルを復旧・統合 | 7ファイルの対応テストが全pass、アサーション数≥旧版 |
| FR-03-3 | skip 48件をmock化して解消 | `pytest -m "not e2e" --collect-only` でskip 0件 |
| FR-03-4 | E2E 8件は `@pytest.mark.e2e` でCI optional | `pytest -m "not e2e"` で全テストpass |

### FR-04: CI/CDパイプライン

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-04-1 | `.github/workflows/test.yml` 作成 | PR作成時にCI自動実行 |
| FR-04-2 | Python 3.12, 3.13 のmatrix実行 | 2バージョンで全テストpass |
| FR-04-3 | pytest-cov でカバレッジ計測 | `--cov=src/yui --cov-report=xml` が正常動作 |
| FR-04-4 | PRマージゲート設定 | GitHub branch protection rulesで "Require status checks to pass" 有効 |
| FR-04-5 | カバレッジ閾値: 70%スタート→85%段階引き上げ | `fail_ci_if_under` が段階的に設定 |

### FR-05: mock自動化

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-05-1 | `scripts/generate_mock_fixtures.py` — AST解析でmock fixture自動生成 | `python scripts/generate_mock_fixtures.py src/yui/tools/new.py` が conftest.pyに追記 |
| FR-05-2 | 全patchでautospec=True強制 | `tests/conftest.py` のautouse fixtureでautospec強制 |
| FR-05-3 | `scripts/check_mock_drift.py` — 実APIとmockの乖離検知 | 週次CIで自動実行、乖離時GitHub Issue作成 |
| FR-05-4 | `tests/contracts/` — Contract Test 5+件 | `pytest tests/contracts/ -m integration` が全pass |
| FR-05-5 | `scripts/check_mock_coverage.py` — 外部依存のmock化チェック | CI実行時に未mock外部依存を検知 |
| FR-05-6 | `scripts/check_unused_mocks.py` — 未使用fixture検知 | CI実行時にunused fixture 0件 |
| FR-05-7 | fixture重複検知 | CIで同名fixture複数定義を検知、0件 |

### FR-06: ドキュメント

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-06-1 | `tests/README.md` にmock fixture一覧+使用サンプル | fixture名、用途、使用例が記載 |
| FR-06-2 | conftest.py内の全fixtureにdocstring | 全fixtureに1行以上のdocstring |

---

## 4. 非機能要件

### NFR-01: パフォーマンス

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-01-1 | CI実行時間（unit+component） | ≤ 5分 |
| NFR-01-2 | ローカル実行時間（unitのみ） | ≤ 30秒 |

### NFR-02: 品質

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-02-1 | テストカバレッジ | ≥ 85%（段階: 70→80→85%） |
| NFR-02-2 | 品質後退なし | 既存911 passingテストが全pass |
| NFR-02-3 | バグ検出力 | 新規テストで未検出バグ1件以上発見 |

### NFR-03: 保守性

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-03-1 | mock fixture集約率 | ≥ 80% |
| NFR-03-2 | mock更新影響範囲 | API変更時、修正ファイル ≤ 3 |
| NFR-03-3 | mock再利用率 | 新テスト追加時 ≥ 60% |

### NFR-04: セキュリティ

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-04-1 | テストコード内に認証情報平文なし | `detect-secrets` でクリーン |
| NFR-04-2 | security markerテスト全pass | 攻撃パターンテスト全pass |

### NFR-05: 開発者体験

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-05-1 | 認証不要実行 | AWS/Slack認証なしでunit/component全pass |
| NFR-05-2 | ドキュメント | tests/README.md完備 |

---

## 5. 実装フェーズ

| Phase | 内容 | 期間 | 担当 | 完了判定 |
|---|---|---|---|---|
| 0 | spike: autospec試行+mock生成スクリプト試作+工数再見積 | 0.8日 | Kiro | fail率≤20%, 工数見積完了 |
| 1 | conftest.py設計+マーカー+CI yml+カバレッジ初回計測 | 1.2日 | Kiro | FR-01全項, FR-04-1/3 |
| 1.5 | 旧テスト7ファイル復旧+共通fixture集約 | 1.5日 | Kiro | FR-02-1, FR-03-2 |
| 2a | mockなし9ファイル+mock生成スクリプト適用 | 2.0日 | Kiro | FR-03-1, FR-05-1 |
| 2b | skip 48件mock化解消 | 3.0日 | Kiro | FR-03-3/4 |
| 2c | autospec強制+contract test | 1.2日 | Kiro | FR-05-2/3/4 |
| 3 | CI/CD+mock品質検証 | 1.0日 | AYA | FR-04-2/4/5, FR-05-5/6/7 |
| 4 | カバレッジ段階達成+週次integration test | 0.8日 | AYA | NFR-02-1, 最終検証 |

**合計: 11.5日**

---

## 6. リスクと軽減策

| リスク | 発生確率 | 影響 | 軽減策 |
|---|---|---|---|
| autospec適用で既存テスト大量fail | 中 | Phase 0ブロック | spike 5ファイルで事前検証、fail率≤20%でGo |
| skip解消が想定以上に複雑 | 中 | Phase 2b膨張 | spike最複雑2件で事前検証、超過→スコープ縮小 |
| CI実行時間超過 | 低 | DX低下 | pytest-xdist並列化、marker分離で段階実行 |
| 旧テストAPI差分大 | 低 | Phase 1.5遅延 | 最初2ファイルで判断、差分大→復旧中止 |
| mock生成スクリプト精度不足 | 中 | Phase 2a遅延 | spike試作で80%自動可能か判定、手動フォールバック |

---

## 7. 依存関係

- GitHub Actions: リポジトリSettings → Actions → Allowed に設定
- GitHub Secrets: `AWS_ACCESS_KEY_ID`, `SLACK_BOT_TOKEN` （Integration test用、Phase 3以降）
- Branch protection rules: Phase 3でrequired checks設定
- Codecov: Phase 3でGitHub App連携（代替: pytest-cov HTML artifact）
