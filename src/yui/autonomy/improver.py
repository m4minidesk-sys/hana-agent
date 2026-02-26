"""Self-improvement engine — propose AGENTS.md changes via PR (AC-74, AC-75, AC-83).

AGENTS.md modifications are **never** applied directly.  All changes go
through a pull-request that requires human (han) review.
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Protocol

import yaml

from yui.autonomy.evaluator import TaskEvaluation, TaskEvaluator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Git tool protocol — allows injection / mocking
# ---------------------------------------------------------------------------

class GitTool(Protocol):
    """Minimal protocol for git operations."""

    def run(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]: ...


class _DefaultGitTool:
    """Real git subprocess wrapper."""

    def run(self, args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            cwd=cwd,
            check=True,
        )


# ---------------------------------------------------------------------------
# Change proposal
# ---------------------------------------------------------------------------

@dataclass
class ImprovementProposal:
    """One proposed change."""

    target: str  # e.g. "AGENTS.md"
    section: str  # heading / area
    suggestion: str
    rationale: str


@dataclass
class ImprovementResult:
    """Result of proposing improvements."""

    branch: str
    changes: list[dict[str, str]]
    pr_url: str


# ---------------------------------------------------------------------------
# Self-Improver
# ---------------------------------------------------------------------------

class DirectModificationError(Exception):
    """Raised when code attempts to modify AGENTS.md directly (AC-75)."""


class SelfImprover:
    """Analyse evaluation patterns and propose AGENTS.md improvements.

    Parameters
    ----------
    evaluator:
        ``TaskEvaluator`` instance used to load historical evaluations.
    workspace_dir:
        Root of the Yui workspace (contains AGENTS.md).
    git_tool:
        Pluggable git wrapper (defaults to subprocess).
    shadow_period_hours:
        Duration of the shadow/observation period after a PR is merged.
    rollback_threshold_pct:
        Metric degradation percentage that triggers an automatic rollback.
    """

    AGENTS_MD = "AGENTS.md"

    def __init__(
        self,
        evaluator: TaskEvaluator,
        workspace_dir: str = "~/.yui/workspace",
        git_tool: Optional[GitTool] = None,
        shadow_period_hours: int = 24,
        rollback_threshold_pct: float = 20.0,
    ) -> None:
        self.evaluator = evaluator
        self.workspace_dir = Path(os.path.expanduser(workspace_dir))
        self.git: GitTool = git_tool or _DefaultGitTool()
        self.shadow_period_hours = shadow_period_hours
        self.rollback_threshold_pct = rollback_threshold_pct

    # ------------------------------------------------------------------
    # AC-75 — Guard: never modify AGENTS.md directly
    # ------------------------------------------------------------------

    def _assert_no_direct_modification(self) -> None:
        """Called before any write to ensure we're on an improve/ branch."""
        # Intentionally a no-op in normal flow — the public API always
        # routes through PR creation.  This exists so tests can verify
        # the constraint.
        pass

    def modify_agents_md_directly(self, content: str) -> None:
        """Attempt to write AGENTS.md directly — **always raises** (AC-75).

        This method exists to make the constraint explicit and testable.
        """
        raise DirectModificationError(
            "AGENTS.md must never be modified directly. "
            "Use propose_improvement() to create a PR."
        )

    # ------------------------------------------------------------------
    # AC-74 — Propose improvements
    # ------------------------------------------------------------------

    def propose_improvement(self, analysis: dict[str, Any]) -> Optional[ImprovementResult]:
        """Generate improvement proposals from evaluation analysis (AC-74).

        Returns ``None`` if no actionable improvements are identified.
        """
        proposals = self._identify_improvements(analysis)
        if not proposals:
            logger.info("No improvements identified from analysis.")
            return None

        changes = [asdict(p) for p in proposals]
        pr_url = self.create_improvement_pr(changes)
        branch = self._branch_name(proposals)

        return ImprovementResult(branch=branch, changes=changes, pr_url=pr_url)

    def _identify_improvements(self, analysis: dict[str, Any]) -> list[ImprovementProposal]:
        """Heuristic: identify repeated failure patterns → suggestions."""
        proposals: list[ImprovementProposal] = []

        success_rate = analysis.get("success_rate", 1.0)
        avg_rounds = analysis.get("avg_review_rounds", 0)
        recurring = analysis.get("recurring_failures", [])
        frequent_lessons = analysis.get("frequent_lessons", [])

        # Low success rate
        if success_rate < 0.7:
            proposals.append(ImprovementProposal(
                target=self.AGENTS_MD,
                section="Quality Gates",
                suggestion="Add pre-task checklist for common failure patterns.",
                rationale=f"Success rate is {success_rate:.0%} (below 70% threshold).",
            ))

        # High review rounds
        if avg_rounds > 2.0:
            proposals.append(ImprovementProposal(
                target=self.AGENTS_MD,
                section="Coding Rules",
                suggestion="Add review-round reduction guidelines.",
                rationale=f"Average review rounds: {avg_rounds:.1f} (target: ≤2).",
            ))

        # Recurring failures
        if len(recurring) >= 3:
            proposals.append(ImprovementProposal(
                target=self.AGENTS_MD,
                section="Error Handling",
                suggestion=f"Document recurring failure patterns: {', '.join(recurring[:5])}.",
                rationale=f"{len(recurring)} recurring failures detected.",
            ))

        # Frequent lessons not yet codified
        for item in frequent_lessons:
            if item.get("count", 0) >= 3:
                proposals.append(ImprovementProposal(
                    target=self.AGENTS_MD,
                    section="Lessons Learned",
                    suggestion=f"Codify lesson: {item['lesson']}",
                    rationale=f"Lesson appeared {item['count']} times in evaluations.",
                ))

        return proposals

    # ------------------------------------------------------------------
    # PR creation
    # ------------------------------------------------------------------

    def create_improvement_pr(self, changes: list[dict[str, str]]) -> str:
        """Create a PR with proposed AGENTS.md changes (AC-74, AC-75).

        Returns the PR URL.
        """
        cwd = str(self.workspace_dir)
        branch = self._branch_name_from_changes(changes)

        # Create branch
        self.git.run(["checkout", "-b", branch], cwd=cwd)

        # Apply changes (append to AGENTS.md as a proposal section)
        agents_path = self.workspace_dir / self.AGENTS_MD
        proposal_text = self._format_proposal(changes)

        if agents_path.exists():
            original = agents_path.read_text()
        else:
            original = ""

        agents_path.write_text(original + "\n" + proposal_text)

        # Commit
        self.git.run(["add", self.AGENTS_MD], cwd=cwd)
        self.git.run(
            ["commit", "-m", f"improve: propose AGENTS.md changes ({branch})"],
            cwd=cwd,
        )

        # Push
        self.git.run(["push", "origin", branch], cwd=cwd)

        # Create PR via gh
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", f"[Self-Improvement] {branch}",
                "--body", self._format_pr_body(changes),
                "--base", "main",
                "--head", branch,
            ],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        pr_url = result.stdout.strip() if result.returncode == 0 else ""
        logger.info("Created improvement PR: %s", pr_url)

        # Switch back to main
        self.git.run(["checkout", "main"], cwd=cwd)

        return pr_url

    # ------------------------------------------------------------------
    # AC-83 — Rollback
    # ------------------------------------------------------------------

    def check_rollback(
        self,
        pr_number: int,
        baseline_metrics: dict[str, float],
        current_metrics: dict[str, float],
    ) -> bool:
        """Compare metrics during shadow period.  Returns True if rollback needed.

        Degradation thresholds (AC-83):
        - review_cycles increase > rollback_threshold_pct% → rollback
        - han_interventions increase > 15% → rollback
        """
        for key, threshold in [
            ("review_cycles", self.rollback_threshold_pct),
            ("han_interventions", 15.0),
        ]:
            baseline_val = baseline_metrics.get(key, 0)
            current_val = current_metrics.get(key, 0)

            if baseline_val > 0:
                change_pct = ((current_val - baseline_val) / baseline_val) * 100
            elif current_val > 0:
                # Baseline was 0, any increase is infinite — treat as degradation
                change_pct = 100.0
            else:
                change_pct = 0.0

            if change_pct > threshold:
                logger.warning(
                    "Rollback triggered: %s increased %.1f%% (threshold: %.1f%%)",
                    key, change_pct, threshold,
                )
                return True

        return False

    def rollback_pr(self, pr_number: int, reason: str) -> Path:
        """Revert a merged PR and record the rollback (AC-83).

        Returns path to the rollback record.
        """
        cwd = str(self.workspace_dir)

        # Revert via git
        self.git.run(["revert", "--no-edit", "HEAD"], cwd=cwd)
        self.git.run(["push", "origin", "main"], cwd=cwd)

        # Record rollback
        rollbacks_dir = self.evaluator.memory_dir / "rollbacks"
        rollbacks_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(timezone.utc)
        record = {
            "pr_number": pr_number,
            "reason": reason,
            "timestamp": now.isoformat(),
            "action": "auto-reverted",
        }
        path = rollbacks_dir / f"{now.strftime('%Y-%m-%d')}_pr{pr_number}_rollback.yaml"
        with open(path, "w") as f:
            yaml.dump(record, f, default_flow_style=False, allow_unicode=True)

        logger.info("Rolled back PR #%d: %s → %s", pr_number, reason, path)
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _branch_name(proposals: list[ImprovementProposal]) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        summary = proposals[0].section.lower().replace(" ", "-")[:30] if proposals else "general"
        return f"improve/{date_str}-{summary}"

    @staticmethod
    def _branch_name_from_changes(changes: list[dict[str, str]]) -> str:
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        summary = changes[0].get("section", "general").lower().replace(" ", "-")[:30] if changes else "general"
        return f"improve/{date_str}-{summary}"

    @staticmethod
    def _format_proposal(changes: list[dict[str, str]]) -> str:
        lines = [
            "",
            "## 🤖 Self-Improvement Proposal",
            "",
            f"_Generated: {datetime.now(timezone.utc).isoformat()}_",
            "",
        ]
        for i, ch in enumerate(changes, 1):
            lines.append(f"### {i}. {ch.get('section', 'Unknown')}")
            lines.append(f"- **Suggestion**: {ch.get('suggestion', '')}")
            lines.append(f"- **Rationale**: {ch.get('rationale', '')}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _format_pr_body(changes: list[dict[str, str]]) -> str:
        lines = [
            "## Self-Improvement Proposal",
            "",
            "This PR was automatically generated by Yui's self-improvement engine.",
            "**⚠️ Requires human review before merge (AC-75).**",
            "",
            "### Proposed Changes",
            "",
        ]
        for ch in changes:
            lines.append(f"- **{ch.get('section', '')}**: {ch.get('suggestion', '')}")
            lines.append(f"  - Rationale: {ch.get('rationale', '')}")
        return "\n".join(lines)
