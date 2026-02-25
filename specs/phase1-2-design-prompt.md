# Phase 1+2 Design & Implementation Spec — 結（Yui）

## Overview

Implement Phase 1 (Slack + Sessions) and Phase 2 (Kiro + Git + AgentCore) for the Yui agent.

Phase 0 is already merged (`src/yui/` with config, agent, cli, safe_shell, 38 passing tests).

## Phase 1 Scope (AC-09 ~ AC-14)

### 1. Slack Socket Mode Adapter (`src/yui/slack_adapter.py`)

Create a Slack adapter using `slack-bolt` in Socket Mode:

- **Tokens**: Load `SLACK_BOT_TOKEN` (xoxb-) and `SLACK_APP_TOKEN` (xapp-) from:
  1. Environment variables
  2. `~/.yui/.env` file
  3. `config.yaml` (fallback)
- **Events to handle**:
  - `app_mention`: Respond in thread to @Yui mentions
  - `message` (DM): Respond directly to DMs
- **Response flow**:
  1. Receive event
  2. Add 👀 reaction (acknowledged)
  3. Look up or create session (by channel+user or DM)
  4. Pass message to Strands Agent
  5. Post response in thread (mentions) or as reply (DM)
  6. Add ✅ reaction when done
- **Error handling**: Post error message to user on failure; log full traceback
- **Entry point**: `run_slack()` function that starts the Socket Mode handler

### 2. SQLite Session Manager (`src/yui/session.py`)

Persistent conversation storage:

- **Database**: `~/.yui/sessions.db` (SQLite with WAL mode)
- **Schema**:
  ```sql
  CREATE TABLE sessions (
    session_id TEXT PRIMARY KEY,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    metadata TEXT  -- JSON: channel, user, etc.
  );
  CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(session_id),
    role TEXT NOT NULL,  -- 'user', 'assistant', 'system', 'tool_use', 'tool_result'
    content TEXT NOT NULL,  -- JSON-encoded message content
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
  );
  ```
- **Session ID format**: `slack:{channel_id}:{user_id}` or `cli:{uuid}`
- **API**:
  - `get_or_create_session(session_id, metadata)` → Session
  - `add_message(session_id, role, content)` → None
  - `get_messages(session_id, limit=None)` → list[Message]
  - `compact_session(session_id)` → None (summarize old messages)
- **Compaction** (AC-13, AC-14):
  - Trigger when message count exceeds threshold (configurable, default 50)
  - Summarize old messages into a single system message using the agent
  - Keep recent N messages (configurable, default 5)
  - Summary preserves key context, decisions, and ongoing topics

### 3. Config additions

```yaml
slack:
  bot_token: ${SLACK_BOT_TOKEN}  # or direct value
  app_token: ${SLACK_APP_TOKEN}
  
runtime:
  session:
    db_path: ~/.yui/sessions.db
    compaction_threshold: 50  # messages before compaction
    keep_recent_messages: 5
```

### 4. CLI update

- `python -m yui` → CLI REPL (existing)
- `python -m yui --slack` or `python -m yui slack` → Start Slack adapter

## Phase 2 Scope (AC-15 ~ AC-19a)

### 5. Kiro CLI Delegate Tool (`src/yui/tools/kiro_delegate.py`)

```python
@tool
def kiro_delegate(task: str, working_directory: str = ".") -> str:
    """Delegate a coding task to Kiro CLI."""
```

- Invoke: `~/.local/bin/kiro-cli chat --no-interactive --trust-all-tools "<task>"`
- Working directory from parameter
- Timeout: configurable (default 300s), graceful error on timeout (AC-19)
- ANSI color code stripping from output (`re.sub(r'\x1b\[[0-9;]*m', '', output)`)
- Startup check: verify kiro-cli exists (AC-19a), clear error if missing
- Retry logic: 1 retry on connection timeout

### 6. Git Tool (`src/yui/tools/git_tool.py`)

```python
@tool
def git_tool(subcommand: str, args: str = "", working_directory: str = ".") -> str:
    """Execute git operations safely."""
```

- Allowed subcommands: `status`, `add`, `commit`, `push`, `log`, `diff`, `branch`, `checkout`, `pull`, `fetch`, `stash`
- Blocked: `push --force`, `push -f`, `reset --hard`, `clean -f`
- Timeout: 30s

### 7. AgentCore Tools (`src/yui/tools/agentcore.py`)

Three tools wrapping Bedrock AgentCore:

#### 7a. AgentCore Browser
```python
@tool
def web_browse(url: str, task: str = "extract content") -> str:
    """Browse a web page using AgentCore Browser."""
```
- Uses `bedrock-agentcore` SDK
- Creates browser session → navigates → extracts → closes
- Handles: timeouts, page load errors, content extraction failures

#### 7b. AgentCore Memory
```python
@tool  
def memory_store(key: str, value: str, category: str = "general") -> str:
    """Store a fact in long-term memory."""

@tool
def memory_recall(query: str, limit: int = 5) -> str:
    """Recall facts from long-term memory."""
```

#### 7c. AgentCore Code Interpreter
```python
@tool
def code_execute(code: str, language: str = "python") -> str:
    """Execute code in a sandboxed environment."""
```

### 8. Tool Registration Update

Update `agent.py` to conditionally register tools based on config and availability:
- Kiro CLI: only if binary exists at configured path
- AgentCore tools: only if `bedrock-agentcore` is installed and credentials available
- Git tool: always (uses system git)

## Testing Requirements

### Phase 1 Tests
- `test_slack_adapter.py`: Token loading, event handling (mocked), reaction flow
- `test_session.py`: CRUD operations, compaction logic, WAL mode verification

### Phase 2 Tests
- `test_kiro_delegate.py`: Subprocess mock, ANSI stripping, timeout, missing binary
- `test_git_tool.py`: Allowed/blocked subcommands, working directory
- `test_agentcore.py`: Mock AgentCore SDK calls (Browser, Memory, Code Interpreter)

## Files to Create/Modify

### New Files
- `src/yui/slack_adapter.py`
- `src/yui/session.py`
- `src/yui/tools/kiro_delegate.py`
- `src/yui/tools/git_tool.py`
- `src/yui/tools/agentcore.py`
- `docs/slack-setup-guide.md` (already created)
- `tests/test_slack_adapter.py`
- `tests/test_session.py`
- `tests/test_kiro_delegate.py`
- `tests/test_git_tool.py`
- `tests/test_agentcore.py`

### Modified Files
- `src/yui/config.py` — Add slack + session DB config
- `src/yui/agent.py` — Conditional tool registration
- `src/yui/cli.py` — Add `--slack` flag
- `src/yui/__main__.py` — Route to CLI or Slack
- `pyproject.toml` — Ensure all deps listed

## Important SDK Notes (from Phase 0 learnings)

1. **strands_tools module-level import**: `file_read` and `file_write` use `TOOL_SPEC` pattern — pass module, not function
2. **`@tool` decorated functions**: Use `DecoratedFunctionTool` — callable directly with kwargs
3. **ANSI codes in Kiro output**: Always strip with regex
4. **BedrockModel constructor**: `BedrockModel(model_id=..., region_name=..., max_tokens=...)`
