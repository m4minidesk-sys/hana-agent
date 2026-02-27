"""Pytest configuration and shared fixtures for yui-agent test suite.

This module defines:
- Test classification markers (unit/component/integration/e2e/security)
- Shared mock fixtures for external dependencies
- Test quality enforcement (goldbergyoni R1-R28 + t-wada TW1-TW8)
"""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom pytest markers for test classification."""
    config.addinivalue_line(
        "markers",
        "unit: Unit tests - test individual functions/classes in isolation"
    )
    config.addinivalue_line(
        "markers",
        "component: Component tests - test API/module boundaries with mocked dependencies"
    )
    config.addinivalue_line(
        "markers",
        "integration: Integration tests - test real external service interactions"
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests - test complete user workflows"
    )
    config.addinivalue_line(
        "markers",
        "security: Security tests - test injection, traversal, and attack scenarios"
    )
