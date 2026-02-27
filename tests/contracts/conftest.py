"""Shared fixtures for contract tests.

Provides real clients for AWS Bedrock, Slack, and boto3 services.
"""

import os
from datetime import datetime

import boto3
import pytest
from slack_sdk import WebClient


@pytest.fixture
def bedrock_client():
    """Real Bedrock client for contract tests."""
    try:
        client = boto3.client("bedrock-runtime", region_name="us-east-1")
        # Test credentials
        boto3.client("bedrock", region_name="us-east-1").list_foundation_models()
        return client
    except Exception:
        pytest.skip("AWS credentials not configured")


@pytest.fixture
def slack_client():
    """Real Slack client for contract tests."""
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token:
        pytest.skip("SLACK_BOT_TOKEN not set")
    return WebClient(token=token)


@pytest.fixture
def cfn_client():
    """Real CloudFormation client for contract tests."""
    try:
        client = boto3.client("cloudformation", region_name="us-east-1")
        # Test credentials
        client.describe_stacks()
        return client
    except Exception:
        pytest.skip("AWS credentials not configured")


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
