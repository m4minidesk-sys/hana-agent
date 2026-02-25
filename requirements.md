# Yui — Requirements Document

> Lightweight, AWS-optimized AI agent orchestrator inspired by OpenClaw.
> Version: 0.5.0-draft | Last updated: 2026-02-25 | Reviewed by: Kiro CLI (v1.26.2, 2 rounds) + han feedback

---

## 1. Background & Problem Statement

### 1.1 Why build this?

OpenClaw is a powerful AI agent orchestrator (400K+ lines TypeScript, 54 npm deps, 300MB+ install) but has critical constraints for AWS corporate environments:

- **License**: ELv2 (Elastic License v2) — restricts providing as a managed service
- **External API dependency**: Default model calls go through Anthropic/OpenAI APIs — violates corporate data governance policies that require data to stay within AWS VPC
- **Size/complexity**: 300MB+ install with Node.js runtime — excessive for a corporate laptop tool
- **No Bedrock-native support**: Requires additional configuration to use AWS Bedrock; not designed for it

### 1.2 Target users

AWS corporate engineers who need a local AI coding assistant that:
- Integrates with Slack for daily communication
- Uses Bedrock API for LLM calls (data stays in AWS)
- Runs local tools (Kiro CLI, git, Outlook, shell commands)
- Can be set up in <10 minutes on a Mac

### 1.3 Success criteria

