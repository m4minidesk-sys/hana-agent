"""Conflict resolution for Yui⇔Kiro review cycles (AC-82).

When Yui disagrees with a Kiro finding, she can CHALLENGE it.
Kiro re-evaluates. Unresolved Criticals escalate to han.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from yui.autonomy.reflexion import ReviewFinding, ReviewSeverity

logger = logging.getLogger(__name__)


@dataclass
class Challenge:
    """A challenge to a review finding."""

    finding_id: str
    finding_severity: ReviewSeverity
    challenger: str  # "yui" | "kiro"
    reason: str
    resolution: str = ""  # "accepted" | "dismissed" | "escalated"
    kiro_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict."""
        return {
            "finding_id": self.finding_id,
            "finding_severity": self.finding_severity.value,
            "challenger": self.challenger,
            "reason": self.reason,
            "resolution": self.resolution,
            "kiro_response": self.kiro_response,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Challenge:
        """Deserialize from dict."""
        return cls(
            finding_id=data["finding_id"],
            finding_severity=ReviewSeverity(data["finding_severity"]),
            challenger=data["challenger"],
            reason=data["reason"],
            resolution=data.get("resolution", ""),
            kiro_response=data.get("kiro_response", ""),
        )


class ConflictResolver:
    """Handles challenges between Yui and Kiro during review cycles.

    Flow:
    1. Yui challenges a Kiro finding (challenge_finding)
    2. Kiro re-evaluates (resolve_challenge)
    3. If unresolved Critical → escalate to han (should_escalate)
    """

    def __init__(self) -> None:
        self.challenges: list[Challenge] = []

    def challenge_finding(
        self,
        finding: ReviewFinding,
        reason: str,
        challenger: str = "yui",
    ) -> Challenge:
        """Create a challenge against a review finding.

        Args:
            finding: The finding being challenged.
            reason: Why the challenger disagrees.
            challenger: Who is challenging ("yui" or "kiro").

        Returns:
            The created Challenge object.
        """
        challenge = Challenge(
            finding_id=finding.id,
            finding_severity=finding.severity,
            challenger=challenger,
            reason=reason,
        )

        # Mark the finding as challenged
        finding.challenged = True
        finding.challenge_reason = reason

        self.challenges.append(challenge)
        logger.info(
            "Challenge created: %s challenges %s (%s) — %s",
            challenger,
            finding.id,
            finding.severity.value,
            reason,
        )

        return challenge

    def resolve_challenge(
        self,
        challenge: Challenge,
        kiro_response: str,
    ) -> Challenge:
        """Kiro re-evaluates a challenged finding.

        Resolution logic:
        - If Kiro agrees the finding is invalid → "accepted" (finding dismissed)
        - If Kiro maintains the finding → "dismissed" (challenge rejected)
        - Unresolved Criticals → checked by should_escalate

        Args:
            challenge: The challenge to resolve.
            kiro_response: Kiro's response to the challenge.

        Returns:
            Updated Challenge with resolution.
        """
        challenge.kiro_response = kiro_response

        # Simple heuristic: if response contains agreement keywords, accept
        response_lower = kiro_response.lower()
        agreement_keywords = [
            "agree",
            "valid point",
            "you're right",
            "accepted",
            "retract",
            "withdraw",
            "false positive",
            "not an issue",
        ]
        dismissal_keywords = [
            "disagree",
            "maintain",
            "still valid",
            "confirmed",
            "stands",
            "reject",
            "important",
        ]

        agreement_score = sum(
            1 for kw in agreement_keywords if kw in response_lower
        )
        dismissal_score = sum(
            1 for kw in dismissal_keywords if kw in response_lower
        )

        if agreement_score > dismissal_score:
            challenge.resolution = "accepted"
            logger.info("Challenge %s accepted by Kiro", challenge.finding_id)
        else:
            challenge.resolution = "dismissed"
            logger.info("Challenge %s dismissed by Kiro", challenge.finding_id)

        return challenge

    def should_escalate(self, challenge: Challenge) -> bool:
        """Check if an unresolved challenge should escalate to han.

        Escalation criteria:
        - Finding severity is CRITICAL
        - Challenge was dismissed (Kiro maintains the finding)
        - OR resolution is empty (unresolved)

        Returns:
            True if the challenge should be escalated to han.
        """
        if challenge.finding_severity != ReviewSeverity.CRITICAL:
            return False

        # Escalate if dismissed or unresolved
        return challenge.resolution in ("dismissed", "")

    def get_escalation_summary(self, challenge: Challenge) -> str:
        """Generate a summary for han when escalating.

        Returns:
            Formatted string describing the conflict.
        """
        return (
            f"⚠️ Escalation: Unresolved Critical finding\n"
            f"Finding: {challenge.finding_id} ({challenge.finding_severity.value})\n"
            f"Challenger: {challenge.challenger}\n"
            f"Challenge reason: {challenge.reason}\n"
            f"Kiro response: {challenge.kiro_response}\n"
            f"Resolution: {challenge.resolution or 'unresolved'}\n"
            f"Action needed: han to decide whether this finding should be addressed."
        )

    def dismiss_minor_with_justification(
        self,
        finding: ReviewFinding,
        justification: str,
    ) -> Challenge:
        """Dismiss a Minor finding with justification (no Kiro re-evaluation needed).

        Minor findings can be dismissed by Yui with a reason, without requiring
        Kiro to re-evaluate. The challenge is auto-resolved as "accepted".

        Args:
            finding: The Minor finding to dismiss.
            justification: Why this Minor finding is acceptable.

        Returns:
            Auto-resolved Challenge.

        Raises:
            ValueError: If the finding is not Minor.
        """
        if finding.severity != ReviewSeverity.MINOR:
            raise ValueError(
                f"Only Minor findings can be auto-dismissed. "
                f"Got: {finding.severity.value}"
            )

        challenge = Challenge(
            finding_id=finding.id,
            finding_severity=finding.severity,
            challenger="yui",
            reason=justification,
            resolution="accepted",
            kiro_response="Auto-accepted: Minor finding dismissed with justification.",
        )

        finding.challenged = True
        finding.challenge_reason = justification

        self.challenges.append(challenge)
        logger.info(
            "Minor finding %s auto-dismissed: %s", finding.id, justification
        )

        return challenge
