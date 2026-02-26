"""Tests for yui.cli workshop subcommands (AC-82, AC-85)."""
from __future__ import annotations
import sys
from io import StringIO
from unittest.mock import MagicMock, patch
import pytest
from yui.workshop.models import TestRun


def _make_test_run():
    return TestRun(test_id="wt-abc12345", workshop_url="https://catalog.workshops.aws/example",
                   workshop_title="Example Workshop", outcomes=[],
                   start_time="2026-02-26T10:00:00+00:00", end_time="2026-02-26T10:02:00+00:00",
                   total_duration_seconds=120.0)


def _run_cli(args):
    from yui.cli import main
    old_argv, old_stdout, old_stderr = sys.argv, sys.stdout, sys.stderr
    sys.argv = ["yui"] + args
    stdout_buf, stderr_buf = StringIO(), StringIO()
    sys.stdout, sys.stderr = stdout_buf, stderr_buf
    exit_code = 0
    try:
        main()
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    finally:
        sys.argv, sys.stdout, sys.stderr = old_argv, old_stdout, old_stderr
    return exit_code, stdout_buf.getvalue(), stderr_buf.getvalue()


class TestWorkshopTestCommand:
    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_test_command_basic(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        test_run = _make_test_run()
        with patch("asyncio.run", side_effect=lambda coro: test_run):
            code, out, err = _run_cli(["workshop", "test", "https://catalog.workshops.aws/example"])
        assert code == 0
        assert "Starting workshop test" in out

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_dry_run_flag(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        test_run = _make_test_run()
        with patch("asyncio.run", return_value=test_run):
            code, out, err = _run_cli(["workshop", "test", "https://catalog.workshops.aws/example", "--dry-run"])
        assert code == 0
        assert "Dry-run" in out

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_cron_flag(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        test_run = _make_test_run()
        with patch("asyncio.run", return_value=test_run):
            code, out, err = _run_cli(["workshop", "test", "https://catalog.workshops.aws/example", "--cron"])
        assert code == 0
        assert "Regression mode" in out

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_steps_flag(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        test_run = _make_test_run()
        with patch("asyncio.run", return_value=test_run):
            code, out, err = _run_cli(["workshop", "test", "https://catalog.workshops.aws/example", "--steps", "1-3"])
        assert code == 0

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_record_flag(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        test_run = _make_test_run()
        with patch("asyncio.run", return_value=test_run):
            code, out, err = _run_cli(["workshop", "test", "https://catalog.workshops.aws/example", "--record"])
        assert code == 0


class TestWorkshopListTests:
    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_list_tests_empty(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.list_tests.return_value = []
        code, out, err = _run_cli(["workshop", "list-tests"])
        assert code == 0
        assert "No test runs found" in out

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_list_tests_with_results(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.list_tests.return_value = [
            {"test_id": "wt-abc123", "modified": "2026-02-26T10:00:00", "size": 1234, "file": "/tmp/r.md"},
        ]
        code, out, err = _run_cli(["workshop", "list-tests"])
        assert code == 0
        assert "wt-abc123" in out


class TestWorkshopShowReport:
    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_show_report_found(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.show_report.return_value = "# Test Report Content"
        code, out, err = _run_cli(["workshop", "show-report", "wt-abc123"])
        assert code == 0
        assert "# Test Report Content" in out

    @patch("yui.config.load_config")
    @patch("yui.workshop.runner.WorkshopTestRunner")
    def test_show_report_not_found(self, mock_runner_cls, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        mock_runner = MagicMock()
        mock_runner_cls.return_value = mock_runner
        mock_runner.show_report.return_value = None
        code, out, err = _run_cli(["workshop", "show-report", "wt-nonexistent"])
        assert code == 1
        assert "Report not found" in err


class TestWorkshopNoAction:
    @patch("yui.config.load_config")
    def test_no_workshop_action(self, mock_load_config):
        mock_load_config.return_value = {"workshop": {"test": {"output_dir": "/tmp"}}}
        code, out, err = _run_cli(["workshop"])
        assert code == 1
        assert "Usage" in err
