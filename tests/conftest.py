"""Pytest configuration and shared fixtures for yui-agent test suite.

Test classification markers (unit/component/integration/e2e/security)
are defined in pyproject.toml [tool.pytest.ini_options].markers.

Shared mock fixtures follow goldbergyoni R5 (stub/spy over mock)
and R15 (no global seed — each fixture creates its own data).
"""

import unittest.mock
from unittest.mock import MagicMock, patch

import pytest
from faker import Faker


# ---------------------------------------------------------------------------
# autospec enforcement (Phase 2c)
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def enforce_autospec(request, monkeypatch):
    """Force autospec=True for all unittest.mock.patch calls.
    
    Opt-out: @pytest.mark.no_autospec
    """
    if "no_autospec" in request.keywords:
        yield
        return
    
    original_patch = unittest.mock.patch
    
    def autospec_patch(target, *args, autospec=True, **kwargs):
        return original_patch(target, *args, autospec=autospec, **kwargs)
    
    # Copy over the object attribute from original patch
    autospec_patch.object = original_patch.object
    autospec_patch.dict = original_patch.dict
    autospec_patch.multiple = original_patch.multiple
    autospec_patch.stopall = original_patch.stopall
    autospec_patch.TEST_PREFIX = original_patch.TEST_PREFIX
    
    monkeypatch.setattr(unittest.mock, 'patch', autospec_patch)
    
    yield


# ---------------------------------------------------------------------------
# Faker instance (R6: realistic test data, R15: no global seed)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake(request):
    """Provide a Faker instance for generating realistic test data (R6).

    Each test gets its own Faker instance seeded from the test node id (R15).
    This ensures reproducibility: same test → same seed → same data.
    Different tests → different seeds → independent data.

    Usage: fake.name(), fake.email(), fake.text(), fake.url(), etc.
    """
    f = Faker()
    f.seed_instance(hash(request.node.nodeid) % (2**32))
    return f


# ---------------------------------------------------------------------------
# AWS / Bedrock mocks (top 3 most duplicated patterns)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_bedrock_client():
    """Stub for boto3 Bedrock client.

    Provides a MagicMock that simulates boto3.client("bedrock-runtime").
    Avoids real AWS calls in unit/component tests (NFR-05-1).
    """
    client = MagicMock()
    client.converse.return_value = {
        "output": {"message": {"content": [{"text": "mocked response"}]}},
        "usage": {"inputTokens": 10, "outputTokens": 20},
        "stopReason": "end_turn",
    }
    return client


@pytest.fixture
def mock_boto3_client(mock_bedrock_client):
    """Patch boto3.client to return mock_bedrock_client.

    Usage: add mock_boto3_client to test params (autouse=False).
    """
    with patch("boto3.client", return_value=mock_bedrock_client) as m:
        yield m


@pytest.fixture
def mock_bedrock_model():
    """Stub for yui.agent.BedrockModel (28 duplications across tests)."""
    with patch("yui.agent.BedrockModel") as m:
        model_instance = MagicMock()
        m.return_value = model_instance
        yield model_instance


# ---------------------------------------------------------------------------
# subprocess mock (39 duplications — most common pattern)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_subprocess_run():
    """Stub for subprocess.run (39 duplications across tests).

    Returns a CompletedProcess with returncode=0 by default.
    Customize: mock_subprocess_run.return_value = ...
    """
    with patch("subprocess.run") as m:
        m.return_value = MagicMock(
            returncode=0,
            stdout="",
            stderr="",
        )
        yield m


# ---------------------------------------------------------------------------
# Config mock (10 duplications)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    """Stub for yui.config.load_config (10 duplications).

    Returns a minimal valid config dict.
    """
    config = {
        "model_id": "anthropic.claude-3-5-sonnet-20241022-v2:0",
        "region": "us-east-1",
        "max_tokens": 4096,
        "allowlist": ["ls", "cat", "grep"],
        "blocklist": ["rm -rf"],
    }
    with patch("yui.config.load_config", return_value=config) as m:
        yield config


# ---------------------------------------------------------------------------
# AgentCore mocks (27 duplications for AGENTCORE_AVAILABLE)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_agentcore_available():
    """Stub AGENTCORE_AVAILABLE=True (27 duplications)."""
    with patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True):
        yield


@pytest.fixture
def mock_agentcore_unavailable():
    """Stub AGENTCORE_AVAILABLE=False."""
    with patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False):
        yield


# ---------------------------------------------------------------------------
# Slack mocks
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_slack_client():
    """Stub for Slack WebClient.

    Provides a MagicMock with common Slack API methods.
    """
    client = MagicMock()
    client.chat_postMessage.return_value = {"ok": True, "ts": "1234567890.123456"}
    client.conversations_history.return_value = {"ok": True, "messages": []}
    client.auth_test.return_value = {"ok": True, "user_id": "U_TEST", "team": "test_team"}
    return client


# ---------------------------------------------------------------------------
# File system helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_open_file():
    """Stub for builtins.open (file read/write mocking)."""
    with patch("builtins.open", MagicMock()) as m:
        yield m


@pytest.fixture
def tmp_workspace(tmp_path):
    """Provide a temporary workspace directory for tests.

    Creates standard yui workspace structure.
    """
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "AGENTS.md").write_text("# Test AGENTS")
    (workspace / "SOUL.md").write_text("# Test SOUL")
    return workspace


# ---------------------------------------------------------------------------
# Issue #73: テスト有効性の可視化（skip率監視）
# ---------------------------------------------------------------------------

def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Skip率が閾値を超えた場合に警告を表示する。

    Issue #73: skipをsilentに成功扱いする設計思想の問題を可視化する。
    skipは「未検証」であり「成功」ではない。
    閾値: skip/(pass+skip) > 10% で警告
    """
    passed = len(terminalreporter.stats.get("passed", []))
    skipped = len(terminalreporter.stats.get("skipped", []))
    total = passed + skipped

    if total > 0 and skipped > 0:
        skip_ratio = skipped / total
        terminalreporter.write_sep("-", "skip ratio report")
        terminalreporter.write_line(
            f"⚠️  SKIP RATIO: {skipped}/{total} tests skipped ({skip_ratio:.1%})"
        )
        if skip_ratio > 0.10:
            terminalreporter.write_line(
                "    > 10% threshold exceeded — review skip reasons and ensure test resources exist."
            )
            terminalreporter.write_line(
                "    Set env vars (YUI_AWS_E2E=1, YUI_TEST_AWS=1, YUI_TEST_SLACK=1) to reduce skips."
            )
        else:
            terminalreporter.write_line("    Within acceptable threshold (<=10%).")
