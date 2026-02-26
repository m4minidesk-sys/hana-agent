"""Autonomy package — Yui⇔Kiro cross-review, self-evaluation, and self-improvement."""

from yui.autonomy.budget import (
    BEDROCK_PRICING,
    BudgetExceededError,
    CostBudgetGuard,
    UsageRecord,
)
from yui.autonomy.conflict import Challenge, ConflictResolver
from yui.autonomy.evaluator import TaskEvaluation, TaskEvaluator
from yui.autonomy.improver import (
    DirectModificationError,
    ImprovementProposal,
    ImprovementResult,
    SelfImprover,
)
from yui.autonomy.levels import (
    AutonomyLevel,
    AutonomyManager,
    LevelTransition,
    TRANSITION_CRITERIA,
)
from yui.autonomy.reflexion import (
    ReflexionGraph,
    ReflexionMaxCyclesError,
    ReflexionState,
    ReflexionTimeoutError,
    ReviewFinding,
    ReviewResult,
    ReviewSeverity,
)

__all__ = [
    # budget
    "BEDROCK_PRICING",
    "BudgetExceededError",
    "CostBudgetGuard",
    "UsageRecord",
    # conflict
    "Challenge",
    "ConflictResolver",
    # evaluator
    "TaskEvaluation",
    "TaskEvaluator",
    # improver
    "DirectModificationError",
    "ImprovementProposal",
    "ImprovementResult",
    "SelfImprover",
    # levels
    "AutonomyLevel",
    "AutonomyManager",
    "LevelTransition",
    "TRANSITION_CRITERIA",
    # reflexion
    "ReflexionGraph",
    "ReflexionMaxCyclesError",
    "ReflexionState",
    "ReflexionTimeoutError",
    "ReviewFinding",
    "ReviewResult",
    "ReviewSeverity",
]
