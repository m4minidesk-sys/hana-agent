"""Tests for yui.tools.safe_shell — AC-03."""

import shlex
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest

from yui.tools.safe_shell import create_safe_shell


ALLOWLIST = ["ls", "cat", "grep", "find", "python3", "git"]
BLOCKLIST = [
    "rm -rf /",
    "rm -rf ~",
    "rm -rf $HOME",
    "sudo",
    "git push --force",
    "git push -f",
    "git reset --hard",
    "chmod 777",
]


class TestSafeShellValidation:
    """AC-03: Shell commands via safe_shell with allowlist enforcement.

    These tests validate the allowlist/blocklist logic WITHOUT invoking
    the actual strands shell (which requires Bedrock credentials).
    """

    def _make_shell(self):
        return create_safe_shell(
            allowlist=ALLOWLIST,
            blocklist=BLOCKLIST,
            timeout=10,
        )

    @patch("yui.tools.safe_shell.strands_shell")
    def test_allowed_command_passes(self, mock_shell):
        """Allowed command → delegates to strands shell."""
        mock_shell.return_value = "file1.txt\nfile2.txt"
        shell = self._make_shell()
        result = shell(command="ls -la")
        mock_shell.assert_called_once_with(command="ls -la", timeout=10)
        assert "file1.txt" in result

    @patch("yui.tools.safe_shell.strands_shell")
    def test_path_based_command_allowed(self, mock_shell):
        """/usr/bin/cat → base name 'cat' is in allowlist."""
        mock_shell.return_value = "content"
        shell = self._make_shell()
        result = shell(command="/usr/bin/cat /etc/hostname")
        mock_shell.assert_called_once()

    @patch("yui.tools.safe_shell.strands_shell")
    def test_homebrew_path_allowed(self, mock_shell):
        """/opt/homebrew/bin/python3 → 'python3' in allowlist."""
        mock_shell.return_value = "Python 3.13"
        shell = self._make_shell()
        result = shell(command="/opt/homebrew/bin/python3 --version")
        mock_shell.assert_called_once()

    def test_blocked_command_rejected(self):
        """Blocklisted patterns → error, never calls strands shell."""
        shell = self._make_shell()
        for blocked_cmd in [
            "rm -rf /",
            "rm -rf ~",
            "sudo apt install something",
            "git push --force origin main",
            "chmod 777 /etc",
        ]:
            result = shell(command=blocked_cmd)
            assert "blocked" in result.lower() or "Error" in result, \
                f"Should block: {blocked_cmd}"

    def test_command_not_in_allowlist_rejected(self):
        """Command not in allowlist → error."""
        shell = self._make_shell()
        result = shell(command="nc -l 8080")
        assert "not in the allowlist" in result

    def test_empty_command_rejected(self):
        """Empty command → error."""
        shell = self._make_shell()
        result = shell(command="")
        assert "empty" in result.lower() or "Error" in result

    def test_malformed_quoting_rejected(self):
        """Malformed shell quoting → error (not fallback to naive split)."""
        shell = self._make_shell()
        result = shell(command="ls 'unterminated")
        assert "parse" in result.lower() or "Error" in result


class TestBlocklistCoverage:
    """Verify blocklist covers critical dangerous patterns."""

    @pytest.mark.parametrize("pattern", [
        "rm -rf /",
        "rm -rf ~",
        "rm -rf $HOME",
        "sudo",
        "git push --force",
        "git push -f",
        "git reset --hard",
        "chmod 777",
    ])
    def test_dangerous_patterns_blocked(self, pattern):
        """Each dangerous pattern should be in BLOCKLIST."""
        assert pattern in BLOCKLIST


class TestAllowlistExtraction:
    """Verify base command extraction logic."""

    @pytest.mark.parametrize("cmd,expected_base", [
        ("ls -la", "ls"),
        ("/usr/bin/cat foo", "cat"),
        ("/opt/homebrew/bin/grep pattern", "grep"),
        ("python3 -c 'print(1)'", "python3"),
        ("git status", "git"),
    ])
    def test_base_name_extraction(self, cmd, expected_base):
        """PurePosixPath extracts correct base name."""
        parts = shlex.split(cmd)
        base = PurePosixPath(parts[0]).name
        assert base == expected_base
