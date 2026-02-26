"""Tests for Slack adapter."""

import os

import pytest

from yui.slack_adapter import _load_tokens


def test_load_tokens_from_env(monkeypatch) -> None:
    """Test token loading from environment variables."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-test")
    
    bot_token, app_token = _load_tokens({})
    assert bot_token == "xoxb-test"
    assert app_token == "xapp-test"


def test_load_tokens_from_config(monkeypatch, tmp_path) -> None:
    """Test token loading from config."""
    # Clear environment
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    
    # Create empty .env file to prevent loading from ~/.yui/.env
    env_file = tmp_path / ".env"
    env_file.write_text("")
    monkeypatch.setenv("HOME", str(tmp_path))
    
    config = {
        "slack": {
            "bot_token": "xoxb-config",
            "app_token": "xapp-config",
        }
    }
    
    bot_token, app_token = _load_tokens(config)
    assert bot_token == "xoxb-config"
    assert app_token == "xapp-config"


def test_load_tokens_missing(monkeypatch, tmp_path) -> None:
    """Test error when tokens are missing."""
    # Clear environment
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    monkeypatch.delenv("SLACK_APP_TOKEN", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    
    with pytest.raises(ValueError, match="Missing Slack tokens"):
        _load_tokens({})


def test_load_tokens_env_priority(monkeypatch) -> None:
    """Test environment variables take priority over config."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-env")
    monkeypatch.setenv("SLACK_APP_TOKEN", "xapp-env")
    
    config = {
        "slack": {
            "bot_token": "xoxb-config",
            "app_token": "xapp-config",
        }
    }
    
    bot_token, app_token = _load_tokens(config)
    assert bot_token == "xoxb-env"
    assert app_token == "xapp-env"
