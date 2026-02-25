"""Configuration loading and validation."""

import os
from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "bedrock",
        "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "region": "us-east-1",
        "max_tokens": 4096,
    },
    "tools": {
        "shell": {
            "allowlist": ["ls", "cat", "grep", "find", "python3", "kiro-cli", "brew"],
            "blocklist": [
                "rm -rf /",
                "rm -rf ~",
                "rm -rf $HOME",
                "rm -rf .",
                "sudo",
                "curl | bash",
                "wget | bash",
                "eval",
                "exec",
                "git push --force",
                "git push -f",
                "git reset --hard",
                "git clean -f",
                "mkfs",
                "dd if=",
                "> /dev/sd",
                "chmod 777",
                "chown root",
            ],
            "timeout_seconds": 30,
        },
        "file": {
            "workspace_root": "~/.yui/workspace",
        },
        "kiro": {
            "binary_path": "~/.local/bin/kiro-cli",
            "timeout_seconds": 300,
        },
    },
    "runtime": {
        "session": {
            "compaction_threshold": 0.8,
            "keep_recent_messages": 5,
        },
    },
}


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def load_config(config_path: str | None = None) -> dict[str, Any]:
    """Load config from ~/.yui/config.yaml with defaults.

    Args:
        config_path: Override path to config file. Defaults to ~/.yui/config.yaml.

    Returns:
        Merged configuration dictionary.

    Raises:
        ConfigError: If config file exists but is invalid.
    """
    if config_path is None:
        config_path = os.path.expanduser("~/.yui/config.yaml")

    path = Path(config_path).expanduser()

    if not path.exists():
        return _deep_copy(DEFAULT_CONFIG)

    try:
        with open(path) as f:
            user_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in {path}: {e}") from e

    if user_config is None:
        return _deep_copy(DEFAULT_CONFIG)

    if not isinstance(user_config, dict):
        raise ConfigError(
            f"Config file {path} must be a YAML mapping (got {type(user_config).__name__})"
        )

    # Merge with defaults
    config = _deep_copy(DEFAULT_CONFIG)
    _deep_merge(config, user_config)

    # Validate required fields
    _validate(config)

    return config


def _validate(config: dict[str, Any]) -> None:
    """Validate config after merge."""
    model = config.get("model", {})
    if not model.get("model_id"):
        raise ConfigError("model.model_id is required")
    if not model.get("region"):
        raise ConfigError("model.region is required")

    shell_cfg = config.get("tools", {}).get("shell", {})
    if not isinstance(shell_cfg.get("allowlist", []), list):
        raise ConfigError("tools.shell.allowlist must be a list")
    if not isinstance(shell_cfg.get("blocklist", []), list):
        raise ConfigError("tools.shell.blocklist must be a list")


def _deep_copy(d: dict) -> dict:
    """Simple deep copy for nested dicts/lists."""
    out: dict = {}
    for k, v in d.items():
        if isinstance(v, dict):
            out[k] = _deep_copy(v)
        elif isinstance(v, list):
            out[k] = v[:]
        else:
            out[k] = v
    return out


def _deep_merge(base: dict, override: dict) -> None:
    """Deep merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
