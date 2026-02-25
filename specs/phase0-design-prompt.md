# Phase 0 Design & Implementation — Kiro CLI Delegation

## Context
You are implementing Phase 0 of 結(Yui) — a lightweight AI agent built on Strands Agent SDK + AWS Bedrock.
Requirements are in `requirements.md` (v0.10.0). Focus ONLY on Phase 0 scope.

## SDK Verification Results (CONFIRMED WORKING)
- `strands-agents` v1.27.0, `strands-agents-tools` v0.2.21
- `from strands import Agent, tool` ✅
- `from strands.models.bedrock import BedrockModel` ✅
- `BedrockModel(model_id=..., region_name=..., max_tokens=...)` ✅
- `Agent(model=model, system_prompt=..., tools=[...])` ✅
- `agent('message')` returns response text ✅
- BedrockConfig supports: `guardrail_id`, `guardrail_version`, `guardrail_latest_message`, `temperature`, `top_p`, `stop_sequences`, `streaming`
- Shell tool signature: `shell(command, parallel, ignore_errors, timeout, work_dir, non_interactive)`
- Shell tool does NOT have built-in allowlist/blocklist — we must implement our own wrapper
- `@tool` decorator produces `DecoratedFunctionTool` — subprocess works inside @tool
- GraphBuilder has: `add_node`, `add_edge(condition=Callable)`, `build`, `set_max_node_executions`, `set_execution_timeout` (verified but NOT needed for Phase 0)

## Phase 0 Scope (AC-01 through AC-08)
- AC-01: `python -m yui` starts a CLI REPL that accepts user input
- AC-02: User message sent to Bedrock via Strands Agent SDK, response displayed
- AC-03: Agent can execute shell commands via `shell` tool with allowlist enforcement
- AC-04: Agent can read, write, and edit files via strands-agents-tools
- AC-05: System prompt includes content from AGENTS.md and SOUL.md
- AC-06: `config.yaml` is loaded and validated on startup
- AC-07: Invalid config produces a clear error message and exits
- AC-08: CLI supports readline history (up arrow recalls previous input)

## Project Structure to Create
```
yui-agent/
├── src/
│   └── yui/
│       ├── __init__.py           # Package init, version
│       ├── __main__.py           # Entry point: python -m yui
│       ├── agent.py              # Agent setup (Strands Agent + BedrockModel)
│       ├── cli.py                # CLI REPL with readline
│       ├── config.py             # Config loading + validation
│       └── tools/
│           ├── __init__.py
│           └── safe_shell.py     # Shell wrapper with allowlist/blocklist
├── workspace/
│   ├── AGENTS.md                 # Default system prompt
│   └── SOUL.md                   # Default persona
├── config.yaml.example           # Example config
├── pyproject.toml                # Updated with dependencies + entry points
├── tests/
│   ├── test_config.py
│   ├── test_agent.py
│   └── test_safe_shell.py
└── requirements.md               # (existing)
```

## Key Design Decisions (from requirements.md)
1. **Config**: `~/.yui/config.yaml` + `~/.yui/.env` for secrets
2. **System Prompt**: Read AGENTS.md + SOUL.md from `~/.yui/workspace/`, inject as system_prompt
3. **Shell Security**: Custom `safe_shell` tool wrapping strands shell with allowlist + blocklist
4. **File Security**: Restrict file_read/file_write/editor to `tools.file.workspace_root`
5. **Model**: BedrockModel with configurable model_id, region, max_tokens
6. **CLI**: readline-based REPL with Ctrl+C graceful exit, Ctrl+D for EOF
7. **No Slack, no sessions, no heartbeat** — those are Phase 1+

## Config Schema (from requirements.md Section 7.2)
```yaml
model:
  provider: bedrock
  model_id: us.anthropic.claude-sonnet-4-20250514-v1:0
  region: us-east-1
  max_tokens: 4096

tools:
  shell:
    allowlist: ["ls", "cat", "grep", "find", "python3", "kiro-cli", "brew"]
    blocklist: ["rm -rf /", "sudo", "curl | bash", "eval", "git push --force", "git reset --hard", "git clean -f"]
    timeout_seconds: 30
  file:
    workspace_root: "~/workspace"
  kiro:
    binary_path: "~/.local/bin/kiro-cli"
    timeout_seconds: 300

runtime:
  session:
    compaction_threshold: 0.8
    keep_recent_messages: 5
```

## Error Handling (Phase 0 relevant)
- E-01: AWS credentials not configured → clear error, exit 1
- E-02: Bedrock permission denied → IAM error
- E-03: Bedrock timeout → 3 retries with exponential backoff
- E-07: Kiro CLI not found → graceful error with install instructions
- E-08: Shell blocklisted command → "blocked by security policy"
- E-09: File operation outside workspace → "access denied"
- E-10: config.yaml missing → use defaults, log info

## Instructions for Kiro
1. Create `specs/design.md` with detailed module design
2. Create `specs/tasks.md` with ordered implementation tasks
3. Implement all modules per the design
4. Run tests
5. Ensure all AC-01 through AC-08 pass
