# Phase 4: AWS Workshop Auto-Execution Testing — Discovery Spec v2

## 概要
Yui Agent の新機能として、AWS Workshop Studio のワークショップコンテンツを
自動的に実行・検証する機能を追加する。

ワークショップ作者がコンテンツを公開する前に、「手順通りにやったら本当に動くか」を
AIエージェントが自動でウォークスルーし、テスト結果をレポート＋操作動画として出力する。

## ユースケース

### Primary: ワークショップ品質保証（QA）
- ワークショップ作者 → コンテンツ作成 → Yui に自動テスト依頼
- Yui がWorkshop StudioのURLからコンテンツを取得
- ステップバイステップで**AWS Console上で操作を実行**（ブラウザ自動化）
- 各ステップの成功/失敗を記録
- **操作画面の動画を自動撮影**（Playwright video recording）
- テスト結果レポート + 動画を出力

### Secondary: ワークショップ定期回帰テスト
- 既存ワークショップがAWSサービス更新で壊れてないか定期チェック
- CronやEventBridgeで週次実行
- 失敗検知 → Slack通知

---

## hanさん確認結果（2026-02-26）

| 質問 | 回答 |
|---|---|
| コンテンツソース | **Workshop Studio上のコンテンツ（catalog.workshops.aws）が初版**。将来GitHub対応 |
| 環境プロビジョニング | **Yuiがコンソール操作で実施**。動画撮影予定 |
| Console操作検証 | **ブラウザ自動化でカバーする（必須）** |
| ワークショップジャンル | **限定なし。Cloudで基本完結するもの全般** |

---

## アーキテクチャ

```
┌──────────────────────────────────────────────────────────┐
│                  Yui Workshop Tester                      │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐   │
│  │ Content  │  │  Step    │  │  Console Executor   │   │
│  │ Scraper  │→│ Planner  │→│  (Playwright/Browser)│   │
│  │(Browser) │  │(Bedrock) │  │  + Video Recorder   │   │
│  └──────────┘  └──────────┘  └─────────────────────┘   │
│       ↑                              ↑         ↑        │
│  ┌──────────┐                 ┌──────┴──┐ ┌───┴────┐  │
│  │Workshop  │                 │AWS      │ │Video   │  │
│  │Studio URL│                 │Console  │ │Output  │  │
│  │          │                 │(Browser)│ │(.webm) │  │
│  └──────────┘                 └─────────┘ └────────┘  │
└──────────────────────────────────────────────────────────┘
```

### コアコンポーネント

| # | コンポーネント | 役割 | 実装 |
|---|---|---|---|
| 1 | Content Scraper | Workshop Studio URLからページ内容をスクレイピング | Playwright (headless browser) |
| 2 | Step Planner | コンテンツをLLMで解析→実行可能ステップに変換 | Bedrock Converse |
| 3 | Console Executor | AWS Management Consoleで操作を自動実行 | Playwright (headed/headless) |
| 4 | CLI Executor | AWS CLI / shell コマンド実行（手順にCLI手順がある場合） | subprocess + safe_shell |
| 5 | Video Recorder | Console操作の全画面を動画記録 | Playwright `record_video` |
| 6 | Screenshot Capture | 各ステップ完了時のスクリーンショット | Playwright `page.screenshot()` |
| 7 | Validator | 期待結果との照合（画面状態 + CLI出力） | Bedrock Converse (vision) |
| 8 | Reporter | テスト結果レポート生成（Markdown + 動画リンク） | Python |
| 9 | Resource Manager | テスト用AWSリソースの追跡・クリーンアップ | boto3 + Resource Groups Tagging API |

---

## ワークフロー詳細

### 1. テスト開始
```bash
yui workshop test <workshop-studio-url> [--record] [--cleanup] [--headed]
```

### 2. Workshop Studioコンテンツ取得（ブラウザスクレイピング）
Workshop Studioは SPA（Single Page Application）なのでweb_fetchでは取得不可。
Playwrightでブラウザを起動し、ページを巡回して全ステップのコンテンツを取得。

