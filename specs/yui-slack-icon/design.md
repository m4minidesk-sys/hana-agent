# 設計: Slack Icon Generation Script

## アーキテクチャ

```
scripts/generate_icon.py (CLI)
├── argparse: CLI引数パース
├── load_presets(): icon_presets.yaml読み込み
├── generate_icons(): 画像生成コア関数
│   ├── boto3.client('bedrock-runtime')
│   ├── invoke_model(amazon.nova-canvas-v1:0)
│   └── base64デコード + PNG保存
└── main(): エントリポイント

scripts/icon_presets.yaml
└── presets: {name: {prompt, negative, cfg_scale}}
```

## モジュール構成

### scripts/generate_icon.py

**関数:**

1. `load_presets() -> dict`
   - `icon_presets.yaml` を読み込み
   - 存在しない場合は空辞書を返す

2. `generate_icons(prompt, output_dir, count=3, size=1024, seed=None, quality='premium', negative=None, cfg_scale=8.0) -> None`
   - Bedrock Nova Canvas APIを呼び出し
   - 画像をbase64デコードしてPNG保存
   - エラー時は適切な例外を投げる（SystemExit(1)）

3. `main()`
   - argparseでCLI引数をパース
   - `--preset list` の場合はプリセット一覧表示して終了
   - `--preset` と `--prompt` の排他チェック
   - プリセット適用
   - `generate_icons()` を呼び出し

### scripts/icon_presets.yaml

```yaml
presets:
  elegant-secretary:
    prompt: "Professional AI assistant avatar, elegant secretary character, purple theme #4A154B, minimalist design, friendly and intelligent appearance, suitable for Slack profile icon, 512x512px"
    negative: "photo, realistic, human face, text, watermark, blurry"
    cfg_scale: 8.0
  
  minimal-logo:
    prompt: "Abstract logo design, interconnected nodes representing 'Yui' (to bind, to connect), dark purple #4A154B, clean geometric shapes, modern tech aesthetic, 512x512px"
    negative: "text, letters, words, realistic, photo, complex details"
    cfg_scale: 7.0
```

## API呼び出し仕様

**Bedrock Nova Canvas (amazon.nova-canvas-v1:0)**

```python
import boto3
import json

client = boto3.client('bedrock-runtime', region_name='us-east-1')

body = {
    "taskType": "TEXT_IMAGE",
    "textToImageParams": {
        "text": prompt,
        "negativeText": negative,  # optional
    },
    "imageGenerationConfig": {
        "numberOfImages": count,
        "height": size,
        "width": size,
        "cfgScale": cfg_scale,
        "seed": seed,  # optional
        "quality": quality,
    }
}

response = client.invoke_model(
    modelId="amazon.nova-canvas-v1:0",
    body=json.dumps(body)
)

result = json.loads(response['body'].read())
images = result['images']  # list of base64 strings
```

## エラーハンドリング

| エラー | 処理 | Exit Code |
|---|---|---|
| argparse validation失敗 | argparseが自動処理 | 2 |
| ClientError (Bedrock API) | エラーメッセージ表示 + 対処方法 | 1 |
| 空のimages配列 | "No images generated" 表示 | 1 |
| IOError/OSError (ファイル書き込み) | エラーメッセージ表示 | 1 |
| プリセット不存在 | 利用可能なプリセット一覧表示 | 1 |
| --preset + --prompt 同時指定 | エラーメッセージ表示 | 1 |

## ファイル命名規則

```
{output_dir}/yui-icon-{seed}-{index}.png
```

- `seed`: 指定されたシード値（未指定時は0）
- `index`: 0から始まる連番

## テスト戦略

- **AC tests (tests/test_generate_icon.py)**: 全受入条件を検証（変更禁止）
- **Unit tests (tests/test_generate_icon_unit.py)**: 実装詳細のテスト（任意）
  - `load_presets()` の動作
  - エラーメッセージの内容
  - ファイル名生成ロジック

## 依存関係

- `boto3>=1.35.0` (既存)
- `pyyaml>=6.0` (既存)
- Python 3.12+

## セキュリティ考慮事項

- AWS認証情報はハードコードしない（boto3のデフォルト認証チェーンを使用）
- ファイルパスのバリデーション（パストラバーサル対策）
- プロンプトインジェクション対策（ユーザー入力をそのまま使用するが、Bedrock側でフィルタリング）
