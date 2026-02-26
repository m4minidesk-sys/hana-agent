# Yui Slack Icon — 生成ログ

## 選定結果
**採用: B-2（minimal-logo プリセット, seed=200, index=1）**
→ `yui-slack-icon.png` として保存

## 生成パラメータ

### 【A】elegant-secretary プリセット（seed=100, count=3）
- **プロンプト**: `Professional AI assistant avatar, elegant secretary character, purple theme #4A154B, minimalist design, friendly and intelligent appearance, suitable for Slack profile icon, 512x512px`
- **ネガティブ**: `photo, realistic, human face, text, watermark, blurry`
- **cfgScale**: 8.0 / **quality**: premium / **size**: 1024x1024

| ファイル | 説明 | 評価 |
|---|---|---|
| yui-icon-100-0.png | メガネひげ男性 | ❌ 性別不一致 |
| yui-icon-100-1.png | メガネ女性、紫背景 | ⭐ 有能秘書感 |
| yui-icon-100-2.png | ヘッドセット女性 | ○ カスタマーサポート風 |

### 【B】minimal-logo プリセット（seed=200, count=3）
- **プロンプト**: `Abstract logo design, interconnected nodes representing 'Yui' (to bind, to connect), dark purple #4A154B, clean geometric shapes, modern tech aesthetic, 512x512px`
- **ネガティブ**: `text, letters, words, realistic, photo, complex details`
- **cfgScale**: 7.0 / **quality**: premium / **size**: 1024x1024

| ファイル | 説明 | 評価 |
|---|---|---|
| yui-icon-200-0.png | ネットワークノード | ○ テック感 |
| **yui-icon-200-1.png** | **組紐モチーフ** | **🏆 採用！「結ぶ」のコンセプト** |
| yui-icon-200-2.png | 分子構造風 | △ ライト背景 |

### 【C】漢字カスタムプロンプト（seed=300, count=3）
- **プロンプト**: `A stylized Japanese kanji character 結 (Yui, meaning 'to bind/connect') rendered as a modern app icon, deep purple #4A154B gradient background, white and gold kanji strokes, elegant calligraphy meets tech aesthetic, clean minimalist design, suitable for Slack profile icon`
- **ネガティブ**: `realistic photo, human face, text other than kanji, blurry, cluttered, low quality`
- **cfgScale**: 8.0 / **quality**: premium / **size**: 1024x1024

| ファイル | 説明 | 評価 |
|---|---|---|
| yui-icon-300-0.png | 金+白の書道風 | ○ アプリアイコン感 |
| yui-icon-300-1.png | 紫×金の角丸アイコン | ○ 高級感 |
| yui-icon-300-2.png | "Yui"+書道 | △ 漢字不正確 |

### 【C-3改】漢字リトライ（seed=500, count=5）
- **プロンプト**: `A stylized Japanese kanji character 結 (meaning 'to bind, to connect') as a modern app icon, deep purple gradient background, the kanji 結 written in bold white and gold calligraphy brush strokes, with small golden 'Yui' text in the upper left corner, elegant fusion of traditional Japanese calligraphy and modern tech design, clean composition, suitable for Slack profile icon, high quality`
- **ネガティブ**: `wrong kanji, incorrect character, realistic photo, human face, blurry, cluttered, low quality, extra text, random symbols`
- **cfgScale**: 8.0 / **quality**: premium / **size**: 1024x1024

| ファイル | 説明 | 評価 |
|---|---|---|
| yui-icon-500-0.png | 書道風+Yui+印章 | △ 漢字崩れ |
| yui-icon-500-1.png | 白+金の筆ストローク | △ 漢字崩れ |
| yui-icon-500-2.png | 金+白、大胆な構図 | △ 漢字崩れ |
| yui-icon-500-3.png | 金箔テクスチャ+飛沫 | △ 漢字崩れ |
| yui-icon-500-4.png | 白+金、二段構成 | △ 漢字崩れ |

## 学び
- Nova Canvas は抽象ロゴ・キャラクターアバター生成が得意
- 漢字（特に画数の多い文字）の正確な再現は苦手 — IMAGE_VARIATION + 正確な元画像で対処可能
- コスト: ~$0.04/枚（standard）、~$0.08/枚（premium）、全14枚で ~$0.56

## 生成ツール
- `scripts/generate_icon.py` （PR #29 で導入）
- モデル: `amazon.nova-canvas-v1:0` (Bedrock, us-east-1)
- 生成日: 2026-02-26
