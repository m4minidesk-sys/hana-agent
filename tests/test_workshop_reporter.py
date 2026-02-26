"""Tests for yui.workshop.reporter (AC-78, AC-79)."""
from __future__ import annotations
import os
from pathlib import Path
import pytest
from yui.workshop.models import (
    ExecutableStep, StepOutcome, StepResult, StepType, TestRun,
)
from yui.workshop.reporter import WorkshopReporter, _count_by_result, _fmt_duration


def _make_step(step_id="1.0.1", title="Navigate to S3", step_type=StepType.CONSOLE_NAVIGATE,
               description="Open the S3 console", action=None, expected_result="S3 console opens",
               timeout_seconds=300):
    return ExecutableStep(step_id=step_id, title=title, step_type=step_type, description=description,
                          action=action or {}, expected_result=expected_result, timeout_seconds=timeout_seconds)


def _make_outcome(step=None, result=StepResult.PASS, actual_output="", screenshot_path=None,
                  video_path=None, error_message="", duration_seconds=5.0,
                  timestamp="2026-02-26T10:00:00+00:00"):
    return StepOutcome(step=step or _make_step(), result=result, actual_output=actual_output,
                       screenshot_path=screenshot_path, video_path=video_path,
                       error_message=error_message, duration_seconds=duration_seconds, timestamp=timestamp)


def _make_test_run(test_id="wt-abc12345", outcomes=None, total_duration_seconds=120.0):
    return TestRun(test_id=test_id, workshop_url="https://catalog.workshops.aws/example",
                   workshop_title="Example Workshop", outcomes=outcomes or [],
                   start_time="2026-02-26T10:00:00+00:00", end_time="2026-02-26T10:02:00+00:00",
                   total_duration_seconds=total_duration_seconds, output_dir="/tmp/test-reports")


class TestFmtDuration:
    def test_seconds_only(self):
        assert _fmt_duration(45) == "45s"

    def test_minutes_and_seconds(self):
        assert _fmt_duration(150) == "2m 30s"

    def test_zero(self):
        assert _fmt_duration(0) == "0s"

    def test_negative_clamped(self):
        assert _fmt_duration(-5) == "0s"


class TestCountByResult:
    def test_empty(self):
        assert _count_by_result([]) == {}

    def test_mixed(self):
        outcomes = [
            _make_outcome(result=StepResult.PASS), _make_outcome(result=StepResult.PASS),
            _make_outcome(result=StepResult.FAIL), _make_outcome(result=StepResult.SKIP),
        ]
        counts = _count_by_result(outcomes)
        assert counts[StepResult.PASS] == 2
        assert counts[StepResult.FAIL] == 1
        assert counts[StepResult.SKIP] == 1


