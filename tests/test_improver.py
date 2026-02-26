"""Tests for yui.autonomy.improver — Self-Improvement (AC-74, AC-75, AC-83)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest
import yaml

from yui.autonomy.evaluator import TaskEvaluation, TaskEvaluator
from yui.autonomy.improver import (
    DirectModificationError,
    ImprovementResult,
    SelfImprover,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    return tmp_path / "memory"


@pytest.fixture()
def workspace_dir(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir()
    (ws / "AGENTS.md").write_text("# AGENTS.md\n\nOriginal content.\n")
    return ws


@pytest.fixture()
def evaluator(memory_dir: Path) -> TaskEvaluator:
    return TaskEvaluator(memory_dir=str(memory_dir), schema_path="/nonexistent")


@pytest.fixture()
def mock_git() -> MagicMock:
    git = MagicMock()
    git.run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    return git


@pytest.fixture()
def improver(evaluator: TaskEvaluator, workspace_dir: Path, mock_git: MagicMock) -> SelfImprover:
    return SelfImprover(
        evaluator=evaluator,
        workspace_dir=str(workspace_dir),
        git_tool=mock_git,
        shadow_period_hours=24,
        rollback_threshold_pct=20.0,
    )


def _low_success_analysis() -> dict:
    return {
        "total": 10,
        "success_rate": 0.5,
        "avg_review_rounds": 3.5,
        "total_critical_findings": 8,
        "frequent_lessons": [
            {"lesson": "Run tests before push", "count": 5},
        ],
        "recurring_failures": ["task-a", "task-b", "task-c"],
    }


def _healthy_analysis() -> dict:
    return {
        "total": 20,
        "success_rate": 0.95,
        "avg_review_rounds": 1.2,
        "total_critical_findings": 1,
        "frequent_lessons": [],
        "recurring_failures": [],
    }


# --------------------------------------------------------------------------
# AC-75: Direct AGENTS.md modification is FORBIDDEN
# --------------------------------------------------------------------------


class TestAC75DirectModificationForbidden:
    """AGENTS.md must never be modified directly — always via PR."""

    def test_modify_agents_md_directly_raises(self, improver: SelfImprover):
        with pytest.raises(DirectModificationError):
            improver.modify_agents_md_directly("new content")

    def test_direct_modification_error_message(self, improver: SelfImprover):
        with pytest.raises(DirectModificationError, match="AGENTS.md must never be modified directly"):
            improver.modify_agents_md_directly("anything")

    def test_propose_improvement_uses_pr(self, improver: SelfImprover):
        """propose_improvement creates a PR, not a direct edit."""
        analysis = _low_success_analysis()
        with patch.object(improver, "create_improvement_pr", return_value="https://github.com/pr/1") as mock_pr:
            result = improver.propose_improvement(analysis)
        assert result is not None
        mock_pr.assert_called_once()


# --------------------------------------------------------------------------
# AC-74: Propose improvements from evaluation patterns
# --------------------------------------------------------------------------


class TestProposeImprovement:
    """AC-74: Weekly cron analyzes evaluation patterns → proposes AGENTS.md improvements as PR."""

    def test_no_improvements_for_healthy_analysis(self, improver: SelfImprover):
        result = improver.propose_improvement(_healthy_analysis())
        assert result is None

    def test_low_success_rate_triggers_proposal(self, improver: SelfImprover):
        analysis = {"success_rate": 0.5, "avg_review_rounds": 1.0, "recurring_failures": [], "frequent_lessons": []}
        with patch.object(improver, "create_improvement_pr", return_value=""):
            result = improver.propose_improvement(analysis)
        assert result is not None

    def test_high_review_rounds_triggers_proposal(self, improver: SelfImprover):
        analysis = {"success_rate": 0.9, "avg_review_rounds": 3.5, "recurring_failures": [], "frequent_lessons": []}
        with patch.object(improver, "create_improvement_pr", return_value=""):
            result = improver.propose_improvement(analysis)
        assert result is not None

    def test_recurring_failures_triggers_proposal(self, improver: SelfImprover):
        analysis = {"success_rate": 0.9, "avg_review_rounds": 1.0, "recurring_failures": ["a", "b", "c"], "frequent_lessons": []}
        with patch.object(improver, "create_improvement_pr", return_value=""):
            result = improver.propose_improvement(analysis)
        assert result is not None

    def test_frequent_lessons_triggers_proposal(self, improver: SelfImprover):
        analysis = {
            "success_rate": 0.9,
            "avg_review_rounds": 1.0,
            "recurring_failures": [],
            "frequent_lessons": [{"lesson": "Always check types", "count": 5}],
        }
        with patch.object(improver, "create_improvement_pr", return_value=""):
            result = improver.propose_improvement(analysis)
        assert result is not None

    def test_proposal_result_has_branch_and_changes(self, improver: SelfImprover):
        analysis = _low_success_analysis()
        with patch.object(improver, "create_improvement_pr", return_value="https://example.com/pr/42"):
            result = improver.propose_improvement(analysis)
        assert result is not None
        assert result.branch.startswith("improve/")
        assert len(result.changes) > 0
        assert result.pr_url == "https://example.com/pr/42"


# --------------------------------------------------------------------------
# create_improvement_pr — git operations
# --------------------------------------------------------------------------


class TestCreateImprovementPR:
    """PR creation via git tool."""

    def test_creates_branch(self, improver: SelfImprover, mock_git: MagicMock):
        changes = [{"section": "Quality Gates", "suggestion": "Add checklist", "rationale": "Low success"}]
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="https://pr-url")
            improver.create_improvement_pr(changes)

        # Should have called git checkout -b improve/...
        checkout_calls = [c for c in mock_git.run.call_args_list if "checkout" in c.args[0] and "-b" in c.args[0]]
        assert len(checkout_calls) >= 1

    def test_commits_and_pushes(self, improver: SelfImprover, mock_git: MagicMock):
        changes = [{"section": "X", "suggestion": "Y", "rationale": "Z"}]
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="url")
            improver.create_improvement_pr(changes)

        git_commands = [c.args[0] for c in mock_git.run.call_args_list]
        assert any("commit" in cmd for cmd in git_commands)
        assert any("push" in cmd for cmd in git_commands)

    def test_switches_back_to_main(self, improver: SelfImprover, mock_git: MagicMock):
        changes = [{"section": "X", "suggestion": "Y", "rationale": "Z"}]
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="url")
            improver.create_improvement_pr(changes)

        last_call = mock_git.run.call_args_list[-1]
        assert "checkout" in last_call.args[0] and "main" in last_call.args[0]

    def test_appends_to_agents_md(self, improver: SelfImprover, mock_git: MagicMock, workspace_dir: Path):
        changes = [{"section": "Testing", "suggestion": "Add integration tests", "rationale": "Coverage gap"}]
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="url")
            improver.create_improvement_pr(changes)

        agents_content = (workspace_dir / "AGENTS.md").read_text()
        assert "Self-Improvement Proposal" in agents_content
        assert "Add integration tests" in agents_content


# --------------------------------------------------------------------------
# AC-83: Rollback when metrics degrade >20%
# --------------------------------------------------------------------------


class TestCheckRollback:
    """AC-83: Auto-revert if metrics degrade >20% within 24h shadow period."""

    def test_no_rollback_when_metrics_improve(self, improver: SelfImprover):
        baseline = {"review_cycles": 10, "han_interventions": 5}
        current = {"review_cycles": 8, "han_interventions": 4}
        assert improver.check_rollback(1, baseline, current) is False

    def test_no_rollback_within_threshold(self, improver: SelfImprover):
        baseline = {"review_cycles": 10, "han_interventions": 5}
        current = {"review_cycles": 11, "han_interventions": 5}  # 10% increase
        assert improver.check_rollback(1, baseline, current) is False

    def test_rollback_on_review_cycles_increase_above_20(self, improver: SelfImprover):
        baseline = {"review_cycles": 10, "han_interventions": 5}
        current = {"review_cycles": 13, "han_interventions": 5}  # 30% increase
        assert improver.check_rollback(1, baseline, current) is True

    def test_rollback_on_han_interventions_increase_above_15(self, improver: SelfImprover):
        baseline = {"review_cycles": 10, "han_interventions": 10}
        current = {"review_cycles": 10, "han_interventions": 12}  # 20% increase > 15%
        assert improver.check_rollback(1, baseline, current) is True

    def test_rollback_baseline_zero_with_current_positive(self, improver: SelfImprover):
        baseline = {"review_cycles": 0, "han_interventions": 0}
        current = {"review_cycles": 5, "han_interventions": 0}
        assert improver.check_rollback(1, baseline, current) is True

    def test_no_rollback_both_zero(self, improver: SelfImprover):
        baseline = {"review_cycles": 0, "han_interventions": 0}
        current = {"review_cycles": 0, "han_interventions": 0}
        assert improver.check_rollback(1, baseline, current) is False


# --------------------------------------------------------------------------
# rollback_pr — AC-83
# --------------------------------------------------------------------------


class TestRollbackPR:
    """AC-83: Revert merged PR and record rollback."""

    def test_rollback_calls_git_revert(self, improver: SelfImprover, mock_git: MagicMock):
        path = improver.rollback_pr(42, "Metrics degraded")
        git_commands = [c.args[0] for c in mock_git.run.call_args_list]
        assert any("revert" in cmd for cmd in git_commands)

    def test_rollback_pushes(self, improver: SelfImprover, mock_git: MagicMock):
        path = improver.rollback_pr(42, "Metrics degraded")
        git_commands = [c.args[0] for c in mock_git.run.call_args_list]
        assert any("push" in cmd for cmd in git_commands)

    def test_rollback_records_to_file(self, improver: SelfImprover, mock_git: MagicMock, memory_dir: Path):
        path = improver.rollback_pr(42, "Metrics degraded by 25%")
        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert data["pr_number"] == 42
        assert data["reason"] == "Metrics degraded by 25%"
        assert data["action"] == "auto-reverted"

    def test_rollback_creates_rollbacks_dir(self, improver: SelfImprover, mock_git: MagicMock, memory_dir: Path):
        improver.rollback_pr(1, "test")
        assert (memory_dir / "rollbacks").is_dir()
