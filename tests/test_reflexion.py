"""Tests for Reflexion Graph (AC-69, AC-70, AC-71, AC-72, AC-84).

Covers coding workflow, requirements review, design review,
timeout detection, deadlock detection, and incomplete state saving.
"""

import json
import os
import time
from dataclasses import dataclass
from unittest.mock import MagicMock

import pytest

from yui.autonomy.reflexion import (
    ReflexionGraph,
    ReflexionState,
    ReflexionTimeoutError,
    ReviewFinding,
    ReviewResult,
    ReviewSeverity,
)


# --- Data class serialization tests ---


class TestReviewFinding:
    """Tests for ReviewFinding serialization."""

    def test_to_dict(self) -> None:
        f = ReviewFinding(
            severity=ReviewSeverity.CRITICAL,
            id="SEC-01",
            description="SQL injection",
            suggestion="Use parameterized queries",
        )
        d = f.to_dict()
        assert d["severity"] == "critical"
        assert d["id"] == "SEC-01"
        assert d["description"] == "SQL injection"
        assert d["suggestion"] == "Use parameterized queries"
        assert d["challenged"] is False

    def test_from_dict(self) -> None:
        d = {
            "severity": "major",
            "id": "PERF-01",
            "description": "N+1 query",
            "suggestion": "Use eager loading",
            "challenged": True,
            "challenge_reason": "Not applicable here",
        }
        f = ReviewFinding.from_dict(d)
        assert f.severity == ReviewSeverity.MAJOR
        assert f.challenged is True
        assert f.challenge_reason == "Not applicable here"

    def test_roundtrip(self) -> None:
        f = ReviewFinding(
            severity=ReviewSeverity.MINOR,
            id="STYLE-01",
            description="Naming",
        )
        assert ReviewFinding.from_dict(f.to_dict()).id == f.id


class TestReviewResult:
    """Tests for ReviewResult serialization."""

    def test_to_dict(self) -> None:
        r = ReviewResult(
            findings=[
                ReviewFinding(
                    severity=ReviewSeverity.CRITICAL, id="C-1", description="bad"
                ),
            ],
            approved=False,
            round_number=1,
        )
        d = r.to_dict()
        assert len(d["findings"]) == 1
        assert d["approved"] is False
        assert d["round_number"] == 1

    def test_from_dict_empty(self) -> None:
        r = ReviewResult.from_dict({})
        assert r.findings == []
        assert r.approved is False


class TestReflexionState:
    """Tests for ReflexionState serialization."""

    def test_to_dict(self) -> None:
        s = ReflexionState(
            task_description="implement auth",
            file_path="/tmp/spec.md",
            workflow_type="coding",
        )
        d = s.to_dict()
        assert d["task_description"] == "implement auth"
        assert d["workflow_type"] == "coding"
        assert d["completed"] is False

    def test_roundtrip(self) -> None:
        s = ReflexionState(
            task_description="design API",
            file_path="/tmp/spec.md",
            workflow_type="design",
            current_content="draft v1",
        )
        s2 = ReflexionState.from_dict(s.to_dict())
        assert s2.task_description == s.task_description
        assert s2.current_content == s.current_content


# --- ReflexionGraph tests ---


def _make_state(**kwargs) -> ReflexionState:
    """Helper to create a test ReflexionState."""
    defaults = {
        "task_description": "test task",
        "file_path": "/tmp/test.py",
        "workflow_type": "coding",
    }
    defaults.update(kwargs)
    return ReflexionState(**defaults)


def _make_review(
    findings: list[tuple[str, str, str]] | None = None,
    approved: bool = False,
    round_number: int = 1,
) -> ReviewResult:
    """Helper to create a ReviewResult.

    findings: list of (severity, id, description) tuples.
    """
    result_findings = []
    if findings:
        for sev, fid, desc in findings:
            result_findings.append(
                ReviewFinding(
                    severity=ReviewSeverity(sev),
                    id=fid,
                    description=desc,
                )
            )
    return ReviewResult(
        findings=result_findings,
        approved=approved,
        round_number=round_number,
    )


