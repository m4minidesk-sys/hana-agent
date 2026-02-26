# 要件: Bedrock Nova Canvas で結(Yui)のSlackアイコン画像を生成

## ユーザーストーリー
**As** yui-agentの開発者, **I want** Bedrock Nova Canvasで結(Yui)のキャラクターに合ったSlackアイコンを生成する, **So that** Slack AppにYuiのアイデンティティを視覚的に表現できる

## 背景

### 結(Yui)のキャラクター設定
- **名前**: 結（ゆい / Yui）— "to tie, to bind, to connect"
- **役割**: 賢く有能で仕事の早い秘書
- **システム**: AWS-native AI agent orchestrator（Strands Agent SDK + Bedrock）
- **テーマカラー**: `#4A154B`（Slack manifest の background_color — ダークパープル）
- **特徴**: Lightweight, secure, AWS-optimized

### 現状（As-Is）
- yui-agentリポジトリに `assets/` ディレクトリは存在しない
- Slack App「結 (Yui)」にカスタムアイコンは未設定（デフォルトアイコン状態）
- Slack App Iconの仕様: 512×512〜2048×2048px 正方形、PNG/JPG/GIF対応

### 外部API調査結果（実検証済み）

**Amazon Bedrock Nova Canvas API (`amazon.nova-canvas-v1:0`)**

| パラメータ | 検証結果 | 備考 |
|---|---|---|
| taskType: TEXT_IMAGE | ✅ 動作確認 | テキストプロンプト→画像生成 |
| textToImageParams.text | ✅ 動作確認 | 英語プロンプト推奨 |
| textToImageParams.negativeText | ✅ 動作確認 | 除外条件指定 |
| numberOfImages: 1-5 | ✅ 3枚同時生成確認 | 1リクエストで複数候補 |
| height/width: 512-2048 | ✅ 512,1024確認 | 正方形のみ（Slack仕様に合致）|
| seed | ✅ 動作確認 | 再現性確保 |
| cfgScale | ✅ 動作確認 | プロンプト忠実度 |
| quality: 'standard'/'premium' | ✅ premium確認 | premium=高品質 |

**レスポンス構造:**
```json
{
  "images": ["<base64-encoded-PNG-string>", ...]
}
```

**コスト**: ~$0.04/枚（standard）、~$0.08/枚（premium）
**リージョン**: us-east-1（IAM認証済み、Bedrock InvokeModel権限あり）

### 現状のディレクトリ構造（変更対象）
```
yui-agent/
├── src/yui/          # メインソースコード
├── tests/            # pytest テスト
├── .kiro/specs/      # SPEC駆動開発用（このrequirements.md含む）
├── assets/           # 【新規作成】生成アイコン保存先
└── scripts/          # 【新規作成】画像生成スクリプト
```

## 受入条件（AC）

### AC1: 画像生成スクリプト

- [ ] AC1-1: `scripts/generate_icon.py` が存在し、`python3 scripts/generate_icon.py` で実行可能
- [ ] AC1-2: スクリプトは `boto3` を使い `amazon.nova-canvas-v1:0` の `TEXT_IMAGE` タスクで画像生成する
- [ ] AC1-3: 以下のCLI引数をサポート:
  - `--prompt TEXT` (必須): 画像生成プロンプト
  - `--negative TEXT` (任意): negativeTextプロンプト
  - `--count N` (任意, default=3): 生成枚数 (1-5)
  - `--size N` (任意, default=1024): 画像サイズ (512/1024/2048)
  - `--seed N` (任意): シード値（再現性確保）
  - `--quality TEXT` (任意, default='premium'): 'standard' or 'premium'
  - `--output-dir PATH` (任意, default='assets/icons'): 出力先ディレクトリ
  - `--cfg-scale FLOAT` (任意, default=8.0): cfgScale値
- [ ] AC1-4: 生成画像は `{output_dir}/yui-icon-{seed}-{index}.png` として保存される
- [ ] AC1-5: 生成成功時、保存パスとファイルサイズを標準出力に表示する
- [ ] AC1-6: スクリプト実行後、`assets/icons/` に指定枚数のPNGファイルが存在する

### AC2: エッジケース対策

- [ ] AC2-1: `--prompt` 未指定 → argparse エラーで終了（exit code 2）、使い方を表示
- [ ] AC2-2: Bedrock API呼び出し失敗（認証エラー/リージョンエラー/モデル未有効化）→ `ClientError` をキャッチし、エラーメッセージ + 対処方法を表示して exit code 1
- [ ] AC2-3: `--count` が範囲外(0以下, 6以上) → argparse バリデーションでエラー（exit code 2）
- [ ] AC2-4: `--size` が非対応値 → argparse choices でエラー（exit code 2）
- [ ] AC2-5: `--output-dir` が存在しない → 自動作成（`os.makedirs(exist_ok=True)`）
- [ ] AC2-6: ディスク書き込み失敗（権限なし等）→ `IOError/OSError` をキャッチし、エラーメッセージ表示して exit code 1
- [ ] AC2-7: APIレスポンスに `images` キーがない or 空配列 → 適切なエラーメッセージで exit code 1
- [ ] AC2-8: `--quality` が 'standard'/'premium' 以外 → argparse choices でエラー

### AC3: プロンプトプリセット

- [ ] AC3-1: `--preset NAME` オプションで事前定義プロンプトを使用可能
- [ ] AC3-2: プリセット定義は `scripts/icon_presets.yaml` に外部ファイルとして格納
- [ ] AC3-3: `--preset list` で利用可能なプリセット一覧を表示
- [ ] AC3-4: プリセットYAMLの構造:
  ```yaml
  presets:
    elegant-secretary:
      prompt: "..."
      negative: "..."
      cfg_scale: 8.0
    minimal-logo:
      prompt: "..."
      negative: "..."
  ```
- [ ] AC3-5: `--preset` と `--prompt` が同時指定 → エラー（排他）
- [ ] AC3-6: 存在しないプリセット名 → 利用可能なプリセット一覧を表示してエラー

### AC4: テスト

- [ ] AC4-1: `tests/test_generate_icon.py` に全ACのテストが存在する
- [ ] AC4-2: Bedrock API呼び出しは `unittest.mock` でモック化（実際のAPI呼び出しなし）
- [ ] AC4-3: ファイル出力テストは `tmp_path` fixture を使用
- [ ] AC4-4: `pytest tests/test_generate_icon.py -v` で全テストパス

## 制約・前提

- Python 3.12+（pyproject.toml に `requires-python = ">=3.12"` 指定済み）
- `boto3` は既存依存に含まれる（requirements.txt に `boto3>=1.35.0`）
- `pyyaml` は既存依存に含まれる（pyproject.toml に `pyyaml>=6.0`）
- AWS認証情報はデフォルトプロファイルまたは環境変数から取得（スクリプト内でハードコードしない）
- リージョンは `us-east-1` をデフォルトとするが、`AWS_DEFAULT_REGION` 環境変数で上書き可能

## スコープ外

- Slack APIへのアイコンアップロード自動化（手動でSlack管理画面から設定）
- 画像の後処理（リサイズ/クロップ/フィルター等）
- IMAGE_VARIATION タスクタイプ（バリエーション生成は将来対応）
- Web UI / GUIツール
- 他のモデル（Titan Image等）への対応
