"""Tests for Kiro CLI tools (kiro_review, kiro_implement, check_kiro_available).

AC-67: kiro_review structured findings
AC-68: kiro_implement with spec
AC-78: Startup availability check
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from yui.tools.kiro_tools import (
    MAX_OUTPUT_CHARS,
    _run_kiro_cli,
    _strip_ansi,
    _truncate,
    check_kiro_available,
    kiro_implement,
    kiro_review,
)

pytestmark = pytest.mark.component



# --- Utility tests ---


class TestStripAnsi:
    """Tests for ANSI stripping utility."""

    def test_strips_color_codes(self) -> None:
        text = "\x1b[32mGreen\x1b[0m Normal"
        assert _strip_ansi(text) == "Green Normal"

    def test_strips_bold(self) -> None:
        text = "\x1b[1mBold\x1b[0m"
        assert _strip_ansi(text) == "Bold"

    def test_no_ansi_unchanged(self) -> None:
        text = "Plain text"
        assert _strip_ansi(text) == "Plain text"

    def test_multiple_codes(self) -> None:
        text = "\x1b[31m\x1b[1mRed Bold\x1b[0m"
        assert _strip_ansi(text) == "Red Bold"

    def test_cursor_movement(self) -> None:
        text = "\x1b[2AUp two\x1b[3BDown three"
        assert _strip_ansi(text) == "Up twoDown three"


class TestTruncate:
    """Tests for output truncation."""

    def test_short_text_unchanged(self) -> None:
        text = "short"
        assert _truncate(text) == "short"

    def test_exact_limit_unchanged(self) -> None:
        text = "a" * MAX_OUTPUT_CHARS
        assert _truncate(text) == text

    def test_over_limit_truncated(self) -> None:
        text = "a" * (MAX_OUTPUT_CHARS + 100)
        result = _truncate(text)
        assert len(result) < len(text)
        assert result.endswith("\n... [truncated]")
        assert result.startswith("a" * 100)

    def test_custom_limit(self) -> None:
        text = "a" * 200
        result = _truncate(text, max_chars=100)
        assert result.endswith("\n... [truncated]")
        assert len(result.split("\n")[0]) == 100


# --- check_kiro_available (AC-78) ---


class TestCheckKiroAvailable:
    """Tests for Kiro CLI availability check."""

    @patch("yui.tools.kiro_tools.shutil.which")
    @patch("yui.tools.kiro_tools.Path")
    @patch("yui.tools.kiro_tools.os.access")
    def test_found_at_default_path(
        self, mock_access: MagicMock, mock_path: MagicMock, mock_which: MagicMock
    ) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_access.return_value = True
        mock_which.return_value = None

        assert check_kiro_available() is True

    @patch("yui.tools.kiro_tools.shutil.which")
    @patch("yui.tools.kiro_tools.Path")
    @patch("yui.tools.kiro_tools.os.access")
    def test_found_via_path(
        self, mock_access: MagicMock, mock_path: MagicMock, mock_which: MagicMock
    ) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = False
        mock_access.return_value = False
        mock_which.return_value = "/usr/local/bin/kiro-cli"

        assert check_kiro_available() is True

    @patch("yui.tools.kiro_tools.shutil.which")
    @patch("yui.tools.kiro_tools.Path")
    @patch("yui.tools.kiro_tools.os.access")
    def test_not_found(
        self, mock_access: MagicMock, mock_path: MagicMock, mock_which: MagicMock
    ) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = False
        mock_access.return_value = False
        mock_which.return_value = None

        assert check_kiro_available() is False


# --- _run_kiro_cli ---


class TestRunKiroCli:
    """Tests for the internal Kiro CLI runner."""

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_success(self, mock_path: MagicMock, mock_run: MagicMock) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(stdout="output", stderr="")

        result = _run_kiro_cli("test prompt")
        assert result == "output"

    @patch("yui.tools.kiro_tools.Path")
    def test_binary_not_found(self, mock_path: MagicMock) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = False

        with pytest.raises(FileNotFoundError, match="Kiro CLI not found"):
            _run_kiro_cli("test prompt")

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_timeout(self, mock_path: MagicMock, mock_run: MagicMock) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired("kiro-cli", 120)

        with pytest.raises(subprocess.TimeoutExpired):
            _run_kiro_cli("test prompt")

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_strips_ansi(self, mock_path: MagicMock, mock_run: MagicMock) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(
            stdout="\x1b[32mGreen\x1b[0m", stderr=""
        )

        result = _run_kiro_cli("test")
        assert "\x1b[" not in result
        assert "Green" in result

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_truncates_large_output(
        self, mock_path: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        big_output = "x" * (MAX_OUTPUT_CHARS + 5000)
        mock_run.return_value = MagicMock(stdout=big_output, stderr="")

        result = _run_kiro_cli("test")
        assert result.endswith("\n... [truncated]")
        assert len(result) < len(big_output)

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_bypass_tool_consent_env(
        self, mock_path: MagicMock, mock_run: MagicMock
    ) -> None:
        """Verify BYPASS_TOOL_CONSENT is set in env."""
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(stdout="ok", stderr="")

        _run_kiro_cli("test")

        call_kwargs = mock_run.call_args
        env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert env is not None
        assert env["BYPASS_TOOL_CONSENT"] == "true"

    @patch("yui.tools.kiro_tools.subprocess.run")
    @patch("yui.tools.kiro_tools.Path")
    def test_combines_stdout_stderr(
        self, mock_path: MagicMock, mock_run: MagicMock
    ) -> None:
        mock_path.return_value.expanduser.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(stdout="out", stderr="err")

        result = _run_kiro_cli("test")
        assert "out" in result
        assert "err" in result


# --- kiro_review (AC-67) ---


class TestKiroReview:
    """Tests for the kiro_review tool."""

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = "[CRITICAL] SEC-01: SQL injection risk."
        result = kiro_review(file_path="/tmp/test.py", review_focus="security")
        assert "CRITICAL" in result
        mock_run.assert_called_once()

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_default_focus(self, mock_run: MagicMock) -> None:
        mock_run.return_value = "No issues found."
        kiro_review(file_path="/tmp/test.py")
        prompt = mock_run.call_args[0][0]
        assert "general" in prompt

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_timeout_returns_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("kiro-cli", 120)
        result = kiro_review(file_path="/tmp/test.py")
        assert "Error:" in result
        assert "timed out" in result

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_not_found_returns_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("Kiro CLI not found")
        result = kiro_review(file_path="/tmp/test.py")
        assert "Error:" in result
        assert "not found" in result

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_generic_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = RuntimeError("something broke")
        result = kiro_review(file_path="/tmp/test.py")
        assert "Error:" in result
        assert "something broke" in result


# --- kiro_implement (AC-68) ---


class TestKiroImplement:
    """Tests for the kiro_implement tool."""

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_success(self, mock_run: MagicMock) -> None:
        mock_run.return_value = "Created src/module.py"
        result = kiro_implement(
            spec_path="/tmp/spec.md", task_description="implement auth"
        )
        assert "Created" in result

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_timeout_returns_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = subprocess.TimeoutExpired("kiro-cli", 180)
        result = kiro_implement(
            spec_path="/tmp/spec.md", task_description="implement auth"
        )
        assert "Error:" in result
        assert "timed out" in result

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_not_found_returns_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = FileNotFoundError("Kiro CLI not found")
        result = kiro_implement(
            spec_path="/tmp/spec.md", task_description="implement auth"
        )
        assert "Error:" in result

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_spec_path_in_prompt(self, mock_run: MagicMock) -> None:
        mock_run.return_value = "Done"
        kiro_implement(spec_path="/tmp/spec.md", task_description="implement auth")
        prompt = mock_run.call_args[0][0]
        assert "spec.md" in prompt
        assert "implement auth" in prompt

    @patch("yui.tools.kiro_tools._run_kiro_cli")
    def test_generic_error(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = RuntimeError("disk full")
        result = kiro_implement(
            spec_path="/tmp/spec.md", task_description="implement"
        )
        assert "Error:" in result
        assert "disk full" in result
