"""Tests for yui.workshop.runner (AC-82, AC-83, AC-84, AC-85)."""
from __future__ import annotations
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from yui.workshop.models import (
    ExecutableStep, StepOutcome, StepResult, StepType, TestRun, WorkshopPage,
)
from yui.workshop.runner import (
    WorkshopCostLimitError, WorkshopTestRunner, WorkshopTimeoutError, _parse_step_range,
)


def _make_config(**overrides):
    cfg = {
        "workshop": {
            "test": {
                "region": "us-east-1", "cleanup_after_test": False,
                "timeout_per_step_seconds": 300, "max_total_duration_minutes": 120,
                "max_cost_usd": 10.0, "output_dir": "/tmp/yui-test-reports",
                "video": {"output_dir": "/tmp/yui-test-reports"},
            },
            "report": {"format": "markdown", "slack_notify": False},
        },
    }
    for k, v in overrides.items():
        cfg["workshop"]["test"][k] = v
    return cfg


def _make_step(step_id="1.0.1", title="Test Step", step_type=StepType.CONSOLE_NAVIGATE,
               timeout_seconds=300):
    return ExecutableStep(step_id=step_id, title=title, step_type=step_type,
                          description="Test step", action={}, expected_result="Success",
                          timeout_seconds=timeout_seconds)


def _make_pages():
    return [WorkshopPage(title="Example Workshop", url="https://catalog.workshops.aws/example",
                         content="Setup instructions", module_index=1, step_index=0)]


class TestParseStepRange:
    def test_single_step(self):
        assert _parse_step_range("3", 5) == {2}

    def test_range(self):
        assert _parse_step_range("1-3", 5) == {0, 1, 2}

    def test_comma_list(self):
        assert _parse_step_range("1,3,5", 5) == {0, 2, 4}

    def test_mixed(self):
        assert _parse_step_range("1-2,4", 5) == {0, 1, 3}

    def test_out_of_range_ignored(self):
        assert _parse_step_range("10", 5) == set()

    def test_full_range(self):
        assert _parse_step_range("1-5", 5) == {0, 1, 2, 3, 4}


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_not_run(self, tmp_path):
        steps = [_make_step(step_id=f"1.0.{i}") for i in range(3)]
        pages = _make_pages()
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=steps),
        ):
            config = _make_config(output_dir=str(tmp_path))
            runner = WorkshopTestRunner(config)
            result = await runner.run_test("https://catalog.workshops.aws/example", {"dry_run": True})
        assert len(result.outcomes) == 3
        assert all(o.result == StepResult.NOT_RUN for o in result.outcomes)
        assert result.test_id.startswith("wt-")

    @pytest.mark.asyncio
    async def test_dry_run_with_step_filter(self, tmp_path):
        steps = [_make_step(step_id=f"1.0.{i}") for i in range(5)]
        pages = _make_pages()
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=steps),
        ):
            config = _make_config(output_dir=str(tmp_path))
            runner = WorkshopTestRunner(config)
            result = await runner.run_test("https://catalog.workshops.aws/example",
                                           {"dry_run": True, "steps": "1-3"})
        assert len(result.outcomes) == 3


class TestExecutionWithoutExecutor:
    @pytest.mark.asyncio
    async def test_marks_steps_not_run(self, tmp_path):
        steps = [_make_step()]
        pages = _make_pages()
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=steps),
            patch("yui.workshop.runner.StepExecutor", None),
        ):
            config = _make_config(output_dir=str(tmp_path))
            runner = WorkshopTestRunner(config)
            result = await runner.run_test("https://catalog.workshops.aws/example")
        assert len(result.outcomes) == 1
        assert result.outcomes[0].result == StepResult.NOT_RUN


