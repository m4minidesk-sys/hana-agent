"""Tests for HANA git tool."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from hana.local_tools.git_tool import _is_allowed_git_command, configure, git


@pytest.fixture(autouse=True)
def _setup_config() -> None:
    """Configure git tool with test settings."""
    configure({
        "enabled": True,
        "allowed_commands": [
            "status", "log", "diff", "add", "commit",
            "push", "pull", "branch", "checkout",
        ],
    })


class TestIsAllowed:
    """Tests for git command allowlist."""

    def test_allowed_status(self) -> None:
        assert _is_allowed_git_command("status") is True

    def test_allowed_log_with_args(self) -> None:
        assert _is_allowed_git_command("log --oneline -5") is True

    def test_disallowed_reset(self) -> None:
        assert _is_allowed_git_command("reset --hard HEAD~1") is False

    def test_disallowed_rebase(self) -> None:
        assert _is_allowed_git_command("rebase -i HEAD~3") is False


class TestGitTool:
    """Tests for git tool function."""

    def test_git_status(self, tmp_path: Path) -> None:
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        result = git(command="status", repo_dir=str(tmp_path))
        assert result["returncode"] == 0

    def test_disallowed_command(self, tmp_path: Path) -> None:
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        result = git(command="reset --hard", repo_dir=str(tmp_path))
        assert result["returncode"] == -1
        assert "not allowed" in result["stderr"].lower()

    def test_nonexistent_repo(self) -> None:
        result = git(command="status", repo_dir="/nonexistent/repo")
        assert result["returncode"] == -1
        assert "not found" in result["stderr"].lower()

    def test_disabled(self) -> None:
        configure({"enabled": False})
        result = git(command="status")
        assert result["returncode"] == -1
        assert "disabled" in result["stderr"].lower()
        # Restore
        configure({
            "enabled": True,
            "allowed_commands": ["status", "log"],
        })