class TestCodingWorkflow:
    """Tests for run_coding_workflow (AC-69)."""

    @pytest.mark.asyncio
    async def test_approved_first_cycle(self) -> None:
        """Single cycle: Kiro implements, Yui auto-approves."""
        mock_impl = MagicMock(return_value="implemented code")
        graph = ReflexionGraph(
            kiro_implement_fn=mock_impl,
            max_cycles=4,
        )

        state = _make_state()
        result = await graph.run_coding_workflow(state)

        assert result.completed is True
        assert len(result.review_results) == 1
        assert result.review_results[0].approved is True
        mock_impl.assert_called_once()

    @pytest.mark.asyncio
    async def test_two_cycle_loop(self) -> None:
        """Two cycles: first has critical finding, second approves."""
        call_count = 0

        def mock_impl(spec_path: str, task_description: str) -> str:
            nonlocal call_count
            call_count += 1
            return f"implementation v{call_count}"

        @dataclass
        class MockYuiAgent:
            call_idx: int = 0

            async def review(self, content: str, task: str) -> str:
                idx = self.call_idx
                self.call_idx += 1
                if idx == 0:
                    return "[CRITICAL] C-1: bad code."
                return "Looks good!"

        graph = ReflexionGraph(
            kiro_implement_fn=mock_impl,
            yui_agent=MockYuiAgent(),
            max_cycles=4,
        )

        state = _make_state()
        result = await graph.run_coding_workflow(state)

        assert result.completed is True
        assert len(result.review_results) == 2
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_cycles_exhausted(self, tmp_path) -> None:
        """Exceeds max cycles → saves incomplete (AC-71, AC-84)."""

        @dataclass
        class MockYuiAgent:
            async def review(self, content: str, task: str) -> str:
                return "[CRITICAL] C-1: still broken."

        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="code"),
            yui_agent=MockYuiAgent(),
            max_cycles=2,
            memory_dir=str(tmp_path),
        )

        state = _make_state()
        result = await graph.run_coding_workflow(state)

        assert result.completed is False
        assert "Max cycles" in result.error

        # Check incomplete file saved (AC-84)
        incomplete_dir = tmp_path / "incomplete"
        assert incomplete_dir.exists()
        files = list(incomplete_dir.iterdir())
        assert len(files) == 1
        assert "max_cycles" in files[0].name

    @pytest.mark.asyncio
    async def test_no_kiro_impl_still_works(self) -> None:
        """Without kiro_implement, still runs (Yui auto-approves)."""
        graph = ReflexionGraph(max_cycles=4)
        state = _make_state()
        result = await graph.run_coding_workflow(state)
        assert result.completed is True


class TestRequirementsReview:
    """Tests for run_requirements_review (AC-70)."""

    @pytest.mark.asyncio
    async def test_approved_first_cycle(self) -> None:
        """Kiro approves requirements on first review."""
        mock_review = MagicMock(return_value="No issues found.")
        graph = ReflexionGraph(kiro_review_fn=mock_review, max_cycles=4)

        state = _make_state(workflow_type="requirements")
        result = await graph.run_requirements_review(state)

        assert result.completed is True
        assert len(result.review_results) == 1
        mock_review.assert_called_once()

    @pytest.mark.asyncio
    async def test_critical_then_fix_then_approve(self) -> None:
        """Kiro finds Critical → Yui revises → Kiro approves."""
        review_responses = [
            "[CRITICAL] REQ-01: Missing error handling.",
            "No issues found. Looks good.",
        ]
        call_idx = 0

        def mock_review(file_path: str, review_focus: str) -> str:
            nonlocal call_idx
            resp = review_responses[call_idx]
            call_idx += 1
            return resp

        @dataclass
        class MockYui:
            async def revise(self, content: str, feedback: dict) -> str:
                return content + "\n# Added error handling"

        graph = ReflexionGraph(
            kiro_review_fn=mock_review,
            yui_agent=MockYui(),
            max_cycles=4,
        )

        state = _make_state(workflow_type="requirements")
        result = await graph.run_requirements_review(state)

        assert result.completed is True
        assert len(result.review_results) == 2

    @pytest.mark.asyncio
    async def test_max_cycles_exhausted(self, tmp_path) -> None:
        """Requirements review exceeds max cycles."""
        mock_review = MagicMock(return_value="[CRITICAL] REQ-01: Still bad.")
        graph = ReflexionGraph(
            kiro_review_fn=mock_review,
            max_cycles=2,
            memory_dir=str(tmp_path),
        )

        state = _make_state(workflow_type="requirements")
        result = await graph.run_requirements_review(state)

        assert result.completed is False
        assert "Max cycles" in result.error

    @pytest.mark.asyncio
    async def test_no_kiro_review_auto_approves(self) -> None:
        """Without kiro_review, auto-approves."""
        graph = ReflexionGraph(max_cycles=4)
        state = _make_state(workflow_type="requirements")
        result = await graph.run_requirements_review(state)
        assert result.completed is True


