# requirements.md — mockカバレッジ100% + CI/CD自動化 + クラウドテスト

> **Discovery**: `specs/mock-coverage-cicd/discovery.md`
> **Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)
> **方針**: mockは資産。全廃ではなく最大活用。
> **Appetite**: 17日（クラウドテスト追加で+4日）
> **テスト思想**: goldbergyoni (R1-R28) + t-wada TDD原則 (TW1-TW8) 準拠
> **Rev**: v2 — 2026-02-27 クラウド実装（Phase 6: Lambda Deployment）対応追加

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

**v2追加背景（2026-02-27）:**
Phase 6（Lambda Deployment — クラウドSlackアダプタ）の実装が直近で開始される。
これにより以下の新コンポーネントがテスト対象に加わる：
- `lambda_handler.py` — Lambda handler（Slack Events API受信）
- CloudFormation/CDK テンプレート — Lambda + API Gateway + EventBridge
- Secrets Manager — トークン取得
- Socket Mode ↔ Events API 切替ロジック
- Lambda Layers

クラウドコンポーネントの追加に伴い、テストピラミッドの各層（コンポーネント/インテグレーション/E2E）を
クラウド対応で再設計する必要がある。

### 目的
1. **外部依存分離率100%** — 全テストで外部依存（AWS/Slack/I/O）がmock/stubで分離
2. **skip 0達成** — E2E含む全テストがskipなしでPASS
3. **CI/CD自動化** — 全PRで自動テスト実行、PRマージゲート
4. **mock自動化** — mock生成・更新・品質検証の仕組みを構築
5. **テスト品質準拠** — goldbergyoni + t-wada原則を全新規テストに適用
6. **テストカバレッジ85%** — 段階的に達成（80→85%）
7. **🆕 クラウドテスト3層設計** — Lambda/API GW/SecretsManagerのコンポーネント/インテグレーション/E2Eテスト

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
- 🆕 **クラウドコンポーネントテスト** — Lambda handler, Events APIパース, Secrets Manager取得のmockテスト
- 🆕 **クラウドインテグレーションテスト** — 実AWS環境でのLambda invoke, API Gateway経由リクエスト, CFnスタックデプロイ
- 🆕 **クラウドE2Eテスト** — デプロイ済みLambda + Slack Events API → 実Slackメッセージ送受信の全フロー
- 🆕 **CI E2Eジョブ** — クラウドE2Eテスト用のCI/CDジョブ（デプロイ→テスト→クリーンアップ）

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

### 🆕 FR-08: クラウドテスト3層設計（v2追加 — Phase 6 Lambda Deployment対応）

#### FR-08-A: コンポーネントテスト（mock/stub — CIで毎回実行）

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-08-A1 | Lambda handlerのリクエストパース+レスポンス生成テスト | Slack Events APIのchallenge/event/url_verification 3パターン以上。stubされたboto3/Slack SDKでhandler単体テスト |
| FR-08-A2 | Secrets Manager トークン取得のstubテスト | 正常取得 / シークレット未存在 / 権限エラー 3パターン。boto3 stub |
| FR-08-A3 | Socket Mode ↔ Events API 切替ロジックのテスト | 設定値に応じた正しいアダプタ選択。mock環境変数+設定 |
| FR-08-A4 | Lambda冷起動シミュレーション | handler初期化（グローバル変数/コンテキスト再利用）のテスト。stubされた外部依存 |
| FR-08-A5 | API Gateway イベント→Slack Event変換 | API GW proxy event形式 → Slackイベント構造体への正しいパース |
| FR-08-A6 | EventBridge cronトリガーのテスト | EventBridgeスケジュールイベント → heartbeat/cron処理の正しい呼び出し |

