"""Tests for yui.autonomy.levels — Autonomy Levels (AC-76, AC-80)."""

from __future__ import annotations

import pytest

from yui.autonomy.levels import (
    AutonomyLevel,
    AutonomyManager,
    LevelTransition,
    TRANSITION_CRITERIA,
)



pytestmark = pytest.mark.unit

# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------


def _make_config(level: int = 1, overrides: dict | None = None) -> dict:
    return {
        "autonomy": {
            "level": level,
            "per_task_overrides": overrides or {},
        },
    }


# --------------------------------------------------------------------------
# AutonomyLevel enum
# --------------------------------------------------------------------------


class TestAutonomyLevel:
    def test_level_values(self):
        assert AutonomyLevel.L0_MANUAL == 0
        assert AutonomyLevel.L1_ASSISTED == 1
        assert AutonomyLevel.L2_SUPERVISED == 2
        assert AutonomyLevel.L3_AUTONOMOUS == 3
        assert AutonomyLevel.L4_SELF_EVOLVING == 4

    def test_level_ordering(self):
        assert AutonomyLevel.L0_MANUAL < AutonomyLevel.L4_SELF_EVOLVING

    def test_level_from_int(self):
        assert AutonomyLevel(2) == AutonomyLevel.L2_SUPERVISED


# --------------------------------------------------------------------------
# get_level — AC-76
# --------------------------------------------------------------------------


class TestGetLevel:
    """AC-76: Autonomy level configurable in config.yaml with per-task override."""

    def test_default_level(self):
        mgr = AutonomyManager(_make_config(level=1))
        assert mgr.get_level() == AutonomyLevel.L1_ASSISTED

    def test_custom_level(self):
        mgr = AutonomyManager(_make_config(level=3))
        assert mgr.get_level() == AutonomyLevel.L3_AUTONOMOUS

    def test_per_task_override(self):
        mgr = AutonomyManager(_make_config(level=3, overrides={"security": 1}))
        assert mgr.get_level("security") == AutonomyLevel.L1_ASSISTED
        assert mgr.get_level("coding") == AutonomyLevel.L3_AUTONOMOUS

    def test_per_task_override_unknown_task(self):
        mgr = AutonomyManager(_make_config(level=2, overrides={"deploy": 0}))
        assert mgr.get_level("other") == AutonomyLevel.L2_SUPERVISED

    def test_level_none_task_type(self):
        mgr = AutonomyManager(_make_config(level=2))
        assert mgr.get_level(None) == AutonomyLevel.L2_SUPERVISED

    def test_empty_config_defaults_l1(self):
        mgr = AutonomyManager({})
        assert mgr.get_level() == AutonomyLevel.L1_ASSISTED


# --------------------------------------------------------------------------
# can_execute_autonomously
# --------------------------------------------------------------------------


class TestCanExecuteAutonomously:
    def test_l0_cannot(self):
        mgr = AutonomyManager(_make_config(level=0))
        assert mgr.can_execute_autonomously() is False

    def test_l1_cannot(self):
        mgr = AutonomyManager(_make_config(level=1))
        assert mgr.can_execute_autonomously() is False

    def test_l2_can(self):
        mgr = AutonomyManager(_make_config(level=2))
        assert mgr.can_execute_autonomously() is True

    def test_l3_can(self):
        mgr = AutonomyManager(_make_config(level=3))
        assert mgr.can_execute_autonomously() is True

    def test_l4_can(self):
        mgr = AutonomyManager(_make_config(level=4))
        assert mgr.can_execute_autonomously() is True

    def test_per_task_override_restricts(self):
        mgr = AutonomyManager(_make_config(level=3, overrides={"risky": 1}))
        assert mgr.can_execute_autonomously("risky") is False
        assert mgr.can_execute_autonomously("normal") is True


# --------------------------------------------------------------------------
# check_transition
# --------------------------------------------------------------------------


