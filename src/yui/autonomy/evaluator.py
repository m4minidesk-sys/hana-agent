"""Task-level self-evaluation and cross-review recording (AC-73, AC-79).

Evaluations are persisted as YAML files under ``memory/evaluations/`` and
validated against ``schema/evaluation.schema.json``.  Invalid payloads are
redirected to ``memory/invalid/`` so nothing is silently dropped.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional jsonschema support — graceful fallback when not installed
# ---------------------------------------------------------------------------
try:
    import jsonschema  # type: ignore[import-untyped]

    _HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    _HAS_JSONSCHEMA = False


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TaskEvaluation:
    """One evaluation record produced after a task completes."""

    task_id: str
    timestamp: str  # ISO-8601
    outcome: str  # "success" | "partial" | "failure"
    metrics: dict[str, Any] = field(default_factory=dict)
    lessons: list[str] = field(default_factory=list)
    improvements: list[dict[str, str]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class TaskEvaluator:
    """Record, load and analyse task evaluations.

    Parameters
    ----------
    memory_dir:
        Root directory for memory persistence (default ``~/.yui/workspace/memory``).
    schema_path:
        Path to the JSON-Schema file used for validation.  When *None* the
        evaluator will look for ``schema/evaluation.schema.json`` relative to
        the repository root.
    """

    def __init__(
        self,
        memory_dir: str = "~/.yui/workspace/memory",
        schema_path: Optional[str] = None,
    ) -> None:
        self.memory_dir = Path(os.path.expanduser(memory_dir))
        self.evaluations_dir = self.memory_dir / "evaluations"
        self.reviews_dir = self.memory_dir / "reviews"
        self.invalid_dir = self.memory_dir / "invalid"

        for d in [self.evaluations_dir, self.reviews_dir, self.invalid_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Load JSON schema (best-effort)
        self._schema: Optional[dict] = None
        if schema_path:
            self._schema = self._load_schema(Path(schema_path))
        else:
            # Try repo-relative default
            default = Path(__file__).resolve().parents[3] / "schema" / "evaluation.schema.json"
            if default.exists():
                self._schema = self._load_schema(default)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_evaluation(self, evaluation: TaskEvaluation) -> Path:
        """Persist a task evaluation to ``memory/evaluations/`` (AC-73).

        Invalid evaluations are stored under ``memory/invalid/`` — they are
        never silently dropped.

        Returns the path the file was written to.
        """
        data = asdict(evaluation)
        valid, errors = self._validate(data)

        if not valid:
            logger.warning(
                "Invalid evaluation for task %s: %s — saving to invalid/",
                evaluation.task_id,
                errors,
            )
            return self._write_invalid(data, errors)

        date_prefix = self._date_prefix(evaluation.timestamp)
        filename = f"{date_prefix}_{evaluation.task_id}.yaml"
        path = self.evaluations_dir / filename
        self._write_yaml(path, data)
        logger.info("Recorded evaluation: %s", path)
        return path

    def record_review(self, review_data: dict[str, Any]) -> Path:
        """Persist cross-review findings to ``memory/reviews/`` (AC-79).

        Returns the path the file was written to.
        """
        review_id = review_data.get("review_id", "unknown")
        ts = review_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        date_prefix = self._date_prefix(ts)
        filename = f"{date_prefix}_{review_id}.yaml"
        path = self.reviews_dir / filename
        self._write_yaml(path, review_data)
        logger.info("Recorded review: %s", path)
        return path

    def load_evaluations(self, days: int = 7) -> list[TaskEvaluation]:
        """Load evaluations from the most recent *days* days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        results: list[TaskEvaluation] = []

        if not self.evaluations_dir.exists():
            return results

        for path in sorted(self.evaluations_dir.glob("*.yaml")):
            try:
                data = self._read_yaml(path)
                ts_str = data.get("timestamp", "")
                ts = self._parse_timestamp(ts_str)
                if ts and ts >= cutoff:
                    results.append(self._dict_to_evaluation(data))
            except Exception:  # noqa: BLE001
                logger.warning("Skipping unreadable evaluation: %s", path)

        return results

    def analyze_patterns(self, evaluations: list[TaskEvaluation]) -> dict[str, Any]:
        """Analyse evaluation list and return aggregate statistics."""
        if not evaluations:
            return {
                "total": 0,
                "success_rate": 0.0,
                "avg_review_rounds": 0.0,
                "total_critical_findings": 0,
                "frequent_lessons": [],
                "recurring_failures": [],
            }

        total = len(evaluations)
        successes = sum(1 for e in evaluations if e.outcome == "success")
        failures = [e for e in evaluations if e.outcome == "failure"]

        review_rounds = [
            e.metrics.get("kiro_review_rounds", 0)
            for e in evaluations
            if "kiro_review_rounds" in e.metrics
        ]
        avg_rounds = sum(review_rounds) / len(review_rounds) if review_rounds else 0.0

        total_critical = sum(
            e.metrics.get("critical_findings", 0) for e in evaluations
        )

        # Count lesson occurrences
        lesson_counts: dict[str, int] = {}
        for e in evaluations:
            for lesson in e.lessons:
                lesson_counts[lesson] = lesson_counts.get(lesson, 0) + 1
        frequent = sorted(lesson_counts.items(), key=lambda x: x[1], reverse=True)[:5]

        # Recurring failure patterns — task_ids that failed
        failure_ids = [e.task_id for e in failures]

        return {
            "total": total,
            "success_rate": successes / total,
            "avg_review_rounds": round(avg_rounds, 2),
            "total_critical_findings": total_critical,
            "frequent_lessons": [{"lesson": l, "count": c} for l, c in frequent],
            "recurring_failures": failure_ids,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_schema(path: Path) -> Optional[dict]:
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            logger.warning("Could not load schema from %s", path)
            return None

    def _validate(self, data: dict) -> tuple[bool, list[str]]:
        """Validate *data* against the JSON schema.

        Returns ``(valid, error_messages)``.
        """
        if self._schema is None or not _HAS_JSONSCHEMA:
            # No schema available — accept everything
            return True, []

        errors: list[str] = []
        try:
            jsonschema.validate(instance=data, schema=self._schema)
        except jsonschema.ValidationError as exc:
            errors.append(str(exc.message))
        return (len(errors) == 0), errors

    def _write_invalid(self, data: dict, errors: list[str]) -> Path:
        ts = data.get("timestamp", datetime.now(timezone.utc).isoformat())
        task_id = data.get("task_id", "unknown")
        date_prefix = self._date_prefix(ts)
        filename = f"{date_prefix}_{task_id}_INVALID.yaml"
        path = self.invalid_dir / filename
        payload = {"data": data, "validation_errors": errors}
        self._write_yaml(path, payload)
        return path

    @staticmethod
    def _write_yaml(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

    @staticmethod
    def _read_yaml(path: Path) -> dict:
        with open(path) as f:
            return yaml.safe_load(f) or {}

    @staticmethod
    def _date_prefix(ts: str) -> str:
        """Extract ``YYYY-MM-DD`` from an ISO-8601 timestamp."""
        return ts[:10] if len(ts) >= 10 else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    @staticmethod
    def _parse_timestamp(ts: str) -> Optional[datetime]:
        """Best-effort ISO-8601 parse."""
        if not ts:
            return None
        try:
            # Python 3.11+ fromisoformat handles timezone offsets
            return datetime.fromisoformat(ts)
        except ValueError:
            return None

    @staticmethod
    def _dict_to_evaluation(d: dict) -> TaskEvaluation:
        return TaskEvaluation(
            task_id=d.get("task_id", ""),
            timestamp=d.get("timestamp", ""),
            outcome=d.get("outcome", ""),
            metrics=d.get("metrics", {}),
            lessons=d.get("lessons", []),
            improvements=d.get("improvements", []),
        )
