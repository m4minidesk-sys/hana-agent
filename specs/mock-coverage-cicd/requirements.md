# requirements.md — mockカバレッジ100% + CI/CD自動化

> **Discovery**: `specs/mock-coverage-cicd/discovery.md`
> **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
> **方針**: mockは資産。全廃ではなく最大活用。
> **Appetite**: 13日
> **テスト思想**: goldbergyoni (R1-R28) + t-wada TDD原則 (TW1-TW8) 準拠

---

## 0. テスト品質原則（AGENTS.md準拠）

本プロジェクトで新規追加・修正する全テストは以下の原則に従う。

### goldbergyoni テスト品質ルール（必須適用）

| ルール | 内容 | 適用範囲 |
|---|---|---|
| R1 | テスト名3パーツ構成: [対象]+[条件]+[期待結果] | 全新規テスト必須 |
| R2 | AAA（Arrange-Act-Assert）パターン厳守、空行で分離 | 全新規テスト必須 |
| R4 | ブラックボックステスト — publicメソッドのみテスト | 全テスト |
| R5 | mockよりstub/spyを優先（mockは内部実装への結合を生む） | 全テスト |
| R6 | リアルなテストデータ（faker/factory_boy推奨、"foo"/"bar"禁止） | 全新規テスト必須 |
| R7 | Property-based testing（hypothesis）— セキュリティクリティカル部分 | safe_shell, file操作, 入力検証 |
| R13 | コンポーネントテスト最優先（API単位の統合テストがROI最高） | テスト設計方針 |
| R15 | グローバルseed禁止 — 各テストが自分のデータを作成 | 全テスト |
| R16 | テストの5結果をカバー: Response/New state/External calls/Message queues/Observability | 新規テスト |
| R17 | 障害シナリオテスト: タイムアウト、503、遅延レスポンス | 外部API連携テスト |
| R25 | カバレッジ目標80%以上（段階的: 80→85%） | CI閾値 |
| R27 | ミューテーションテスト（mutmut）でテストの質を測定 | Phase 4 |

### t-wada TDD原則（必須適用）

| ルール | 内容 | 適用 |
|---|---|---|
| TW1 | テストの4性質: Self-Validating / Repeatable / Independent / Fast | 全テスト |
| TW2 | 効果最大化4因子: 誰が/いつ/どのくらい/どの頻度で | テスト設計方針 |
| TW4 | TDDサイクル: TODOリスト→Red→Green→Refactor | 新規テスト追加時 |
| TW5 | 構造的結合を避ける: 振る舞いの変化に敏感、構造の変化に鈍感 | 全テスト |
| TW6 | YAGNI + シンプルな設計の4原則 | テスト設計方針 |

### AGENTS.md厳守ルール

- **pytest.mark.skip / skipif / importorskip 全面禁止**
- **全テストが skip 0 で PASS することが必須**（E2E含む）
- E2Eテストは `@pytest.mark.e2e` で分類するが、CI環境を整備して全件実行可能にする

---

## 1. 背景と目的

### 背景
yui-agentは967テスト/46ファイルの既存テスト資産を持つが、以下の問題がある：
- テスト分類なし（unit/component/integration/e2eが混在）
- CI/CDパイプラインなし（テストが自動実行されない）
- mockなしファイル9個、skipテスト56件
- mockと実APIの整合性チェックなし
- 過去破棄されたテスト資産（7ファイル/400行）が未活用
- テスト品質ルール（R1-R28, TW1-TW8）が未適用

### 目的
1. **外部依存分離率100%** — 全テストで外部依存（AWS/Slack/I/O）がmock/stubで分離
2. **skip 0達成** — E2E含む全テストがskipなしでPASS
3. **CI/CD自動化** — 全PRで自動テスト実行、PRマージゲート
4. **mock自動化** — mock生成・更新・品質検証の仕組みを構築
5. **テスト品質準拠** — goldbergyoni + t-wada原則を全新規テストに適用
6. **テストカバレッジ85%** — 段階的に達成（80→85%）

---

## 2. スコープ

