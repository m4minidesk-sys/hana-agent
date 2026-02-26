"""Autonomy level management (AC-76, AC-80).

Yui operates at configurable autonomy levels (L0-L4).  Each level
determines what actions can be taken without human approval.

Levels
------
- **L0 (Manual)**: Every action requires approval.
- **L1 (Assisted)**: Suggestions only; human executes.
- **L2 (Supervised)**: Executes autonomously with notification.
- **L3 (Autonomous)**: Full autonomy for routine tasks.
- **L4 (Self-Evolving)**: Can propose self-improvements.

Per-task overrides allow fine-grained control (e.g. security tasks
always at L1 even when global level is L3).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Autonomy levels
# ---------------------------------------------------------------------------

class AutonomyLevel(IntEnum):
    """Autonomy levels L0 through L4."""

    L0_MANUAL = 0
    L1_ASSISTED = 1
    L2_SUPERVISED = 2
    L3_AUTONOMOUS = 3
    L4_SELF_EVOLVING = 4


# ---------------------------------------------------------------------------
# Transition tracking
# ---------------------------------------------------------------------------

@dataclass
class LevelTransition:
    """Records a level transition event."""

    from_level: AutonomyLevel
    to_level: AutonomyLevel
    criteria_met: dict[str, Any]
    approved_by: str  # "automatic" | "han"
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Transition criteria
# ---------------------------------------------------------------------------

TRANSITION_CRITERIA: dict[tuple[int, int], dict[str, Any]] = {
    # L0 → L1: setup complete
    (0, 1): {
        "setup_complete": True,
    },
    # L1 → L2: 20+ tasks, <10% intervention
    (1, 2): {
        "min_successful_tasks": 20,
        "max_intervention_rate": 0.10,
    },
    # L2 → L3: 50+ tasks, Kiro catches 90%+ issues, 0 security incidents
    (2, 3): {
        "min_successful_tasks": 50,
        "min_kiro_catch_rate": 0.90,
        "max_security_incidents": 0,
    },
    # L3 → L4: 100+ tasks, eval accuracy >85%
    (3, 4): {
        "min_successful_tasks": 100,
        "min_eval_accuracy": 0.85,
    },
}


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class AutonomyManager:
    """Manage the current autonomy level and per-task overrides (AC-76).

    Parameters
    ----------
    config:
        Configuration dict (the ``autonomy`` section of config.yaml).
    """

    def __init__(self, config: dict[str, Any]) -> None:
        autonomy_cfg = config.get("autonomy", {})
        self.level = AutonomyLevel(autonomy_cfg.get("level", 1))
        self.per_task_overrides: dict[str, int] = autonomy_cfg.get("per_task_overrides", {})
        self.transitions: list[LevelTransition] = []

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_level(self, task_type: str | None = None) -> AutonomyLevel:
        """Return the effective autonomy level for *task_type*.

        If a per-task override exists, that takes precedence.
        """
        if task_type and task_type in self.per_task_overrides:
            return AutonomyLevel(self.per_task_overrides[task_type])
        return self.level

    def can_execute_autonomously(self, task_type: str | None = None) -> bool:
        """Return True if the effective level is L2 (Supervised) or above."""
        return self.get_level(task_type) >= AutonomyLevel.L2_SUPERVISED

    # ------------------------------------------------------------------
    # Transitions (AC-76)
    # ------------------------------------------------------------------

    def check_transition(self, stats: dict[str, Any]) -> Optional[LevelTransition]:
        """Check if a level transition is warranted based on *stats*.

        Returns a ``LevelTransition`` if criteria are met, else ``None``.
        The transition is **not** applied automatically — call
        ``apply_transition()`` after human approval when required.
        """
        current = int(self.level)
        next_level = current + 1

        if next_level > AutonomyLevel.L4_SELF_EVOLVING:
            return None  # Already at max

        criteria = TRANSITION_CRITERIA.get((current, next_level))
        if criteria is None:
            return None

        criteria_met: dict[str, Any] = {}

        for key, required in criteria.items():
            actual = stats.get(key)
            if actual is None:
                return None  # Missing stat → cannot evaluate

            if key.startswith("min_"):
                if actual < required:
                    return None
            elif key.startswith("max_"):
                if actual > required:
                    return None
            elif isinstance(required, bool):
                if actual != required:
                    return None

            criteria_met[key] = actual

        transition = LevelTransition(
            from_level=self.level,
            to_level=AutonomyLevel(next_level),
            criteria_met=criteria_met,
            approved_by="automatic" if next_level <= 2 else "han",
        )
        return transition

    def apply_transition(self, transition: LevelTransition) -> None:
        """Apply a previously checked transition."""
        logger.info(
            "Level transition: %s → %s (approved by: %s)",
            transition.from_level.name,
            transition.to_level.name,
            transition.approved_by,
        )
        self.level = transition.to_level
        self.transitions.append(transition)

    # ------------------------------------------------------------------
    # Emergency downgrade
    # ------------------------------------------------------------------

    def emergency_downgrade(self, reason: str) -> LevelTransition:
        """Immediately downgrade to L0 (Manual).

        Used for security incidents or consecutive failures.
        Returns the transition record.
        """
        transition = LevelTransition(
            from_level=self.level,
            to_level=AutonomyLevel.L0_MANUAL,
            criteria_met={"reason": reason},
            approved_by="automatic",
        )
        logger.warning(
            "EMERGENCY DOWNGRADE: %s → L0_MANUAL — %s",
            self.level.name,
            reason,
        )
        self.level = AutonomyLevel.L0_MANUAL
        self.transitions.append(transition)
        return transition