#### FR-08-B: インテグレーションテスト（実AWS — CI integrationジョブ）

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-08-B1 | CFnスタックデプロイ+検証+クリーンアップ | テスト用CFnテンプレートでLambda+API GWスタック作成→リソース存在確認→スタック削除。CI Secrets使用 |
| FR-08-B2 | Lambda invoke（デプロイ済みfunction） | `lambda:InvokeFunction` でテストイベント送信→正常レスポンス確認 |
| FR-08-B3 | Secrets Manager 実取得 | テスト用シークレット作成→取得→検証→削除 |
| FR-08-B4 | API Gateway → Lambda 経由リクエスト | API GWエンドポイントにHTTPリクエスト→Lambda経由→正常レスポンス |
| FR-08-B5 | EventBridge ルール作成+トリガー確認 | テスト用ルール作成→Lambda起動確認→ルール削除 |

#### FR-08-C: E2Eテスト（フルフロー — 手動/ステージング環境）

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-08-C1 | Slack → API GW → Lambda → Bedrock → Slack 全フロー | 実Slackチャンネルにメッセージ送信→API GW受信→Lambda処理→Bedrock呼び出し→Slack返信確認。エンドツーエンド30秒以内 |
| FR-08-C2 | Lambda冷起動→応答 | 15分間未使用のLambdaに初回リクエスト→正常応答。冷起動時間計測 |
| FR-08-C3 | EventBridge → Lambda → Heartbeat | EventBridgeスケジュール発火→Lambda起動→Heartbeat処理→Slack通知確認 |
| FR-08-C4 | フェイルオーバー: Lambda → ローカルSocket Mode | Lambda障害時にSocket Mode（ローカル）にフォールバック可能なことを確認 |

#### FR-08-D: CI/CDジョブ拡張

| ID | 要求 | 受入基準 |
|---|---|---|
| FR-08-D1 | CI `cloud-component` ジョブ | FR-08-Aのテストを既存unit/componentジョブに統合（追加mock依存なし） |
| FR-08-D2 | CI `cloud-integration` ジョブ | FR-08-BのテストをAWS Secrets付きジョブで実行。`needs: test`で依存 |
| FR-08-D3 | E2Eテストは手動トリガー | `workflow_dispatch`でE2Eジョブを手動実行可能に。定期実行はステージング環境構築後 |

---

## 4. 非機能要件

### NFR-01: パフォーマンス

| ID | 要求 | 受入基準 | 根拠 |
|---|---|---|---|
| NFR-01-1 | CI実行時間（unit+component） | ≤ 5分 | TW1 Fast原則。現状967テスト未計測→Phase 1で初回計測して再調整 |
| NFR-01-2 | ローカル実行時間（unitのみ） | ≤ 30秒 | TW2 高頻度実行のため高速必須 |
| NFR-01-3 | 🆕 CI cloud-integration実行時間 | ≤ 10分 | CFnスタックデプロイ+テスト+クリーンアップ含む |
| NFR-01-4 | 🆕 Lambda冷起動時間 | ≤ 10秒 | E2Eテストで計測・記録 |

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
| NFR-03-4 | テストピラミッド比率維持 | Unit ~20% / Component ~50% / Integration ~20% / E2E ~10% をCIで計測（クラウドテスト追加で integration比率増加） |

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

### 完了済み ✅

| Phase | 内容 | 期間 | 担当 | PR |
|---|---|---|---|---|
| 0 | spike: autospec試行+mock生成スクリプト試作+faker動作確認+工数再見積 | 0.8日 | Kiro | — |
| 1 | conftest.py設計+マーカー+CI yml+カバレッジ初回計測+実行時間ベースライン | 1.2日 | Kiro | #77 |
| 1.5 | 旧テスト7ファイル復旧+共通fixture集約（R1/R2/R6準拠） | 1.5日 | Kiro | #78 |
| 2a | mockなし9ファイル+mock生成スクリプト適用（R5 stub/spy優先） | 2.0日 | Kiro | #79 |
| 2b | skip全件解消 + CI integrationジョブ + マーカー3層分離 | 3.0日 | Kiro | #80 |

### 残りフェーズ（v2更新）