```python
# Workshop Studio URL形式
# https://catalog.workshops.aws/<workshop-slug>/en-US
# https://catalog.us-east-1.prod.workshops.aws/workshops/<uuid>/en-US

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.goto(workshop_url)
    
    # サイドバーナビゲーションから全ページURLを取得
    nav_links = await page.query_selector_all("nav a")
    
    for link in nav_links:
        await link.click()
        content = await page.inner_text("main")  # メインコンテンツ抽出
        # ステップ解析に渡す
```

### 3. ステップ解析（LLM）
Bedrockに全コンテンツを送り、構造化ステップを抽出:
```json
{
  "workshop": "Building a Serverless Web Application",
  "total_pages": 8,
  "steps": [
    {
      "id": 1,
      "page": "Setup",
      "title": "Sign in to AWS Console",
      "type": "console_navigate",
      "action": "Navigate to AWS Console and sign in",
      "url": "https://console.aws.amazon.com/",
      "expected": "Console dashboard visible",
      "timeout_seconds": 60
    },
    {
      "id": 2,
      "page": "Module 1",
      "title": "Create an S3 bucket",
      "type": "console_action",
      "service": "s3",
      "action": "Navigate to S3 → Create bucket → Name: workshop-{random} → Create",
      "expected": "Bucket created successfully message",
      "timeout_seconds": 120,
      "screenshots": ["before_create", "after_create"]
    },
    {
      "id": 3,
      "page": "Module 1",
      "title": "Upload index.html",
      "type": "console_action",
      "service": "s3",
      "action": "Open bucket → Upload → Select index.html → Upload",
      "expected": "Upload successful",
      "timeout_seconds": 60
    }
  ]
}
```

### 4. Console操作実行（Playwright）
**これが本機能の核心。AWS Consoleをブラウザ自動化で操作する。**

```python
async def execute_console_step(page, step, bedrock_client):
    """
    LLMがConsole操作を自然言語で指示 → Playwright が実行
    AgentCore Browser パターンを活用
    """
    # 動画録画開始（コンテキスト作成時に設定済み）
    
    # LLMに現在のページ状態を送信 → 次のアクション取得
    screenshot = await page.screenshot()
    
    response = bedrock_client.converse(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        messages=[{
            "role": "user",
            "content": [
                {"image": {"source": {"bytes": screenshot}}},
                {"text": f"Workshop step: {step['action']}\n"
                         f"Current page URL: {page.url}\n"
                         "What Playwright action should I take next? "
                         "Respond with a JSON action."}
            ]
        }]
    )
    
    # LLMの指示に基づいてPlaywright操作を実行
    action = parse_action(response)
    await execute_playwright_action(page, action)
```

### 5. 動画録画
Playwright の組み込みビデオ録画機能を使用:

```python
context = await browser.new_context(
    record_video_dir="~/.yui/workshop-tests/{test-id}/videos/",
    record_video_size={"width": 1920, "height": 1080}
)
page = await context.new_page()

# ... 全操作を実行 ...

# コンテキストクローズ時に動画が自動保存される（.webm形式）
await context.close()
video_path = await page.video.path()
```

各ステップで区切り動画を撮る場合:
- ステップ開始時にコンテキスト作成
- ステップ終了時にコンテキストクローズ → 動画保存
- 全体を通した連続動画も別途記録

### 6. 結果検証（Vision LLM）
スクリーンショットをBedrock Claude（Vision対応）に送信して結果判定:

```python
async def validate_step(page, step, bedrock_client):
    screenshot = await page.screenshot(full_page=True)
    
    response = bedrock_client.converse(
        modelId="us.anthropic.claude-sonnet-4-20250514-v1:0",
        messages=[{
            "role": "user", 
            "content": [
                {"image": {"source": {"bytes": screenshot}}},
                {"text": f"Expected result: {step['expected']}\n"
                         "Does the current screen match the expected result?\n"
                         "Respond: PASS (matches), FAIL (doesn't match), or UNCLEAR.\n"
                         "If FAIL, explain what's different."}
            ]
        }]
    )
    return parse_validation(response)
```

