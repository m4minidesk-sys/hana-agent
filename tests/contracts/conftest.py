"""Shared fixtures for contract tests.

Provides mocked clients for AWS Bedrock, Slack, and boto3 services.
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def bedrock_client():
    """Mocked Bedrock client for contract tests."""
    return MagicMock()


@pytest.fixture
def slack_client():
    """Mocked Slack client for contract tests."""
    return MagicMock()


@pytest.fixture
def cfn_client():
    """Mocked CloudFormation client for contract tests."""
    return MagicMock()


@pytest.fixture
def lambda_client():
    """Mocked Lambda client for contract tests."""
    return MagicMock()


@pytest.fixture
def secrets_client():
    """Mocked Secrets Manager client for contract tests."""
    return MagicMock()


def assert_schema_match(response: dict, schema: dict) -> None:
    """Assert that response matches schema structure."""
    for key_path, expected_type in schema.items():
        keys = key_path.split(".")
        value = response
        for key in keys:
            if "[" in key:
                # Handle list indexing: "Stacks[0]"
                key_name, idx = key.split("[")
                idx = int(idx.rstrip("]"))
                value = value[key_name][idx]
            else:
                value = value[key]
        
        if expected_type == "datetime":
            assert isinstance(value, datetime), f"{key_path}: expected datetime, got {type(value)}"
        else:
            assert isinstance(value, expected_type), f"{key_path}: expected {expected_type}, got {type(value)}"
