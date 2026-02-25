"""HANA exec tool — shell command execution with allowlist/blocklist."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from strands import tool

logger = logging.getLogger(__name__)

# Module-level config storage (set by agent_core at init time)
_tool_config: dict[str, Any] = {}


def configure(config: dict[str, Any]) -> None:
    """Store exec tool configuration.

    Args:
        config: The ``tools.exec`` section of HANA config.
    """
    global _tool_config
    _tool_config = config


def _is_allowed(command: str) -> bool:
    """Check if a command passes the allowlist/blocklist filters.

    Args:
        command: Shell command string.

    Returns:
        True if the command is allowed.
    """
    blocklist: list[str] = _tool_config.get("blocklist", [])
    for blocked in blocklist:
        if blocked in command:
            return False

    allowlist: list[str] = _tool_config.get("allowlist", [])
    if not allowlist:
        return True  # No allowlist = allow all (except blocklist)

    # Check if the command starts with any allowed prefix
    cmd_base = command.strip().split()[0] if command.strip() else ""
    return any(cmd_base == allowed or cmd_base.endswith(f"/{allowed}") for allowed in allowlist)


@tool
def exec_command(command: str, timeout: int = 30, workdir: str | None = None) -> dict[str, Any]:
    """Execute a shell command on the local machine.

    This tool runs shell commands with configurable timeouts and working
    directories.  Commands are filtered against an allowlist and blocklist
    for safety.

    Args:
        command: Shell command to execute.
        timeout: Execution timeout in seconds (default 30).
        workdir: Working directory for the command (optional).

    Returns:
        Dictionary with stdout, stderr, and returncode.
    """
    if not _tool_config.get("enabled", True):
        return {"stdout": "", "stderr": "exec tool is disabled", "returncode": -1}

    if not _is_allowed(command):
        logger.warning("Blocked command: %s", command)
        return {
            "stdout": "",
            "stderr": f"Command not allowed: {command}",
            "returncode": -1,
        }

    max_timeout = _tool_config.get("timeout", 30)
    effective_timeout = min(timeout, max_timeout)
    max_output = _tool_config.get("max_output", 102400)

    logger.info("Executing: %s (timeout=%ds, workdir=%s)", command, effective_timeout, workdir)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            cwd=workdir,
        )

        stdout = result.stdout[:max_output] if result.stdout else ""
        stderr = result.stderr[:max_output] if result.stderr else ""

        truncated = len(result.stdout or "") > max_output or len(result.stderr or "") > max_output

        return {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode,
            "truncated": truncated,
        }

    except subprocess.TimeoutExpired:
        logger.warning("Command timed out after %ds: %s", effective_timeout, command)
        return {
            "stdout": "",
            "stderr": f"Command timed out after {effective_timeout}s",
            "returncode": -1,
        }
    except Exception as exc:
        logger.error("Command execution failed: %s", exc)
        return {
            "stdout": "",
            "stderr": str(exc),
            "returncode": -1,
        }