### 7. テストレポート
```markdown
# Workshop Test Report — 2026-02-26 14:30

## Workshop: Building a Serverless Web Application
## Source: https://catalog.workshops.aws/serverless-webapp/en-US

### Summary
- Total Steps: 24
- Passed: 21 ✅ | Failed: 2 ❌ | Skipped: 1 ⏭
- Duration: 35m 12s
- AWS Cost (estimated): $0.85

### Video Recordings
- 📹 Full walkthrough: videos/full-walkthrough.webm (35:12)
- 📹 Module 1 — Static Hosting: videos/module-1.webm (8:45)
- 📹 Module 2 — User Management: videos/module-2.webm (12:30)
- ...

### Step Results
| # | Module | Step | Result | Screenshot | Video |
|---|---|---|---|---|---|
| 1 | Setup | Sign in to Console | ✅ PASS | [📸](screenshots/step-01.png) | 0:00-0:45 |
| 2 | Module 1 | Create S3 bucket | ✅ PASS | [📸](screenshots/step-02.png) | 0:45-2:30 |
| ... | | | | | |
| 15 | Module 3 | Create API Gateway | ❌ FAIL | [📸](screenshots/step-15.png) | 18:20-20:15 |

### Failed Steps Detail
#### Step 15: Create API Gateway
- **Expected**: REST API created with name "WorkshopAPI"
- **Actual**: Error: "You have reached the maximum number of APIs"
- **Screenshot**: ![](screenshots/step-15.png)
- **Recommendation**: Delete unused APIs or request limit increase

### AWS Resources Created (for cleanup)
- S3 bucket: workshop-abc123
- Cognito User Pool: workshop-users
- Lambda function: WorkshopFunction
- API Gateway: WorkshopAPI (FAILED)
```

### 8. クリーンアップ
テスト用に作成したAWSリソースを自動削除:
- タグベースで追跡: `yui:workshop-test={test-id}` タグを全リソースに付与
- Resource Groups Tagging API でタグ付きリソースを検索
- サービス別の削除API呼び出し
- CloudFormationスタック経由のリソースはスタック削除で一括

---

## Step Types（更新版）

| Type | 説明 | Executor | 動画 |
|---|---|---|---|
| `console_navigate` | Consoleページ遷移 | Playwright | ✅ |
| `console_action` | Console上でのCRUD操作（ボタンクリック・フォーム入力等） | Playwright + LLM Vision | ✅ |
| `console_verify` | Console画面の状態確認 | Playwright screenshot + LLM Vision | ✅ |
| `cli_command` | AWS CLIコマンド実行 | subprocess | ❌ |
| `cli_check` | CLI出力の検証 | subprocess + LLM | ❌ |
| `cfn_deploy` | CloudFormation スタック操作（手順にCFnがある場合） | boto3 | ❌ |
| `http_test` | HTTP エンドポイントテスト | requests | ❌ |
| `code_run` | コード実行（手順にコード実行がある場合） | subprocess | ❌ |
| `wait` | リソース準備待ち | polling | ❌ |
| `manual_step` | 手動操作（スキップ or 代替） | — | — |

**Console操作がメイン！** ほとんどのワークショップ手順はConsole UIでの操作。

---

## AWS Console認証

Workshop TestはAWS Consoleにログインして操作するため、認証が必要:

### 方式1: IAM User + Console Login（推奨）
```python
# ConsoleログインURLを生成
login_url = f"https://signin.aws.amazon.com/console"
# Playwright でログインフォームに入力
await page.goto(login_url)
await page.fill("#account", account_id)
await page.fill("#username", iam_user)
await page.fill("#password", password)
await page.click("#signin_button")
```

### 方式2: Federation Token（一時認証）
```python
# STS GetFederationToken で一時URL生成
sts = boto3.client('sts')
token = sts.get_federation_token(Name='workshop-test', ...)
signin_url = generate_console_url(token)
await page.goto(signin_url)  # 自動ログイン
```

### 方式3: SSO（IAM Identity Center）
```python
# SSO ポータル経由でConsoleにアクセス
await page.goto(sso_start_url)
# SSO認証フロー...
```

---

## Config（更新版）

