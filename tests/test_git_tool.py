"""Tests for yui.tools.git_tool — AC-16.

All tests use REAL git execution in temp repos (no mocks).
"""

import subprocess

import pytest

from yui.tools.git_tool import git_tool, ALLOWED_SUBCOMMANDS, BLOCKED_PATTERNS


@pytest.fixture
def git_repo(tmp_path):
    """Create a temporary git repo with an initial commit."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), capture_output=True, check=True)
    (repo / "README.md").write_text("# Test Repo")
    subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo), capture_output=True, check=True)
    return repo


class TestGitToolAllowed:
    """Test allowed git subcommands with real git."""

    def test_status_clean(self, git_repo):
        """git status on clean repo."""
        result = git_tool(subcommand="status", working_directory=str(git_repo))
        assert "nothing to commit" in result or "clean" in result

    def test_status_dirty(self, git_repo):
        """git status with uncommitted changes."""
        (git_repo / "new.txt").write_text("new file")
        result = git_tool(subcommand="status", working_directory=str(git_repo))
        assert "new.txt" in result

    def test_log_shows_commits(self, git_repo):
        """git log shows commit history."""
        result = git_tool(subcommand="log", args="--oneline", working_directory=str(git_repo))
        assert "Initial commit" in result

    def test_diff_empty_on_clean(self, git_repo):
        """git diff on clean repo shows no output."""
        result = git_tool(subcommand="diff", working_directory=str(git_repo))
        assert result.strip() == "" or "(no output)" in result

    def test_diff_shows_changes(self, git_repo):
        """git diff after modification shows changes."""
        (git_repo / "README.md").write_text("# Modified")
        result = git_tool(subcommand="diff", working_directory=str(git_repo))
        assert "Modified" in result or "+# Modified" in result

    def test_branch_lists_branches(self, git_repo):
        """git branch lists branches."""
        result = git_tool(subcommand="branch", working_directory=str(git_repo))
        assert "main" in result or "master" in result

    def test_add_and_commit(self, git_repo):
        """git add + commit workflow."""
        (git_repo / "new.txt").write_text("content")
        add_result = git_tool(subcommand="add", args="new.txt", working_directory=str(git_repo))
        commit_result = git_tool(subcommand="commit", args='-m "Add new file"', working_directory=str(git_repo))
        assert "new file" in commit_result.lower() or "1 file changed" in commit_result

    def test_stash_empty(self, git_repo):
        """git stash on clean repo."""
        result = git_tool(subcommand="stash", working_directory=str(git_repo))
        assert "No local changes" in result or "no changes" in result.lower() or "(no output)" in result


class TestGitToolBlocked:
    """Test blocked git operations."""

    def test_push_force_long_blocked(self, git_repo):
        """git push --force is blocked."""
        result = git_tool(subcommand="push", args="--force origin main", working_directory=str(git_repo))
        assert "Blocked" in result or "blocked" in result.lower()

    def test_push_force_short_blocked(self, git_repo):
        """git push -f is blocked."""
        result = git_tool(subcommand="push", args="-f origin main", working_directory=str(git_repo))
        assert "Blocked" in result or "blocked" in result.lower()

    def test_reset_hard_blocked(self, git_repo):
        """git reset --hard is blocked."""
        result = git_tool(subcommand="reset", args="--hard", working_directory=str(git_repo))
        assert "Blocked" in result or "blocked" in result.lower()

    def test_clean_force_blocked(self, git_repo):
        """git clean -f is blocked."""
        result = git_tool(subcommand="clean", args="-f", working_directory=str(git_repo))
        # "clean" is not in ALLOWED_SUBCOMMANDS OR the clean -f pattern is blocked
        assert "not allowed" in result.lower() or "blocked" in result.lower()


class TestGitToolDisallowed:
    """Test disallowed subcommands."""

    @pytest.mark.parametrize("subcmd", [
        "remote", "submodule", "rebase", "cherry-pick", "bisect",
    ])
    def test_disallowed_subcommands(self, subcmd, git_repo):
        """Subcommands not in allowlist are rejected."""
        result = git_tool(subcommand=subcmd, working_directory=str(git_repo))
        assert "not allowed" in result.lower()


class TestAllowedSubcommandsList:
    """Verify the allowed subcommands set."""

    def test_expected_subcommands_present(self):
        """Core git subcommands should be in the allowed set."""
        for cmd in ["status", "log", "diff", "branch", "add", "commit"]:
            assert cmd in ALLOWED_SUBCOMMANDS, f"{cmd} should be allowed"

    def test_blocked_patterns_list(self):
        """Blocked patterns should include dangerous operations."""
        patterns_str = " ".join(BLOCKED_PATTERNS)
        assert "force" in patterns_str
        assert "hard" in patterns_str