class TestDesignReview:
    """Tests for run_design_review."""

    @pytest.mark.asyncio
    async def test_approved_first_cycle(self) -> None:
        """Design approved on first cycle."""
        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="design doc"),
            max_cycles=4,
        )

        state = _make_state(workflow_type="design")
        result = await graph.run_design_review(state)
        assert result.completed is True

    @pytest.mark.asyncio
    async def test_max_cycles_saves_incomplete(self, tmp_path) -> None:
        """Design review max cycles saves incomplete."""

        @dataclass
        class MockYui:
            async def review(self, content: str, task: str) -> str:
                return "[MAJOR] DES-01: Missing scalability."

        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="design"),
            yui_agent=MockYui(),
            max_cycles=2,
            memory_dir=str(tmp_path),
        )

        state = _make_state(workflow_type="design")
        result = await graph.run_design_review(state)
        assert result.completed is False
        assert "Max cycles" in result.error


class TestTimeout:
    """Tests for timeout detection (AC-72)."""

    @pytest.mark.asyncio
    async def test_timeout_raises(self) -> None:
        """Timeout raises ReflexionTimeoutError."""
        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="code"),
            timeout=0,  # Immediate timeout
        )

        state = _make_state()
        state.start_time = time.time() - 1  # Already expired

        with pytest.raises(ReflexionTimeoutError):
            await graph.run_coding_workflow(state)

    @pytest.mark.asyncio
    async def test_timeout_saves_incomplete(self, tmp_path) -> None:
        """Timeout saves incomplete state before raising."""
        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="code"),
            timeout=0,
            memory_dir=str(tmp_path),
        )

        state = _make_state()
        state.start_time = time.time() - 1

        with pytest.raises(ReflexionTimeoutError):
            await graph.run_coding_workflow(state)

        incomplete_dir = tmp_path / "incomplete"
        assert incomplete_dir.exists()
        files = list(incomplete_dir.iterdir())
        assert any("timeout" in f.name for f in files)


class TestDeadlock:
    """Tests for deadlock detection."""

    @pytest.mark.asyncio
    async def test_deadlock_detected(self, tmp_path) -> None:
        """Three identical finding sets triggers deadlock."""

        @dataclass
        class MockYui:
            async def review(self, content: str, task: str) -> str:
                return "[CRITICAL] C-1: same finding every time."

        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="code"),
            yui_agent=MockYui(),
            max_cycles=5,
            memory_dir=str(tmp_path),
        )

        state = _make_state()
        result = await graph.run_coding_workflow(state)

        assert "Deadlock" in result.error
        # Incomplete should be saved
        incomplete_dir = tmp_path / "incomplete"
        assert incomplete_dir.exists()

    @pytest.mark.asyncio
    async def test_no_deadlock_with_different_findings(self) -> None:
        """Different findings each cycle → no deadlock."""
        idx = 0

        @dataclass
        class MockYui:
            async def review(self, content: str, task: str) -> str:
                nonlocal idx
                idx += 1
                if idx < 3:
                    return f"[CRITICAL] C-{idx}: finding {idx}."
                return "All good!"

        graph = ReflexionGraph(
            kiro_implement_fn=MagicMock(return_value="code"),
            yui_agent=MockYui(),
            max_cycles=5,
        )

        state = _make_state()
        result = await graph.run_coding_workflow(state)
        assert result.completed is True
        assert "Deadlock" not in (result.error or "")

    def test_detect_deadlock_less_than_3_results(self) -> None:
        """Less than 3 results → no deadlock."""
        graph = ReflexionGraph()
        state = _make_state()
        state.review_results = [
            _make_review(findings=[("critical", "C-1", "bad")]),
            _make_review(findings=[("critical", "C-1", "bad")]),
        ]
        assert graph._detect_deadlock(state) is False

    def test_detect_deadlock_empty_findings_no_deadlock(self) -> None:
        """Empty findings don't count as deadlock."""
        graph = ReflexionGraph()
        state = _make_state()
        state.review_results = [
            _make_review(),
            _make_review(),
            _make_review(),
        ]
        assert graph._detect_deadlock(state) is False


