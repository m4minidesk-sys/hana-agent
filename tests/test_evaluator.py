"""Tests for yui.autonomy.evaluator — Task-level self-evaluation (AC-73, AC-79)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from yui.autonomy.evaluator import TaskEvaluation, TaskEvaluator


@pytest.fixture()
def memory_dir(tmp_path: Path) -> Path:
    """Provide a temp memory directory."""
    return tmp_path / "memory"


@pytest.fixture()
def schema_path() -> Path:
    """Return path to the real evaluation schema."""
    p = Path(__file__).resolve().parents[1] / "schema" / "evaluation.schema.json"
    assert p.exists(), f"Schema not found at {p}"
    return p


@pytest.fixture()
def evaluator(memory_dir: Path, schema_path: Path) -> TaskEvaluator:
    """Create a TaskEvaluator with real schema."""
    return TaskEvaluator(memory_dir=str(memory_dir), schema_path=str(schema_path))


@pytest.fixture()
def evaluator_no_schema(memory_dir: Path) -> TaskEvaluator:
    """Create a TaskEvaluator without schema validation."""
    return TaskEvaluator(memory_dir=str(memory_dir), schema_path="/nonexistent")


def _make_eval(
    task_id: str = "test-task-1",
    outcome: str = "success",
    days_ago: int = 0,
    **kwargs,
) -> TaskEvaluation:
    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    return TaskEvaluation(
        task_id=task_id,
        timestamp=ts,
        outcome=outcome,
        metrics=kwargs.get("metrics", {}),
        lessons=kwargs.get("lessons", []),
        improvements=kwargs.get("improvements", []),
    )


# --------------------------------------------------------------------------
# record_evaluation — AC-73
# --------------------------------------------------------------------------


class TestRecordEvaluation:
    """AC-73: Task-level self-evaluation recorded to memory/evaluations/."""

    def test_record_valid_evaluation(self, evaluator: TaskEvaluator, memory_dir: Path):
        ev = _make_eval()
        path = evaluator.record_evaluation(ev)
        assert path.exists()
        assert path.parent.name == "evaluations"
        data = yaml.safe_load(path.read_text())
        assert data["task_id"] == "test-task-1"
        assert data["outcome"] == "success"

    def test_record_evaluation_with_metrics(self, evaluator: TaskEvaluator):
        ev = _make_eval(
            metrics={"kiro_review_rounds": 2, "critical_findings": 1},
        )
        path = evaluator.record_evaluation(ev)
        data = yaml.safe_load(path.read_text())
        assert data["metrics"]["kiro_review_rounds"] == 2
        assert data["metrics"]["critical_findings"] == 1

    def test_record_evaluation_with_lessons(self, evaluator: TaskEvaluator):
        ev = _make_eval(lessons=["Always run tests", "Check edge cases"])
        path = evaluator.record_evaluation(ev)
        data = yaml.safe_load(path.read_text())
        assert len(data["lessons"]) == 2

    def test_record_evaluation_with_improvements(self, evaluator: TaskEvaluator):
        ev = _make_eval(
            improvements=[
                {"target": "AGENTS.md", "suggestion": "Add pre-task checklist"},
            ],
        )
        path = evaluator.record_evaluation(ev)
        data = yaml.safe_load(path.read_text())
        assert data["improvements"][0]["target"] == "AGENTS.md"

    def test_record_evaluation_filename_format(self, evaluator: TaskEvaluator):
        ev = _make_eval(task_id="fix-123")
        path = evaluator.record_evaluation(ev)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert path.name == f"{today}_fix-123.yaml"

    def test_record_partial_outcome(self, evaluator: TaskEvaluator):
        ev = _make_eval(outcome="partial")
        path = evaluator.record_evaluation(ev)
        data = yaml.safe_load(path.read_text())
        assert data["outcome"] == "partial"

    def test_record_failure_outcome(self, evaluator: TaskEvaluator):
        ev = _make_eval(outcome="failure")
        path = evaluator.record_evaluation(ev)
        data = yaml.safe_load(path.read_text())
        assert data["outcome"] == "failure"


# --------------------------------------------------------------------------
# Schema validation
# --------------------------------------------------------------------------


class TestSchemaValidation:
    """Evaluations are validated against JSON Schema."""

    def test_valid_evaluation_passes_schema(self, evaluator: TaskEvaluator, memory_dir: Path):
        ev = _make_eval()
        path = evaluator.record_evaluation(ev)
        assert path.parent.name == "evaluations"  # Not in invalid/

    def test_invalid_outcome_goes_to_invalid(self, evaluator: TaskEvaluator, memory_dir: Path):
        ev = _make_eval(outcome="unknown-bad-value")
        path = evaluator.record_evaluation(ev)
        assert path.parent.name == "invalid"

    def test_invalid_evaluation_not_silently_dropped(self, evaluator: TaskEvaluator, memory_dir: Path):
        """Invalid evaluations are stored in memory/invalid/ — never dropped."""
        ev = _make_eval(outcome="not-a-valid-outcome")
        path = evaluator.record_evaluation(ev)
        assert path.exists()
        data = yaml.safe_load(path.read_text())
        assert "validation_errors" in data
        assert data["data"]["outcome"] == "not-a-valid-outcome"

    def test_invalid_evaluation_filename_has_INVALID(self, evaluator: TaskEvaluator):
        ev = _make_eval(outcome="bogus")
        path = evaluator.record_evaluation(ev)
        assert "INVALID" in path.name

    def test_no_schema_accepts_anything(self, evaluator_no_schema: TaskEvaluator):
        """Without a schema, all evaluations are accepted."""
        ev = _make_eval(outcome="anything-goes")
        path = evaluator_no_schema.record_evaluation(ev)
        assert path.parent.name == "evaluations"


# --------------------------------------------------------------------------
# record_review — AC-79
# --------------------------------------------------------------------------


class TestRecordReview:
    """AC-79: Cross-review findings logged to memory/reviews/."""

    def test_record_review(self, evaluator: TaskEvaluator, memory_dir: Path):
        review = {
            "review_id": "review-001",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "findings": ["Missing edge case test"],
            "severity": "warning",
        }
        path = evaluator.record_review(review)
        assert path.exists()
        assert path.parent.name == "reviews"
        data = yaml.safe_load(path.read_text())
        assert data["review_id"] == "review-001"

    def test_record_review_filename(self, evaluator: TaskEvaluator):
        review = {
            "review_id": "rev-abc",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        path = evaluator.record_review(review)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert path.name == f"{today}_rev-abc.yaml"


# --------------------------------------------------------------------------
# load_evaluations
# --------------------------------------------------------------------------


class TestLoadEvaluations:
    """Load evaluations with day-based filtering."""

    def test_load_recent_evaluations(self, evaluator: TaskEvaluator):
        # Create evaluations at different ages
        for i in range(5):
            ev = _make_eval(task_id=f"task-{i}", days_ago=i)
            evaluator.record_evaluation(ev)

        loaded = evaluator.load_evaluations(days=3)
        # Should include today (0), yesterday (1), 2 days ago (2) — at least 3
        assert len(loaded) >= 3

    def test_load_evaluations_empty_dir(self, evaluator: TaskEvaluator):
        loaded = evaluator.load_evaluations(days=7)
        assert loaded == []

    def test_load_evaluations_excludes_old(self, evaluator: TaskEvaluator):
        ev = _make_eval(task_id="old-task", days_ago=10)
        evaluator.record_evaluation(ev)

        loaded = evaluator.load_evaluations(days=3)
        assert all(e.task_id != "old-task" for e in loaded)


# --------------------------------------------------------------------------
# analyze_patterns
# --------------------------------------------------------------------------


class TestAnalyzePatterns:
    """Pattern analysis for evaluation data."""

    def test_analyze_empty(self, evaluator: TaskEvaluator):
        result = evaluator.analyze_patterns([])
        assert result["total"] == 0
        assert result["success_rate"] == 0.0

    def test_analyze_success_rate(self, evaluator: TaskEvaluator):
        evals = [
            _make_eval(task_id="t1", outcome="success"),
            _make_eval(task_id="t2", outcome="success"),
            _make_eval(task_id="t3", outcome="failure"),
            _make_eval(task_id="t4", outcome="partial"),
        ]
        result = evaluator.analyze_patterns(evals)
        assert result["total"] == 4
        assert result["success_rate"] == 0.5  # 2/4

    def test_analyze_avg_review_rounds(self, evaluator: TaskEvaluator):
        evals = [
            _make_eval(task_id="t1", metrics={"kiro_review_rounds": 1}),
            _make_eval(task_id="t2", metrics={"kiro_review_rounds": 3}),
        ]
        result = evaluator.analyze_patterns(evals)
        assert result["avg_review_rounds"] == 2.0

    def test_analyze_critical_findings(self, evaluator: TaskEvaluator):
        evals = [
            _make_eval(task_id="t1", metrics={"critical_findings": 2}),
            _make_eval(task_id="t2", metrics={"critical_findings": 3}),
        ]
        result = evaluator.analyze_patterns(evals)
        assert result["total_critical_findings"] == 5

    def test_analyze_frequent_lessons(self, evaluator: TaskEvaluator):
        evals = [
            _make_eval(task_id="t1", lessons=["Run tests"]),
            _make_eval(task_id="t2", lessons=["Run tests", "Check types"]),
            _make_eval(task_id="t3", lessons=["Run tests"]),
        ]
        result = evaluator.analyze_patterns(evals)
        top = result["frequent_lessons"]
        assert top[0]["lesson"] == "Run tests"
        assert top[0]["count"] == 3

    def test_analyze_recurring_failures(self, evaluator: TaskEvaluator):
        evals = [
            _make_eval(task_id="flaky-task", outcome="failure"),
            _make_eval(task_id="good-task", outcome="success"),
            _make_eval(task_id="flaky-task-2", outcome="failure"),
        ]
        result = evaluator.analyze_patterns(evals)
        assert "flaky-task" in result["recurring_failures"]
        assert "good-task" not in result["recurring_failures"]


# --------------------------------------------------------------------------
# Directory creation
# --------------------------------------------------------------------------


class TestDirectoryCreation:
    """Evaluator creates required directories on init."""

    def test_creates_evaluations_dir(self, evaluator: TaskEvaluator, memory_dir: Path):
        assert (memory_dir / "evaluations").is_dir()

    def test_creates_reviews_dir(self, evaluator: TaskEvaluator, memory_dir: Path):
        assert (memory_dir / "reviews").is_dir()

    def test_creates_invalid_dir(self, evaluator: TaskEvaluator, memory_dir: Path):
        assert (memory_dir / "invalid").is_dir()
