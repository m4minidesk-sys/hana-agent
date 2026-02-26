"""Cost budget guard — enforce monthly Bedrock spend limits (AC-77).

Tracks per-invocation token usage, warns at 80% of budget, and
hard-stops at 100%.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bedrock pricing (per 1K tokens, us-east-1, 2026)
# ---------------------------------------------------------------------------

BEDROCK_PRICING: dict[str, dict[str, float]] = {
    "us.anthropic.claude-sonnet-4-20250514-v1:0": {
        "input_per_1k": 0.003,
        "output_per_1k": 0.015,
    },
    "us.anthropic.claude-haiku-3-20250307-v1:0": {
        "input_per_1k": 0.00025,
        "output_per_1k": 0.00125,
    },
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class UsageRecord:
    """A single API invocation's token usage."""

    timestamp: str
    model_id: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


# ---------------------------------------------------------------------------
# Budget status
# ---------------------------------------------------------------------------

class BudgetExceededError(Exception):
    """Raised when the monthly budget is exceeded."""


class CostBudgetGuard:
    """Track and enforce monthly Bedrock cost limits (AC-77).

    Parameters
    ----------
    max_monthly_usd:
        Hard monthly spending cap in USD.
    warning_threshold_pct:
        Percentage of budget at which a warning is emitted.
    usage_file:
        Path to the JSON file storing usage records.
    """

    def __init__(
        self,
        max_monthly_usd: float = 50.0,
        warning_threshold_pct: float = 80.0,
        usage_file: str = "~/.yui/usage.json",
    ) -> None:
        self.max_monthly_usd = max_monthly_usd
        self.warning_threshold_pct = warning_threshold_pct
        self.usage_file = Path(os.path.expanduser(usage_file))
        self.records: list[UsageRecord] = []
        self._load_usage()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_usage(
        self,
        model_id: str,
        input_tokens: int,
        output_tokens: int,
    ) -> UsageRecord:
        """Record an API invocation's token usage.

        Returns the created ``UsageRecord``.
        """
        cost = self._estimate_cost(model_id, input_tokens, output_tokens)
        record = UsageRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_id=model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
        )
        self.records.append(record)
        self._save_usage()
        return record

    def get_monthly_cost(self) -> float:
        """Return the total estimated cost for the current calendar month."""
        now = datetime.now(timezone.utc)
        current_month = now.strftime("%Y-%m")

        total = 0.0
        for rec in self.records:
            if rec.timestamp[:7] == current_month:
                total += rec.estimated_cost_usd
        return total

    def check_budget(self) -> tuple[bool, str]:
        """Check current spend against the monthly budget.

        Returns ``(allowed, message)`` where *allowed* is False when the
        hard cap is reached.
        """
        cost = self.get_monthly_cost()

        if self.max_monthly_usd <= 0:
            return True, "ok"

        pct = (cost / self.max_monthly_usd) * 100

        if pct >= 100:
            msg = f"Budget exceeded: ${cost:.2f}/${self.max_monthly_usd:.2f}"
            logger.error(msg)
            return False, msg

        if pct >= self.warning_threshold_pct:
            msg = f"Budget warning: ${cost:.2f}/${self.max_monthly_usd:.2f} ({pct:.0f}%)"
            logger.warning(msg)
            return True, msg

        return True, "ok"

    def reset(self) -> None:
        """Clear all usage records and persist the empty state."""
        self.records.clear()
        self._save_usage()
        logger.info("Usage records reset.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
        """Estimate USD cost for a single invocation."""
        pricing = BEDROCK_PRICING.get(model_id)
        if pricing is None:
            # Unknown model — use sonnet pricing as fallback
            pricing = BEDROCK_PRICING.get(
                "us.anthropic.claude-sonnet-4-20250514-v1:0",
                {"input_per_1k": 0.003, "output_per_1k": 0.015},
            )
        input_cost = (input_tokens / 1000) * pricing["input_per_1k"]
        output_cost = (output_tokens / 1000) * pricing["output_per_1k"]
        return input_cost + output_cost

    def _load_usage(self) -> None:
        """Load records from the JSON file."""
        if not self.usage_file.exists():
            self.records = []
            return

        try:
            with open(self.usage_file) as f:
                data = json.load(f)

            self.records = [
                UsageRecord(**rec) for rec in data.get("records", [])
            ]
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Could not load usage file %s: %s", self.usage_file, exc)
            self.records = []

    def _save_usage(self) -> None:
        """Persist records to the JSON file."""
        self.usage_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"records": [asdict(r) for r in self.records]}
        with open(self.usage_file, "w") as f:
            json.dump(data, f, indent=2)
