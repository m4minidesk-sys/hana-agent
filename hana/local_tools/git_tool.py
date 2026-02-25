"""HANA git tool — Git operations with command allowlist."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

_tool_config: dict[str, Any] = {}


def configure(config: dict[str, Any]) -> None:
    """Store git tool configuration.

    Args:
        config: The ``tools.git`` section of HANA config.
    """
    global _tool_config
    _tool_config = config


def _is_allowed_git_command(command: str) -> bool:
    """Check if a git subcommand is in the allowed list.

    Args:
        command: Git command string (e.g., 'status', 'log --oneline').

    Returns:
        True if the subcommand is allowed.
    """
    allowed = _tool_config.get("allowed_commands", [])
    if not allowed:
        return True  # No restriction

    subcmd = command.strip().split()[0] if command.strip() else ""
    return subcmd in allowed


@tool
def git(command: str, repo_dir: str | None = None) -> dict[str, Any]:
    """Execute a git command in a repository.

    Only allowed git subcommands can be executed (configurable).

    Args:
        command: Git subcommand and arguments (e.g., 'status', 'log --oneline -5').
        repo_dir: Repository directory (optional, uses cwd if not set).

    Returns:
        Dictionary with stdout, stderr, and returncode.
    """
    if not _tool_config.get("enabled", True):
        return {"stdout": "", "stderr": "git tool is disabled", "returncode": -1}

    if not _is_allowed_git_command(command):
        return {
            "stdout": "",
            "stderr": f"Git command not allowed: {command}",
            "returncode": -1,
        }

    cwd = None
    if repo_dir:
        repo_path = Path(repo_dir).expanduser()
        if not repo_path.is_dir():
            return {
                "stdout": "",
                "stderr": f"Repository directory not found: {repo_dir}",
                "returncode": -1,
            }
        cwd = str(repo_path)

    full_cmd = f"git {command}"

    logger.info("Git: %s (repo=%s)", full_cmd, cwd or "cwd")

    try:
        result = subprocess.run(
            full_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=cwd,
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": "Git command timed out after 30s",
            "returncode": -1,
        }
    except Exception as exc:
        logger.error("Git command failed: %s", exc)
        return {"stdout": "", "stderr": str(exc), "returncode": -1}
