"""Tests for Kiro CLI delegation tool."""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from yui.tools.kiro_delegate import kiro_delegate

pytestmark = pytest.mark.component



@patch("yui.tools.kiro_delegate.Path")
@patch("yui.tools.kiro_delegate.subprocess.run")
def test_kiro_delegate_success(mock_run: MagicMock, mock_path: MagicMock) -> None:
    """Test successful Kiro delegation."""
    mock_path.return_value.expanduser.return_value.exists.return_value = True
    mock_run.return_value = MagicMock(stdout="Success", stderr="")

    result = kiro_delegate("Test task")
    assert "Success" in result


@patch("yui.tools.kiro_delegate.Path")
def test_kiro_delegate_binary_missing(mock_path: MagicMock) -> None:
    """Test error when Kiro binary is missing."""
    mock_path.return_value.expanduser.return_value.exists.return_value = False

    result = kiro_delegate("Test task")
    assert "Error: Kiro CLI not found" in result


@patch("yui.tools.kiro_delegate.Path")
@patch("yui.tools.kiro_delegate.subprocess.run")
def test_kiro_delegate_timeout(mock_run: MagicMock, mock_path: MagicMock) -> None:
    """Test timeout handling."""
    mock_path.return_value.expanduser.return_value.exists.return_value = True
    mock_run.side_effect = subprocess.TimeoutExpired("kiro-cli", 300)

    result = kiro_delegate("Test task")
    assert "timed out" in result


@patch("yui.tools.kiro_delegate.Path")
@patch("yui.tools.kiro_delegate.subprocess.run")
def test_kiro_delegate_ansi_stripping(mock_run: MagicMock, mock_path: MagicMock) -> None:
    """Test ANSI code stripping."""
    mock_path.return_value.expanduser.return_value.exists.return_value = True
    mock_run.return_value = MagicMock(
        stdout="\x1b[32mGreen text\x1b[0m Normal text",
        stderr=""
    )

    result = kiro_delegate("Test task")
    assert "\x1b[" not in result
    assert "Green text Normal text" in result


@patch("yui.tools.kiro_delegate.Path")
@patch("yui.tools.kiro_delegate.subprocess.run")
def test_kiro_delegate_working_directory(mock_run: MagicMock, mock_path: MagicMock) -> None:
    """Test working directory parameter."""
    mock_path.return_value.expanduser.return_value.exists.return_value = True
    mock_run.return_value = MagicMock(stdout="Success", stderr="")

    kiro_delegate("Test task", working_directory="/tmp")
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["cwd"] == "/tmp"