class TestTotalTimeout:
    @pytest.mark.asyncio
    async def test_total_timeout_aborts(self, tmp_path):
        steps = [_make_step(step_id=f"1.0.{i}") for i in range(3)]
        pages = _make_pages()
        mock_executor_cls = MagicMock()
        mock_executor = MagicMock()
        async def slow_execute(step):
            return StepOutcome(step=step, result=StepResult.PASS)
        mock_executor.execute = slow_execute
        mock_executor_cls.return_value = mock_executor
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=steps),
            patch("yui.workshop.runner.StepExecutor", mock_executor_cls),
        ):
            config = _make_config(output_dir=str(tmp_path), max_total_duration_minutes=0)
            runner = WorkshopTestRunner(config)
            runner.max_total_duration = 0
            result = await runner.run_test("https://catalog.workshops.aws/example")
        timeout_steps = [o for o in result.outcomes if o.result == StepResult.TIMEOUT]
        assert len(timeout_steps) >= 1


class TestCostGuard:
    @pytest.mark.asyncio
    async def test_cost_guard_aborts_on_exceed(self, tmp_path):
        steps = [_make_step()]
        pages = _make_pages()
        mock_executor_cls = MagicMock()
        mock_executor = MagicMock()
        async def fake_execute(step):
            return StepOutcome(step=step, result=StepResult.PASS)
        mock_executor.execute = fake_execute
        mock_executor_cls.return_value = mock_executor
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=steps),
            patch("yui.workshop.runner.StepExecutor", mock_executor_cls),
        ):
            config = _make_config(output_dir=str(tmp_path))
            runner = WorkshopTestRunner(config)
            runner.resource_manager.check_cost_guard = MagicMock(return_value=False)
            result = await runner.run_test("https://catalog.workshops.aws/example")
        fail_steps = [o for o in result.outcomes if o.result == StepResult.FAIL]
        assert len(fail_steps) >= 1
        assert "cost" in fail_steps[0].error_message.lower()


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_called_when_requested(self, tmp_path):
        pages = _make_pages()
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=[]),
        ):
            config = _make_config(output_dir=str(tmp_path), cleanup_after_test=True)
            runner = WorkshopTestRunner(config)
            runner.resource_manager.cleanup_resources = MagicMock(
                return_value={"deleted": [], "failed": [], "skipped": []})
            await runner.run_test("https://catalog.workshops.aws/example", {"cleanup": True})
            runner.resource_manager.cleanup_resources.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_cleanup_on_dry_run(self, tmp_path):
        pages = _make_pages()
        with (
            patch("yui.workshop.scraper.scrape_workshop", new_callable=AsyncMock, return_value=pages),
            patch("yui.workshop.planner.plan_steps", new_callable=AsyncMock, return_value=[]),
        ):
            config = _make_config(output_dir=str(tmp_path))
            runner = WorkshopTestRunner(config)
            runner.resource_manager.cleanup_resources = MagicMock()
            await runner.run_test("https://catalog.workshops.aws/example",
                                  {"dry_run": True, "cleanup": True})
            runner.resource_manager.cleanup_resources.assert_not_called()


class TestListAndShow:
    def test_list_tests_empty(self, tmp_path):
        config = _make_config(output_dir=str(tmp_path))
        runner = WorkshopTestRunner(config)
        runner.output_dir = str(tmp_path)
        assert runner.list_tests() == []

    def test_list_tests_with_reports(self, tmp_path):
        (tmp_path / "report-wt-abc123.md").write_text("# Report")
        (tmp_path / "report-wt-def456.md").write_text("# Report 2")
        config = _make_config(output_dir=str(tmp_path))
        runner = WorkshopTestRunner(config)
        runner.output_dir = str(tmp_path)
        tests = runner.list_tests()
        assert len(tests) == 2
        test_ids = [t["test_id"] for t in tests]
        assert "wt-abc123" in test_ids
        assert "wt-def456" in test_ids

    def test_show_report_found(self, tmp_path):
        (tmp_path / "report-wt-abc123.md").write_text("# Test Report Content")
        config = _make_config(output_dir=str(tmp_path))
        runner = WorkshopTestRunner(config)
        runner.output_dir = str(tmp_path)
        content = runner.show_report("wt-abc123")
        assert content == "# Test Report Content"

    def test_show_report_not_found(self, tmp_path):
        config = _make_config(output_dir=str(tmp_path))
        runner = WorkshopTestRunner(config)
        runner.output_dir = str(tmp_path)
        content = runner.show_report("wt-nonexistent")
        assert content is None