```yaml
workshop:
  test:
    region: us-east-1
    cleanup_after_test: true
    timeout_per_step_seconds: 300
    max_total_duration_minutes: 120
    max_cost_usd: 10.0
    headed: false  # true=ブラウザ表示、false=headless
    
    # Console認証
    console_auth:
      method: iam_user  # iam_user | federation | sso
      account_id: ""
      username: ""
      # password は .env から読む: YUI_CONSOLE_PASSWORD
    
    # 動画録画
    video:
      enabled: true
      resolution:
        width: 1920
        height: 1080
      per_step: true       # ステップごとの個別動画
      full_walkthrough: true  # 通し動画
      output_dir: ~/.yui/workshop-tests/
    
    # スクリーンショット
    screenshot:
      enabled: true
      on_step_complete: true
      on_failure: true
      full_page: true
  
  report:
    format: markdown
    include_screenshots: true
    include_video_links: true
    slack_notify: true
    save_path: ~/.yui/workshop-tests/
```

---

## ACs（更新版）

| # | AC | 内容 |
|---|---|---|
| AC-70 | Workshop Studio scraping | Playwright でWorkshop Studio SPA からコンテンツ取得 |
| AC-71 | Step planning | Bedrock LLM がコンテンツを実行可能ステップに変換 |
| AC-72 | Console login | AWS Console にPlaywrightで自動ログイン |
| AC-73 | Console navigation | AWS Console のサービスページ間を自動遷移 |
| AC-74 | Console CRUD | Console UI上でリソース作成/更新/削除を自動実行 |
| AC-75 | Vision validation | スクリーンショット + Bedrock Vision で結果判定 |
| AC-76 | Video recording | Playwright video で全操作を動画記録（per-step + full） |
| AC-77 | Screenshot capture | 各ステップ完了時 + 失敗時のスクリーンショット |
| AC-78 | Test report | 構造化レポート（Markdown + 動画リンク + スクリーンショット） |
| AC-79 | Slack notification | テスト結果サマリー + レポートリンクをSlack通知 |
| AC-80 | Resource cleanup | タグベースでテスト用リソースを自動削除 |
| AC-81 | Cost guard | コスト上限超過時のテスト中断 |
| AC-82 | CLI entry point | `yui workshop test <url>` + `--record` + `--cleanup` + `--headed` |
| AC-83 | Timeout handling | ステップ/全体タイムアウト |
| AC-84 | CLI fallback | 手順にCLIコマンドがある場合のsubprocess実行 |
| AC-85 | Regression mode | 定期回帰テスト（cron対応） |
| AC-86 | GitHub content (future) | 将来: GitHubリポのMarkdownからもコンテンツ取得 |

---

## 実装計画

| サブフェーズ | 内容 | 見積 |
|---|---|---|
| 4a | Content Scraper (Workshop Studio Playwright scraping) | 1日 |
| 4b | Step Planner (Bedrock LLM解析) | 0.5日 |
| 4c | Console Executor (Playwright + LLM Vision Console操作) | 2日 |
| 4d | Video Recorder + Screenshot | 0.5日 |
| 4e | Validator (Vision判定) + Reporter | 1日 |
| 4f | Resource Manager + Cleanup | 0.5日 |
| 4g | CLI + Config + Tests | 0.5日 |
| **合計** | | **6日** |

---

## 技術的考慮事項

### Playwright + AWS Console の課題
1. **Console UIは頻繁に変わる** → LLM Vision で動的に対応（セレクタ固定しない）
2. **MFA要求** → テスト用IAMユーザーはMFA無効推奨（or TOTP自動入力）
3. **リージョン選択** → URLパラメータで制御 (`?region=us-east-1`)
4. **ページ読み込み待ち** → `page.wait_for_load_state("networkidle")` + カスタム待機
5. **CAPTCHAリスク** → headless=false + 低速操作で回避

### Playwright Video Recording
- 出力形式: WebM (VP8)
- ブラウザコンテキスト単位で録画開始/停止
- headless モードでも録画可能
- 解像度は `record_video_size` で指定

### コスト見積
- Bedrock (Claude Sonnet): ~$0.003/step (input) + ~$0.015/step (output + vision)
- AWS Console操作のリソース作成コスト: ワークショップ依存（$0〜$5）
- 合計: ワークショップ1回のフルテスト ≈ $1〜$10
