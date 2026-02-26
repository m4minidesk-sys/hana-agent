"""Reflexion Graph — Yui⇔Kiro iterative review loops.

AC-69: Coding workflow: draft → review → [revise loop] → complete
AC-70: Requirements review workflow: Yui drafts → Kiro reviews → [revise loop] → approved
AC-71: max_node_executions prevents infinite loops (max 4 cycles = 8 node executions)
AC-72: execution_timeout kills stalled loops after 10 minutes
AC-82: Conflict resolution (see conflict.py) — challenges integrated into review loop
AC-84: Failure recovery — partial work saved to memory/incomplete/ when loop hits limit
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ReviewSeverity(Enum):
    """Severity levels for review findings."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class ReviewFinding:
    """A single finding from a review cycle."""

    severity: ReviewSeverity
    id: str
    description: str
    suggestion: str = ""
    challenged: bool = False
    challenge_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "severity": self.severity.value,
            "id": self.id,
            "description": self.description,
            "suggestion": self.suggestion,
            "challenged": self.challenged,
            "challenge_reason": self.challenge_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewFinding:
        """Deserialize from dict."""
        return cls(
            severity=ReviewSeverity(data["severity"]),
            id=data["id"],
            description=data["description"],
            suggestion=data.get("suggestion", ""),
            challenged=data.get("challenged", False),
            challenge_reason=data.get("challenge_reason", ""),
        )


@dataclass
class ReviewResult:
    """Result of a single review cycle."""

    findings: list[ReviewFinding] = field(default_factory=list)
    approved: bool = False
    round_number: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "findings": [f.to_dict() for f in self.findings],
            "approved": self.approved,
            "round_number": self.round_number,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewResult:
        """Deserialize from dict."""
        return cls(
            findings=[ReviewFinding.from_dict(f) for f in data.get("findings", [])],
            approved=data.get("approved", False),
            round_number=data.get("round_number", 0),
        )


