# Testing Philosophy — YUI Agent

## 概要

YUI Agentのテスト戦略。「mock全廃」から「mock活用」への方針転換を経て、
現在は **テスト種別に応じた適切なmock活用** を基本方針とする。

---

## 方針転換の背景

以前（〜2026年2月）は「実APIを使ったテストのみが信頼できる」として mock を避ける方針があったが、
以下の問題から方針を転換した:

- CI/CDコストが増大（Bedrock APIコール課金）
- ネットワーク依存でテストが不安定
- 開発速度の低下（実API待ちが発生）

**現方針: "mock for speed, real for confidence"**
- 高速フィードバックが必要な開発時: mockを積極活用
- 本番品質の確認が必要な場合: 実APIテスト（YUI_TEST_AWS=1 等）

---

## テスト種別の定義

### unit（ユニットテスト）
- **対象**: 単一クラス・関数の動作
- **外部依存**: なし（すべてmock）
- **実行速度**: 高速（< 1秒/テスト）
- **CIで実行**: 常時
- **マーカー**: `@pytest.mark.unit`

### component（コンポーネントテスト）
- **対象**: 複数クラスの協調動作（内部インターフェース）
- **外部依存**: なし（外部API/DBはmock）
- **実行速度**: 中速（< 5秒/テスト）
- **CIで実行**: 常時
- **マーカー**: `@pytest.mark.component`

### integration（インテグレーションテスト）
- **対象**: モジュール間の統合（Slack ↔ Agent ↔ Session等）
- **外部依存**: 内部コンポーネントは実物、外部API（Bedrock/Slack）はmock
- **実行速度**: 中速（< 10秒/テスト）
- **CIで実行**: 常時
- **マーカー**: `@pytest.mark.integration`

### e2e（エンドツーエンドテスト）
- **対象**: ユーザーフロー通し（メンション受信 → Bedrock → Slack返信等）
- **外部依存**: 外部API（Bedrock/Slack）はmock、内部フローは実物
- **実行速度**: 中速（< 30秒/テスト）
- **CIで実行**: 常時
- **マーカー**: `@pytest.mark.e2e`

### live（ライブテスト）
- **対象**: 実Bedrock API / 実Slackチャンネルを使った検証
- **外部依存**: あり（実APIコール）
- **実行速度**: 低速（1〜30秒/テスト）
- **CIで実行**: 手動のみ（`YUI_TEST_AWS=1` または `YUI_LIVE_INTEGRATION=1` 設定時）
- **マーカー**: `@pytest.mark.live`
- **環境変数**: `YUI_TEST_AWS=1`, `YUI_LIVE_INTEGRATION=1`

---

## mockを使うべき場面 vs 実APIが必要な場面

### ✅ mockを使うべき場面

| 場面 | 理由 |
|---|---|
| ユニット・コンポーネントテスト | 外部APIと無関係のロジック検証 |
| CI/CDパイプライン（日常のPR） | コスト・速度・安定性 |
| エラーハンドリングのテスト | エラー発生をmockで再現するほうが確実 |
| 並列・並行動作のテスト | 外部APIのレート制限を回避 |
| E2Eフローの通しテスト | 外部APIの変動を排除して決定論的に |
| 開発中の高速フィードバック | プロトタイプ段階での動作確認 |

### ✅ 実APIが必要な場面

| 場面 | 理由 |
|---|---|
| Bedrockのモデル応答品質確認 | モデルの振る舞いはmockで再現不可 |
| Slack API互換性確認 | APIバージョン変更の検知 |
| リリース前の最終確認 | 本番環境と同条件での動作保証 |
| Bedrockのエラーコード確認 | 実際のエラーメッセージ形式の把握 |
| CloudFormationデプロイ検証 | インフラの実際の挙動確認 |

---

## 既存テストのカテゴリ対応表

| テストファイル | カテゴリ | マーカー | 説明 |
|---|---|---|---|
| `tests/test_agent.py` | unit/component | `@component` | エージェント設定・プロンプト読み込み |
| `tests/test_config.py` | unit | `@unit` | 設定読み込み・バリデーション |
| `tests/test_session.py` | unit/component | `@component` | セッション管理（SQLite） |
| `tests/test_slack_adapter.py` | unit | `@unit` | Slackアダプター単体 |
| `tests/test_slack_e2e.py` | e2e | `@e2e` | Slackイベント処理E2E（mockベース） |
| `tests/test_e2e_flows.py` | e2e | `@e2e` | ユーザーフロー通しE2E（mockベース） |
| `tests/test_integration.py` | integration/live | `@integration/@e2e` | 統合テスト（一部 YUI_TEST_AWS=1 要） |
| `tests/test_agentcore.py` | unit/component | `@unit` | AgentCoreツール単体 |
| `tests/test_agentcore_e2e.py` | e2e | `@e2e` | AgentCoreフロー通し |
| `tests/test_safe_shell.py` | unit | `@unit` | SafeShellセキュリティ |
| `tests/test_security.py` | unit | `@unit` | セキュリティルール検証 |
| `tests/test_error_handling.py` | unit | `@unit` | エラーハンドリング |
| `tests/test_budget.py` | unit | `@unit` | 予算管理 |
| `tests/test_lambda_handler.py` | component | `@component` | Lambdaハンドラ |
| `tests/test_kiro_delegate.py` | unit | `@unit` | Kiroデリゲート |
| `tests/test_kiro_tools.py` | unit | `@unit` | Kiroツール |
| `tests/unit/test_file_interface.py` | unit | `@unit` | FileInterface単体 |
| `tests/unit/test_kiro_runner.py` | unit | `@unit` | KiroRunner単体 |
| `tests/unit/test_task_delegator.py` | unit | `@unit` | TaskDelegator単体 |
| `tests/test_slack_live.py` | live | `@live` | 実Slack APIテスト（YUI_LIVE_INTEGRATION=1 要） |
| `tests/test_guardrails_e2e.py` | live | `@e2e` | Guardrails E2E（YUI_TEST_AWS=1 要） |
| `tests/test_workshop_*.py` | unit/component | `@unit/@component` | Workshopモジュール群 |
| `tests/test_meeting_*.py` | unit/component | `@unit/@component` | Meetingモジュール群 |

---

## CI実行ポリシー

```
# 日常のPR（全テスト、liveのみスキップ）
pytest -m 'not live' tests/

# ユニット + コンポーネントのみ（高速チェック）
pytest -m 'unit or component' tests/

# E2E含む完全テスト
pytest tests/

# ライブテスト（手動実行のみ）
YUI_TEST_AWS=1 YUI_LIVE_INTEGRATION=1 pytest -m live tests/
```

---

## mockドリフト防止

外部APIのインターフェース変更によるmockとの乖離（drift）を防ぐため:

```bash
# mockドリフト検査
python scripts/check_mock_drift.py --dry-run

# 特定APIの確認
python scripts/check_mock_drift.py --api bedrock --dry-run

# 乖離検出時にIssue自動作成
python scripts/check_mock_drift.py --create-issue
```

詳細: `scripts/check_mock_drift.py`

---

## 関連ドキュメント

- `docs/test-quality-rca-2026-02-26.md` — テスト品質改善のRoot Cause Analysis
- `requirements.md` — テスト要件（R1〜R27）
- `tests/contracts/` — コントラクトテスト定義
