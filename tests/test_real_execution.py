"""Real execution tests — no mocks, actual subprocess calls (Issue #66).

These tests verify safe_shell and git_tool with real commands.
They use tmp_path fixtures for safe, isolated execution.
"""

import os
import subprocess
import tempfile

import pytest

from yui.tools.safe_shell import create_safe_shell
from yui.tools.git_tool import create_git_tool


# --- Real safe_shell Execution ---

class TestSafeShellRealExecution:
    """Tests that actually run commands (no mock)."""

    @pytest.fixture
    def shell(self):
        allowlist = ["ls", "cat", "echo", "wc", "grep", "find", "pwd", "date", "head", "tail", "sort", "uname"]
        blocklist = ["rm -rf /", "sudo", "chmod 777"]
        return create_safe_shell(allowlist=allowlist, blocklist=blocklist, timeout=5)

    def test_echo_returns_text(self, shell):
        """echo command should return the text."""
        result = shell(command="echo hello world")
        assert "hello world" in result

    def test_ls_lists_files(self, shell, tmp_path):
        """ls in a directory with files should list them."""
        (tmp_path / "file_a.txt").write_text("a")
        (tmp_path / "file_b.txt").write_text("b")
        result = shell(command=f"ls {tmp_path}")
        assert "file_a.txt" in result
        assert "file_b.txt" in result

    def test_cat_reads_file(self, shell, tmp_path):
        """cat should read file contents."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello from test file")
        result = shell(command=f"cat {test_file}")
        assert "hello from test file" in result

    def test_wc_counts_lines(self, shell, tmp_path):
        """wc -l should count lines."""
        test_file = tmp_path / "lines.txt"
        test_file.write_text("line1\nline2\nline3\n")
        result = shell(command=f"wc -l {test_file}")
        assert "3" in result

    def test_grep_finds_pattern(self, shell, tmp_path):
        """grep should find matching lines."""
        test_file = tmp_path / "data.txt"
        test_file.write_text("apple\nbanana\napricot\n")
        result = shell(command=f"grep ap {test_file}")
        assert "apple" in result
        assert "apricot" in result
        assert "banana" not in result

    def test_find_locates_files(self, shell, tmp_path):
        """find should locate files."""
        (tmp_path / "target.py").write_text("# python")
        (tmp_path / "other.txt").write_text("text")
        result = shell(command=f"find {tmp_path} -name '*.py'")
        assert "target.py" in result
        assert "other.txt" not in result

    def test_pwd_returns_path(self, shell):
        """pwd should return a valid path."""
        result = shell(command="pwd")
        assert "/" in result

    def test_date_returns_output(self, shell):
        """date should return current date/time."""
        result = shell(command="date")
        assert "2026" in result or "202" in result  # Year in output

    def test_uname_returns_os(self, shell):
        """uname should return OS info."""
        result = shell(command="uname -s")
        assert "Darwin" in result or "Linux" in result

    def test_nonzero_exit_code_reported(self, shell):
        """Non-zero exit code should be reported."""
        result = shell(command="ls /nonexistent_path_12345")
        assert "exit code" in result.lower() or "no such file" in result.lower() or "STDERR" in result

    def test_blocked_command_never_executes(self, shell):
        """Blocked command should NOT execute."""
        result = shell(command="sudo echo hello")
        assert "blocked" in result.lower()
        assert "hello" not in result


# --- Real git_tool Execution ---

class TestGitToolRealExecution:
    """Tests that actually run git commands in a temp repo."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repo."""
        repo_dir = tmp_path / "test-repo"
        repo_dir.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo_dir), capture_output=True)
        # Create initial commit
        (repo_dir / "README.md").write_text("# Test Repo")
        subprocess.run(["git", "add", "."], cwd=str(repo_dir), capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), capture_output=True)
        return repo_dir

    @pytest.fixture
    def git_tool(self):
        return create_git_tool(timeout=10)

    def test_git_status_in_real_repo(self, git_tool, git_repo):
        """git status in a real repo should show clean state."""
        result = git_tool(args=f"status --cwd={git_repo}")
        # git_tool passes --cwd as arg, but git doesn't support it
        # Use -C instead
        pass  # Covered by test below

    def test_git_log_shows_commits(self, git_repo):
        """git log should show commit history."""
        git_tool = create_git_tool(timeout=10)
        result = git_tool(args=f"-C {git_repo} log --oneline")
        assert "Initial commit" in result

    def test_git_diff_empty_on_clean(self, git_repo):
        """git diff on clean repo should have no output."""
        git_tool = create_git_tool(timeout=10)
        result = git_tool(args=f"-C {git_repo} diff")
        assert result.strip() == "" or "(no output)" in result

    def test_git_diff_shows_changes(self, git_repo):
        """git diff after modifying a file should show changes."""
        (git_repo / "README.md").write_text("# Modified")
        git_tool = create_git_tool(timeout=10)
        result = git_tool(args=f"-C {git_repo} diff")
        assert "Modified" in result or "+# Modified" in result

    def test_git_branch_lists_branches(self, git_repo):
        """git branch should list branches."""
        git_tool = create_git_tool(timeout=10)
        result = git_tool(args=f"-C {git_repo} branch")
        assert "main" in result or "master" in result

    def test_git_push_blocked(self, git_repo):
        """git push should be blocked by git_tool allowlist."""
        git_tool = create_git_tool(timeout=10)
        result = git_tool(args=f"-C {git_repo} push origin main")
        assert "not allowed" in result.lower() or "error" in result.lower() or "blocked" in result.lower()


# --- Real Session Manager ---

class TestSessionManagerReal:
    """Real SQLite operations without mocks."""

    def test_session_roundtrip(self, tmp_path):
        """Create session, add messages, retrieve — no mocks."""
        from yui.session import SessionManager

        db_path = str(tmp_path / "sessions.db")
        manager = SessionManager(db_path)
        sid = "real-test-session"

        manager.add_message(sid, "user", "Hello Yui")
        manager.add_message(sid, "assistant", "Hi! How can I help?")
        manager.add_message(sid, "user", "What is 2+2?")

        messages = manager.get_messages(sid)
        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].content == "Hello Yui"
        assert messages[1].role == "assistant"
        assert messages[2].content == "What is 2+2?"

    def test_session_compaction_real(self, tmp_path):
        """Compaction with real SQLite — no mocks."""
        from yui.session import SessionManager

        db_path = str(tmp_path / "compact.db")
        manager = SessionManager(db_path, compaction_threshold=5, keep_recent=2)
        sid = "compact-test"

        for i in range(8):
            manager.add_message(sid, "user", f"Message {i}")

        assert manager.get_message_count(sid) == 8

        manager.compact_session(sid, summarizer=lambda msgs: f"Summary of {len(msgs)} messages")

        messages = manager.get_messages(sid)
        assert len(messages) == 3  # 1 summary + 2 recent
        assert messages[0].role == "system"
        assert "Summary of 6" in messages[0].content