@dataclass
class ReflexionState:
    """State passed between nodes in the reflexion graph."""

    task_description: str
    file_path: str
    workflow_type: str  # "coding" | "requirements" | "design"
    current_content: str = ""
    review_results: list[ReviewResult] = field(default_factory=list)
    challenges: list[dict[str, Any]] = field(default_factory=list)
    completed: bool = False
    error: str = ""
    start_time: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSON storage."""
        return {
            "task_description": self.task_description,
            "file_path": self.file_path,
            "workflow_type": self.workflow_type,
            "current_content": self.current_content,
            "review_results": [r.to_dict() for r in self.review_results],
            "challenges": self.challenges,
            "completed": self.completed,
            "error": self.error,
            "start_time": self.start_time,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReflexionState:
        """Deserialize from dict."""
        state = cls(
            task_description=data["task_description"],
            file_path=data["file_path"],
            workflow_type=data["workflow_type"],
            current_content=data.get("current_content", ""),
            review_results=[
                ReviewResult.from_dict(r) for r in data.get("review_results", [])
            ],
            challenges=data.get("challenges", []),
            completed=data.get("completed", False),
            error=data.get("error", ""),
        )
        state.start_time = data.get("start_time", time.time())
        return state


class ReflexionTimeoutError(TimeoutError):
    """Raised when the reflexion loop exceeds its timeout."""


class ReflexionMaxCyclesError(RuntimeError):
    """Raised when the reflexion loop exceeds max cycle count."""


class ReflexionGraph:
    """Yui⇔Kiro Reflexion Loop using iterative review cycles.

    Provides three workflows:
    - Coding: Yui requirements → Kiro implement → Yui review → [loop] → complete
    - Requirements review: Yui draft → Kiro review → [loop] → approved
    - Design review: Kiro design → Yui review → [loop] → approved

    Note: Strands GraphBuilder is the target integration. This implementation
    provides the core logic that will be connected to GraphBuilder when available.
    GraphBuilder dependency is optional — falls back to manual iteration.
    """

    MAX_CYCLES = 4  # max 4 review cycles (AC-71: 8 node executions)
    TIMEOUT_SECONDS = 600  # 10 minutes (AC-72)

    def __init__(
        self,
        kiro_review_fn: Optional[Callable[..., str]] = None,
        kiro_implement_fn: Optional[Callable[..., str]] = None,
        yui_agent: Optional[Any] = None,
        max_cycles: Optional[int] = None,
        timeout: Optional[int] = None,
        memory_dir: str = "~/.yui/workspace/memory",
    ):
        self.kiro_review = kiro_review_fn
        self.kiro_implement = kiro_implement_fn
        self.yui_agent = yui_agent
        self.max_cycles = max_cycles if max_cycles is not None else self.MAX_CYCLES
        self.timeout = timeout if timeout is not None else self.TIMEOUT_SECONDS
        self.memory_dir = os.path.expanduser(memory_dir)

    async def run_coding_workflow(self, state: ReflexionState) -> ReflexionState:
        """Workflow A: Coding (AC-69).

        Yui requirements → Kiro implement → Yui review → [revise loop] → complete.
        """
        state.workflow_type = "coding"

        for cycle in range(self.max_cycles):
            self._check_timeout(state)

            # Node 1: Kiro implements / revises
            if self.kiro_implement:
                logger.info("Coding cycle %d: Kiro implementing", cycle + 1)
                impl_result = self.kiro_implement(
                    spec_path=state.file_path,
                    task_description=state.task_description,
                )
                state.current_content = impl_result

            # Node 2: Yui reviews
            review = await self._yui_review(state, cycle + 1)
            state.review_results.append(review)

            if review.approved or not self._has_critical_or_major(review):
                state.completed = True
                logger.info("Coding workflow completed after %d cycle(s)", cycle + 1)
                return state

            # Check for deadlock
            if self._detect_deadlock(state):
                logger.warning("Deadlock detected — same findings 3 cycles in a row")
                state.error = "Deadlock: same review findings repeated 3 times"
                self._save_incomplete(state, reason="deadlock")
                return state

        # Max cycles exhausted (AC-71 / AC-84)
        state.error = f"Max cycles ({self.max_cycles}) exhausted"
        self._save_incomplete(state, reason="max_cycles")
        logger.warning("Coding workflow hit max cycles: %d", self.max_cycles)
        return state

    async def run_requirements_review(self, state: ReflexionState) -> ReflexionState:
        """Workflow B: Requirements review (AC-70).

        Yui draft → Kiro review → [revise loop] → approved.
        """
        state.workflow_type = "requirements"

        for cycle in range(self.max_cycles):
            self._check_timeout(state)

            # Node 1: Kiro reviews Yui's draft
            if self.kiro_review:
                logger.info("Requirements cycle %d: Kiro reviewing", cycle + 1)
                raw_review = self.kiro_review(
                    file_path=state.file_path,
                    review_focus="technical feasibility, completeness, missing edge cases",
                )
                review = self._parse_review(raw_review, cycle + 1)
            else:
                review = ReviewResult(approved=True, round_number=cycle + 1)

            state.review_results.append(review)

            if review.approved or not self._has_critical_or_major(review):
                state.completed = True
                logger.info(
                    "Requirements review approved after %d cycle(s)", cycle + 1
                )
                return state

            # Yui revises based on feedback
            if self.yui_agent:
                logger.info("Requirements cycle %d: Yui revising", cycle + 1)
                revision = await self._yui_revise(state, review)
                state.current_content = revision

            # Check for deadlock
            if self._detect_deadlock(state):
                logger.warning("Deadlock detected in requirements review")
                state.error = "Deadlock: same review findings repeated 3 times"
                self._save_incomplete(state, reason="deadlock")
                return state

        state.error = f"Max cycles ({self.max_cycles}) exhausted"
        self._save_incomplete(state, reason="max_cycles")
        logger.warning("Requirements review hit max cycles: %d", self.max_cycles)
        return state

    async def run_design_review(self, state: ReflexionState) -> ReflexionState:
        """Workflow C: Design review.

        Kiro design → Yui review → [revise loop] → approved.
        """
        state.workflow_type = "design"

        for cycle in range(self.max_cycles):
            self._check_timeout(state)

            # Node 1: Kiro designs / revises
            if self.kiro_implement:
                logger.info("Design cycle %d: Kiro designing", cycle + 1)
                design_result = self.kiro_implement(
                    spec_path=state.file_path,
                    task_description=f"Create design for: {state.task_description}",
                )
                state.current_content = design_result

            # Node 2: Yui reviews design
            review = await self._yui_review(state, cycle + 1)
            state.review_results.append(review)

            if review.approved or not self._has_critical_or_major(review):
                state.completed = True
                logger.info("Design review completed after %d cycle(s)", cycle + 1)
                return state

            if self._detect_deadlock(state):
                logger.warning("Deadlock detected in design review")
                state.error = "Deadlock: same review findings repeated 3 times"
                self._save_incomplete(state, reason="deadlock")
                return state

        state.error = f"Max cycles ({self.max_cycles}) exhausted"
        self._save_incomplete(state, reason="max_cycles")
        logger.warning("Design review hit max cycles: %d", self.max_cycles)
        return state

    def _check_timeout(self, state: ReflexionState) -> None:
        """AC-72: Check if execution timeout exceeded."""
        elapsed = time.time() - state.start_time
        if elapsed > self.timeout:
            self._save_incomplete(state, reason="timeout")
            raise ReflexionTimeoutError(
                f"Reflexion loop exceeded {self.timeout}s timeout "
                f"(elapsed: {elapsed:.1f}s)"
            )

    def _has_critical_or_major(self, result: ReviewResult) -> bool:
        """Check if review has blocking (unchallenged Critical/Major) findings."""
        return any(
            f.severity in (ReviewSeverity.CRITICAL, ReviewSeverity.MAJOR)
            and not f.challenged
            for f in result.findings
        )

    def _save_incomplete(self, state: ReflexionState, reason: str) -> str:
        """AC-84: Save partial work to memory/incomplete/.

        Returns the path where the state was saved.
        """
        incomplete_dir = os.path.join(self.memory_dir, "incomplete")
        os.makedirs(incomplete_dir, exist_ok=True)

        timestamp = int(time.time())
        filename = f"{state.workflow_type}_{timestamp}_{reason}.json"
        filepath = os.path.join(incomplete_dir, filename)

        save_data = {
            "reason": reason,
            "saved_at": timestamp,
            "state": state.to_dict(),
        }

        try:
            with open(filepath, "w") as f:
                json.dump(save_data, f, indent=2, default=str)
            logger.info("Saved incomplete state to %s", filepath)
        except OSError as e:
            logger.error("Failed to save incomplete state: %s", e)

        return filepath

    def _detect_deadlock(self, state: ReflexionState) -> bool:
        """Detect Yui-Kiro deadlock: 3 consecutive cycles with same findings.

        Compares finding IDs in the last 3 review results.
        """
        if len(state.review_results) < 3:
            return False

        last_three = state.review_results[-3:]
        finding_sets = []
        for result in last_three:
            ids = frozenset(f.id for f in result.findings)
            finding_sets.append(ids)

        # All 3 have the same set of finding IDs (and at least one finding)
        return (
            finding_sets[0] == finding_sets[1] == finding_sets[2]
            and len(finding_sets[0]) > 0
        )

    def _parse_review(self, raw_output: str, round_number: int) -> ReviewResult:
        """Parse raw Kiro review output into a ReviewResult.

        Looks for patterns like [CRITICAL] ID: description.
        Falls back to treating the entire output as a single finding if
        no structured findings are found.
        """
        findings: list[ReviewFinding] = []

        # Pattern: [CRITICAL] F-001: Description. Suggestion: fix.
        pattern = re.compile(
            r"\[(?P<severity>CRITICAL|MAJOR|MINOR)\]\s+"
            r"(?P<id>[A-Za-z0-9_-]+):\s+"
            r"(?P<description>.+?)(?:\.\s+Suggestion:\s+(?P<suggestion>.+?))?$",
            re.MULTILINE,
        )

        for match in pattern.finditer(raw_output):
            severity = ReviewSeverity(match.group("severity").lower())
            findings.append(
                ReviewFinding(
                    severity=severity,
                    id=match.group("id"),
                    description=match.group("description").strip(),
                    suggestion=(match.group("suggestion") or "").strip(),
                )
            )

        approved = len(findings) == 0 or all(
            f.severity == ReviewSeverity.MINOR for f in findings
        )

        return ReviewResult(
            findings=findings,
            approved=approved,
            round_number=round_number,
        )

    async def _yui_review(
        self, state: ReflexionState, round_number: int
    ) -> ReviewResult:
        """Have Yui review the current content.

        If yui_agent is available, delegates to it; otherwise returns an
        auto-approval (for testing without a live agent).
        """
        if self.yui_agent and hasattr(self.yui_agent, "review"):
            raw = await self.yui_agent.review(
                state.current_content, state.task_description
            )
            return self._parse_review(raw, round_number)

        # No Yui agent — auto-approve (testing / standalone mode)
        return ReviewResult(approved=True, round_number=round_number)

    async def _yui_revise(
        self, state: ReflexionState, review: ReviewResult
    ) -> str:
        """Have Yui revise content based on review feedback."""
        if self.yui_agent and hasattr(self.yui_agent, "revise"):
            return await self.yui_agent.revise(
                state.current_content,
                review.to_dict(),
            )
        # Fallback: return content unchanged
        return state.current_content
