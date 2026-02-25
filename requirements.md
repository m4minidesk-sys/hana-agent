# HANA — Requirements Specification

> **Version:** 1.0.0  
> **Last Updated:** 2026-02-25  
> **Author:** AYA (AI Secretary) on behalf of han  
> **Status:** Approved for Implementation  
> **Quality Gate:** fullspec (85-min standard)

---

## 1. Executive Summary

HANA (Helpful Autonomous Networked Agent) is a lightweight, secure, AWS-optimized AI agent orchestrator designed as an alternative to OpenClaw. It leverages the **Strands Agent SDK** with **Amazon Bedrock Converse API** as its LLM backbone, providing a clean separation between local tools (exec, file ops, git, Kiro delegation, Outlook) and cloud tools (AgentCore Browser, Memory, Guardrails).

### Key Differentiators from OpenClaw
- **Lighter footprint**: Python-only, no Node.js dependency
- **AWS-native**: Built on Bedrock + AgentCore, no third-party LLM API keys needed
- **macOS-focused**: Optimized for Mac (arm64) with launchd daemon
- **Strands SDK**: Modern agent framework with built-in tool orchestration
- **No mwinit dependency**: Uses standard AWS CLI authentication chain

---

## 2. Project Overview

| Attribute | Value |
|---|---|
| **Project Name** | HANA (Helpful Autonomous Networked Agent) |
| **Language** | Python 3.12+ |
| **Target Platforms** | macOS (arm64/x86_64) |
| **Agent Framework** | Strands Agent SDK (`strands-agents`, `strands-agents-tools`) |
| **LLM Provider** | Amazon Bedrock Converse API |
| **Default Model** | `us.anthropic.claude-sonnet-4-20250514` (configurable) |
| **Authentication** | Standard AWS CLI credential chain (boto3) |
| **Channels** | CLI REPL, Slack (Socket Mode) |
| **Session Storage** | SQLite (local) + S3 (sync) |
| **Configuration** | YAML + Markdown (AGENTS.md / SOUL.md) |

---

## 3. Architecture

```
LOCAL TIER (macOS)                    CLOUD TIER (AWS)
┌────────────────────────────┐    ┌─────────────────────────────┐
│  Strands Agent (Core)      │←──→│  Bedrock Converse API       │
│  ├── Local Tools           │    │  ├── Claude / Nova models   │
│  │   ├── exec              │    │  └── Bedrock Guardrails     │
│  │   ├── read_file         │    │                             │
│  │   ├── write_file        │    │  AgentCore Services         │
│  │   ├── edit_file         │    │  ├── Browser Tool (Nova Act)│
│  │   ├── kiro_delegate     │    │  ├── Memory (search/store)  │
│  │   ├── outlook_calendar  │    │  └── Web Search             │
│  │   ├── outlook_mail      │    │                             │
│  │   └── git               │    │  Storage & Logging          │
│  │                         │    │  ├── S3 (session sync)      │
│  ├── Channels              │    │  └── CloudWatch Logs        │
│  │   ├── CLI REPL          │    └─────────────────────────────┘
│  │   └── Slack Socket Mode │
│  │                         │
│  ├── Runtime               │
│  │   ├── Session (SQLite)  │
│  │   ├── Config Loader     │
│  │   ├── Heartbeat         │
│  │   └── Daemon            │
│  │                         │
│  └── Workspace             │
│      ├── AGENTS.md         │
│      └── SOUL.md           │
└────────────────────────────┘
```

### 3.1 Data Flow

1. **User Input** → Channel Adapter (CLI or Slack) → Agent Core
2. **Agent Core** → Strands Agent SDK → Bedrock Converse API
3. **LLM Response** → Tool invocations (local or cloud) → Results back to LLM
4. **Final Response** → Channel Adapter → User
5. **Session Data** → SQLite (local) → S3 (async sync)

### 3.2 Authentication Flow

```
boto3 credential chain:
  1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
  2. AWS config files (~/.aws/credentials, ~/.aws/config)
  3. IAM Instance Profile (EC2/ECS)
  4. SSO cache (~/.aws/sso/cache/*)
```

**Note:** mwinit authentication caching is explicitly excluded from this design. The user is responsible for maintaining valid AWS credentials through standard mechanisms.

---

## 4. Tool Specifications

### 4.1 Local Tools

#### 4.1.1 `exec` — Shell Command Execution
- **Purpose:** Execute shell commands on the local machine
- **Security:** Command allowlist/blocklist in config.yaml
- **Parameters:**
  - `command: str` — Shell command to execute
  - `timeout: int = 30` — Execution timeout in seconds
  - `workdir: str | None` — Working directory
