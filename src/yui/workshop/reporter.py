"""Workshop Test Reporter — structured reports and Slack notifications (AC-78, AC-79)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from yui.workshop.models import StepOutcome, StepResult, TestRun

logger = logging.getLogger(__name__)

_RESULT_EMOJI: dict[StepResult, str] = {
    StepResult.PASS: "✅",
    StepResult.FAIL: "❌",
    StepResult.SKIP: "⏭️",
    StepResult.TIMEOUT: "⏰",
    StepResult.NOT_RUN: "⬜",
}


def _fmt_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    if mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def _count_by_result(outcomes: list[StepOutcome]) -> dict[StepResult, int]:
    counts: dict[StepResult, int] = {}
    for o in outcomes:
        counts[o.result] = counts.get(o.result, 0) + 1
    return counts


class WorkshopReporter:
    def generate_report(self, test_run: TestRun) -> str:
        lines: list[str] = []
        date_str = test_run.start_time or datetime.now(timezone.utc).isoformat()
        lines.append(f"# Workshop Test Report — {date_str}")
        lines.append("")
        lines.append(f"**Workshop:** {test_run.workshop_title}")
        lines.append(f"**URL:** {test_run.workshop_url}")
        lines.append(f"**Test ID:** {test_run.test_id}")
        lines.append("")

        counts = _count_by_result(test_run.outcomes)
        total = len(test_run.outcomes)
        passed = counts.get(StepResult.PASS, 0)
        failed = counts.get(StepResult.FAIL, 0)
        skipped = counts.get(StepResult.SKIP, 0)
        timed_out = counts.get(StepResult.TIMEOUT, 0)
        duration = _fmt_duration(test_run.total_duration_seconds)

        lines.append("## Summary")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Total Steps | {total} |")
        lines.append(f"| Passed | {passed} |")
        lines.append(f"| Failed | {failed} |")
        lines.append(f"| Skipped | {skipped} |")
        lines.append(f"| Timed Out | {timed_out} |")
        lines.append(f"| Duration | {duration} |")
        lines.append("")

        videos = [o for o in test_run.outcomes if o.video_path]
        if videos:
            lines.append("## Video Recordings")
            lines.append("")
            for o in videos:
                lines.append(
                    f"- **{o.step.title}** ({o.step.step_id}): "
                    f"[{o.video_path}]({o.video_path})"
                )
            lines.append("")

        lines.append("## Step Results")
        lines.append("")
        lines.append("| # | Step | Type | Result | Duration |")
        lines.append("|---|------|------|--------|----------|")
        for o in test_run.outcomes:
            emoji = _RESULT_EMOJI.get(o.result, "❓")
            lines.append(
                f"| {o.step.step_id} "
                f"| {o.step.title} "
                f"| {o.step.step_type.value} "
                f"| {emoji} {o.result.value} "
                f"| {_fmt_duration(o.duration_seconds)} |"
            )
        lines.append("")

        failed_outcomes = [
            o for o in test_run.outcomes
            if o.result in (StepResult.FAIL, StepResult.TIMEOUT)
        ]
        if failed_outcomes:
            lines.append("## Failed Steps Detail")
            lines.append("")
            for o in failed_outcomes:
                lines.append(f"### {o.step.step_id}: {o.step.title}")
                lines.append("")
                if o.error_message:
                    lines.append(f"**Error:** {o.error_message}")
                    lines.append("")
                if o.screenshot_path:
                    lines.append(f"**Screenshot:** ![screenshot]({o.screenshot_path})")
                    lines.append("")
                if o.actual_output:
                    lines.append("**Actual Output:**")
                    lines.append("```")
                    lines.append(o.actual_output)
                    lines.append("```")
                    lines.append("")

        lines.append("## AWS Resources Created")
        lines.append("")
        lines.append(
            f"_Resource tracking managed by ResourceManager "
            f"(tag: `yui:workshop-test={test_run.test_id}`)_"
        )
        lines.append("")
        return "\n".join(lines)

    def generate_slack_summary(self, test_run: TestRun) -> str:
        counts = _count_by_result(test_run.outcomes)
        total = len(test_run.outcomes)
        passed = counts.get(StepResult.PASS, 0)
        failed = counts.get(StepResult.FAIL, 0)
        skipped = counts.get(StepResult.SKIP, 0)
        timed_out = counts.get(StepResult.TIMEOUT, 0)
        duration = _fmt_duration(test_run.total_duration_seconds)

        if failed > 0 or timed_out > 0:
            status = "🔴 FAIL"
        elif total > 0 and passed == total:
            status = "🟢 PASS"
        else:
            status = "🟡 PARTIAL"

        parts: list[str] = [
            f"*Workshop Test Result: {status}*",
            f"📘 {test_run.workshop_title}",
            f"🆔 `{test_run.test_id}`",
            f"✅ {passed}/{total} passed | ❌ {failed} failed | ⏭️ {skipped} skipped | ⏰ {timed_out} timeout",
            f"⏱️ {duration}",
        ]

        failed_names = [
            o.step.title
            for o in test_run.outcomes
            if o.result in (StepResult.FAIL, StepResult.TIMEOUT)
        ]
        if failed_names:
            parts.append("❌ Failed: " + ", ".join(failed_names[:5]))
            if len(failed_names) > 5:
                parts.append(f"   ...and {len(failed_names) - 5} more")

        return "\n".join(parts)

    def save_report(self, test_run: TestRun, output_dir: str) -> str:
        report_content = self.generate_report(test_run)
        out_path = Path(os.path.expanduser(output_dir))
        out_path.mkdir(parents=True, exist_ok=True)
        filename = f"report-{test_run.test_id}.md"
        filepath = out_path / filename
        filepath.write_text(report_content, encoding="utf-8")
        logger.info("Report saved to %s", filepath)
        return str(filepath.resolve())