class TestGenerateReport:
    def test_all_pass(self):
        steps = [_make_step(step_id=f"1.0.{i}", title=f"Step {i}") for i in range(3)]
        outcomes = [_make_outcome(step=s, result=StepResult.PASS) for s in steps]
        run = _make_test_run(outcomes=outcomes)
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "# Workshop Test Report" in md
        assert "Example Workshop" in md
        assert "wt-abc12345" in md
        assert "| Passed | 3 |" in md
        assert "| Failed | 0 |" in md
        assert "## Failed Steps Detail" not in md

    def test_all_fail(self):
        step = _make_step(step_id="1.0.1", title="Create Bucket")
        outcome = _make_outcome(step=step, result=StepResult.FAIL,
                                error_message="Access denied", screenshot_path="/tmp/screenshot.png")
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "| Failed | 1 |" in md
        assert "## Failed Steps Detail" in md
        assert "Access denied" in md
        assert "screenshot.png" in md

    def test_mixed_results(self):
        steps = [_make_step(step_id="1.0.1", title="Setup"),
                 _make_step(step_id="1.0.2", title="Deploy"),
                 _make_step(step_id="1.0.3", title="Verify")]
        outcomes = [_make_outcome(step=steps[0], result=StepResult.PASS),
                    _make_outcome(step=steps[1], result=StepResult.FAIL, error_message="Deploy failed"),
                    _make_outcome(step=steps[2], result=StepResult.SKIP)]
        run = _make_test_run(outcomes=outcomes)
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "| Passed | 1 |" in md
        assert "| Failed | 1 |" in md
        assert "| Skipped | 1 |" in md

    def test_empty_test_run(self):
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "# Workshop Test Report" in md
        assert "| Total Steps | 0 |" in md
        assert "## Step Results" in md

    def test_video_links_included(self):
        step = _make_step(step_id="1.0.1", title="Video Step")
        outcome = _make_outcome(step=step, result=StepResult.PASS, video_path="/tmp/videos/step1.mp4")
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "## Video Recordings" in md
        assert "/tmp/videos/step1.mp4" in md

    def test_no_video_section_when_no_videos(self):
        step = _make_step()
        outcome = _make_outcome(step=step, result=StepResult.PASS)
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "## Video Recordings" not in md

    def test_screenshot_in_failed_detail(self):
        step = _make_step(step_id="2.0.1", title="Failing Step")
        outcome = _make_outcome(step=step, result=StepResult.FAIL,
                                screenshot_path="/tmp/fail.png", error_message="Element not found")
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "![screenshot](/tmp/fail.png)" in md
        assert "Element not found" in md

    def test_timeout_shown_in_failed_detail(self):
        step = _make_step(step_id="3.0.1", title="Slow Step")
        outcome = _make_outcome(step=step, result=StepResult.TIMEOUT, error_message="Step timeout exceeded")
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "## Failed Steps Detail" in md
        assert "Slow Step" in md
        assert "Step timeout exceeded" in md

    def test_actual_output_in_failed_detail(self):
        step = _make_step(step_id="4.0.1", title="CLI Step")
        outcome = _make_outcome(step=step, result=StepResult.FAIL,
                                actual_output="Error: permission denied", error_message="Command failed")
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "**Actual Output:**" in md
        assert "Error: permission denied" in md

    def test_aws_resources_section_present(self):
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "## AWS Resources Created" in md
        assert "yui:workshop-test=wt-abc12345" in md

    def test_step_results_table_columns(self):
        step = _make_step(step_id="1.0.1", title="Test Step", step_type=StepType.CLI_COMMAND)
        outcome = _make_outcome(step=step, result=StepResult.PASS, duration_seconds=10.0)
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        md = reporter.generate_report(run)
        assert "| # | Step | Type | Result | Duration |" in md
        assert "cli_command" in md


class TestGenerateSlackSummary:
    def test_all_pass(self):
        steps = [_make_step(step_id=f"1.0.{i}") for i in range(3)]
        outcomes = [_make_outcome(step=s, result=StepResult.PASS) for s in steps]
        run = _make_test_run(outcomes=outcomes)
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "🟢 PASS" in summary
        assert "3/3 passed" in summary
        assert "wt-abc12345" in summary

    def test_has_failures(self):
        step = _make_step(step_id="1.0.1", title="Broken Step")
        outcome = _make_outcome(step=step, result=StepResult.FAIL)
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "🔴 FAIL" in summary
        assert "❌ Failed: Broken Step" in summary

    def test_partial_pass(self):
        outcomes = [_make_outcome(step=_make_step(step_id="1"), result=StepResult.PASS),
                    _make_outcome(step=_make_step(step_id="2"), result=StepResult.SKIP)]
        run = _make_test_run(outcomes=outcomes)
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "🟡 PARTIAL" in summary

    def test_empty_run(self):
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "0/0 passed" in summary
        assert "wt-abc12345" in summary

    def test_timeout_counts_as_fail(self):
        step = _make_step(step_id="1.0.1", title="Timeout Step")
        outcome = _make_outcome(step=step, result=StepResult.TIMEOUT)
        run = _make_test_run(outcomes=[outcome])
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "🔴 FAIL" in summary
        assert "Timeout Step" in summary

    def test_many_failures_truncated(self):
        outcomes = [_make_outcome(step=_make_step(step_id=f"1.0.{i}", title=f"Step {i}"),
                                  result=StepResult.FAIL) for i in range(8)]
        run = _make_test_run(outcomes=outcomes)
        reporter = WorkshopReporter()
        summary = reporter.generate_slack_summary(run)
        assert "...and 3 more" in summary


class TestSaveReport:
    def test_saves_to_file(self, tmp_path):
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        path = reporter.save_report(run, str(tmp_path))
        assert os.path.exists(path)
        assert path.endswith("report-wt-abc12345.md")
        content = Path(path).read_text()
        assert "# Workshop Test Report" in content

    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "subdir" / "reports"
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        path = reporter.save_report(run, str(new_dir))
        assert os.path.exists(path)
        assert new_dir.exists()

    def test_overwrites_existing(self, tmp_path):
        run = _make_test_run(outcomes=[])
        reporter = WorkshopReporter()
        path1 = reporter.save_report(run, str(tmp_path))
        path2 = reporter.save_report(run, str(tmp_path))
        assert path1 == path2