- **Returns:** `{"stdout": str, "stderr": str, "returncode": int}`
- **Platform:** Uses `subprocess.run()` with shell=True
- **Guardrails:** 
  - Blocked commands: `rm -rf /`, `shutdown`, etc.
  - Configurable allowlist in `config.yaml`
  - Max output size: 100KB (configurable)

#### 4.1.2 `read_file` — File Read
- **Purpose:** Read file contents (text or binary detection)
- **Parameters:**
  - `file_path: str` — Path to file (relative to workspace or absolute)
  - `offset: int = 0` — Line offset (0-indexed)
  - `limit: int | None` — Max lines to read
- **Returns:** `{"content": str, "lines": int, "truncated": bool}`
- **Limits:** Max 50KB or 2000 lines per read

#### 4.1.3 `write_file` — File Write
- **Purpose:** Create or overwrite files
- **Parameters:**
  - `file_path: str` — Path to file
  - `content: str` — Content to write
  - `create_dirs: bool = True` — Auto-create parent directories
- **Returns:** `{"path": str, "bytes_written": int}`

#### 4.1.4 `edit_file` — Surgical File Edit
- **Purpose:** Replace exact text in a file
- **Parameters:**
  - `file_path: str` — Path to file
  - `old_text: str` — Exact text to find
  - `new_text: str` — Replacement text
- **Returns:** `{"path": str, "replacements": int}`

#### 4.1.5 `kiro_delegate` — Kiro CLI Delegation
- **Purpose:** Delegate coding tasks to Kiro CLI agent
- **Parameters:**
  - `instruction: str` — Task instruction for Kiro
  - `project_dir: str` — Project directory to work in
  - `timeout: int = 120` — Max execution time
- **Returns:** `{"output": str, "exit_code": int}`
- **Implementation:** Calls `~/.local/bin/kiro-cli chat --no-interactive --trust-all-tools "<instruction>"`

#### 4.1.6 `outlook_calendar` — Outlook Calendar
- **Purpose:** Read/create calendar events
- **Parameters:**
  - `action: str` — "list" | "create" | "search"
  - `start_date: str | None` — ISO date
  - `end_date: str | None` — ISO date
  - `title: str | None` — Event title (for create)
  - `body: str | None` — Event body (for create)
- **Platform:**
  - macOS: AppleScript via `osascript`

#### 4.1.7 `outlook_mail` — Outlook Mail
- **Purpose:** Read/send/search emails
- **Parameters:**
  - `action: str` — "list" | "read" | "send" | "search"
  - `folder: str = "Inbox"` — Mail folder
  - `limit: int = 10` — Max results
  - `to: str | None` — Recipient (for send)
  - `subject: str | None` — Subject (for send)
  - `body: str | None` — Body (for send)
- **Platform:** macOS: AppleScript via `osascript`

#### 4.1.8 `git` — Git Operations
- **Purpose:** Execute git commands
- **Parameters:**
  - `command: str` — Git subcommand and arguments
  - `repo_dir: str | None` — Repository directory
- **Returns:** `{"stdout": str, "stderr": str, "returncode": int}`
- **Allowed:** status, log, diff, add, commit, push, pull, branch, checkout, stash, tag

### 4.2 Cloud Tools

#### 4.2.1 `llm_converse` — Bedrock Converse API
- **Purpose:** Direct LLM conversation (for sub-agent or multi-model scenarios)
- **Parameters:**
  - `messages: list[dict]` — Conversation messages
  - `model_id: str | None` — Override model
  - `system_prompt: str | None` — System prompt
  - `max_tokens: int = 4096`
  - `temperature: float = 0.7`
- **Returns:** `{"response": str, "usage": dict}`

#### 4.2.2 `web_browse` — AgentCore Browser Tool
- **Purpose:** Browse web pages using Nova Act (AgentCore)
- **Parameters:**
  - `url: str` — URL to browse
  - `action: str | None` — Action to perform on page
  - `extract: str | None` — Data extraction instruction
- **Returns:** `{"content": str, "screenshot": str | None}`
- **Dependency:** `agentcore-tools[browser]`

#### 4.2.3 `web_search` — Web Search
- **Purpose:** Search the web
- **Parameters:**
  - `query: str` — Search query
  - `count: int = 5` — Number of results
- **Returns:** `{"results": list[{"title": str, "url": str, "snippet": str}]}`

#### 4.2.4 `memory_search` — AgentCore Memory Search
- **Purpose:** Search stored memories
- **Parameters:**
  - `query: str` — Search query
  - `limit: int = 5`
  - `namespace: str = "default"`