### IN-SCOPE
- pytestマーカー定義（unit/component/integration/e2e/security）
- GitHub Actions CI/CDパイプライン構築
- mockなし9ファイルへのmock追加
- 旧テスト7ファイル復旧・統合
- skip 56件全件解消（E2E 8件含む — CI環境整備で実行可能化）
- conftest.py共通mock fixture集約
- mock生成スクリプト（`scripts/generate_mock_fixtures.py`）
- autospec強制（R5 stub/spy優先と両立）
- 簡易Contract Testing（週次、主要API毎に10+件 = 計30+件）
- CI mock品質検証（unused/重複/使用率）
- mock factory pattern + テストヘルパー（faker連携）
- faker/factory_boy導入（R6準拠 — 全新規テストに必須適用）
- テスト名3パーツ構成（R1 — 全新規テストに必須適用）
- AAA構造（R2 — 全新規テストに必須適用）
- Property-based testing導入（R7 — hypothesis、セキュリティクリティカル部分）
- ミューテーションテスト導入（R27 — mutmut）
- 障害シナリオテスト（R17 — タイムアウト、503、遅延）
- tests/README.md（fixture一覧+サンプル+TW1の4性質ガイド）

### OUT-OF-SCOPE
- 既存テストの全面リネーム（R1は新規テストのみ必須、既存は段階的改善）
- 既存テストの全面AAA書き換え（R2は新規テストのみ必須）
- moto, responses等の外部mockライブラリ導入
- カオステスト

---

## 3. 要求仕様

### FR-01: テスト分類基盤

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-01-1 | `tests/conftest.py` にpytestマーカー5種を定義 | `pytest --markers` で unit/component/integration/e2e/security が表示 |
| FR-01-2 | `pyproject.toml` の `[tool.pytest.ini_options]` にマーカー登録 | マーカー未登録の警告が0件 |
| FR-01-3 | 既存46テストファイルにマーカー付与 | 全ファイルに適切なマーカー、テストピラミッド比率: Unit ~20% / Component ~55% / Integration ~15% / E2E ~10% |

### FR-02: mock共通基盤

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-02-1 | `tests/conftest.py` に共通mock fixture 10+個を定義 | `mock_bedrock_client`, `mock_slack_client`, `mock_open_file` 等。グローバルseed禁止（R15）、各fixtureが独立データ生成 |
| FR-02-2 | fixture命名規則: `mock_{service}_client` / `mock_{module}_factory` | 全fixtureが命名規則に準拠 |
| FR-02-3 | fixtureスコープ戦略: session(認証系)/module(API)/function(状態変更) | 各fixtureに適切なscope指定。sessionスコープは状態を持たないこと |
| FR-02-4 | `tests/factories.py` にfaker連携mock response factory定義 | `BedrockResponseFactory`, `SlackResponseFactory` がfakerでリアルデータ生成（R6） |
| FR-02-5 | `tests/helpers.py` にテストヘルパー関数定義 | `assert_bedrock_called_with_model()` 等。振る舞い検証のみ（R4/TW5） |

### FR-03: mockカバレッジ100% + skip 0

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-03-1 | mockなし9ファイルに外部依存mock/stubを追加 | 9ファイル全てでstub/spy優先のmock使用（R5）、全テストpass |
| FR-03-2 | 旧テスト7ファイルを復旧・統合 | 7ファイル全pass、アサーション数≥旧版、R16（5結果）のうち最低3結果をカバー |
| FR-03-3 | skip 48件をmock化して解消 | `pytest --collect-only` でskip 0件（unit/component層） |
| FR-03-4 | E2E 8件もCI環境整備で実行可能化 | `pytest -m e2e` で全8件pass（CI環境にSecrets設定）、skip 0 |
| FR-03-5 | 全テストでR1/R2準拠（新規追加分） | 新規追加テストの100%がテスト名3パーツ+AAA構造 |