class TestCheckTransition:
    """Level transition criteria checks."""

    def test_l0_to_l1_setup_complete(self):
        mgr = AutonomyManager(_make_config(level=0))
        stats = {"setup_complete": True}
        transition = mgr.check_transition(stats)
        assert transition is not None
        assert transition.to_level == AutonomyLevel.L1_ASSISTED

    def test_l0_to_l1_setup_not_complete(self):
        mgr = AutonomyManager(_make_config(level=0))
        stats = {"setup_complete": False}
        assert mgr.check_transition(stats) is None

    def test_l1_to_l2(self):
        mgr = AutonomyManager(_make_config(level=1))
        stats = {"min_successful_tasks": 25, "max_intervention_rate": 0.05}
        transition = mgr.check_transition(stats)
        assert transition is not None
        assert transition.to_level == AutonomyLevel.L2_SUPERVISED

    def test_l1_to_l2_insufficient_tasks(self):
        mgr = AutonomyManager(_make_config(level=1))
        stats = {"min_successful_tasks": 10, "max_intervention_rate": 0.05}
        assert mgr.check_transition(stats) is None

    def test_l1_to_l2_too_many_interventions(self):
        mgr = AutonomyManager(_make_config(level=1))
        stats = {"min_successful_tasks": 25, "max_intervention_rate": 0.15}
        assert mgr.check_transition(stats) is None

    def test_l2_to_l3(self):
        mgr = AutonomyManager(_make_config(level=2))
        stats = {
            "min_successful_tasks": 60,
            "min_kiro_catch_rate": 0.95,
            "max_security_incidents": 0,
        }
        transition = mgr.check_transition(stats)
        assert transition is not None
        assert transition.to_level == AutonomyLevel.L3_AUTONOMOUS
        assert transition.approved_by == "han"

    def test_l3_to_l4(self):
        mgr = AutonomyManager(_make_config(level=3))
        stats = {"min_successful_tasks": 120, "min_eval_accuracy": 0.90}
        transition = mgr.check_transition(stats)
        assert transition is not None
        assert transition.to_level == AutonomyLevel.L4_SELF_EVOLVING
        assert transition.approved_by == "han"

    def test_l4_no_further_transition(self):
        mgr = AutonomyManager(_make_config(level=4))
        stats = {"anything": True}
        assert mgr.check_transition(stats) is None

    def test_missing_stat_blocks_transition(self):
        mgr = AutonomyManager(_make_config(level=1))
        stats = {"min_successful_tasks": 25}  # Missing max_intervention_rate
        assert mgr.check_transition(stats) is None


# --------------------------------------------------------------------------
# apply_transition
# --------------------------------------------------------------------------


class TestApplyTransition:
    def test_apply_transition(self):
        mgr = AutonomyManager(_make_config(level=1))
        transition = LevelTransition(
            from_level=AutonomyLevel.L1_ASSISTED,
            to_level=AutonomyLevel.L2_SUPERVISED,
            criteria_met={"min_successful_tasks": 25},
            approved_by="automatic",
        )
        mgr.apply_transition(transition)
        assert mgr.level == AutonomyLevel.L2_SUPERVISED
        assert len(mgr.transitions) == 1


# --------------------------------------------------------------------------
# emergency_downgrade
# --------------------------------------------------------------------------


class TestEmergencyDowngrade:
    """Emergency downgrade to L0."""

    def test_downgrades_to_l0(self):
        mgr = AutonomyManager(_make_config(level=3))
        transition = mgr.emergency_downgrade("Security incident")
        assert mgr.level == AutonomyLevel.L0_MANUAL
        assert transition.from_level == AutonomyLevel.L3_AUTONOMOUS
        assert transition.to_level == AutonomyLevel.L0_MANUAL

    def test_downgrade_from_any_level(self):
        for level in range(5):
            mgr = AutonomyManager(_make_config(level=level))
            mgr.emergency_downgrade("test")
            assert mgr.level == AutonomyLevel.L0_MANUAL

    def test_downgrade_records_reason(self):
        mgr = AutonomyManager(_make_config(level=2))
        transition = mgr.emergency_downgrade("3 consecutive failures")
        assert transition.criteria_met["reason"] == "3 consecutive failures"

    def test_downgrade_records_transition_history(self):
        mgr = AutonomyManager(_make_config(level=3))
        mgr.emergency_downgrade("incident")
        assert len(mgr.transitions) == 1
        assert mgr.transitions[0].to_level == AutonomyLevel.L0_MANUAL
