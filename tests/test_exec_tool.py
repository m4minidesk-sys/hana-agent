"""Tests for HANA exec tool."""

from __future__ import annotations

import pytest

from hana.local_tools.exec_tool import _is_allowed, configure, exec_command


@pytest.fixture(autouse=True)
def _setup_config() -> None:
    """Configure exec tool with test settings."""
    configure({
        "enabled": True,
        "allowlist": ["ls", "echo", "cat", "pwd", "date"],
        "blocklist": ["rm -rf /", "shutdown"],
        "timeout": 10,
        "max_output": 1024,
    })


class TestIsAllowed:
    """Tests for allowlist/blocklist checking."""

    def test_allowed_command(self) -> None:
        assert _is_allowed("ls -la") is True

    def test_allowed_command_no_args(self) -> None:
        assert _is_allowed("pwd") is True

    def test_blocked_command(self) -> None:
        assert _is_allowed("rm -rf /") is False

    def test_disallowed_command(self) -> None:
        assert _is_allowed("curl http://example.com") is False

    def test_empty_command(self) -> None:
        assert _is_allowed("") is False


class TestExecCommand:
    """Tests for exec_command tool function."""

    def test_simple_echo(self) -> None:
        result = exec_command(command="echo hello", timeout=5)
        assert result["stdout"].strip() == "hello"
        assert result["returncode"] == 0

    def test_working_directory(self) -> None:
        result = exec_command(command="pwd", timeout=5, workdir="/tmp")
        assert "/tmp" in result["stdout"] or "/private/tmp" in result["stdout"]

    def test_blocked_command_rejected(self) -> None:
        result = exec_command(command="rm -rf /", timeout=5)
        assert result["returncode"] == -1
        assert "not allowed" in result["stderr"].lower()

    def test_disallowed_command_rejected(self) -> None:
        result = exec_command(command="curl http://example.com", timeout=5)
        assert result["returncode"] == -1

    def test_timeout(self) -> None:
        result = exec_command(command="echo start && sleep 30", timeout=2)
        assert result["returncode"] == -1
        assert "timed out" in result["stderr"].lower()

    def test_disabled_tool(self) -> None:
        configure({"enabled": False})
        result = exec_command(command="echo hello", timeout=5)
        assert result["returncode"] == -1
        assert "disabled" in result["stderr"].lower()
        # Re-enable for other tests
        configure({
            "enabled": True,
            "allowlist": ["ls", "echo", "cat", "pwd", "date"],
            "blocklist": ["rm -rf /", "shutdown"],
            "timeout": 10,
            "max_output": 1024,
        })
