"""Tests for Conflict Resolution (AC-82).

Covers challenge creation, resolution, escalation,
and Minor finding dismissal with justification.
"""

import pytest

from yui.autonomy.conflict import Challenge, ConflictResolver
from yui.autonomy.reflexion import ReviewFinding, ReviewSeverity


@pytest.fixture
def resolver() -> ConflictResolver:
    return ConflictResolver()


@pytest.fixture
def critical_finding() -> ReviewFinding:
    return ReviewFinding(
        severity=ReviewSeverity.CRITICAL,
        id="SEC-01",
        description="SQL injection vulnerability",
        suggestion="Use parameterized queries",
    )


@pytest.fixture
def major_finding() -> ReviewFinding:
    return ReviewFinding(
        severity=ReviewSeverity.MAJOR,
        id="PERF-01",
        description="N+1 query detected",
    )


@pytest.fixture
def minor_finding() -> ReviewFinding:
    return ReviewFinding(
        severity=ReviewSeverity.MINOR,
        id="STYLE-01",
        description="Inconsistent naming convention",
    )


class TestChallengeCreation:
    """Tests for challenge_finding."""

    def test_creates_challenge(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(
            critical_finding, reason="This is a false positive"
        )

        assert challenge.finding_id == "SEC-01"
        assert challenge.finding_severity == ReviewSeverity.CRITICAL
        assert challenge.challenger == "yui"
        assert challenge.reason == "This is a false positive"
        assert challenge.resolution == ""

    def test_marks_finding_as_challenged(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        resolver.challenge_finding(critical_finding, reason="false positive")
        assert critical_finding.challenged is True
        assert critical_finding.challenge_reason == "false positive"

    def test_tracks_challenge_in_list(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        resolver.challenge_finding(critical_finding, reason="nope")
        assert len(resolver.challenges) == 1

    def test_custom_challenger(
        self, resolver: ConflictResolver, major_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(
            major_finding, reason="not relevant", challenger="kiro"
        )
        assert challenge.challenger == "kiro"


class TestChallengeResolution:
    """Tests for resolve_challenge."""

    def test_accepted_when_kiro_agrees(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="false positive")
        resolved = resolver.resolve_challenge(
            challenge, "I agree, this is a false positive."
        )
        assert resolved.resolution == "accepted"

    def test_dismissed_when_kiro_disagrees(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="false positive")
        resolved = resolver.resolve_challenge(
            challenge,
            "I disagree. The vulnerability is still valid and confirmed.",
        )
        assert resolved.resolution == "dismissed"

    def test_kiro_response_stored(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="test")
        resolver.resolve_challenge(challenge, "my response")
        assert challenge.kiro_response == "my response"

    def test_retract_keyword_accepted(
        self, resolver: ConflictResolver, major_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(major_finding, reason="not applicable")
        resolved = resolver.resolve_challenge(challenge, "I retract this finding.")
        assert resolved.resolution == "accepted"

    def test_ambiguous_response_dismissed(
        self, resolver: ConflictResolver, major_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(major_finding, reason="maybe")
        resolved = resolver.resolve_challenge(
            challenge, "The finding stands as important."
        )
        assert resolved.resolution == "dismissed"


class TestEscalation:
    """Tests for should_escalate."""

    def test_dismissed_critical_escalates(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="false positive")
        resolver.resolve_challenge(challenge, "I disagree. Still valid.")
        assert resolver.should_escalate(challenge) is True

    def test_unresolved_critical_escalates(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="test")
        # resolution is "" (unresolved)
        assert resolver.should_escalate(challenge) is True

    def test_accepted_critical_no_escalation(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(critical_finding, reason="false positive")
        resolver.resolve_challenge(challenge, "I agree, false positive.")
        assert resolver.should_escalate(challenge) is False

    def test_dismissed_major_no_escalation(
        self, resolver: ConflictResolver, major_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(major_finding, reason="test")
        resolver.resolve_challenge(challenge, "I disagree.")
        assert resolver.should_escalate(challenge) is False

    def test_minor_never_escalates(
        self, resolver: ConflictResolver, minor_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(minor_finding, reason="test")
        resolver.resolve_challenge(challenge, "I disagree.")
        assert resolver.should_escalate(challenge) is False


class TestEscalationSummary:
    """Tests for escalation summary generation."""

    def test_summary_contains_key_info(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        challenge = resolver.challenge_finding(
            critical_finding, reason="false positive"
        )
        resolver.resolve_challenge(challenge, "Still valid.")
        summary = resolver.get_escalation_summary(challenge)

        assert "SEC-01" in summary
        assert "critical" in summary
        assert "yui" in summary
        assert "false positive" in summary
        assert "Still valid." in summary


class TestMinorDismissal:
    """Tests for dismiss_minor_with_justification."""

    def test_dismisses_minor(
        self, resolver: ConflictResolver, minor_finding: ReviewFinding
    ) -> None:
        challenge = resolver.dismiss_minor_with_justification(
            minor_finding, "Consistent with project style guide"
        )
        assert challenge.resolution == "accepted"
        assert minor_finding.challenged is True
        assert minor_finding.challenge_reason == "Consistent with project style guide"

    def test_rejects_non_minor(
        self, resolver: ConflictResolver, critical_finding: ReviewFinding
    ) -> None:
        with pytest.raises(ValueError, match="Only Minor"):
            resolver.dismiss_minor_with_justification(
                critical_finding, "I don't think so"
            )

    def test_rejects_major(
        self, resolver: ConflictResolver, major_finding: ReviewFinding
    ) -> None:
        with pytest.raises(ValueError, match="Only Minor"):
            resolver.dismiss_minor_with_justification(major_finding, "nah")

    def test_tracked_in_challenges_list(
        self, resolver: ConflictResolver, minor_finding: ReviewFinding
    ) -> None:
        resolver.dismiss_minor_with_justification(minor_finding, "ok")
        assert len(resolver.challenges) == 1
        assert resolver.challenges[0].resolution == "accepted"


class TestChallengeSerialization:
    """Tests for Challenge to_dict / from_dict."""

    def test_to_dict(self) -> None:
        c = Challenge(
            finding_id="C-1",
            finding_severity=ReviewSeverity.CRITICAL,
            challenger="yui",
            reason="false positive",
            resolution="dismissed",
            kiro_response="nope",
        )
        d = c.to_dict()
        assert d["finding_id"] == "C-1"
        assert d["finding_severity"] == "critical"
        assert d["resolution"] == "dismissed"

    def test_from_dict(self) -> None:
        d = {
            "finding_id": "M-1",
            "finding_severity": "major",
            "challenger": "kiro",
            "reason": "test",
            "resolution": "accepted",
            "kiro_response": "ok",
        }
        c = Challenge.from_dict(d)
        assert c.finding_id == "M-1"
        assert c.finding_severity == ReviewSeverity.MAJOR
        assert c.challenger == "kiro"

    def test_roundtrip(self) -> None:
        c = Challenge(
            finding_id="S-1",
            finding_severity=ReviewSeverity.MINOR,
            challenger="yui",
            reason="style",
        )
        c2 = Challenge.from_dict(c.to_dict())
        assert c2.finding_id == c.finding_id
        assert c2.reason == c.reason