- **Returns:** `{"results": list[{"content": str, "score": float, "metadata": dict}]}`

#### 4.2.5 `memory_store` — AgentCore Memory Store
- **Purpose:** Store information in long-term memory
- **Parameters:**
  - `content: str` — Content to store
  - `metadata: dict | None` — Optional metadata
  - `namespace: str = "default"`
- **Returns:** `{"id": str, "stored": bool}`

### 4.3 Hybrid Tools

#### 4.3.1 `message_slack` — Slack Messaging
- **Purpose:** Send/read Slack messages
- **Parameters:**
  - `action: str` — "send" | "read" | "react" | "thread"
  - `channel: str` — Channel ID or name
  - `text: str | None` — Message text
  - `thread_ts: str | None` — Thread timestamp
- **Implementation:** Slack SDK with Socket Mode for receiving, Web API for sending

#### 4.3.2 `session_manage` — Session Management
- **Purpose:** Manage conversation sessions
- **Parameters:**
  - `action: str` — "create" | "load" | "save" | "list" | "delete" | "sync"
  - `session_id: str | None`
- **Storage:** SQLite locally, S3 sync for backup/cross-device

#### 4.3.3 `cron_schedule` — Scheduled Tasks
- **Purpose:** Schedule recurring tasks
- **Parameters:**
  - `action: str` — "add" | "remove" | "list"
  - `schedule: str` — Cron expression
  - `task: str` — Task description
- **Platform:**
  - macOS: launchd plist generation

---

## 5. Configuration

### 5.1 config.yaml

```yaml
agent:
  model_id: "us.anthropic.claude-sonnet-4-20250514"
  max_tokens: 4096
  temperature: 0.7
  region: "us-east-1"

workspace:
  root: "~/.hana/workspace"
  agents_md: "AGENTS.md"
  soul_md: "SOUL.md"

tools:
  exec:
    enabled: true
    allowlist:
      - "ls"
      - "cat"
      - "grep"
      - "find"
      - "git"
      - "python"
      - "pip"
    blocklist:
      - "rm -rf /"
      - "format"
      - "shutdown"
    timeout: 30
    max_output: 102400

  file:
    enabled: true
    max_read_size: 51200
    max_read_lines: 2000

  kiro:
    enabled: true
    binary: "~/.local/bin/kiro-cli"
    timeout: 120

  outlook:
    enabled: false  # Enable when configured
    # macOS only — uses AppleScript via osascript

  git:
    enabled: true
    allowed_commands:
      - "status"
      - "log"
      - "diff"
      - "add"
      - "commit"
      - "push"
      - "pull"
      - "branch"
      - "checkout"

channels:
  cli:
    enabled: true
    prompt: "hana> "
    history_file: "~/.hana/history"

  slack:
    enabled: false
    app_token: "${SLACK_APP_TOKEN}"
    bot_token: "${SLACK_BOT_TOKEN}"
    default_channel: ""

session:
  backend: "sqlite"
  db_path: "~/.hana/sessions.db"
  s3_sync:
    enabled: false
    bucket: ""
    prefix: "hana/sessions/"

heartbeat:
  enabled: false
  interval_minutes: 30
  tasks: []

logging:
  level: "INFO"
  file: "~/.hana/logs/hana.log"
  cloudwatch:
    enabled: false
    log_group: "/hana/agent"
    region: "us-east-1"

guardrails:
  enabled: false
  guardrail_id: ""
  guardrail_version: "DRAFT"
```

### 5.2 Environment Variables (.env)

```
AWS_REGION=us-east-1
AWS_PROFILE=default
HANA_CONFIG=~/.hana/config.yaml
HANA_WORKSPACE=~/.hana/workspace
SLACK_APP_TOKEN=xapp-...
SLACK_BOT_TOKEN=xoxb-...
```

---

## 6. Phase Plan

### Phase 0: CLI + Bedrock + Core Tools (3 days)
**Goal:** Minimal viable agent that can chat and manipulate files

| Deliverable | Description | Priority |
|---|---|---|
| `hana/main.py` | CLI entry point with argument parsing | P0 |
| `hana/agent_core.py` | Strands Agent + BedrockModel initialization | P0 |
| `hana/local_tools/exec_tool.py` | Shell command execution with allowlist | P0 |
| `hana/local_tools/file_ops.py` | read_file, write_file, edit_file | P0 |
| `hana/runtime/config_loader.py` | YAML + AGENTS.md/SOUL.md loading | P0 |
| `hana/channels/cli_adapter.py` | Terminal REPL with history | P0 |
| `hana/auth/aws_credentials.py` | AWS credential validation | P0 |