| Phase | 内容 | 期間 | 担当 | 完了判定 |
|---|---|---|---|---|
| 2c | autospec強制+contract test 30+件（障害シナリオ含む） | 1.5日 | Kiro | FR-05-2/3/4, R17障害テスト含む |
| 3a | 🆕 クラウドコンポーネントテスト — Lambda handler/Secrets Manager/Events APIのmockテスト | 2.0日 | Kiro | FR-08-A全項。`pytest -m component` に含まれてCIで毎回実行 |
| 3b | 🆕 クラウドインテグレーションテスト — 実AWSでのLambda invoke/CFnデプロイ/API GW | 2.0日 | Kiro+AYA | FR-08-B全項。CI `cloud-integration` ジョブ追加 |
| 3c | 🆕 クラウドE2Eテスト設計 — Slack→API GW→Lambda→Bedrock→Slack全フロー | 1.5日 | AYA | FR-08-C全項。`workflow_dispatch`で手動トリガー |
| 3d | CI/CD拡張+mock品質検証+E2Eジョブ | 1.0日 | AYA | FR-04全項, FR-05-5/6/7, FR-08-D全項 |
| 4 | カバレッジ段階達成+Property-based testing+ミューテーションテスト+週次integration test | 2.0日 | AYA+Kiro | NFR-02-1/4, FR-06-2/3, 最終検証 |

**合計: 17日**（完了済み8.5日 + 残り10日。クラウドテスト3Phase追加で+5.5日）

### Phase 3a-3c テスト設計詳細

#### テストピラミッド（v2 — クラウド対応版）

```
┌─────────────────────────────────────────────────────────┐
│    E2E (手動/ステージング)                                │  ~10%
│    Slack → API GW → Lambda → Bedrock → Slack            │
│    EventBridge → Lambda → Heartbeat → Slack              │
├─────────────────────────────────────────────────────────┤
│    Integration (CI cloud-integrationジョブ)               │  ~20%
│    ├─ 既存: Bedrock Converse / Slack API / CFn           │
│    └─ 🆕: Lambda invoke / API GW / SecretsManager       │
├─────────────────────────────────────────────────────────┤
│    Component (CI testジョブ — mock/stub)                  │  ~50%
│    ├─ 既存: Agent / SlackAdapter / Tools / Autonomy      │
│    └─ 🆕: Lambda handler / Events API / SecretsMgr stub │
├─────────────────────────────────────────────────────────┤
│    Unit (CI testジョブ)                                   │  ~20%
│    Config / Session / Models / Budget / Levels           │
└─────────────────────────────────────────────────────────┘
```

#### クラウドコンポーネントテスト (Phase 3a) — 新規テストファイル

| テストファイル | 対象 | マーカー | テスト数目安 |
|---|---|---|---|
| `test_lambda_handler.py` | Lambda handler — Events APIパース、challenge応答、イベントルーティング | component | 15-20 |
| `test_secrets_manager.py` | Secrets Manager取得 — 正常/エラー/キャッシュ | component | 8-10 |
| `test_events_api_adapter.py` | Events API ↔ Socket Mode切替、API GWイベント変換 | component | 10-12 |
| `test_eventbridge_handler.py` | EventBridgeスケジュールイベント → heartbeat/cron処理 | component | 6-8 |

#### クラウドインテグレーションテスト (Phase 3b) — CI Secrets必須

| テストファイル | 対象 | マーカー | テスト数目安 |
|---|---|---|---|
| `test_lambda_deploy.py` | CFnスタックデプロイ→Lambda invoke→クリーンアップ | integration | 5-8 |
| `test_api_gateway.py` | API GWエンドポイント→Lambda経由→レスポンス | integration | 4-6 |
| `test_secrets_live.py` | Secrets Manager実取得（テスト用シークレット） | integration | 3-4 |
| `test_eventbridge_live.py` | EventBridgeルール作成→Lambda起動確認→削除 | integration | 3-4 |

#### クラウドE2Eテスト (Phase 3c) — ステージング環境

