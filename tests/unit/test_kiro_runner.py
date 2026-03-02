"""Unit tests for kiro_runner.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yui.autonomy.kiro_runner import KiroRunner


@pytest.fixture
def kiro_runner():
    """Create KiroRunner instance."""
    return KiroRunner(kiro_path="kiro-cli")


def test_build_command(kiro_runner):
    """T-YUI-H-02: KiroRunner can build kiro-cli command (mock execution)."""
    persona = "engineer"
    instruction = "implement feature X"
    
    cmd = kiro_runner.build_command(persona, instruction)
    
    assert cmd == [
        "kiro-cli",
        "chat",
        "--no-interactive",
        "--trust-all-tools",
        "--agent",
        "engineer",
        "implement feature X",
    ]


def test_build_command_with_custom_path():
    """Test command building with custom kiro path."""
    runner = KiroRunner(kiro_path="/usr/local/bin/kiro-cli")
    cmd = runner.build_command("reviewer", "review code")
    
    assert cmd[0] == "/usr/local/bin/kiro-cli"
    assert "--no-interactive" in cmd
    assert "--trust-all-tools" in cmd


@patch("subprocess.run")
def test_run_saves_output(mock_run, kiro_runner, tmp_path):
    """T-YUI-H-05: KiroRunner output path is tasks/{id}/{persona}.md."""
    # Mock subprocess result
    mock_result = MagicMock()
    mock_result.stdout = "Success output"
    mock_result.stderr = "Warning message"
    mock_result.returncode = 0
    mock_run.return_value = mock_result
    
    output_path = tmp_path / "engineer.md"
    result = kiro_runner.run("engineer", "test instruction", output_path)
    
    # Verify subprocess.run was called
    assert mock_run.called
    call_args = mock_run.call_args
    assert call_args[0][0][0] == "kiro-cli"
    assert call_args[1]["capture_output"] is True
    assert call_args[1]["text"] is True
    
    # Verify result
    assert result["stdout"] == "Success output"
    assert result["stderr"] == "Warning message"
    assert result["returncode"] == 0
    
    # Verify output file
    assert output_path.exists()
    content = output_path.read_text()
    assert "# Kiro CLI Output: engineer" in content
    assert "Success output" in content
    assert "Warning message" in content


@patch("subprocess.run")
def test_run_with_error(mock_run, kiro_runner, tmp_path):
    """Test KiroRunner handles non-zero exit codes."""
    mock_result = MagicMock()
    mock_result.stdout = ""
    mock_result.stderr = "Error: command failed"
    mock_result.returncode = 1
    mock_run.return_value = mock_result
    
    output_path = tmp_path / "failed.md"
    result = kiro_runner.run("engineer", "bad command", output_path)
    
    assert result["returncode"] == 1
    assert "Error: command failed" in result["stderr"]
    
    # Output file should still be created
    assert output_path.exists()
    content = output_path.read_text()
    assert "Exit Code\n1" in content