### FR-04: CI/CDパイプライン

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-04-1 | `.github/workflows/test.yml` 作成 | PR作成時にCI自動実行 |
| FR-04-2 | Python 3.12, 3.13 のmatrix実行 | 2バージョンで全テストpass |
| FR-04-3 | pytest-cov でカバレッジ計測 | `--cov=src/yui --cov-report=xml` が正常動作 |
| FR-04-4 | PRマージゲート設定 | GitHub branch protection rulesで "Require status checks to pass" 有効 |
| FR-04-5 | カバレッジ閾値: 80%スタート→85%最終 | `fail_ci_if_under` が段階的に設定（80→85） |
| FR-04-6 | E2E CIジョブ（Secrets付き） | `.github/workflows/e2e.yml` でE2Eテスト実行、Secrets設定済み |

### FR-05: mock自動化

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-05-1 | `scripts/generate_mock_fixtures.py` — AST解析でmock fixture自動生成 | `python scripts/generate_mock_fixtures.py src/yui/tools/new.py` が conftest.pyに追記。R4準拠（publicインターフェースのみ対象） |
| FR-05-2 | 全patchでautospec=True強制 | `tests/conftest.py` のautouse fixtureでautospec強制。R5（stub/spy優先）と両立: autospecはシグネチャ安全性、stub/spyは検証方法 |
| FR-05-3 | `scripts/check_mock_drift.py` — 実APIとmockの乖離検知 | 週次CIで自動実行、乖離時GitHub Issue作成 |
| FR-05-4 | `tests/contracts/` — Contract Test 30+件 | 主要API毎（Bedrock/Slack/boto3）に10+件。障害シナリオ含む（R17: タイムアウト、503、遅延）。`pytest tests/contracts/ -m integration` が全pass |
| FR-05-5 | `scripts/check_mock_coverage.py` — 外部依存のmock化チェック | CI実行時に未mock外部依存を検知 |
| FR-05-6 | `scripts/check_unused_mocks.py` — 未使用fixture検知 | CI実行時にunused fixture 0件 |
| FR-05-7 | fixture重複検知 | CIで同名fixture複数定義を検知、0件 |

### FR-06: テスト品質向上

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-06-1 | faker/factory_boy導入 | `pip install faker factory_boy` が `pyproject.toml [dev]` に追加。全新規テストでfakerによるリアルデータ生成（R6） |
| FR-06-2 | Property-based testing導入 | `pip install hypothesis`。safe_shell, file操作, 入力検証に対してhypothesisテスト10+件追加（R7） |
| FR-06-3 | ミューテーションテスト導入 | `pip install mutmut`。Phase 4でmutmut実行、ミューテーションスコア≥70%（R27） |
| FR-06-4 | 障害シナリオテスト | 外部API連携テストにタイムアウト/503/遅延シナリオ各1件以上（R17） |

### FR-07: ドキュメント

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-07-1 | `tests/README.md` にmock fixture一覧+使用サンプル+テスト品質ガイド | fixture名、用途、使用例、TW1の4性質（Self-Validating/Repeatable/Independent/Fast）ガイド |
| FR-07-2 | conftest.py内の全fixtureにdocstring | 全fixtureに1行以上のdocstring |

---

## 4. 非機能要件

### NFR-01: パフォーマンス

| ID | 要求 | 受入基準 | 根拠 |
|---|---|---|---|
| NFR-01-1 | CI実行時間（unit+component） | ≤ 5分 | TW1 Fast原則。現状967テスト未計測→Phase 1で初回計測して再調整 |
| NFR-01-2 | ローカル実行時間（unitのみ） | ≤ 30秒 | TW2 高頻度実行のため高速必須 |

### NFR-02: 品質

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-02-1 | テストカバレッジ | ≥ 85%（段階: 80→85%）。R25準拠: 80%を初期閾値 |
| NFR-02-2 | 品質後退なし | 既存911 passingテストが全pass |
| NFR-02-3 | バグ検出力 | 新規テストで未検出バグ1件以上発見 |
| NFR-02-4 | ミューテーションスコア | mutmutによるミューテーションスコア≥70%（R27） |

### NFR-03: 保守性

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-03-1 | mock fixture集約率 | ≥ 80% |
| NFR-03-2 | mock更新影響範囲 | API変更時、修正ファイル ≤ 3 |
| NFR-03-3 | mock再利用率 | 新テスト追加時 ≥ 60% |
| NFR-03-4 | テストピラミッド比率維持 | Unit ~20% / Component ~55% / Integration ~15% / E2E ~10% をCIで計測 |

