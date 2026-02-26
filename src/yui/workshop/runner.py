"""Workshop Test Runner — integration orchestrator (AC-82, AC-83, AC-84, AC-85)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from yui.workshop.models import (
    ExecutableStep,
    StepOutcome,
    StepResult,
    StepType,
    TestRun,
)
from yui.workshop.reporter import WorkshopReporter
from yui.workshop.resource_manager import ResourceManager

try:
    from yui.workshop.console_auth import ConsoleAuthenticator  # type: ignore[import-not-found]
except ImportError:
    ConsoleAuthenticator = None  # type: ignore[assignment,misc]

try:
    from yui.workshop.executor import StepExecutor  # type: ignore[import-not-found]
except ImportError:
    StepExecutor = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


class WorkshopTimeoutError(Exception):
    """Raised when a step or total timeout is exceeded."""


class WorkshopCostLimitError(Exception):
    """Raised when the cost guard threshold is breached."""


def _parse_step_range(spec: str, total: int) -> set[int]:
    indices: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            start = int(start_s.strip())
            end = int(end_s.strip())
            for i in range(max(1, start), min(total, end) + 1):
                indices.add(i - 1)
        else:
            idx = int(part.strip()) - 1
            if 0 <= idx < total:
                indices.add(idx)
    return indices


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkshopTestRunner:
    """Orchestrates full workshop test execution."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        ws_cfg = config.get("workshop", {}).get("test", {})
        self.timeout_per_step = ws_cfg.get("timeout_per_step_seconds", 300)
        self.max_total_duration = ws_cfg.get("max_total_duration_minutes", 120) * 60
        self.max_cost_usd = ws_cfg.get("max_cost_usd", 10.0)
        self.cleanup_after_test = ws_cfg.get("cleanup_after_test", True)
        self.region = ws_cfg.get("region", "us-east-1")
        self.output_dir = ws_cfg.get(
            "output_dir",
            config.get("workshop", {}).get("test", {}).get(
                "video", {}
            ).get("output_dir", "~/.yui/workshop-tests/"),
        )
        self.reporter = WorkshopReporter()
        self.resource_manager = ResourceManager(
            region=self.region,
            max_cost_usd=self.max_cost_usd,
        )

    async def run_test(
        self,
        workshop_url: str,
        options: dict[str, Any] | None = None,
    ) -> TestRun:
        opts = options or {}
        dry_run: bool = opts.get("dry_run", False)
        step_filter: str | None = opts.get("steps")
        do_cleanup: bool = opts.get("cleanup", self.cleanup_after_test)

        test_id = f"wt-{uuid.uuid4().hex[:8]}"
        test_run = TestRun(
            test_id=test_id,
            workshop_url=workshop_url,
            workshop_title="",
            start_time=_now_iso(),
            output_dir=str(Path(self.output_dir).expanduser()),
        )

        overall_start = time.monotonic()

        try:
            from yui.workshop.scraper import scrape_workshop
            pages = await scrape_workshop(workshop_url)
            if pages:
                test_run.workshop_title = pages[0].title
            logger.info("Scraped %d pages from %s", len(pages), workshop_url)

            from yui.workshop.planner import plan_steps
            bedrock_client = None
            steps = await plan_steps(pages, bedrock_client)
            test_run.steps = steps
            logger.info("Planned %d executable steps", len(steps))

            if step_filter:
                selected = _parse_step_range(step_filter, len(steps))
                steps = [s for i, s in enumerate(steps) if i in selected]
                test_run.steps = steps
                logger.info("Filtered to %d steps (spec=%s)", len(steps), step_filter)

            if dry_run:
                for step in steps:
                    test_run.outcomes.append(
                        StepOutcome(step=step, result=StepResult.NOT_RUN, timestamp=_now_iso())
                    )
                test_run.end_time = _now_iso()
                test_run.total_duration_seconds = time.monotonic() - overall_start
                return test_run

            if StepExecutor is None:
                logger.warning(
                    "StepExecutor not available (C-3/C-4 not installed). "
                    "Marking all steps as NOT_RUN."
                )
                for step in steps:
                    test_run.outcomes.append(
                        StepOutcome(step=step, result=StepResult.NOT_RUN, timestamp=_now_iso())
                    )
            else:
                await self._execute_steps(test_run, steps, overall_start)

        except WorkshopCostLimitError as e:
            logger.error("Cost guard triggered: %s", e)
        except WorkshopTimeoutError as e:
            logger.error("Total timeout exceeded: %s", e)
        except Exception as e:
            logger.error("Unexpected error during test run: %s", e, exc_info=True)
        finally:
            test_run.end_time = _now_iso()
            test_run.total_duration_seconds = time.monotonic() - overall_start

            try:
                report_path = self.reporter.save_report(test_run, self.output_dir)
                logger.info("Report saved: %s", report_path)
            except Exception as e:
                logger.error("Failed to save report: %s", e)

            if do_cleanup and not dry_run:
                try:
                    result = self.resource_manager.cleanup_resources(test_id)
                    logger.info("Cleanup result: %s", result)
                except Exception as e:
                    logger.error("Cleanup failed: %s", e)

        return test_run

    async def _execute_steps(
        self,
        test_run: TestRun,
        steps: list[ExecutableStep],
        overall_start: float,
    ) -> None:
        for step in steps:
            elapsed = time.monotonic() - overall_start
            if elapsed > self.max_total_duration:
                test_run.outcomes.append(
                    StepOutcome(
                        step=step,
                        result=StepResult.TIMEOUT,
                        error_message="Total test duration exceeded",
                        timestamp=_now_iso(),
                    )
                )
                raise WorkshopTimeoutError(
                    f"Total timeout ({self.max_total_duration}s) exceeded after {elapsed:.0f}s"
                )

            if not self.resource_manager.check_cost_guard(test_run.test_id):
                test_run.outcomes.append(
                    StepOutcome(
                        step=step,
                        result=StepResult.FAIL,
                        error_message=f"Cost guard: limit ${self.max_cost_usd} exceeded",
                        timestamp=_now_iso(),
                    )
                )
                raise WorkshopCostLimitError(f"Projected cost exceeds ${self.max_cost_usd}")

            step_timeout = step.timeout_seconds or self.timeout_per_step
            step_start = time.monotonic()

            try:
                outcome = await asyncio.wait_for(
                    self._execute_single_step(step, test_run.test_id),
                    timeout=step_timeout,
                )
                outcome.duration_seconds = time.monotonic() - step_start
                outcome.timestamp = _now_iso()
                test_run.outcomes.append(outcome)
            except asyncio.TimeoutError:
                test_run.outcomes.append(
                    StepOutcome(
                        step=step,
                        result=StepResult.TIMEOUT,
                        error_message=f"Step timeout ({step_timeout}s) exceeded",
                        duration_seconds=time.monotonic() - step_start,
                        timestamp=_now_iso(),
                    )
                )

    async def _execute_single_step(
        self,
        step: ExecutableStep,
        test_id: str,
    ) -> StepOutcome:
        if step.step_type == StepType.CLI_COMMAND and StepExecutor is None:
            return StepOutcome(
                step=step,
                result=StepResult.SKIP,
                error_message="CLI fallback: executor not available",
            )

        if StepExecutor is not None:
            executor = StepExecutor()
            return await executor.execute(step)

        return StepOutcome(
            step=step,
            result=StepResult.NOT_RUN,
            error_message="Executor not available",
        )

    def list_tests(self) -> list[dict[str, Any]]:
        out_dir = Path(self.output_dir).expanduser()
        if not out_dir.exists():
            return []

        tests: list[dict[str, Any]] = []
        for report_file in sorted(out_dir.glob("report-*.md"), reverse=True):
            test_id = report_file.stem.replace("report-", "")
            stat = report_file.stat()
            tests.append({
                "test_id": test_id,
                "file": str(report_file),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            })
        return tests

    def show_report(self, test_id: str) -> str | None:
        out_dir = Path(self.output_dir).expanduser()
        report_path = out_dir / f"report-{test_id}.md"
        if report_path.exists():
            return report_path.read_text(encoding="utf-8")
        return None
