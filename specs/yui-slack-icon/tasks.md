# タスク: Slack Icon Generation Script 実装

## タスク一覧

- [ ] Task 1: ディレクトリ・ファイル構造作成
- [ ] Task 2: scripts/icon_presets.yaml 作成
- [ ] Task 3: scripts/__init__.py 作成（importable化）
- [ ] Task 4: scripts/generate_icon.py 実装
- [ ] Task 5: テスト実行・デバッグ
- [ ] Task 6: Git commit

---

## Task 1: ディレクトリ・ファイル構造作成

```bash
mkdir -p scripts
mkdir -p assets/icons
```

## Task 2: scripts/icon_presets.yaml 作成

プリセット定義ファイルを作成。最低2つのプリセット（elegant-secretary, minimal-logo）を含める。

## Task 3: scripts/__init__.py 作成

テストから `from scripts.generate_icon import generate_icons` でインポート可能にするため、scriptsをパッケージ化。

```python
# scripts/__init__.py
"""Yui agent utility scripts."""
```

## Task 4: scripts/generate_icon.py 実装

### 実装順序

1. **import文**
   - argparse, base64, json, os, sys
   - boto3, botocore.exceptions
   - yaml, pathlib

2. **load_presets() 関数**
   - `icon_presets.yaml` を読み込み
   - FileNotFoundError時は空辞書を返す

3. **generate_icons() 関数**
   - boto3クライアント作成
   - Bedrock API呼び出し
   - base64デコード + PNG保存
   - エラーハンドリング（ClientError, IOError, 空配列）
   - 成功時の出力（パス + ファイルサイズ）

4. **main() 関数**
   - argparseセットアップ
     - `--prompt` (required, mutually exclusive with --preset)
     - `--preset` (mutually exclusive with --prompt)
     - `--negative`, `--count`, `--size`, `--seed`, `--quality`, `--output-dir`, `--cfg-scale`
   - `--preset list` 処理
   - `--preset` と `--prompt` の排他チェック
   - プリセット適用
   - `generate_icons()` 呼び出し

5. **if __name__ == "__main__"**
   - `main()` 実行

### 実装の注意点

- `--count`: `type=int, choices=range(1, 6)` でバリデーション
- `--size`: `type=int, choices=[512, 1024, 2048]` でバリデーション
- `--quality`: `choices=['standard', 'premium']` でバリデーション
- `seed` 未指定時は `0` をデフォルトとしてファイル名に使用
- `output_dir` は `os.makedirs(exist_ok=True)` で自動作成
- エラー時は `print()` でメッセージ表示 + `sys.exit(1)`
- 成功時は各ファイルのパスとサイズを表示

## Task 5: テスト実行・デバッグ

```bash
# ACテスト実行
python3 -m pytest tests/test_generate_icon.py -v

# 失敗したテストを修正
# テストコードは変更しない！実装を修正する
```

## Task 6: Git commit

```bash
git add scripts/ assets/ specs/yui-slack-icon/
git commit -m 'feat: implement Slack icon generation script #28'
```

---

## 実装チェックリスト

### scripts/generate_icon.py

- [ ] `load_presets()` 関数実装
- [ ] `generate_icons()` 関数実装
  - [ ] boto3クライアント作成（region='us-east-1'）
  - [ ] Bedrock API呼び出し（modelId='amazon.nova-canvas-v1:0'）
  - [ ] base64デコード
  - [ ] PNG保存（ファイル名: `yui-icon-{seed}-{index}.png`）
  - [ ] ClientErrorハンドリング
  - [ ] IOError/OSErrorハンドリング
  - [ ] 空配列チェック
  - [ ] 成功時の出力
- [ ] `main()` 関数実装
  - [ ] argparseセットアップ
  - [ ] mutually exclusive group (--prompt, --preset)
  - [ ] `--preset list` 処理
  - [ ] プリセット不存在チェック
  - [ ] プリセット適用
  - [ ] `generate_icons()` 呼び出し

### scripts/icon_presets.yaml

- [ ] `presets` キー
- [ ] `elegant-secretary` プリセット
- [ ] `minimal-logo` プリセット
- [ ] 各プリセットに `prompt`, `negative`, `cfg_scale` キー

### scripts/__init__.py

- [ ] 空ファイルまたはdocstring

### テスト

- [ ] 全ACテストパス（tests/test_generate_icon.py）
