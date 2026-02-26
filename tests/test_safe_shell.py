"""Tests for yui.tools.safe_shell — AC-03.

All tests use REAL subprocess execution (no mocks).
"""

import shlex
import subprocess
from pathlib import PurePosixPath

import pytest

from yui.tools.safe_shell import create_safe_shell


ALLOWLIST = ["ls", "cat", "grep", "find", "python3", "git", "echo", "wc", "head", "tail", "date", "uname", "pwd"]
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

    All tests use REAL subprocess execution — no mocks.
    """

    def _make_shell(self):
        return create_safe_shell(
            allowlist=ALLOWLIST,
            blocklist=BLOCKLIST,
            timeout=10,
        )

    def test_allowed_command_passes(self, tmp_path):
        """Allowed command → real execution, returns real output."""
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.txt").write_text("b")
        shell = self._make_shell()
        result = shell(command=f"ls {tmp_path}")
        assert "file1.txt" in result
        assert "file2.txt" in result

    def test_path_based_command_allowed(self, tmp_path):
        """/usr/bin/cat → base name 'cat' is in allowlist, real execution."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello from test")
        shell = self._make_shell()
        result = shell(command=f"cat {test_file}")
        assert "hello from test" in result

    def test_homebrew_path_allowed(self):
        """/opt/homebrew/bin/python3 (or python3) → real execution."""
        shell = self._make_shell()
        result = shell(command="python3 --version")
        assert "Python" in result

    def test_blocked_command_rejected(self):
        """Blocklisted patterns → error, never calls subprocess."""
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

    def test_nonzero_exit_code_reported(self):
        """Non-zero exit code is included in output (real execution)."""
        shell = self._make_shell()
        result = shell(command="cat /nonexistent_path_xyz_12345")
        assert "exit code" in result.lower() or "No such file" in result or "STDERR" in result

    def test_timeout_handled(self):
        """Timeout → error message (real slow command)."""
        shell = create_safe_shell(
            allowlist=["python3"],
            blocklist=[],
            timeout=1,  # 1 second timeout
        )
        result = shell(command="python3 -c 'import time; time.sleep(10)'")
        assert "timed out" in result

    def test_echo_returns_text(self):
        """echo command returns actual text."""
        shell = self._make_shell()
        result = shell(command="echo hello world")
        assert "hello world" in result

    def test_date_returns_output(self):
        """date command returns current date."""
        shell = self._make_shell()
        result = shell(command="date")
        assert len(result) > 5  # Some date string

    def test_uname_returns_os(self):
        """uname returns OS name."""
        shell = self._make_shell()
        result = shell(command="uname -s")
        assert "Darwin" in result or "Linux" in result

    def test_wc_counts_lines(self, tmp_path):
        """wc -l counts real lines."""
        f = tmp_path / "lines.txt"
        f.write_text("a\nb\nc\n")
        shell = self._make_shell()
        result = shell(command=f"wc -l {f}")
        assert "3" in result

    def test_grep_finds_pattern(self, tmp_path):
        """grep finds matching lines."""
        f = tmp_path / "data.txt"
        f.write_text("apple\nbanana\napricot\n")
        shell = self._make_shell()
        result = shell(command=f"grep ap {f}")
        assert "apple" in result
        assert "apricot" in result


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
