"""Tests for git tool."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from yui.tools.git_tool import git_tool

pytestmark = pytest.mark.component



@patch("yui.tools.git_tool.subprocess.run")
def test_git_tool_allowed_subcommand(mock_run: MagicMock) -> None:
    """Test allowed git subcommand."""
    mock_run.return_value = MagicMock(stdout="On branch main", stderr="")

    result = git_tool("status")
    assert "On branch main" in result


def test_git_tool_blocked_subcommand() -> None:
    """Test blocked git subcommand."""
    result = git_tool("rebase")
    assert "not allowed" in result


def test_git_tool_blocked_pattern_force_push() -> None:
    """Test blocked force push pattern."""
    result = git_tool("push", "--force")
    assert "Blocked git operation" in result


def test_git_tool_blocked_pattern_reset_hard() -> None:
    """Test blocked reset --hard pattern."""
    result = git_tool("reset", "--hard")
    assert "Blocked git operation" in result


@patch("yui.tools.git_tool.subprocess.run")
def test_git_tool_with_args(mock_run: MagicMock) -> None:
    """Test git command with arguments."""
    mock_run.return_value = MagicMock(stdout="Committed", stderr="")

    result = git_tool("commit", "-m 'Test commit'")
    assert "Committed" in result
    mock_run.assert_called_once()
    assert "commit" in mock_run.call_args.args[0]


@patch("yui.tools.git_tool.subprocess.run")
def test_git_tool_timeout(mock_run: MagicMock) -> None:
    """Test timeout handling."""
    mock_run.side_effect = subprocess.TimeoutExpired("git", 30)

    result = git_tool("status")
    assert "timed out" in result


@patch("yui.tools.git_tool.subprocess.run")
def test_git_tool_working_directory(mock_run: MagicMock) -> None:
    """Test working directory parameter."""
    mock_run.return_value = MagicMock(stdout="Success", stderr="")

    git_tool("status", working_directory="/tmp")
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["cwd"] == "/tmp"


def test_git_tool_allowed_subcommands() -> None:
    """Test all allowed subcommands are accepted."""
    allowed = ["status", "add", "commit", "push", "log", "diff", "branch", "checkout", "pull", "fetch", "stash"]
    for cmd in allowed:
        with patch("yui.tools.git_tool.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="OK", stderr="")
            result = git_tool(cmd)
            assert "not allowed" not in result
