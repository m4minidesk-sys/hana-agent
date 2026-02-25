"""Tests for HANA guardrails filter."""

from __future__ import annotations

from typing import Any

import pytest

from hana.runtime.guardrails import GuardrailsFilter


class TestGuardrailsFilter:
    """Tests for GuardrailsFilter."""

    def test_disabled_allows_all(self) -> None:
        config = {"guardrails": {"enabled": False}}
        gf = GuardrailsFilter(config)
        result = gf.filter_input("test content")
        assert result["allowed"] is True
        assert result["text"] == "test content"

    def test_disabled_output_allows_all(self) -> None:
        config = {"guardrails": {"enabled": False}}
        gf = GuardrailsFilter(config)
        result = gf.filter_output("test output")
        assert result["allowed"] is True

    def test_is_active_when_disabled(self) -> None:
        config = {"guardrails": {"enabled": False}}
        gf = GuardrailsFilter(config)
        assert gf.is_active is False

    def test_enabled_no_guardrail_id(self) -> None:
        config = {"guardrails": {"enabled": True, "guardrail_id": ""}}
        gf = GuardrailsFilter(config)
        # Should be effectively disabled without an ID
        result = gf.filter_input("test")
        assert result["allowed"] is True

    def test_enabled_no_boto3(self) -> None:
        # Even with enabled=True, if boto3/client init fails,
        # it should gracefully degrade
        config = {
            "guardrails": {
                "enabled": True,
                "guardrail_id": "fake-id",
                "guardrail_version": "DRAFT",
            },
            "agent": {"region": "us-east-1"},
        }
        # GuardrailsFilter tries to init client, may fail if no credentials
        gf = GuardrailsFilter(config)
        # Should still work (fail-open)
        result = gf.filter_input("test content")
        assert result["allowed"] is True
