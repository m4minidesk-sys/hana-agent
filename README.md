# HANA — Helpful Autonomous Networked Agent

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![AWS](https://img.shields.io/badge/AWS-Bedrock-orange.svg)](https://aws.amazon.com/bedrock/)

**Lightweight, secure, AWS-optimized AI agent orchestrator** — an OpenClaw alternative built on the Strands Agent SDK.

## Features

- 🧠 **Strands Agent SDK** — Modern agent framework with built-in tool orchestration
- ☁️ **AWS-Native** — Bedrock Converse API, AgentCore Browser/Memory, Guardrails
- 🛠️ **Rich Tool Suite** — exec, file ops, git, Kiro delegation, Outlook (AppleScript), Slack
- 💬 **Multi-Channel** — CLI REPL + Slack Socket Mode
- 💾 **Persistent Sessions** — SQLite local + S3 sync
- 🔒 **Security First** — Command allowlists, Bedrock Guardrails, scoped file access
- 🍎 **macOS-Optimized** — Designed for Mac (arm64) with launchd daemon
- ⏰ **Heartbeat** — Periodic autonomous actions with configurable schedules
- 😈 **Daemon Mode** — launchd background service

## Architecture

```
LOCAL TIER (macOS)                    CLOUD TIER (AWS)
┌────────────────────────────┐    ┌─────────────────────────────┐
│  Strands Agent (Core)      │←──→│  Bedrock Converse API       │
│  ├── Local Tools           │    │  ├── Claude / Nova models   │
│  │   ├── exec              │    │  └── Bedrock Guardrails     │
│  │   ├── file ops          │    │                             │
│  │   ├── git               │    │  AgentCore Services         │
│  │   ├── kiro delegate     │    │  ├── Browser Tool           │
│  │   └── outlook           │    │  ├── Memory                 │
│  │                         │    │  └── Web Search             │
│  ├── Channels              │    │                             │
│  │   ├── CLI REPL          │    │  Storage & Logging          │
│  │   └── Slack             │    │  ├── S3 (session sync)      │
│  │                         │    │  └── CloudWatch Logs        │
│  └── Runtime               │    └─────────────────────────────┘
│      ├── Session (SQLite)  │
│      ├── Config Loader     │
│      ├── Heartbeat         │
│      └── Daemon            │
└────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.12+
- AWS credentials configured (`~/.aws/credentials` or environment variables)
- Bedrock model access enabled in your AWS account

### Installation

```bash
# Clone
git clone https://github.com/m4minidesk-sys/hana-agent.git
cd hana-agent

# Install
pip install -e .

# Copy config
cp config.yaml.example ~/.hana/config.yaml
cp .env.example .env

# Run
python -m hana
```

### Usage

```bash
# Interactive REPL
python -m hana

# Single command
python -m hana --prompt "List files in the current directory"

# With custom config
python -m hana --config /path/to/config.yaml

# Slack mode
python -m hana --channel slack

# Daemon mode
python -m hana --daemon
```

## Configuration

Edit `~/.hana/config.yaml`:

```yaml
agent:
  model_id: "us.anthropic.claude-sonnet-4-20250514"
  region: "us-east-1"

workspace:
  root: "~/.hana/workspace"
```

See [config.yaml.example](config.yaml.example) for full options.

## Workspace

HANA uses markdown files for agent behavior and personality:

- **AGENTS.md** — Agent behavior rules and conventions
- **SOUL.md** — Agent personality and tone

Place these in your workspace directory (`~/.hana/workspace/` by default).

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .

# Type check
mypy hana/
```

## Phase Roadmap

| Phase | Scope | Timeline |
|---|---|---|
| **Phase 0** ✅ | CLI + Bedrock + exec/file tools | 3 days |
| **Phase 1** ✅ | Slack + Session management | 1 week |
| **Phase 2** ✅ | Kiro/git/AgentCore Browser/Memory | 1 week |
| **Phase 3** ✅ | Guardrails + Heartbeat + Daemon (launchd) | 1 week |

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

- [Strands Agent SDK](https://github.com/strands-agents/sdk-python) — The agent framework
- [Amazon Bedrock](https://aws.amazon.com/bedrock/) — LLM backbone
- [OpenClaw](https://github.com/nichochar/openclaw) — Inspiration and reference architecture
