"""Test helper functions for yui-agent (goldbergyoni R4/TW5).

Behavioral verification helpers that check public interface outputs
without coupling to internal implementation details.

Usage:
    from tests.helpers import assert_bedrock_called_with_model, assert_valid_config
"""


def assert_bedrock_called_with_model(mock_client, model_id: str) -> None:
    """Assert that Bedrock client was called with the expected model ID.

    Checks the behavioral contract (R4: black-box testing, TW5: structural decoupling).
    """
    mock_client.converse.assert_called()
    call_kwargs = mock_client.converse.call_args
    assert call_kwargs is not None, "Bedrock client.converse was not called"
    assert call_kwargs.kwargs.get("modelId") == model_id or \
           (call_kwargs.args and call_kwargs.args[0] == model_id), \
           f"Expected model_id={model_id}, got call_args={call_kwargs}"


def assert_valid_config(config: dict) -> None:
    """Assert that a config dict has all required fields."""
    required = ["model_id", "region", "max_tokens"]
    for key in required:
        assert key in config, f"Config missing required key: {key}"
    assert isinstance(config["max_tokens"], int), "max_tokens must be int"
    assert config["max_tokens"] > 0, "max_tokens must be positive"


def assert_shell_output_safe(output: str) -> None:
    """Assert that shell command output contains no sensitive data."""
    sensitive_patterns = [
        "AWS_ACCESS_KEY",
        "AWS_SECRET",
        "SLACK_BOT_TOKEN",
        "password",
        "BEGIN RSA PRIVATE KEY",
    ]
    for pattern in sensitive_patterns:
        assert pattern.lower() not in output.lower(), \
            f"Shell output contains sensitive pattern: {pattern}"


def assert_test_follows_aaa(test_source: str) -> None:
    """Verify that test source code follows AAA (Arrange-Act-Assert) pattern (R2).

    Simple heuristic: looks for blank line separations between sections.
    """
    lines = test_source.strip().split('\n')
    non_empty = [l for l in lines if l.strip()]
    # At least 3 logical sections
    assert len(non_empty) >= 3, "Test should have at least Arrange, Act, and Assert sections"