### NFR-04: セキュリティ

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-04-1 | テストコード内に認証情報平文なし | `detect-secrets` でクリーン |
| NFR-04-2 | security markerテスト全pass | 攻撃パターンテスト全pass |

### NFR-05: 開発者体験

| ID | 要求 | 受入基準 |
|---|---|---|
| NFR-05-1 | 認証不要実行 | AWS/Slack認証なしでunit/component全pass |
| NFR-05-2 | ドキュメント | tests/README.md完備（TW1ガイド含む） |
| NFR-05-3 | TDDサイクルガイド | 新規テスト追加時のTDDフロー（TW4: TODOリスト→Red→Green→Refactor）をREADMEに記載 |

---

## 5. 実装フェーズ

| Phase | 内容 | 期間 | 担当 | 完了判定 |
|---|---|---|---|---|
| 0 | spike: autospec試行+mock生成スクリプト試作+faker動作確認+工数再見積 | 0.8日 | Kiro | fail率≤20%, faker/hypothesis動作確認, 工数見積完了 |
| 1 | conftest.py設計+マーカー+CI yml+カバレッジ初回計測+実行時間ベースライン | 1.2日 | Kiro | FR-01全項, FR-04-1/3, 実行時間計測 |
| 1.5 | 旧テスト7ファイル復旧+共通fixture集約（R1/R2/R6準拠） | 1.5日 | Kiro | FR-02-1, FR-03-2, 復旧テストがR1/R2/R6/R16準拠 |
| 2a | mockなし9ファイル+mock生成スクリプト適用（R5 stub/spy優先） | 2.0日 | Kiro | FR-03-1, FR-05-1, 新規テストR1/R2/R6準拠 |
| 2b | skip 56件全件解消（E2E 8件含む — CI Secrets設定） | 3.0日 | Kiro | FR-03-3/4, skip 0件 |
| 2c | autospec強制+contract test 30+件（障害シナリオ含む） | 1.5日 | Kiro | FR-05-2/3/4, R17障害テスト含む |
| 3 | CI/CD+mock品質検証+E2E CIジョブ | 1.0日 | AYA | FR-04全項, FR-05-5/6/7, FR-04-6 |
| 4 | カバレッジ段階達成+Property-based testing+ミューテーションテスト+週次integration test | 2.0日 | AYA+Kiro | NFR-02-1/4, FR-06-2/3, 最終検証 |

**合計: 13日**（テスト品質ルール適用+E2E CI整備+R7/R27追加で増加）

---

## 6. リスクと軽減策

| リスク | 発生確率 | 影響 | 軽減策 |
|---|---|---|---|
| autospec適用で既存テスト大量fail | 中 | Phase 0ブロック | spike 5ファイルで事前検証、fail率≤20%でGo |
| skip解消が想定以上に複雑 | 中 | Phase 2b膨張 | spike最複雑2件で事前検証、超過→スコープ縮小 |
| E2E CI環境整備（Secrets設定）が困難 | 中 | Phase 2b/3遅延 | hanさんにSecrets設定依頼、最悪ローカルE2E実行で代替 |
| CI実行時間超過 | 低 | DX低下 | pytest-xdist並列化、marker分離で段階実行 |
| 旧テストAPI差分大 | 低 | Phase 1.5遅延 | 最初2ファイルで判断、差分大→復旧中止 |
| mock生成スクリプト精度不足 | 中 | Phase 2a遅延 | spike試作で80%自動可能か判定、手動フォールバック |
| mutmutの実行時間が長い | 中 | Phase 4遅延 | 対象をクリティカルモジュールに限定（全体の30%） |

---

## 7. 依存関係

- GitHub Actions: リポジトリSettings → Actions → Allowed に設定
- GitHub Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `SLACK_BOT_TOKEN`（E2E+Integration test用）
- Branch protection rules: Phase 3でrequired checks設定
- Codecov: Phase 3でGitHub App連携（代替: pytest-cov HTML artifact）
- pip packages: `faker`, `factory_boy`, `hypothesis`, `mutmut`, `pytest-cov`, `detect-secrets`
