"""Autonomy package — self-evaluation, improvement, levels and budget."""

from yui.autonomy.budget import (
    BEDROCK_PRICING,
    BudgetExceededError,
    CostBudgetGuard,
    UsageRecord,
)
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

__all__ = [
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
    # budget
    "BEDROCK_PRICING",
    "BudgetExceededError",
    "CostBudgetGuard",
    "UsageRecord",
]