| テストファイル | 対象 | マーカー | テスト数目安 |
|---|---|---|---|
| `test_cloud_e2e.py` | Slack→API GW→Lambda→Bedrock→Slack全フロー | e2e | 4-6 |
| `test_cloud_failover.py` | Lambda障害→ローカルSocket Modeフォールバック | e2e | 2-3 |

---

## 6. リスクと軽減策

| リスク | 発生確率 | 影響 | 軽減策 |
|---|---|---|---|
| autospec適用で既存テスト大量fail | 中 | Phase 2c遅延 | spike 5ファイルで事前検証、fail率≤20%でGo |
| CI実行時間超過 | 低 | DX低下 | pytest-xdist並列化、marker分離で段階実行 |
| mock生成スクリプト精度不足 | 中 | Phase 2c遅延 | spike試作で80%自動可能か判定、手動フォールバック |
| mutmutの実行時間が長い | 中 | Phase 4遅延 | 対象をクリティカルモジュールに限定（全体の30%） |
| 🆕 Lambda handler未実装でテスト先行困難 | 高 | Phase 3aブロック | Lambda handler実装（Phase 6）と並行。インターフェース仕様（Events API形式）は確定済みなのでstubテストは先行可能 |
| 🆕 CFnデプロイに時間がかかりCI超過 | 中 | Phase 3b/NFR-01-3 | テスト用は最小構成（Lambda 1つ+API GW 1つ）。テスト後即削除 |
| 🆕 E2Eテストの不安定性（Slack API latency等） | 高 | Phase 3c | リトライロジック+タイムアウト余裕（30秒）。flaky testは`@pytest.mark.flaky`で管理 |
| 🆕 AWSデプロイ権限不足 | 中 | Phase 3b | hanさんにデプロイ権限依頼。IAM最小権限運用のためCI用IAMロール作成が必要 |

---

## 7. 依存関係

- GitHub Actions: リポジトリSettings → Actions → Allowed に設定
- GitHub Secrets: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `SLACK_BOT_TOKEN`（E2E+Integration test用）
- Branch protection rules: Phase 3dでrequired checks設定
- Codecov: Phase 3dでGitHub App連携（代替: pytest-cov HTML artifact）
- pip packages: `faker`, `factory_boy`, `hypothesis`, `mutmut`, `pytest-cov`, `detect-secrets`
- 🆕 **Lambda handler実装** (`src/yui/lambda_handler.py`): Phase 3aのコンポーネントテスト対象。Phase 6で実装予定。インターフェース仕様（Slack Events API形式）は確定済みなのでstubテスト先行可能
- 🆕 **CFnテンプレート** (`cfn/yui-agent-lambda.yaml`): Phase 3bのデプロイテスト対象。Phase 6で作成予定
- 🆕 **CI用IAMロール**: Phase 3b-3cでLambda/API GW/CFn/Secrets Managerの操作権限が必要。hanさんにIAMロール作成を依頼
- 🆕 **ステージング用Slackチャンネル**: Phase 3cのE2Eテスト用。既存 `YUI_TEST_SLACK_CHANNEL` を流用可能

## 8. Phase 6（Lambda Deployment）との依存関係

```
Phase 6（Lambda実装）     テスト設計（本spec）
──────────────────       ──────────────────
lambda_handler.py    ←──  Phase 3a（コンポーネントテスト）※インターフェースstubで先行可
cfn/template.yaml    ←──  Phase 3b（CFnデプロイテスト）
Events API adapter   ←──  Phase 3a（切替ロジックテスト）
API GW endpoint      ←──  Phase 3b-3c（インテグレーション/E2E）
```

**並行作業戦略:**
- Phase 3aの一部（Events APIパース、Secrets Managerスタブ、EventBridgeハンドラ）はLambda handler実装前に着手可能
- Phase 3b-3cはLambda handler + CFnテンプレート完成後に実施
- Phase 2c + Phase 3a前半 → Phase 6（Lambda実装）→ Phase 3a後半 + 3b + 3c の順で進行
