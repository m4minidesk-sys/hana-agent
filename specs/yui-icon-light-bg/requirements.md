# requirements.md — Yui Slackアイコン 明るい背景バリエーション生成

## 背景
現在の `assets/icons/yui-slack-icon.png`（B-2 組紐モチーフ）は背景色が暗い紫（#4A154B系）で、Slack上で使うとチャンネル一覧やメッセージの印象が暗くなる。B-2のデザイン（組紐/結びモチーフ）を維持しつつ、背景を明るくしたバリエーションを複数生成する。

## 対象ファイル
- `scripts/generate_icon.py` — 既存218行。`TEXT_IMAGE`タスクタイプのみ対応。`IMAGE_VARIATION`タスクタイプを追加する
- `scripts/icon_presets.yaml` — 既存10行。2プリセット（elegant-secretary, minimal-logo）。バリエーション用プリセット追加
- `tests/test_generate_icon.py` — 既存20テスト。IMAGE_VARIATION関連テスト追加

## 技術調査結果
- Bedrock Nova Canvas `IMAGE_VARIATION` タスクは動作確認済み（similarityStrength=0.7でB-2の組紐モチーフを維持しつつ背景色変更に成功）
- API パラメータ:
  - `taskType`: `"IMAGE_VARIATION"`
  - `imageVariationParams.text`: テキストプロンプト（背景色指示）
  - `imageVariationParams.negativeText`: ネガティブプロンプト
  - `imageVariationParams.images`: base64エンコード画像配列（元画像）
  - `imageVariationParams.similarityStrength`: 0.2〜1.0（高いほど元画像に近い）
  - `imageGenerationConfig`: numberOfImages, height, width, seed

## AC（受入基準）

### AC-V1: generate_icon.py に IMAGE_VARIATION モード追加
- **AC-V1-1**: `--mode` 引数を追加。値は `"generate"`（デフォルト、既存TEXT_IMAGE）と `"variation"` の2択
- **AC-V1-2**: `--source-image` 引数を追加。`--mode variation` 時に必須。元画像のファイルパスを指定
- **AC-V1-3**: `--similarity` 引数を追加。float型。デフォルト0.7。範囲0.2〜1.0
- **AC-V1-4**: `--mode variation` 時、Bedrock APIに `taskType: "IMAGE_VARIATION"` + `imageVariationParams` で送信
- **AC-V1-5**: `--mode variation` で `--source-image` 未指定の場合、argparseエラー（exit code 2）
- **AC-V1-6**: `--source-image` で指定したファイルが存在しない場合、「Source image not found: {path}」をstderrに出力し exit code 1
- **AC-V1-7**: 出力ファイル名は `yui-variation-{seed}-{index}.png`（generateモードの `yui-icon-` と区別）

### AC-V2: バリエーション用プリセット追加
- **AC-V2-1**: `icon_presets.yaml` に `light-lavender` プリセット追加。prompt に明るいラベンダー背景指示を含む
- **AC-V2-2**: `icon_presets.yaml` に `light-white` プリセット追加。prompt にソフトホワイト背景指示を含む
- **AC-V2-3**: `icon_presets.yaml` に `light-gradient` プリセット追加。prompt に白→薄紫グラデーション背景指示を含む
- **AC-V2-4**: `icon_presets.yaml` に `light-blue` プリセット追加。prompt にアイスブルー背景指示を含む
- **AC-V2-5**: `icon_presets.yaml` に `light-warm` プリセット追加。prompt にウォームベージュ背景指示を含む
- **AC-V2-6**: 各バリエーションプリセットは `mode: variation`, `source_image: assets/icons/yui-slack-icon.png`, `similarity: 0.7` をデフォルト値として含む
- **AC-V2-7**: `--preset` でバリエーションプリセット指定時、プリセットの `mode` が自動適用される（`--mode` 手動指定不要）

### AC-V3: エッジケース
- **AC-V3-1**: `--similarity` が 0.2未満 または 1.0超の場合、argparseエラー（exit code 2）
- **AC-V3-2**: `--mode generate` 時に `--source-image` を指定してもエラーにならない（無視される）
- **AC-V3-3**: `--mode variation` + `--preset` 指定時、プリセットの prompt/negative がIMAGE_VARIATIONのtext/negativeTextとして使用される
- **AC-V3-4**: 元画像が0バイトの場合、「Source image is empty: {path}」をstderrに出力し exit code 1
- **AC-V3-5**: Bedrock APIエラー時（ClientError）、既存のエラーハンドリングがVARIATIONモードでも動作する

### AC-V4: 既存機能の後方互換性
- **AC-V4-1**: `--mode` 未指定時、既存の `TEXT_IMAGE` 動作が変わらない
- **AC-V4-2**: 既存の20テストが全て引き続きパスする
- **AC-V4-3**: `--preset elegant-secretary` / `--preset minimal-logo` が従来通り動作する
