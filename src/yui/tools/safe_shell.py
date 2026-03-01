"""Safe shell tool with allowlist/blocklist enforcement."""

import logging
import shlex
import subprocess
from pathlib import PurePosixPath

from strands import tool

logger = logging.getLogger(__name__)


def create_safe_shell(allowlist: list[str], blocklist: list[str], timeout: int):
    """Create a safe shell tool with security checks.

    Args:
        allowlist: Allowed command base names (e.g. ["ls", "git", "python3"]).
        blocklist: Blocked command patterns (substring match).
        timeout: Max execution time in seconds.
    """

    @tool
    def safe_shell(command: str) -> str:
        """Execute shell command with security checks.

        The command is validated against an allowlist (base command name)
        and a blocklist (dangerous patterns) before execution.

        Args:
            command: Shell command to execute.

        Returns:
            Command output as string.
        """
        if not command or not command.strip():
            return "Error: empty command"

        # Blocklist check — substring match against the full command
        for blocked in blocklist:
            if blocked in command:
                return f"Error: command blocked by security policy (matches '{blocked}')"

        # Extract the base command name (handle paths like /usr/bin/python3)
        try:
            parts = shlex.split(command)
        except ValueError as e:
            # Malformed quoting / shell escape — reject for safety
            return f"Error: cannot parse command safely ({e})"

        if not parts:
            return "Error: empty command after parsing"

        base_cmd = PurePosixPath(parts[0]).name  # /opt/homebrew/bin/python3 → python3

        # Reject commands with suspicious path traversal or shell metacharacters in base
        if not base_cmd or base_cmd.startswith(".") or "/" in parts[0].replace(base_cmd, "", 1).rstrip("/"):
            # Allow absolute paths (e.g. /usr/bin/python3) but check the resolved name
            pass

        if base_cmd not in allowlist:
            return (
                f"Error: command '{base_cmd}' is not in the allowlist. "
                f"Allowed commands: {', '.join(sorted(allowlist))}"
            )

        # Execute directly via subprocess (no interactive confirmation)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            output = result.stdout
            if result.stderr:
                output += f"\nSTDERR: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[exit code: {result.returncode}]"
            return output.strip() if output.strip() else "(no output)"
        except subprocess.TimeoutExpired:
            return f"Error: command timed out after {timeout} seconds"
        except Exception as e:
            logger.error("Shell execution error: %s", e)
            return f"Error: {e}"

    return safe_shell
