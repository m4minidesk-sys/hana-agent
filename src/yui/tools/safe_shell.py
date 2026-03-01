"""Safe shell tool with allowlist/blocklist enforcement."""

import logging
import re
import shlex
import subprocess
from pathlib import PurePosixPath

from strands import tool

logger = logging.getLogger(__name__)

# CWE-78: OS Command Injection — シェルメタ文字パターン
# セミコロン、パイプ、&&、||、バックグラウンド&、改行、コマンド置換$()、バッククォート
_SHELL_METACHAR_PATTERN = re.compile(r'[;|&`$
]')

# CWE-22: パストラバーサル — 機密パスパターン
_SENSITIVE_PATH_PATTERNS = [
    re.compile(r'/etc/'),
    re.compile(r'/proc/'),
    re.compile(r'/sys/'),
    re.compile(r'\.\./'),  # ../
    re.compile(r'^/\.\.$'),  # /..
    re.compile(r'\$HOME'),
    re.compile(r'\$'),  # 環境変数展開
]

# CWE-269: 権限昇格 — 危険なフラグパターン
_DANGEROUS_FLAG_PATTERNS = {
    "python3": re.compile(r'\s+-c\s+'),  # python3 -c "..." は任意コード実行
    "git": re.compile(r'--exec-path'),   # git --exec-path= は任意コマンド実行
    "find": re.compile(r'^/\s'),         # find / は全ファイルシステム探索
    "grep": re.compile(r'/etc'),          # grep ... /etc は機密探索
}


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

        The command is validated against:
        1. Blocklist (substring match)
        2. Shell metacharacter injection (CWE-78)
        3. Path traversal (CWE-22)
        4. Allowlist (base command name)
        5. Dangerous flag patterns (CWE-269)

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

        # CWE-78: Shell metacharacter injection check
        # Detect semicolon, pipe, &&, ||, &, $(), backtick, newline
        if _SHELL_METACHAR_PATTERN.search(command):
            matched = _SHELL_METACHAR_PATTERN.search(command).group()
            return (
                f"Error: command blocked — shell metacharacter '{matched}' "
                f"detected (possible command injection attack)"
            )

        # CWE-22: Path traversal / sensitive path check
        for pattern in _SENSITIVE_PATH_PATTERNS:
            if pattern.search(command):
                return (
                    f"Error: command blocked — sensitive path or traversal "
                    f"pattern detected (possible path traversal attack)"
                )

        # Extract the base command name (handle paths like /usr/bin/python3)
        try:
            parts = shlex.split(command)
        except ValueError as e:
            # Malformed quoting / shell escape — reject for safety
            return f"Error: cannot parse command safely ({e})"

        if not parts:
            return "Error: empty command after parsing"

        base_cmd = PurePosixPath(parts[0]).name  # /opt/homebrew/bin/python3 → python3

        if base_cmd not in allowlist:
            return (
                f"Error: command '{base_cmd}' is not in the allowlist. "
                f"Allowed commands: {', '.join(sorted(allowlist))}"
            )

        # CWE-269: Dangerous flag pattern check (per-command)
        if base_cmd in _DANGEROUS_FLAG_PATTERNS:
            if _DANGEROUS_FLAG_PATTERNS[base_cmd].search(command):
                return (
                    f"Error: command blocked — dangerous flag pattern detected "
                    f"for '{base_cmd}' (possible privilege escalation)"
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