| Criteria | Target |
|---|---|
| Install size | <50MB (vs OpenClaw's 300MB+) |
| Python dependencies | ≤10 packages |
| Time to first working agent | <10 minutes |
| Bedrock Converse API latency overhead | <100ms over raw API call |
| Test coverage | >80% for core modules |

---

## 2. Scope

### 2.1 In scope (Phase 0–3)

| Phase | Deliverables |
|---|---|
| Phase 0 | CLI REPL + Bedrock Converse + exec/file tools + AGENTS.md/SOUL.md config loading |
| Phase 1 | Slack Socket Mode adapter + SQLite session management + session compaction |
| Phase 2 | Kiro CLI delegation tool + git tool + AgentCore Browser Tool + AgentCore Memory + **Meeting Transcription & Minutes (Whisper + Bedrock)** |
| Phase 3 | Bedrock Guardrails integration + Heartbeat scheduler + launchd daemon (macOS) |

### 2.2 Out of scope (explicit exclusions)

- **Windows support** — Mac-only for initial release
- **mwinit/Midway authentication caching** — users handle AWS auth externally
- **Docker sandbox** — uses command allowlist/blocklist instead
- **Multi-channel support** — Slack + CLI only (no Telegram, Discord, etc.)
- **Plugin/Hook system** — tools are registered in code or via MCP, not via plugin hooks
- **MCP server hosting** — Yui consumes MCP tools but does not expose MCP endpoints
- **24/7 Slack Bot (Lambda deployment)** — Phase 0-3 uses local Socket Mode only; cloud Slack adapter deferred to Phase 4+
- **Flexible cron scheduling (EventBridge)** — Phase 0-3 uses fixed-interval Heartbeat only; EventBridge deferred to Phase 4+
- **External search APIs as default** — Tavily/Exa are opt-in only; default web search uses Bedrock Knowledge Base (VPC-internal)

### 2.3 Pre-Phase 0: SDK Verification Gate (Kiro review C-01)

Before any implementation begins, verify all SDK assumptions:

- [ ] Confirm `strands-agents` package name and import path (`from strands import Agent`)
- [ ] List available tools in `strands-agents-tools` and verify exact function signatures
- [ ] Verify `BedrockModel` constructor parameters for Guardrails integration
- [ ] Confirm `shell` tool's built-in allowlist/blocklist capability and configuration API
- [ ] Document any API differences from assumptions in this spec
- [ ] Test minimal "hello world" agent with Bedrock in target AWS region

**Gate**: Phase 0 cannot begin until all items are verified and documented.

---

## 3. Architecture Overview

### 3.1 Layer diagram

```
┌─────────────────────────────────────────────────────┐
│                    Yui Runtime                      │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │          Strands Agent (core loop)            │  │
│  │  model: BedrockModel (Claude Sonnet/Opus)     │  │
│  │  tools: [local + cloud + mcp]                 │  │
│  └──────────┬──────────────────┬─────────────────┘  │
│             ↓                  ↓                    │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │  Local Tools      │  │  Cloud Tools (AWS)      │  │
│  │  • exec (shell)   │  │  • Bedrock Converse     │  │
│  │  • file r/w/edit  │  │  • AgentCore Browser    │  │
│  │  • kiro delegate  │  │  • AgentCore Memory     │  │
│  │  • git            │  │  • Bedrock Guardrails   │  │
│  │  • outlook (Mac)  │  │                         │  │
│  └──────────────────┘  └─────────────────────────┘  │
│             ↕                                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  Channel Adapters                             │  │
│  │  • CLI (terminal REPL)                        │  │
│  │  • Slack (Socket Mode, no public URL needed)  │  │
│  └───────────────────────────────────────────────┘  │
│             ↕                                       │
│  ┌───────────────────────────────────────────────┐  │
│  │  Runtime Services                             │  │
│  │  • Session Manager (SQLite)                   │  │
│  │  • Config Loader (YAML + AGENTS.md/SOUL.md)   │  │
│  │  • Heartbeat Scheduler                        │  │
│  │  • Daemon (launchd plist)                     │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 3.2 Key design decisions

| Decision | Rationale |
|---|---|
| **Strands Agent SDK as base** | AWS-official, Bedrock-native, MCP support, Apache 2.0. Provides the agent loop, tool registration, and model abstraction — avoids reimplementing OpenClaw's 1,165-line `run.ts` |
| **Strands built-in tools where possible** | `shell`, `file_read`, `file_write`, `editor`, `slack_client`, `use_aws` already exist in `strands-agents-tools`. Use them instead of writing custom implementations |
| **Custom tools only for Yui-specific needs** | Kiro CLI delegation, Outlook AppleScript, Heartbeat — things not covered by strands-agents-tools |
| **SQLite for sessions (not S3)** | Phase 0-3 is single-device. S3 sync is a future optimization |
| **Bedrock Guardrails via SDK parameter** | `BedrockModel(guardrail_id=..., guardrail_latest_message=True)` — zero custom code needed |
| **No Docker sandbox** | Command allowlist + blocklist on exec tool. Lighter than Docker for corporate laptop use case |

### 3.3 Data flow: user message → response

```
1. User types in CLI or sends Slack message
2. Channel adapter extracts text, routes to Agent
3. Agent builds system prompt: config.yaml base + AGENTS.md + SOUL.md content
4. Agent calls BedrockModel.converse() with conversation history + tools
5. If model returns tool_use → execute tool → feed result back → loop to step 4
6. If model returns end_turn → extract text → send to channel adapter → display to user
7. Session manager persists conversation history to SQLite
```

---

## 4. Tool Inventory & Local/Cloud Boundary Design

### 4.0 Boundary Design Principles (Kiro review round 2)

Every tool must be explicitly assigned to a tier based on these criteria:

| Criteria | → Local | → Cloud (AWS) |
|---|---|---|
| Needs local filesystem | ✅ Must be local | — |
| Needs local CLI (Kiro, git, osascript) | ✅ Must be local | — |
| Low latency required (<100ms) | ✅ Prefer local | — |
| Must work offline | ✅ Must be local | — |
| Handles sensitive local data (keys, config) | ✅ Must be local | — |
| Heavy compute / memory (browser, ML) | — | ✅ Prefer cloud |
| AWS VPC data governance requirement | — | ✅ Must be cloud |
| 24/7 availability needed | — | ✅ Prefer cloud |
| Sandboxed execution required | — | ✅ Prefer cloud |

### 4.1 Local Tools (run on user's Mac)

These tools MUST run locally because they access local filesystem, CLIs, or macOS APIs.

| Tool | Source | Purpose | Why local |
|---|---|---|---|
| `shell` | strands-agents-tools | Shell command execution with allowlist | Local CLI access |
| `file_read` | strands-agents-tools | Read file contents | Local filesystem |
| `file_write` | strands-agents-tools | Write/create files | Local filesystem |
| `editor` | strands-agents-tools | View, replace, insert, undo edits | Local filesystem |
| `kiro_delegate` | Custom | Delegate coding tasks to Kiro CLI | Local CLI + workspace access. **Kiro CLI is a required dependency** (han review item ④) |
| `git_tool` | Custom | Git operations (status, add, commit, push, log, diff) | Local repo access |
| `http_request` | strands-agents-tools | HTTP GET/POST to public URLs | Low latency, simple HTTP |
| `meeting_recorder` | Custom | Capture system audio + mic for meeting transcription | macOS audio APIs (ScreenCaptureKit / BlackHole), local audio processing |
| `whisper_transcribe` | Custom | Real-time speech-to-text using Whisper | Local ML inference on Apple Silicon (mlx-whisper / whisper.cpp) |

**Note**: `outlook_calendar` and `outlook_mail` are no longer custom local tools. They are provided via the `aws-outlook-mcp` corporate MCP server (see Section 4.4).

### 4.2 Cloud Tools (run on AWS)

These tools run in AWS because they require managed infrastructure, sandboxing, or VPC-internal data processing.

| Tool | Source | Purpose | Why cloud |
|---|---|---|---|
| Bedrock Converse | Strands SDK core | LLM inference | VPC data governance, IAM auth |
| AgentCore Browser | strands-agents-tools `AgentCoreBrowser` | Web browsing automation (managed Chrome) | Memory savings (~2GB), sandboxed, VPC-internal |
| AgentCore Memory | strands-agents-tools `agent_core_memory` | Long-term memory (facts, preferences) | Cross-device sync, managed persistence |
| AgentCore Code Interpreter | strands-agents-tools `code_interpreter` | Python code execution in sandbox | Sandboxed, safe arbitrary code execution |
| Bedrock Knowledge Base | strands-agents-tools `retrieve` | Semantic search over indexed documents | VPC-internal, replaces external search APIs |

### 4.3 Hybrid Tools (local initiation, cloud component)

| Tool | Local component | Cloud component | Rationale |
|---|---|---|---|
| `slack_client` | Socket Mode WebSocket from local machine | Slack API (external SaaS) | Must be local for Socket Mode; Slack API is external but authorized via bot tokens |

### 4.4 MCP Server Integration (han review — items ⑤⑥)

Yui uses Strands SDK's native MCP support (`MCPClient` / `mcp_client` tool) to extend capabilities via MCP servers. This replaces custom tool implementations for Outlook and media/diagram generation.

**Strands MCP integration patterns:**
- **Static (pre-configured)**: `MCPClient` from `strands.tools.mcp` — loaded at startup from config.yaml
- **Dynamic (runtime)**: `mcp_client` tool from `strands-agents-tools` — agent can connect to new MCP servers on demand

```yaml
# config.yaml — MCP server configuration
mcp:
  servers:
    # Corporate MCP servers (pre-configured, loaded at startup)
    outlook:
      transport: stdio
      command: "aws-outlook-mcp"    # Corporate Outlook MCP server
      args: []
      enabled: true
    # Additional MCP servers can be added here
  dynamic:
    enabled: true                   # Allow agent to connect to new MCP servers at runtime
    allowlist: []                   # Optional: restrict to specific server commands
```

**MCP replaces these previously custom/excluded tools:**

| Previously | Now via MCP | MCP Server |
|---|---|---|
| `outlook_calendar` (custom AppleScript) | MCP tool call | `aws-outlook-mcp` (corporate) |
| `outlook_mail` (custom AppleScript) | MCP tool call | `aws-outlook-mcp` (corporate) |
| `diagram` (excluded) | MCP tool call | Corporate/community MCP server |
| `nova_reels` / image / video (excluded) | MCP tool call (opt-in) | Corporate/community MCP server |

### 4.5 Explicitly NOT included as builtin (with rationale + alternative)

| Tool | Why not builtin | Alternative | Status |
|---|---|---|---|
| `tavily_search` / `tavily_extract` / `tavily_crawl` | Sends queries to external SaaS outside AWS VPC | **AgentCore Browser** (cloud-managed Chrome for web browsing + search) | Bedrock feature: AgentCore Browser (`bedrock-agentcore:CreateBrowser`, `StartBrowserSession`) |
| `exa_search` / `exa_get_contents` | Same VPC concern as Tavily | **AgentCore Browser** | Same as above |
| `python_repl` (local) | Arbitrary local code execution without sandbox | **AgentCore Code Interpreter** (sandboxed, multi-language) | Bedrock feature: AgentCore Code Interpreter (`bedrock-agentcore:CreateCodeInterpreter`) |
| `use_browser` (local Chromium) | ~2GB memory overhead | **AgentCore Browser** (default). Local Chromium available as opt-in fallback for auth-required internal sites | Config: `tools.browser.provider: local` |
| `use_computer` | High security risk (arbitrary desktop control) | **MCP servers** for specific desktop integrations as needed | Deferred — no current use case beyond what Outlook MCP + Kiro CLI cover |
| `outlook_calendar` / `outlook_mail` (custom) | AppleScript is Mac-specific, brittle | **`aws-outlook-mcp`** corporate MCP server | MCP: cross-platform, maintained by corporate team |
| `nova_reels` / image / video / audio | Not core to coding assistant use case | **MCP servers** (corporate/community) for on-demand media generation | MCP: extensible without code changes |
| `diagram` | Not core enough for builtin | **MCP server** (community) for diagram generation when needed | MCP: available on-demand |

### 4.6 AWS Bedrock features used (explicit enumeration — han review items ①②③)

Yui depends on the following specific AWS Bedrock/AgentCore features. These must be available in the target AWS region.

| Feature | AWS Service | API/Resource | Purpose in Yui | Phase |
|---|---|---|---|---|
| **LLM Inference** | Bedrock | `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | Core agent loop — Converse API | Phase 0 |
| **Guardrails** | Bedrock | `bedrock:ApplyGuardrail` + Guardrail resource | Input/output safety filtering | Phase 3 |
| **AgentCore Browser** | Bedrock AgentCore | `bedrock-agentcore:CreateBrowser`, `StartBrowserSession`, `ConnectBrowserAutomationStream`, `ConnectBrowserLiveViewStream` | Cloud-managed Chrome for web browsing, search, content extraction. **Replaces Tavily/Exa** | Phase 2 |
| **AgentCore Memory** | Bedrock AgentCore | AgentCore Memory API (create memory, store, retrieve) | Long-term memory (facts, preferences) with cross-device sync | Phase 2 |
| **AgentCore Code Interpreter** | Bedrock AgentCore | `bedrock-agentcore:CreateCodeInterpreter` + session management | Sandboxed Python/JS/TS execution. **Replaces local python_repl** | Phase 2 |
| **Knowledge Base** | Bedrock | `bedrock:Retrieve`, `bedrock:RetrieveAndGenerate` | Semantic search over indexed corporate documents (RAG) | Phase 2 |

### 4.5 Browser provider selection (Kiro review round 2, C-1)

```yaml
tools:
  browser:
    provider: agentcore       # Default: AWS-managed Chrome
    # provider: local         # Fallback: local Chromium (requires pip install strands-agents-tools[local-chromium-browser])
    region: us-east-1         # AgentCore Browser region
```

| Provider | When to use | Pros | Cons |
|---|---|---|---|
| `agentcore` (default) | Normal operation | No local memory cost, sandboxed, VPC-internal | Requires AWS credentials, network latency |
| `local` (fallback) | Offline, AgentCore unavailable | Low latency, works offline | ~2GB memory, local Chromium install required |

### 4.6 Web search strategy (Kiro review round 2, C-2)

**Problem**: Tavily/Exa send search queries to external SaaS → breaks VPC data governance requirement.

**Solution — phased approach**:

| Phase | Web search method | VPC compliance |
|---|---|---|
| Phase 0–1 | `http_request` (direct HTTP GET to public URLs) | ✅ No external API keys, local execution |
| Phase 2 | `retrieve` (Bedrock Knowledge Base) for indexed corporate docs | ✅ VPC-internal semantic search |
| Phase 3+ | `tavily_search` as **opt-in** with config warning | ⚠️ Explicit user choice, logged |

```yaml
tools:
  web_search:
    provider: bedrock_kb      # Default: VPC-internal (requires Knowledge Base setup)
    # provider: tavily        # Opt-in: external SaaS (WARNING: data leaves AWS VPC)
    # provider: http_only     # Minimal: plain HTTP requests only
    knowledge_base_id: ""     # Required for bedrock_kb provider
```

### 4.7 Python execution strategy (Kiro review round 2, C-3)

**Problem**: `python_repl` executes arbitrary code locally without sandbox.

**Solution**:

| Provider | Security | Use case |
|---|---|---|
| `agentcore_code_interpreter` (default) | ✅ AWS-managed sandbox, isolated | Data analysis, calculations, any untrusted code |
| `python_repl` (opt-in) | ⚠️ Local execution, import allowlist | Quick local scripts, requires explicit config flag |

```yaml
tools:
  python:
    provider: agentcore_code_interpreter  # Default: sandboxed
    # provider: local_repl                # Opt-in: local (WARNING: arbitrary code execution)
    region: us-east-1
```

### 4.8 Memory architecture (Kiro review round 2, M-2)

**Two-tier memory with clear separation of concerns:**

| Data type | Storage | Reason |
|---|---|---|
| **Conversation history** (short-term) | SQLite (local) | Low latency, offline-capable, single device |
| **Session metadata** (thread IDs, timestamps) | SQLite (local) | Local management sufficient |
| **Long-term memory** (facts, preferences, learned info) | AgentCore Memory (cloud) | Cross-device sync, managed persistence, semantic retrieval |

SQLite handles ephemeral session data. AgentCore Memory handles durable knowledge that should survive device changes. They are complementary, not redundant.

### 4.9 Scheduler design (Kiro review round 2, M-3)

| Phase | Scheduler | Limitation |
|---|---|---|
| Phase 0–3 | Heartbeat only (fixed-interval, in-process `threading.Timer`) | Machine must be awake; no cron expressions |
| Phase 4+ | EventBridge (cloud) for reliable cron scheduling | Requires AWS setup; machine sleep irrelevant |

**Out of scope for Phase 0–3**: Flexible cron scheduling (EventBridge). Heartbeat is fixed-interval only.

### 4.10 Custom tool implementation details

| Tool | Purpose | Implementation notes |
|---|---|---|
| `kiro_delegate` | Delegate coding tasks to Kiro CLI | `subprocess.run(["kiro-cli", "chat", "--no-interactive", ...])`, ANSI strip, timeout 300s, **output truncated at 50,000 chars**. **Kiro CLI must be installed** — Yui checks at startup and provides install instructions if missing |
| `git_tool` | Git operations (status, add, commit, push, log, diff, branch, checkout) | Wrapper around `subprocess.run(["git", ...])` with allowlisted subcommands |

### 4.11 Tool security model

- **Shell execution**: strands-agents-tools `shell` tool has built-in user confirmation. Yui config adds an allowlist with subcommand granularity (e.g., `"git status"`, `"git log"`, `"git diff"` — not bare `"git"`) and a blocklist (e.g., `["rm -rf /", "sudo", "curl | bash", "git push --force", "git reset --hard", "git clean -f"]`). Remove bare `git` from shell allowlist; use dedicated `git_tool` for safe git operations.
- **File operations**: Restricted to configurable workspace directory by default
- **Outlook**: Provided via `aws-outlook-mcp` corporate MCP server. No local AppleScript — cross-platform, maintained by corporate team.
- **MCP servers**: Static servers loaded from config.yaml at startup. Dynamic server connections require `mcp.dynamic.enabled: true`. Optional allowlist restricts which servers can be connected at runtime.
- **Python execution**: AgentCore Code Interpreter by default (sandboxed). Local `python_repl` requires explicit opt-in + import allowlist.
- **Web search**: Bedrock Knowledge Base by default (VPC-internal). Tavily requires explicit opt-in with logged warning.
- **Browser**: AgentCore Browser by default (managed Chrome). Local Chromium requires explicit opt-in.

---

## 5. Channel Adapters

### 5.1 CLI Adapter (Phase 0)

- Terminal REPL with `readline` history support
- Rich-formatted output (code blocks, tables) via `rich` library
- Ctrl+C graceful exit, Ctrl+D for EOF
- System prompt displayed on startup

### 5.2 Slack Adapter (Phase 1)

- **Library**: `slack-bolt` with Socket Mode (no public URL/ngrok needed)
- **Tokens**: Bot Token (`xoxb-`) + App-Level Token (`xapp-`)
- **Events**: `app_mention`, `message.channels`, `message.im`
- **Threading**: Replies in thread when original message is threaded
- **Reactions**: 👀 on receipt, ✅ on completion. Batch status updates — do NOT react after every tool call (Kiro review M-03)
- **Rate limiting**: `slack-bolt` has built-in rate limit handling with automatic retry+backoff. If rate limited for >30s, send single message: "Response ready but Slack rate limited. Will retry shortly."

---

## 6. Session Management (Phase 1)

### 6.1 Storage

- **Backend**: SQLite database at `~/.yui/sessions.db`
- **WAL mode**: `PRAGMA journal_mode=WAL` for concurrent reads + single writer (Kiro review C-03)
- **Connection timeout**: `sqlite3.connect(timeout=5.0)` to handle lock contention
- **Single instance**: Only ONE Yui process per user. On startup, check PID file at `~/.yui/yui.pid`. If PID file exists and process is alive, exit with: "Another Yui instance is running (PID: X). Stop it first or use that instance."
- **Schema**: `sessions(id TEXT PK, channel TEXT, user TEXT, messages JSON, created_at INT, updated_at INT, token_count INT)`
- **Scope**: per-sender (one session per Slack user or CLI instance)

### 6.2 Compaction

- **Trigger**: When `token_count` exceeds configurable threshold (default: 80% of model context window)
- **Method**: Summarize conversation via LLM call, replace history with summary + recent N messages
- **Preservation**: Always keep system prompt + last 5 messages in full

---

## 7. Configuration (Phase 0)

### 7.1 File structure

```
~/.yui/
├── config.yaml          # Main configuration
├── sessions.db          # SQLite session store (auto-created)
├── workspace/
│   ├── AGENTS.md        # System prompt (what the agent does) — includes Kiro cross-review workflow
│   └── SOUL.md          # Persona definition (how the agent behaves)
└── .env                 # Secrets (SLACK_BOT_TOKEN, etc.)
```

### 7.1.1 Kiro CLI as required dependency (han review item ④)

Kiro CLI is a **required setup dependency**, not optional. Yui delegates all coding tasks to Kiro CLI, following the same pattern as AYA's ecosystem:

**Setup requirement:**
- `kiro-cli` must be installed and authenticated before Yui can start
- Yui checks for Kiro CLI at startup: if missing, displays install instructions and exits
- Kiro CLI path is configurable via `tools.kiro.binary_path`

**AGENTS.md cross-review workflow (built-in):**

The default `~/.yui/workspace/AGENTS.md` shipped with Yui includes a mandatory Kiro⇔Yui cross-review process, modeled on AYA's ecosystem:

```markdown
# Default AGENTS.md excerpt — Kiro Cross-Review Workflow

## Coding Workflow (mandatory)
1. Yui writes requirements.md (What/Why)
2. Kiro CLI generates design.md + tasks.md (How)
3. Kiro CLI implements code
4. Yui reviews Kiro's output against requirements (AC matching)
5. Kiro CLI reviews Yui's requirements for ambiguities
6. Iterate until both pass
7. Only then: PR creation

## Rules
- Yui MUST NOT write code directly — all code via Kiro CLI
- Requirements changes require re-review cycle
- Every PR must have been reviewed by both Yui and Kiro
```

### 7.2 config.yaml schema

```yaml
# Model configuration
model:
  provider: bedrock             # Only bedrock supported initially
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  region: us-east-1
  guardrail_id: ""              # Optional Bedrock Guardrail ID
  guardrail_version: DRAFT
  guardrail_latest_message: false   # Default: full history for security. Set true for cost savings (see Section 8)
  max_tokens: 4096

# Tool configuration
tools:
  shell:
    allowlist:
      - "ls"
      - "cat"
      - "grep"
      - "find"
      - "python3"
      - "kiro-cli"
      - "brew"
      # Note: bare "git" is NOT in allowlist — use git_tool for safe git ops
    blocklist:
      - "rm -rf /"
      - "sudo"
      - "curl | bash"
      - "eval"
      - "git push --force"
      - "git reset --hard"
      - "git clean -f"
    timeout_seconds: 30
  file:
    workspace_root: "~/workspace"   # Restrict file ops to this directory
  kiro:
    binary_path: "~/.local/bin/kiro-cli"
    timeout_seconds: 300

# MCP server configuration (han review items ⑤⑥)
mcp:
  servers:
    outlook:
      transport: stdio
      command: "aws-outlook-mcp"
      args: []
      enabled: true
  dynamic:
    enabled: true
    allowlist: []                   # Optional: restrict dynamic MCP connections
  browser:
    provider: agentcore             # "agentcore" (default, cloud) or "local" (fallback)
    region: us-east-1
  web_search:
    provider: bedrock_kb            # "bedrock_kb" (default, VPC-internal) or "tavily" (opt-in, external)
    knowledge_base_id: ""           # Required for bedrock_kb
    # WARNING: tavily sends queries to external SaaS outside AWS VPC
  python:
    provider: agentcore_code_interpreter  # "agentcore_code_interpreter" (default, sandboxed) or "local_repl" (opt-in)
    region: us-east-1
  memory:
    provider: agentcore             # "agentcore" (default, cloud) or "local_only" (SQLite only)
    region: us-east-1

# Channel configuration  
channels:
  cli:
    enabled: true
  slack:
    enabled: false                  # Requires tokens in .env
    bot_token_env: SLACK_BOT_TOKEN
    app_token_env: SLACK_APP_TOKEN
    default_channel: ""

# Runtime configuration
runtime:
  session:
    compaction_threshold: 0.8       # Compact at 80% of context window
    keep_recent_messages: 5
  heartbeat:
    enabled: false
    interval_minutes: 15
    active_hours: "07:00-24:00"
    timezone: "Asia/Tokyo"          # IANA timezone (DST handled via stdlib zoneinfo)
  daemon:
    enabled: false
    launchd_label: "com.yui.agent"
```

---

## 8. Bedrock Guardrails (Phase 3)

- Integrated via `BedrockModel(guardrail_id=..., guardrail_version=..., guardrail_latest_message=...)`
- **Security trade-off** (Kiro review C-02):
  - `guardrail_latest_message=False` (default): Full conversation history sent to Guardrails — secure against multi-turn attacks but higher token cost
  - `guardrail_latest_message=True`: Only latest message evaluated — faster/cheaper but vulnerable to multi-turn jailbreak
  - **Yui default: `false`** (full history). Users can opt into `true` in config.yaml with explicit warning
  - **Compensating control**: When `guardrail_latest_message=true`, Yui performs a full-history guardrail check every 10 turns as a safety net
- No custom guardrail implementation needed — Strands SDK handles it
- Guardrail violations surface as error messages to the user

---

## 9. Heartbeat (Phase 3)

### 9.1 Behavior

- Reads `~/.yui/workspace/HEARTBEAT.md` (if exists) at configurable interval
- **File integrity** (Kiro review M-04): On first load, compute SHA256 hash. On subsequent loads, verify hash. If changed externally (not by agent), log warning. HEARTBEAT.md must be owned by current user with 600 permissions; reject if world-writable.
- **Content handling**: Heartbeat content is treated as **user input** (not system prompt) — goes through Bedrock Guardrails if enabled
- Sends content to agent as a system event
- Agent responds autonomously (e.g., check Slack for unread messages, run scheduled tasks)
- Active hours restriction prevents execution during sleep hours

### 9.2 Implementation

- Python `threading.Timer` or `schedule` library
- Runs in-process (not a separate process)
- Heartbeat results logged but not sent to any channel unless agent decides to
- **Fixed-interval only** — cron expressions (e.g., "every Monday at 9am") are NOT supported in Phase 0–3. Flexible scheduling via EventBridge is deferred to Phase 4+.

---

## 9.5 Meeting Transcription & Automatic Minutes (Phase 2)

### 9.5.1 Overview

Yui provides automatic meeting transcription, intelligent minute generation, and real-time meeting analysis using a **hybrid local/cloud architecture**: audio capture and speech-to-text run locally (privacy + low latency), while LLM-powered analysis runs via Bedrock (intelligence + quality).

### 9.5.2 Architecture: Local/Cloud Split

```
┌─ LOCAL (Mac) ─────────────────────────────────┐
│                                                │
│  [System Audio]──┐                             │
│                  ├─→ Audio Mixer → Whisper ──→ Transcript chunks
│  [Mic Audio]─────┘   (16kHz mono)  (local)     │
│                                                │
│  Whisper engine: mlx-whisper (Apple Silicon)    │
│  or whisper.cpp (CoreML/ANE acceleration)       │
│                                                │
└──────────────┬─────────────────────────────────┘
               │ transcript text (every ~5-10s)
               ▼
┌─ CLOUD (AWS Bedrock) ─────────────────────────┐
│                                                │
│  [Bedrock Converse API]                        │
│    ├─ Real-time analysis (sliding window)      │
│    ├─ Post-meeting summary & minutes           │
│    └─ Action item extraction                   │
│                                                │
└────────────────────────────────────────────────┘
```

**Why Whisper local (not Amazon Transcribe)?**

| Factor | Whisper Local (mlx-whisper) | Amazon Transcribe Streaming |
|---|---|---|
| **Privacy** | Audio never leaves device | Audio sent to AWS |
| **Cost** | Free (local compute) | $0.024/min (~$1.44/hr meeting) |
| **Latency** | ~0.5s on Apple Silicon | ~1-2s (network round-trip) |
| **Offline** | Works without internet | Requires internet |
| **Accuracy (WER)** | ~4-5% (large-v3-turbo) | ~18-22% |
| **Speaker diarization** | Requires pyannote (optional) | Built-in |
| **Japanese** | Excellent (trained on multilingual data) | Good |

**Decision: Whisper local is default.** Amazon Transcribe is available as opt-in fallback for speaker diarization or when local compute is constrained.

### 9.5.3 Audio Capture (macOS)

**Primary method: ScreenCaptureKit** (macOS 13+)
- Captures system audio directly (no virtual audio driver needed)
- Requires Screen Recording permission in System Preferences
- Can capture specific app audio (e.g., Zoom/Teams only)

**Fallback: BlackHole virtual audio driver**
- For macOS <13 or permission issues
- Requires `brew install blackhole-2ch` + Audio MIDI Setup configuration
- Creates loopback device combining system audio + mic

**Audio pipeline:**
```
System Audio (meeting app) ─┐
                            ├─→ Audio Mixer → Resampler (16kHz mono) → Whisper
Microphone (user's voice) ──┘
```

**Config:**
```yaml
meeting:
  audio:
    capture_method: screencapturekit  # or "blackhole"
    include_mic: true                 # Mix microphone input
    sample_rate: 16000                # Whisper expects 16kHz
    channels: 1                       # Mono
  whisper:
    engine: mlx                       # "mlx" (default on Apple Silicon) or "cpp" (whisper.cpp)
    model: large-v3-turbo             # Best accuracy/speed balance
    language: auto                    # Auto-detect, or "ja", "en"
    chunk_seconds: 5                  # Transcribe every 5 seconds
    vad_enabled: true                 # Voice Activity Detection — skip silence
  analysis:
    provider: bedrock                 # Bedrock Converse for LLM analysis
    realtime_enabled: true            # Enable real-time analysis during meeting
    realtime_interval_seconds: 60     # Analyze every 60 seconds
    minutes_auto_generate: true       # Auto-generate minutes when meeting ends
  output:
    transcript_dir: ~/.yui/meetings/  # Save transcripts here
    format: markdown                  # "markdown" or "json"
    slack_notify: true                # Post minutes to Slack after meeting
```

### 9.5.4 Whisper Engine Options

| Engine | Package | Apple Silicon Optimization | Install |
|---|---|---|---|
| **mlx-whisper** (default) | `mlx-whisper` | MLX framework — 2-3x faster than CPU | `pip install mlx-whisper` |
| **whisper.cpp** | System binary | CoreML + ANE — 3x+ faster than CPU | `brew install whisper-cpp` |
| **faster-whisper** | `faster-whisper` | CTranslate2 (CPU optimized) | `pip install faster-whisper` |

**Default: mlx-whisper** — best Python integration, native Apple Silicon optimization, easy install via pip.

### 9.5.5 Real-time Meeting Analysis (Bedrock)

During a meeting, Yui performs live analysis by sending transcript chunks to Bedrock:

**Every ~60 seconds (configurable):**
```
System prompt: "You are a meeting analyst. Based on the following transcript excerpt,
identify: (1) key decisions being made, (2) action items mentioned, (3) questions
that were asked but not answered, (4) topics that may need follow-up."

[Sliding window: last 5 minutes of transcript]
```

**Output channels:**
- **CLI**: Real-time display in terminal sidebar (if CLI mode)
- **Slack**: Periodic updates to a designated thread (configurable)
- **File**: Appended to `~/.yui/meetings/<meeting_id>/analysis.md`

**Use cases during meeting:**
- 🎯 Track action items as they're assigned ("Bob will send the doc by Friday")
- ❓ Flag unanswered questions ("We didn't resolve the deployment timeline")
- 📊 Detect topic shifts ("We moved from budget to hiring")
- ⚠️ Alert on decisions ("Team decided to use Kafka instead of SQS")

### 9.5.6 Automatic Minutes Generation (Post-meeting)

When the meeting recording stops, Yui automatically generates structured minutes:

**Minutes template (Bedrock LLM prompt):**
```markdown
# Meeting Minutes — {date} {time}
## Attendees
(Identified from transcript if speaker diarization available, otherwise "Participants")

## Summary
(2-3 paragraph executive summary)

## Key Decisions
1. [Decision] — [Context]

## Action Items
| # | Action | Owner | Due Date | Status |
|---|---|---|---|---|
| 1 | ... | ... | ... | Open |

## Discussion Topics
### Topic 1: ...
- Key points discussed
- Outcome / Next steps

## Open Questions
- Questions raised but not resolved

## Raw Transcript
(Link to full transcript file)
```

**Post-processing pipeline:**
1. Meeting ends → `meeting_recorder` tool stops
2. Full transcript assembled from chunks
3. Bedrock Converse API: Generate structured minutes (using Claude)
4. Minutes saved to `~/.yui/meetings/<meeting_id>/minutes.md`
5. If `slack_notify: true` → Post summary to Slack channel
6. If `outlook_mcp` available → Create follow-up calendar events for action items

### 9.5.7 Speaker Diarization (optional)

**Option A: pyannote.audio (local, recommended)**
- Open-source, runs locally
- Requires HuggingFace token (model is gated)
- Can identify 2-10 speakers
- Package: `pyannote-audio`
- Integration: Run after Whisper transcription, align timestamps

**Option B: Amazon Transcribe (cloud fallback)**
- Built-in speaker diarization
- Better for >5 speakers
- Cost: $0.024/min
- Use via `meeting.transcribe.provider: aws_transcribe` config

**Default: No diarization** (Phase 2 MVP). Speaker labels are a Phase 4+ enhancement.

### 9.5.8 Meeting Lifecycle

```
yui meeting start                    # Start recording + transcription
  → Audio capture begins
  → Whisper chunked transcription starts
  → Real-time Bedrock analysis starts (if enabled)

yui meeting status                   # Show current meeting info
  → Duration, word count, current topic, action items so far

yui meeting stop                     # Stop recording
  → Transcription finalized
  → Bedrock generates minutes
  → Slack notification (if configured)
  → Files saved to ~/.yui/meetings/

yui meeting list                     # List past meetings
yui meeting show <id>                # Show transcript + minutes
yui meeting search "keyword"         # Search across meeting transcripts
```

### 9.5.9 Privacy & Security

- **Audio stays local**: Raw audio is processed by Whisper on-device. Never uploaded to cloud.
- **Text to Bedrock**: Only text transcripts are sent to Bedrock for analysis (within AWS VPC).
- **Meeting files**: Stored locally at `~/.yui/meetings/` with permission 700.
- **Retention**: Configurable auto-delete after N days (`meeting.retention_days: 90`).
- **No recording without explicit start**: Yui NEVER records audio without explicit `yui meeting start` command.

### 9.5.10 Dependencies (meeting feature)

| Package | Purpose | License | Phase |
|---|---|---|---|
| `mlx-whisper` | Whisper inference on Apple Silicon | MIT | Phase 2 |
| `pyaudio` or `sounddevice` | Audio capture from system/mic | MIT | Phase 2 |
| `numpy` | Audio buffer processing | BSD | Phase 2 |

**Note**: These are **optional dependencies** — installed only when meeting feature is enabled. Core Yui works without them.

```toml
# pyproject.toml
[project.optional-dependencies]
meeting = ["mlx-whisper>=0.4", "sounddevice>=0.5", "numpy>=1.26"]
```

---

## 10. Daemon (Phase 3, macOS only)

- launchd plist at `~/Library/LaunchAgents/com.yui.agent.plist`
- Starts on login, restarts on crash (5s backoff)
- Environment variables loaded from `~/.yui/.env`
- **Logging**: `~/.yui/logs/yui.log` with `RotatingFileHandler(maxBytes=10MB, backupCount=5)` (Kiro review m-03)
- Control: `launchctl load/unload`, `yui daemon start/stop/status`

---

## 11. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Language** | Python 3.12+ |
| **License** | Apache 2.0 |
| **Install size** | <50MB |
| **Dependencies** | strands-agents, strands-agents-tools, bedrock-agentcore, boto3, slack-bolt, pyyaml, rich, mcp |
| **Startup time** | <3 seconds to CLI REPL |
| **LLM latency** | No measurable overhead vs raw Bedrock API call |
| **Security** | No plaintext secrets in config; .env file with 600 permissions |
| **Logging** | Python `logging` module with `RotatingFileHandler`, configurable level |
| **Error handling** | Graceful degradation: Bedrock timeout → retry 3x with exponential backoff (1s, 2s, 4s) → user error message |
| **Testing** | pytest, >80% coverage for core modules, mocked AWS calls. **Must include negative tests for E-01 through E-12** (Kiro review m-05) |

---

## 12. Acceptance Criteria

### Phase 0 (CLI + Bedrock + Tools)

- [ ] AC-01: `python -m yui` starts a CLI REPL that accepts user input
- [ ] AC-02: User message is sent to Bedrock via Strands Agent SDK and response is displayed
- [ ] AC-03: Agent can execute shell commands via `shell` tool with allowlist enforcement
- [ ] AC-04: Agent can read, write, and edit files via strands-agents-tools
- [ ] AC-05: System prompt includes content from AGENTS.md and SOUL.md
- [ ] AC-06: `config.yaml` is loaded and validated on startup
- [ ] AC-07: Invalid config produces a clear error message and exits
- [ ] AC-08: CLI supports readline history (up arrow recalls previous input)

### Phase 1 (Slack + Sessions)

- [ ] AC-09: Slack Socket Mode connects successfully with bot + app tokens
- [ ] AC-10: @mention in a Slack channel triggers agent response in thread
- [ ] AC-11: DM to bot triggers agent response
- [ ] AC-12: Conversation history is persisted in SQLite across restarts
- [ ] AC-13: Session compaction triggers at configured threshold
- [ ] AC-14: Compacted session preserves context (agent still knows prior discussion)

### Phase 2 (Kiro + Git + Cloud Tools)

- [ ] AC-15: `kiro_delegate` tool invokes Kiro CLI and returns cleaned output
- [ ] AC-16: `git_tool` can run status, add, commit, push, log, diff
- [ ] AC-17: AgentCore Browser Tool can fetch and extract web page content
- [ ] AC-18: AgentCore Memory can store and retrieve memories across sessions
- [ ] AC-19: Kiro CLI timeout (>300s) produces graceful error, not crash
- [ ] AC-19a: Kiro CLI missing at startup → clear error with install instructions, exit code 1

### Phase 2 — Meeting Transcription & Minutes

- [ ] AC-40: `yui meeting start` begins audio capture and Whisper transcription
- [ ] AC-41: `yui meeting stop` stops recording and triggers auto-minutes generation
- [ ] AC-42: Whisper transcribes audio chunks in near-real-time (<5s latency)
- [ ] AC-43: System audio from meeting apps (Zoom/Teams/Chime) is captured
- [ ] AC-44: Microphone audio is mixed with system audio when `include_mic: true`
- [ ] AC-45: Bedrock generates structured meeting minutes (summary, action items, decisions)
- [ ] AC-46: Minutes saved to `~/.yui/meetings/<meeting_id>/minutes.md`
- [ ] AC-47: Slack notification with meeting summary posted after meeting ends (if configured)
- [ ] AC-48: `yui meeting list` shows past meeting transcripts
- [ ] AC-49: `yui meeting search "keyword"` searches across meeting transcripts
- [ ] AC-50: Real-time analysis updates every 60s during active meeting (action items, decisions)
- [ ] AC-51: Meeting feature is opt-in — requires `pip install yui-agent[meeting]`

### Phase 3 (Guardrails + Heartbeat + Daemon)

- [ ] AC-20: Bedrock Guardrail blocks harmful content and surfaces error to user
- [ ] AC-21: Heartbeat reads HEARTBEAT.md and triggers agent at configured interval
- [ ] AC-22: Heartbeat respects active hours (no execution outside configured window)
- [ ] AC-23: `launchctl load` starts Yui as background daemon
- [ ] AC-24: Daemon auto-restarts on crash within 5 seconds
- [ ] AC-25: `yui daemon status` reports running/stopped state
- [ ] AC-25a: Static MCP servers from config.yaml are connected at startup
- [ ] AC-25b: `aws-outlook-mcp` server provides calendar and mail functionality
- [ ] AC-25c: Dynamic MCP server connection works at agent runtime

### Error Handling (negative tests — Kiro review m-05)

- [ ] AC-26: Missing AWS credentials → clear error message, exit code 1 (E-01)
- [ ] AC-27: Bedrock permission denied → actionable IAM error (E-02)
- [ ] AC-28: Bedrock timeout → 3 retries with backoff, then user error (E-03)
- [ ] AC-29: Invalid Slack tokens → startup error with guidance (E-04)
- [ ] AC-30: Shell blocklisted command → "blocked by security policy" (E-08)
- [ ] AC-31: File operation outside workspace → "access denied" (E-09)
- [ ] AC-32: Missing config.yaml → runs with defaults, logs info (E-10)
- [ ] AC-33: Kiro CLI not found → graceful error message (E-07)
- [ ] AC-34: SQLite database locked → retry with backoff, then clear error (E-06)
- [ ] AC-35: Context window exceeded → force compaction or archive session (E-12)
- [ ] AC-36: MCP server connection failure → graceful degradation, agent continues (E-13)
- [ ] AC-37: Kiro CLI missing at startup → exit with install instructions (E-07 revised)

---

## 13. Edge Cases & Error Handling

| # | Scenario | Expected behavior |
|---|---|---|
| E-01 | AWS credentials not configured | Clear error message: "AWS credentials not found. Run `aws configure` or set environment variables." Exit code 1 |
| E-02 | Bedrock model not accessible (permission denied) | Error: "Cannot access model X. Check IAM permissions for bedrock:InvokeModel." |
| E-03 | Bedrock API timeout (30s+) | Retry up to 3 times with exponential backoff (1s, 2s, 4s). Then: "Bedrock API timed out after 3 retries." |
| E-04 | Slack tokens invalid/expired | Error on startup: "Slack authentication failed. Check SLACK_BOT_TOKEN and SLACK_APP_TOKEN." |
| E-05 | Slack Socket Mode disconnects | Auto-reconnect (handled by slack-bolt). Log warning. |
| E-06 | SQLite database locked | Retry with 100ms backoff, max 5 attempts. If still locked: "Session database is locked. Another Yui instance may be running." |
| E-07 | Kiro CLI not found in PATH | **Startup error**: "Kiro CLI not found at configured path. Yui requires Kiro CLI for coding tasks. Install it from https://kiro.dev/docs/cli/ or update tools.kiro.binary_path." **Exit code 1** |
| E-08 | Shell command in blocklist attempted | Return: "Command blocked by security policy." Log the attempt. |
| E-09 | File operation outside workspace_root | Return: "Access denied: path is outside configured workspace." |
| E-10 | config.yaml missing | Use defaults. Log: "No config.yaml found at ~/.yui/config.yaml, using defaults." |
| E-11 | AGENTS.md / SOUL.md missing | Agent runs with base system prompt only. Log info. |
| E-12 | Context window exceeded before compaction | Force compaction. If compaction itself fails (summary too large), archive current session to `~/.yui/sessions_archive/<session_id>.json`, start new session, send user: "Previous conversation was archived due to length. Starting fresh." |
| E-13 | MCP server connection failed | Log warning, continue without that MCP server's tools. User message: "MCP server [name] is unavailable. Some features may be limited." |
| E-14 | MCP server timeout | Retry once after 5s. If still fails, skip tool call with error message. |
| E-15 | Audio capture permission denied (ScreenCaptureKit) | User message: "Screen Recording permission required. Go to System Preferences → Privacy & Security → Screen Recording and enable Yui." |
| E-16 | Whisper model not found / download failed | User message: "Whisper model not available. Run `pip install yui-agent[meeting]` to install meeting dependencies." |
| E-17 | Audio device not found (no mic / no system audio) | User message: "No audio input detected. Check microphone and system audio settings." |
| E-18 | Meeting recording already active | User message: "A meeting is already being recorded. Use `yui meeting stop` first." |

---

## 14. Dependency Inventory

| Package | Version | Purpose | License |
|---|---|---|---|
| `strands-agents` | ≥0.1.0 | Core agent SDK (loop, model, tools) | Apache 2.0 |
| `strands-agents-tools` | ≥0.1.0 | Built-in tools (shell, file, slack, memory, browser) | Apache 2.0 |
| `bedrock-agentcore` | ≥0.1.0 | AgentCore Browser, Memory, Code Interpreter SDKs | Apache 2.0 |
| `boto3` | ≥1.35.0 | AWS SDK (Bedrock, S3, etc.) | Apache 2.0 |
| `slack-bolt` | ≥1.21.0 | Slack Socket Mode adapter | MIT |
| `slack-sdk` | ≥3.33.0 | Slack API client (transitive via slack-bolt) | MIT |
| `pyyaml` | ≥6.0 | YAML config parsing | MIT |
| `rich` | ≥13.0 | CLI formatted output | MIT |
| `mcp` | ≥1.0.0 | MCP protocol client (for MCP server integration) | MIT |

**Total: 9 direct dependencies** (vs OpenClaw's 54)

---

## 15. Open Questions

| # | Question | Impact | Status |
|---|---|---|---|
| Q-01 | ~~Should web search use Tavily or Bedrock Agent inline search?~~ | Phase 2 tool selection | **Resolved** — Default: Bedrock KB (VPC-internal). Tavily opt-in only. |
| Q-02 | AgentCore Browser Tool availability — is it GA in target AWS region? | Phase 2 feasibility | Open — must verify in Pre-Phase 0 SDK Verification Gate |
| Q-03 | Project name "Yui" — confirmed or placeholder? | README/branding | Open |
| Q-04 | Should Heartbeat results be posted to a Slack channel? | Phase 3 behavior | Open |
| Q-05 | ~~MCP tool consumption — should Yui support loading tools from MCP servers?~~ | Future extensibility | Deferred to Phase 4+ |
| Q-06 | AgentCore Code Interpreter availability — GA in target region? | Phase 2 feasibility | Open — must verify in Pre-Phase 0 SDK Verification Gate |
| Q-07 | AgentCore Memory — namespace isolation strategy for multi-user? | Phase 2+ | Open |

---

## 16. Glossary

| Term | Definition |
|---|---|
| Strands Agent SDK | AWS-official open-source Python SDK for building AI agents with Bedrock |
| Bedrock Converse API | AWS API for multi-turn LLM conversations with tool use support |
| Socket Mode | Slack connection method using WebSocket — no public URL needed |
| AgentCore | AWS Bedrock service providing managed browser, memory, and code interpreter |
| Kiro CLI | AWS IDE/CLI tool for agentic coding tasks |
| Compaction | Summarizing long conversation history to fit within model context window |
| HITL | Human-in-the-loop — requiring human approval before executing certain actions |
| Guardrails | Bedrock service that filters model inputs/outputs for safety and compliance |

---

## Changelog

| Date | Author | Change |
|---|---|---|
| 2026-02-25 | AYA | Initial draft — Discovery from OpenClaw source analysis + Strands SDK research |
| 2026-02-25 | AYA | v0.3.0 — Local/Cloud boundary redesign per han's directive + Kiro round 2 review. Section 4 fully rewritten with 3-tier model. |
| 2026-02-25 | AYA | v0.4.0 — han feedback incorporated: (①②③) AWS Bedrock features explicitly enumerated in Section 4.6. (④) Kiro CLI made required dependency with startup check; AGENTS.md ships with Kiro⇔Yui cross-review workflow. (⑤) Outlook tools replaced by aws-outlook-mcp corporate MCP server. (⑥) diagram/media tools replaced by MCP servers. New Section 4.4 for MCP integration. MCP config.yaml schema added. `mcp` package added as 9th dependency. E-13/E-14 error handling for MCP. AC-25a/b/c, AC-36/AC-37 added. |
| 2026-02-25 | AYA | v0.5.0 — HANA→Yui rename (per han's naming decision). New Section 9.5: Meeting Transcription & Automatic Minutes (Whisper + Bedrock). Discovery: Whisper local vs Amazon Transcribe comparison, mlx-whisper as default engine, ScreenCaptureKit for audio capture, hybrid local/cloud architecture (audio local, LLM cloud). New tools: meeting_recorder, whisper_transcribe. CLI: yui meeting start/stop/status/list/search. Auto-minutes with Bedrock (summary, action items, decisions). Real-time analysis during meetings. Optional deps via pyproject.toml extras [meeting]. AC-40–51, E-15–18 added. |