class TestIncompleteStateSaving:
    """Tests for AC-84 failure recovery."""

    def test_save_incomplete_creates_file(self, tmp_path) -> None:
        graph = ReflexionGraph(memory_dir=str(tmp_path))
        state = _make_state()

        filepath = graph._save_incomplete(state, reason="test_reason")

        assert os.path.exists(filepath)
        assert "test_reason" in filepath

        with open(filepath) as f:
            data = json.load(f)
        assert data["reason"] == "test_reason"
        assert data["state"]["task_description"] == "test task"

    def test_save_incomplete_creates_directory(self, tmp_path) -> None:
        memory_dir = str(tmp_path / "nested" / "deep")
        graph = ReflexionGraph(memory_dir=memory_dir)
        state = _make_state()

        filepath = graph._save_incomplete(state, reason="nested")
        assert os.path.exists(filepath)


class TestHasCriticalOrMajor:
    """Tests for blocking finding detection."""

    def test_critical_is_blocking(self) -> None:
        graph = ReflexionGraph()
        result = _make_review(findings=[("critical", "C-1", "bad")])
        assert graph._has_critical_or_major(result) is True

    def test_major_is_blocking(self) -> None:
        graph = ReflexionGraph()
        result = _make_review(findings=[("major", "M-1", "bad")])
        assert graph._has_critical_or_major(result) is True

    def test_minor_not_blocking(self) -> None:
        graph = ReflexionGraph()
        result = _make_review(findings=[("minor", "S-1", "style")])
        assert graph._has_critical_or_major(result) is False

    def test_challenged_critical_not_blocking(self) -> None:
        graph = ReflexionGraph()
        finding = ReviewFinding(
            severity=ReviewSeverity.CRITICAL,
            id="C-1",
            description="bad",
            challenged=True,
        )
        result = ReviewResult(findings=[finding])
        assert graph._has_critical_or_major(result) is False

    def test_empty_findings_not_blocking(self) -> None:
        graph = ReflexionGraph()
        result = _make_review()
        assert graph._has_critical_or_major(result) is False


class TestParseReview:
    """Tests for review output parsing."""

    def test_parses_structured_output(self) -> None:
        graph = ReflexionGraph()
        raw = (
            "[CRITICAL] SEC-01: SQL injection risk. Suggestion: Use parameterized queries.\n"
            "[MAJOR] PERF-01: N+1 query detected.\n"
            "[MINOR] STYLE-01: Inconsistent naming.\n"
        )
        result = graph._parse_review(raw, round_number=1)
        assert len(result.findings) == 3
        assert result.findings[0].severity == ReviewSeverity.CRITICAL
        assert result.findings[0].id == "SEC-01"
        assert result.findings[1].severity == ReviewSeverity.MAJOR
        assert result.findings[2].severity == ReviewSeverity.MINOR
        assert result.approved is False

    def test_no_findings_approved(self) -> None:
        graph = ReflexionGraph()
        result = graph._parse_review("All looks good!", round_number=1)
        assert len(result.findings) == 0
        assert result.approved is True

    def test_only_minor_approved(self) -> None:
        graph = ReflexionGraph()
        raw = "[MINOR] S-01: Formatting issue."
        result = graph._parse_review(raw, round_number=1)
        assert len(result.findings) == 1
        assert result.approved is True

    def test_round_number_preserved(self) -> None:
        graph = ReflexionGraph()
        result = graph._parse_review("ok", round_number=7)
        assert result.round_number == 7