**Acceptance Criteria:**
- `python -m hana` starts a REPL
- Agent responds to natural language queries
- Agent can execute allowed shell commands
- Agent can read, write, and edit files
- Config is loaded from YAML

### Phase 1: Slack + Session Management (1 week)
**Goal:** Multi-channel agent with persistent sessions

| Deliverable | Description | Priority |
|---|---|---|
| `hana/channels/slack_adapter.py` | Slack Socket Mode integration | P1 |
| `hana/runtime/session.py` | SQLite session CRUD + S3 sync | P1 |

**Acceptance Criteria:**
- Agent responds to Slack messages in configured channels
- Conversation history persists across restarts
- Sessions can be synced to S3

### Phase 2: Advanced Tools (1 week)
**Goal:** Full tool suite including delegation and cloud services

| Deliverable | Description | Priority |
|---|---|---|
| `hana/local_tools/kiro.py` | Kiro CLI delegation | P2 |
| `hana/local_tools/git_tool.py` | Git operations | P2 |
| `hana/cloud_tools/browser.py` | AgentCore Browser Tool | P2 |
| `hana/cloud_tools/memory.py` | AgentCore Memory | P2 |
| `hana/cloud_tools/search.py` | Web search | P2 |

**Acceptance Criteria:**
- Agent can delegate coding tasks to Kiro
- Agent can perform git operations
- Agent can browse web pages via AgentCore
- Agent can store and retrieve memories

### Phase 3: Production Hardening (1 week)
**Goal:** Production-ready with guardrails, daemon mode, and heartbeat

| Deliverable | Description | Priority |
|---|---|---|
| Guardrails integration | Bedrock Guardrails for input/output filtering | P3 |
| `hana/runtime/heartbeat.py` | Periodic autonomous actions | P3 |
| `hana/runtime/daemon.py` | Daemon mode (launchd on macOS) | P3 |
| `hana/local_tools/outlook.py` | Outlook calendar + mail (AppleScript) | P3 |

**Acceptance Criteria:**
- Guardrails filter harmful content
- Heartbeat runs scheduled tasks
- Daemon mode runs in background via launchd
- Outlook integration works via AppleScript on macOS

---

## 7. Non-Functional Requirements

### 7.1 Performance
- Agent response latency: < 2s for tool-less responses (excluding LLM time)
- Tool execution: < 30s default timeout (configurable)
- Session load time: < 100ms for SQLite
- Memory footprint: < 200MB resident

### 7.2 Security
- No secrets in code or logs
- AWS credentials via standard chain only (no hardcoding)
- Command execution allowlist enforced
- File operations scoped to workspace (configurable)
- Guardrails for LLM input/output (Phase 3)
- No mwinit dependency

### 7.3 Reliability
- Graceful degradation when AWS services unavailable
- Session auto-save on crash
- Heartbeat with configurable retry
- Daemon auto-restart via launchd

### 7.4 Observability
- Structured logging (JSON format option)
- CloudWatch Logs integration (optional)
- Health check endpoint for daemon mode
- Session statistics

### 7.5 Compatibility
- Python 3.12+
- macOS 13+ (arm64, x86_64)
- AWS SDK (boto3) latest stable

---

## 8. Dependencies

### Core
- `strands-agents>=0.1.0` — Agent SDK
- `strands-agents-tools>=0.1.0` — Built-in tools
- `boto3>=1.35.0` — AWS SDK
- `pyyaml>=6.0` — YAML config parsing
- `rich>=13.0` — Terminal UI

### Phase 1
- `slack-sdk>=3.30.0` — Slack integration
- `slack-bolt>=1.20.0` — Slack Socket Mode

### Phase 2
- (AgentCore tools via strands-agents-tools)

### Phase 3
- (No additional dependencies — Guardrails/Heartbeat/Daemon use built-in libraries + boto3)

### Development
- `pytest>=8.0`
- `pytest-asyncio>=0.24`
- `ruff>=0.8`
- `mypy>=1.13`

---

## 9. Glossary

| Term | Definition |
|---|---|
| **HANA** | Helpful Autonomous Networked Agent |
| **Strands Agent SDK** | AWS agent framework for building AI agents |
| **Bedrock Converse API** | AWS API for LLM conversation |
| **AgentCore** | AWS managed service for agent tools (browser, memory) |
| **Socket Mode** | Slack connection mode using WebSocket (no public URL needed) |
| **mwinit** | Amazon internal authentication tool (excluded from this design) |
| **Kiro** | AI coding assistant CLI tool |
| **AGENTS.md** | Agent behavior configuration file |
| **SOUL.md** | Agent personality/persona configuration file |
