"""Tests for yui.autonomy.budget — Cost Budget Guard (AC-77)."""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from yui.autonomy.budget import (
    BEDROCK_PRICING,
    CostBudgetGuard,
    UsageRecord,
)


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

SONNET_MODEL = "us.anthropic.claude-sonnet-4-20250514-v1:0"


@pytest.fixture()
def usage_file(tmp_path: Path) -> Path:
    return tmp_path / "usage.json"


@pytest.fixture()
def guard(usage_file: Path) -> CostBudgetGuard:
    return CostBudgetGuard(
        max_monthly_usd=10.0,
        warning_threshold_pct=80.0,
        usage_file=str(usage_file),
    )


# --------------------------------------------------------------------------
# record_usage
# --------------------------------------------------------------------------


class TestRecordUsage:
    def test_record_single_usage(self, guard: CostBudgetGuard):
        rec = guard.record_usage(SONNET_MODEL, 1000, 500)
        assert isinstance(rec, UsageRecord)
        assert rec.model_id == SONNET_MODEL
        assert rec.input_tokens == 1000
        assert rec.output_tokens == 500
        assert rec.estimated_cost_usd > 0

    def test_record_accumulates(self, guard: CostBudgetGuard):
        guard.record_usage(SONNET_MODEL, 1000, 500)
        guard.record_usage(SONNET_MODEL, 2000, 1000)
        assert len(guard.records) == 2

    def test_record_persists_to_file(self, guard: CostBudgetGuard, usage_file: Path):
        guard.record_usage(SONNET_MODEL, 1000, 500)
        assert usage_file.exists()
        data = json.loads(usage_file.read_text())
        assert len(data["records"]) == 1

    def test_record_unknown_model_uses_fallback(self, guard: CostBudgetGuard):
        rec = guard.record_usage("unknown-model-id", 1000, 500)
        # Should use sonnet pricing as fallback
        expected = (1000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert abs(rec.estimated_cost_usd - expected) < 0.001


# --------------------------------------------------------------------------
# get_monthly_cost
# --------------------------------------------------------------------------


class TestGetMonthlyCost:
    def test_empty_cost(self, guard: CostBudgetGuard):
        assert guard.get_monthly_cost() == 0.0

    def test_accumulates_current_month(self, guard: CostBudgetGuard):
        guard.record_usage(SONNET_MODEL, 1000, 500)
        guard.record_usage(SONNET_MODEL, 1000, 500)
        expected_per_call = (1000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert abs(guard.get_monthly_cost() - expected_per_call * 2) < 0.001

    def test_excludes_previous_month(self, guard: CostBudgetGuard):
        # Add a record from last month
        last_month = (datetime.now(timezone.utc) - timedelta(days=35)).isoformat()
        guard.records.append(
            UsageRecord(
                timestamp=last_month,
                model_id=SONNET_MODEL,
                input_tokens=100000,
                output_tokens=50000,
                estimated_cost_usd=999.0,
            )
        )
        # This month
        guard.record_usage(SONNET_MODEL, 1000, 500)
        expected = (1000 / 1000) * 0.003 + (500 / 1000) * 0.015
        assert abs(guard.get_monthly_cost() - expected) < 0.001


# --------------------------------------------------------------------------
# check_budget — AC-77
# --------------------------------------------------------------------------


class TestCheckBudget:
    """AC-77: max_monthly_bedrock_usd enforced; warning at 80%, hard stop at 100%."""

    def test_under_budget_ok(self, guard: CostBudgetGuard):
        guard.record_usage(SONNET_MODEL, 1000, 500)  # Tiny cost
        ok, msg = guard.check_budget()
        assert ok is True
        assert msg == "ok"

    def test_warning_at_80_percent(self, usage_file: Path):
        guard = CostBudgetGuard(max_monthly_usd=1.0, usage_file=str(usage_file))
        # Cost ~$0.003 + $0.015 per 1k tokens each call
        # Need ~$0.80 for 80% of $1.00
        # Each call with 10k input + 10k output ≈ $0.03 + $0.15 = $0.18
        for _ in range(5):  # 5 * $0.18 = $0.90 → 90% > 80%
            guard.record_usage(SONNET_MODEL, 10000, 10000)
        ok, msg = guard.check_budget()
        assert ok is True  # Warning but still allowed
        assert "Budget warning" in msg

    def test_hard_stop_at_100_percent(self, usage_file: Path):
        guard = CostBudgetGuard(max_monthly_usd=0.10, usage_file=str(usage_file))
        # One call: 10k input + 10k output ≈ $0.18 — exceeds $0.10
        guard.record_usage(SONNET_MODEL, 10000, 10000)
        ok, msg = guard.check_budget()
        assert ok is False
        assert "Budget exceeded" in msg

    def test_zero_budget_always_ok(self, usage_file: Path):
        guard = CostBudgetGuard(max_monthly_usd=0.0, usage_file=str(usage_file))
        guard.record_usage(SONNET_MODEL, 100000, 100000)
        ok, msg = guard.check_budget()
        assert ok is True


# --------------------------------------------------------------------------
# reset
# --------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_records(self, guard: CostBudgetGuard):
        guard.record_usage(SONNET_MODEL, 1000, 500)
        guard.reset()
        assert len(guard.records) == 0
        assert guard.get_monthly_cost() == 0.0

    def test_reset_persists(self, guard: CostBudgetGuard, usage_file: Path):
        guard.record_usage(SONNET_MODEL, 1000, 500)
        guard.reset()
        data = json.loads(usage_file.read_text())
        assert len(data["records"]) == 0


# --------------------------------------------------------------------------
# Persistence
# --------------------------------------------------------------------------


class TestPersistence:
    def test_load_from_existing_file(self, usage_file: Path):
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "records": [
                {
                    "timestamp": now,
                    "model_id": SONNET_MODEL,
                    "input_tokens": 5000,
                    "output_tokens": 2000,
                    "estimated_cost_usd": 0.045,
                }
            ]
        }
        usage_file.write_text(json.dumps(data))
        guard = CostBudgetGuard(usage_file=str(usage_file))
        assert len(guard.records) == 1
        assert guard.records[0].input_tokens == 5000

    def test_load_corrupted_file(self, usage_file: Path):
        usage_file.write_text("not json")
        guard = CostBudgetGuard(usage_file=str(usage_file))
        assert len(guard.records) == 0

    def test_load_nonexistent_file(self, tmp_path: Path):
        guard = CostBudgetGuard(usage_file=str(tmp_path / "does_not_exist.json"))
        assert len(guard.records) == 0


# --------------------------------------------------------------------------
# Pricing
# --------------------------------------------------------------------------


class TestPricing:
    def test_sonnet_pricing_exists(self):
        assert SONNET_MODEL in BEDROCK_PRICING

    def test_cost_calculation(self, guard: CostBudgetGuard):
        rec = guard.record_usage(SONNET_MODEL, 1000, 1000)
        expected = (1000 / 1000) * 0.003 + (1000 / 1000) * 0.015
        assert abs(rec.estimated_cost_usd - expected) < 0.0001
