"""Tests for Slack adapter."""

import os
from unittest.mock import MagicMock, patch

import pytest

from yui.slack_adapter import _load_tokens


def test_load_tokens_from_env() -> None:
    """Test token loading from environment variables."""
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test", "SLACK_APP_TOKEN": "xapp-test"}):
        bot_token, app_token = _load_tokens({})
        assert bot_token == "xoxb-test"
        assert app_token == "xapp-test"


def test_load_tokens_from_config() -> None:
    """Test token loading from config."""
    config = {
        "slack": {
            "bot_token": "xoxb-config",
            "app_token": "xapp-config",
        }
    }
    with patch.dict(os.environ, {}, clear=True):
        bot_token, app_token = _load_tokens(config)
        assert bot_token == "xoxb-config"
        assert app_token == "xapp-config"


def test_load_tokens_missing() -> None:
    """Test error when tokens are missing."""
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(ValueError, match="Missing Slack tokens"):
            _load_tokens({})


def test_load_tokens_env_priority() -> None:
    """Test environment variables take priority over config."""
    config = {
        "slack": {
            "bot_token": "xoxb-config",
            "app_token": "xapp-config",
        }
    }
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-env", "SLACK_APP_TOKEN": "xapp-env"}):
        bot_token, app_token = _load_tokens(config)
        assert bot_token == "xoxb-env"
        assert app_token == "xapp-env"
