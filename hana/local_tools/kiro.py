"""HANA Kiro CLI delegation tool."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

_tool_config: dict[str, Any] = {}


def configure(config: dict[str, Any]) -> None:
    """Store Kiro tool configuration.

    Args:
        config: The ``tools.kiro`` section of HANA config.
    """
    global _tool_config
    _tool_config = config


@tool
def kiro_delegate(
    instruction: str,
    project_dir: str,
    timeout: int = 120,
) -> dict[str, Any]:
    """Delegate a coding task to Kiro CLI agent.

    Kiro is an AI coding assistant that handles implementation tasks.
    Pass clear instructions and a project directory for Kiro to work in.

    Args:
        instruction: Task instruction for Kiro (natural language).
        project_dir: Project directory to work in.
        timeout: Maximum execution time in seconds (default 120).

    Returns:
        Dictionary with output text and exit code.
    """
    if not _tool_config.get("enabled", True):
        return {"output": "Kiro tool is disabled", "exit_code": -1}

    binary = _tool_config.get("binary", "~/.local/bin/kiro-cli")
    binary_path = Path(binary).expanduser()

    if not binary_path.exists():
        return {
            "output": f"Kiro CLI not found at {binary_path}",
            "exit_code": -1,
        }

    project_path = Path(project_dir).expanduser()
    if not project_path.is_dir():
        return {
            "output": f"Project directory not found: {project_dir}",
            "exit_code": -1,
        }

    max_timeout = _tool_config.get("timeout", 120)
    effective_timeout = min(timeout, max_timeout)

    cmd = [
        str(binary_path),
        "chat",
        "--no-interactive",
        "--trust-all-tools",
        instruction,
    ]

    logger.info(
        "Kiro delegation: project=%s, timeout=%ds, instruction=%s",
        project_dir,
        effective_timeout,
        instruction[:100],
    )

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=str(project_path),
        )

        return {
            "output": result.stdout + (f"\nSTDERR: {result.stderr}" if result.stderr else ""),
            "exit_code": result.returncode,
        }

    except subprocess.TimeoutExpired:
        logger.warning("Kiro timed out after %ds", effective_timeout)
        return {
            "output": f"Kiro timed out after {effective_timeout}s",
            "exit_code": -1,
        }
    except Exception as exc:
        logger.error("Kiro delegation failed: %s", exc)
        return {"output": str(exc), "exit_code": -1}
