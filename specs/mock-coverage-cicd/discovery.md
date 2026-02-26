# Discovery Report: mockカバレッジ100% + CI/CD自動化

**日付**: 2026-02-27
**タイプ**: ⚙️ 開発基盤
**ステータス**: Draft → hanさんレビュー待ち
**Appetite**: 11.5日 / Kiro CLI + GitHub Actions
**Issue**: [#75](https://github.com/m4minidesk-sys/yui-agent/issues/75)

---

## Phase 0: SIGNAL

**課題**: yui-agentのテスト基盤が「量は十分・質が不足」の状態
**発案者**: hanさん（2026-02-27）
**背景/動機**:
- 967テストあるが99.4%がmock依存、CI/CDなし、テスト未分類
- 当初「mock全廃」方針を提案 → hanさん指示で「mock最大活用」に方針転換
- mockは問題ではなく資産。コンポーネントテストでmockカバレッジ100%を目指す

**タイプ判別理由**: テスト基盤の設計変更+CI/CDパイプライン構築 = 開発基盤

---

## Phase 1: LANDSCAPE（技術トレンド+エコシステム）

### 技術トレンド

| トレンド | yui-agentへの影響 |
|---|---|
| pytest + unittest.mock がPython標準 | 追加ツール不要。既存627箇所のmockを活かせる |
| GitHub Actions CI/CDの成熟 | 無料枠で十分（Private repoでも2,000分/月） |
| autospec/spec_set による型安全mock | mock drift（実APIとの乖離）を実行時検知可能 |
| Contract Testing（Pact等） | 週次でmockと実APIの整合性を自動検証 |
| pytest-cov + Codecov | カバレッジ計測+PRゲートが標準化 |

### 現状分析（定量）

| 指標 | 現状値 | 目標値 |
|---|---|---|
| テストファイル | 46 | 53+（旧テスト復旧+セキュリティ追加） |
| テスト総数 | 967 | 1,400+ |
| mockありファイル | 37/46（80%） | 46/46（100%） |
| mock使用箇所 | 627 | 800+（共通fixture集約後） |
| skipテスト | 56 | 0（unit/component層） |
| CI/CD | なし | GitHub Actions + PRマージゲート |
| pytestマーカー | `aws`のみ | unit/component/integration/e2e/security |
| テストカバレッジ | 未計測 | ≥85% |
| テスト分類 | 未分類 | 4層ピラミッド |

### 既存資産

**活用可能なmock資産:**
- 627箇所の既存mock（37ファイル）
- commit `91bfcc1` で破棄された旧テスト7ファイル（~400行）のmockパターン
- Bedrock/Slack/boto3の主要APIに対するmockが既に存在

**技術スタック:**
- Python 3.12+ / pytest / unittest.mock
- boto3 (AWS SDK) / slack_sdk (Slack API) / strands-agents / bedrock-agentcore

---

## Phase 2: STAKEHOLDER（開発チーム要件+運用制約）

### ステークホルダー

| ステークホルダー | 役割 | 要求 |
|---|---|---|
| hanさん | オーナー | mockを最大活用、CI/CD自動化、過去資産の復旧 |
| Yui（AIエージェント） | 運用対象 | テストが実環境で動作する保証 |
| AYA | 品質管理 | テスト品質基準の維持、レビュー |
| Kiro | 実装担当 | 明確な指示、再利用可能なmock fixture |
| IRIS | 自動レビュー | PRレビュー自動実行の基盤 |

### 開発チームの要件

1. **認証不要でローカル実行**: AWS/Slack認証なしで全unit/componentテストがpass
2. **CI自動実行**: PRごとに自動テスト実行、結果が明確
3. **mock再利用**: 新テスト追加時に既存fixtureを簡単に見つけて使える
4. **mockと実APIの乖離検知**: mockが古くなったことを自動で気づける

### 運用制約

| 制約 | 内容 |
|---|---|
| コスト | GitHub Actions無料枠（2,000分/月）内 |
| 認証情報 | AWS/Slack Secrets はCI環境変数で管理 |
| 実行時間 | unit+component: ≤5分、ローカルunit: ≤30秒 |
| Python版 | 3.12, 3.13のマルチバージョン |

---

## Phase 3: COMPETITIVE（技術候補比較）

### mock戦略の比較

| 手法 | メリット | デメリット | 採用 |
|---|---|---|---|
| **unittest.mock（現行）** | 標準ライブラリ、学習コスト0、既存627箇所活用 | 型安全性が弱い | ✅ 継続+autospec強化 |
| pytest-mock | patchのwrapper、mocker fixture | 追加依存、既存コード書き換え必要 | ❌ |
| responses (HTTP mock) | HTTPレベルで実レスポンス記録→再生 | boto3はHTTPレベルが複雑 | 🟡 将来検討 |
| moto (AWS mock) | AWSサービスのフルモック | 重い、起動遅い、strands未対応 | ❌ |
| Pact (Contract Testing) | 実API整合性を自動検証 | 導入コスト高い、サーバー必要 | 🟡 簡易版で採用 |

**結論**: unittest.mock + autospec強制 + 簡易Contract Testingの組み合わせが最適

### CI/CDの比較

| ツール | メリット | デメリット | 採用 |
|---|---|---|---|
| **GitHub Actions** | GitHubネイティブ、無料枠十分、設定簡単 | 複雑なワークフローは冗長 | ✅ |
| CircleCI | 高速、キャッシュ優秀 | 別サービス、設定学習コスト | ❌ |
| AWS CodeBuild | AWS統合 | AWS依存、ローカルデバッグ困難 | ❌ |

---

## Phase 4: HYPOTHESIS（技術選定+アーキテクチャ方針）

### 仮説

**H1**: unittest.mock + autospec強制でmockの型安全性を確保できる
- 検証: Phase 0 spikeでautospec適用時の既存テストpass率を確認

**H2**: 過去破棄テスト7ファイルの復旧でmockパターン抽出が加速する
- 検証: Phase 1.5で復旧し、conftest.pyに集約できるパターン数を計測

**H3**: mock生成スクリプト（AST解析）で新モジュール追加時の工数を50%削減できる
- 検証: Phase 0 spikeでbedrock/slack mockの自動生成を試作

**H4**: CI/CD導入後、PRマージゲートとしてのテスト必須化が開発品質を向上させる
- 検証: Phase 3でmainブランチCIの連続グリーン回数を計測

### アーキテクチャ方針

```
テストピラミッド（4層）:
┌─────────────┐
│    E2E      │  ~10%  日次CI/手動  @pytest.mark.e2e
├─────────────┤
│ Integration │  ~15%  週次CI       @pytest.mark.integration
├─────────────┤
│  Component  │  ~55%  PR CI       @pytest.mark.component  ← mock活用の主戦場
├─────────────┤
│    Unit     │  ~20%  PR CI       デフォルト（マーカーなし）
└─────────────┘
```

### mock自動化3層防御

```
Layer 1: autospec強制（実行時検知）
  → patchのデフォルトをautospec=Trueに
  → 存在しないメソッド呼び出しを即エラー

Layer 2: Contract Testing（週次検証）
  → 実API(read-only)とmock responseのスキーマ比較
  → 乖離検出 → GitHub Issue自動作成

Layer 3: CI品質検証（PR毎）
  → mock使用率100%チェック
  → unused mock検知
  → fixture重複検知
```

---

## Phase 5: VALIDATION（検証設計）

### リスクと検証

| リスク | 影響 | 検証方法 | Go/No-Go基準 |
|---|---|---|---|
| autospec適用で既存テスト大量fail | Phase 0でブロック | Phase 0 spikeで5ファイル試行 | fail率≤20%でGo |
| mock生成スクリプトの精度不足 | Phase 2a遅延 | Phase 0でbedrock/slack 2件試作 | 80%自動生成可能でGo |
| skip解消が想定以上に複雑 | Phase 2b膨張 | Phase 0で最複雑な2件を試行 | 1件あたり≤2時間でGo |
| CI実行時間が5分超過 | DX低下 | Phase 1でカバレッジ計測時に時間も計測 | ≤5分でGo |
| 旧テスト復旧のAPI差分が大 | Phase 1.5遅延 | Phase 1.5で最初の2ファイルで判断 | import変更のみでGo |

### Phase 0（spike）の実施内容

1. autospec強制を5ファイルに適用 → fail率計測
2. `scripts/generate_mock_fixtures.py` 試作 → bedrock/slack mock自動生成
3. skip解消の最複雑ケース（test_kb_search.py, test_converse_errors.py）を1件ずつ試行
4. 結果に基づいてPhase 2b工数を再見積

---

## Phase 6: SPEC BRIDGE → requirements.md

Discovery結果に基づき、`specs/mock-coverage-cicd/requirements.md` を生成する。
