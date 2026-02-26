"""Configuration loading and validation."""

import os
from pathlib import Path
from typing import Any, Optional

import yaml


DEFAULT_CONFIG: dict[str, Any] = {
    "model": {
        "provider": "bedrock",
        "model_id": "us.anthropic.claude-sonnet-4-20250514-v1:0",
        "region": "us-east-1",
        "max_tokens": 4096,
        "guardrail_id": "",
        "guardrail_version": "DRAFT",
        "guardrail_latest_message": False,
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
    "slack": {
        "bot_token": "",
        "app_token": "",
    },
    "meeting": {
        "audio": {
            "capture_method": "screencapturekit",
            "include_mic": True,
            "sample_rate": 16000,
            "channels": 1,
        },
        "whisper": {
            "engine": "mlx",
            "model": "large-v3-turbo",
            "language": "auto",
            "chunk_seconds": 5,
            "vad_enabled": True,
        },
        "analysis": {
            "provider": "bedrock",
            "realtime_enabled": False,
            "realtime_interval_seconds": 60,
            "realtime_window_minutes": 5,
            "max_cost_per_meeting_usd": 2.0,
            "minutes_auto_generate": True,
        },
        "output": {
            "transcript_dir": "~/.yui/meetings/",
            "format": "markdown",
            "save_audio": False,
            "slack_notify": True,
        },
        "retention_days": 90,
        "hotkeys": {
            "enabled": True,
            "toggle_recording": "<cmd>+<shift>+r",
            "stop_generate": "<cmd>+<shift>+s",
            "open_minutes": "<cmd>+<shift>+m",
        },
    },
    "mcp": {
        "servers": [],
        "auto_connect": True,
    },
    "workshop": {
        "test": {
            "region": "us-east-1",
            "cleanup_after_test": True,
            "timeout_per_step_seconds": 300,
            "max_total_duration_minutes": 120,
            "max_cost_usd": 10.0,
            "headed": False,
            "console_auth": {
                "method": "iam_user",
                "account_id": "",
                "username": "",
            },
            "video": {
                "enabled": True,
                "resolution": {"width": 1920, "height": 1080},
                "per_step": True,
                "full_walkthrough": True,
            },
            "output_dir": "~/.yui/workshop-tests/",
            "screenshot": {
                "enabled": True,
                "on_step_complete": True,
                "on_failure": True,
                "full_page": True,
            },
        },
        "report": {
            "format": "markdown",
            "include_screenshots": True,
            "include_video_links": True,
            "slack_notify": True,
        },
    },
    "autonomy": {
        "level": 1,  # L1 = Assisted (default)
        "per_task_overrides": {},
        "budget": {
            "max_monthly_bedrock_usd": 50.0,
            "warning_threshold_pct": 80,
            "hard_stop_threshold_pct": 100,
        },
        "self_improvement": {
            "enabled": False,  # L4 only
            "shadow_period_hours": 24,
            "rollback_threshold_pct": 20,
        },
    },
    "runtime": {
        "session": {
            "db_path": "~/.yui/sessions.db",
            "compaction_threshold": 50,
            "keep_recent_messages": 5,
        },
        "heartbeat": {
            "enabled": False,
            "interval_minutes": 15,
            "active_hours": "07:00-24:00",
            "timezone": "Asia/Tokyo",
        },
        "daemon": {
            "enabled": False,
            "launchd_label": "com.yui.agent",
        },
    },
}


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def load_config(config_path: Optional[str] = None) -> dict[str, Any]:
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
