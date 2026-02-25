"""HANA config loader — YAML config + AGENTS.md / SOUL.md loading."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

DEFAULT_CONFIG: dict[str, Any] = {
    "agent": {
        "model_id": "us.anthropic.claude-sonnet-4-20250514",
        "max_tokens": 4096,
        "temperature": 0.7,
        "region": "us-east-1",
    },
    "workspace": {
        "root": "~/.hana/workspace",
        "agents_md": "AGENTS.md",
        "soul_md": "SOUL.md",
    },
    "tools": {
        "exec": {
            "enabled": True,
            "allowlist": [
                "ls", "cat", "grep", "find", "git", "python", "pip",
                "head", "tail", "wc", "echo", "pwd", "which", "env", "date",
            ],
            "blocklist": [
                "rm -rf /", "rm -rf ~", "shutdown", "reboot", "mkfs",
            ],
            "timeout": 30,
            "max_output": 102400,
        },
        "file": {
            "enabled": True,
            "max_read_size": 51200,
            "max_read_lines": 2000,
        },
        "kiro": {
            "enabled": True,
            "binary": "~/.local/bin/kiro-cli",
            "timeout": 120,
        },
        "outlook": {
            "enabled": False,
        },
        "git": {
            "enabled": True,
            "allowed_commands": [
                "status", "log", "diff", "add", "commit", "push",
                "pull", "branch", "checkout", "stash", "tag", "remote", "fetch",
            ],
        },
    },
    "channels": {
        "cli": {
            "enabled": True,
            "prompt": "hana> ",
            "history_file": "~/.hana/history",
        },
        "slack": {
            "enabled": False,
            "app_token": "",
            "bot_token": "",
            "default_channel": "",
        },
    },
    "session": {
        "backend": "sqlite",
        "db_path": "~/.hana/sessions.db",
        "s3_sync": {
            "enabled": False,
            "bucket": "",
            "prefix": "hana/sessions/",
        },
    },
    "heartbeat": {
        "enabled": False,
        "interval_minutes": 30,
        "tasks": [],
    },
    "logging": {
        "level": "INFO",
        "file": "~/.hana/logs/hana.log",
        "cloudwatch": {
            "enabled": False,
            "log_group": "/hana/agent",
            "region": "us-east-1",
        },
    },
    "guardrails": {
        "enabled": False,
        "guardrail_id": "",
        "guardrail_version": "DRAFT",
    },
}


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base*, returning a new dict.

    Args:
        base: Base dictionary (not mutated).
        override: Values to overlay on top of base.

    Returns:
        Merged dictionary.
    """
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _expand_paths(config: dict) -> dict:
    """Expand ``~`` in path-like string values throughout the config.

    Args:
        config: Configuration dictionary.

    Returns:
        Config with paths expanded.
    """
    expanded: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            expanded[key] = _expand_paths(value)
        elif isinstance(value, str) and "~" in value:
            expanded[key] = str(Path(value).expanduser())
        else:
            expanded[key] = value
    return expanded


def _resolve_env_vars(config: dict) -> dict:
    """Replace ``${VAR}`` placeholders with environment variable values.

    Args:
        config: Configuration dictionary.

    Returns:
        Config with env vars resolved.
    """
    resolved: dict[str, Any] = {}
    for key, value in config.items():
        if isinstance(value, dict):
            resolved[key] = _resolve_env_vars(value)
        elif isinstance(value, str) and value.startswith("${") and value.endswith("}"):
            env_var = value[2:-1]
            resolved[key] = os.environ.get(env_var, "")
        else:
            resolved[key] = value
    return resolved


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load HANA configuration from a YAML file merged with defaults.

    Args:
        config_path: Path to config.yaml.  If ``None``, uses defaults only.

    Returns:
        Fully resolved configuration dictionary.
    """
    config = dict(DEFAULT_CONFIG)

    if config_path:
        path = Path(config_path).expanduser()
        if path.exists():
            logger.info("Loading config from %s", path)
            with open(path) as f:
                user_config = yaml.safe_load(f) or {}
            config = _deep_merge(config, user_config)
        else:
            logger.warning("Config file not found: %s — using defaults", path)

    config = _expand_paths(config)
    config = _resolve_env_vars(config)
    return config


def load_workspace_files(config: dict) -> dict[str, str]:
    """Load AGENTS.md and SOUL.md from the workspace directory.

    Args:
        config: Configuration dictionary.

    Returns:
        Dictionary with keys ``agents_md`` and ``soul_md`` containing file contents
        (empty string if not found).
    """
    workspace_root = Path(config["workspace"]["root"])
    result: dict[str, str] = {}

    for key in ("agents_md", "soul_md"):
        filename = config["workspace"].get(key, "")
        if not filename:
            result[key] = ""
            continue

        filepath = workspace_root / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8")
            result[key] = content
            logger.info("Loaded %s (%d chars)", filepath, len(content))
        else:
            result[key] = ""
            logger.debug("%s not found at %s", key, filepath)

    return result
