"""Safe shell tool with allowlist/blocklist enforcement."""

import logging
import re
import shlex
import subprocess
from pathlib import PurePosixPath

from strands import tool

logger = logging.getLogger(__name__)

# CWE-78: OS Command Injection — シェルメタ文字パターン
_SHELL_METACHAR_PATTERN = re.compile(r"[;|&`\n\r]|\$\(")

# CWE-22: パストラバーサル / 機密パスパターン
_SENSITIVE_PATH_PATTERNS = [
    re.compile(r"/etc/"),
    re.compile(r"/proc/"),
    re.compile(r"/sys/"),
    re.compile(r"\.\./"),
    re.compile(r"\$HOME"),
    re.compile(r"\$\{"),
]

# CWE-269: 権限昇格 — 危険なフラグパターン（コマンド別）
_DANGEROUS_FLAG_PATTERNS: dict[str, re.Pattern] = {
    "python3": re.compile(r"\s+-c\s+"),
    "python": re.compile(r"\s+-c\s+"),
    "git": re.compile(r"--exec-path"),
    "find": re.compile(r"^find\s+/(\s|$)"),
    "grep": re.compile(r"/etc"),
}


def create_safe_shell(allowlist: list[str], blocklist: list[str], timeout: int):
    """Create a safe shell tool with security checks."""

    @tool
    def safe_shell(command: str) -> str:
        """Execute shell command with security checks.

        Validates against:
        1. Blocklist (substring match)
        2. Shell metacharacter injection (CWE-78)
        3. Path traversal / sensitive path (CWE-22)
        4. Allowlist (base command name)
        5. Dangerous flag patterns (CWE-269)
        """
        if not command or not command.strip():
            return "Error: empty command"

        # Blocklist check
        for blocked in blocklist:
            if blocked in command:
                return f"Error: command blocked by security policy (matches '{blocked}')"

        # CWE-78: Shell metacharacter injection check
        meta_match = _SHELL_METACHAR_PATTERN.search(command)
        if meta_match:
            return (
                f"Error: command blocked — shell metacharacter '{meta_match.group()}' "
                f"detected (possible command injection attack)"
            )

        # CWE-22: Path traversal / sensitive path check
        for pattern in _SENSITIVE_PATH_PATTERNS:
            if pattern.search(command):
                return (
                    "Error: command blocked — sensitive path or traversal "
                    "pattern detected (possible path traversal attack)"
                )

        # Extract base command name
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return f"Error: cannot parse command safely ({e})"

        if not parts:
            return "Error: empty command after parsing"

        base_cmd = PurePosixPath(parts[0]).name

        if base_cmd not in allowlist:
            return (
                f"Error: command '{base_cmd}' is not in the allowlist. "
                f"Allowed commands: {', '.join(sorted(allowlist))}"
            )

        # CWE-269: Dangerous flag pattern check (per-command)
        if base_cmd in _DANGEROUS_FLAG_PATTERNS:
            flag_match = _DANGEROUS_FLAG_PATTERNS[base_cmd].search(command)
            if flag_match:
                return (
                    f"Error: command blocked — dangerous flag pattern detected "
                    f"for '{base_cmd}' (possible privilege escalation)"
                )

        # Execute
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
