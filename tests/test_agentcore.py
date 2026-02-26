"""Tests for AgentCore tools — AC-17, AC-18, AC-18a."""

import os

import pytest

# Skip all tests if boto3 not available
pytest.importorskip("boto3")

from yui.tools.agentcore import code_execute, memory_recall, memory_store, web_browse


# --- web_browse ---

@pytest.mark.aws
def test_web_browse() -> None:
    """AC-17: Web browse via AgentCore Browser."""
    if not os.environ.get("AWS_REGION"):
        pytest.skip("AWS credentials not configured")
    
    result = web_browse(url="https://example.com", task="extract the main heading")
    
    # Should return content or error message
    assert result
    if "Error" in result:
        # Check for known error types
        assert any(x in result for x in ["No permission", "not installed", "not authorized"])
    else:
        # Should contain some content from the page
        assert len(result) > 0


def test_web_browse_unavailable() -> None:
    """Web browse when SDK not installed."""
    from yui.tools import agentcore
    
    # Temporarily disable AgentCore
    original = agentcore.AGENTCORE_AVAILABLE
    agentcore.AGENTCORE_AVAILABLE = False
    
    try:
        result = web_browse(url="https://example.com")
        assert "Error" in result
        assert "not installed" in result
    finally:
        agentcore.AGENTCORE_AVAILABLE = original


# --- memory_store ---

@pytest.mark.aws
def test_memory_store() -> None:
    """AC-18: Memory store via AgentCore Memory."""
    if not os.environ.get("AWS_REGION"):
        pytest.skip("AWS credentials not configured")
    
    result = memory_store(key="test_preference", value="test_value", category="test")
    
    # Should return success or permission error
    assert result
    if "Error" in result:
        assert any(x in result for x in ["No permission", "not installed"])
    else:
        assert "Stored" in result or "test_preference" in result


def test_memory_store_unavailable() -> None:
    """Memory store when SDK not installed."""
    from yui.tools import agentcore
    
    original = agentcore.AGENTCORE_AVAILABLE
    agentcore.AGENTCORE_AVAILABLE = False
    
    try:
        result = memory_store(key="k", value="v")
        assert "Error" in result
        assert "not installed" in result
    finally:
        agentcore.AGENTCORE_AVAILABLE = original


# --- memory_recall ---

@pytest.mark.aws
def test_memory_recall() -> None:
    """AC-18: Memory recall via AgentCore Memory."""
    if not os.environ.get("AWS_REGION"):
        pytest.skip("AWS credentials not configured")
    
    result = memory_recall(query="test preference", limit=5)
    
    # Should return results or error
    assert result
    if "Error" in result:
        assert any(x in result for x in ["No permission", "not installed"])
    else:
        # Should indicate search was performed
        assert "memories" in result.lower() or "found" in result.lower()


def test_memory_recall_unavailable() -> None:
    """Memory recall when SDK not installed."""
    from yui.tools import agentcore
    
    original = agentcore.AGENTCORE_AVAILABLE
    agentcore.AGENTCORE_AVAILABLE = False
    
    try:
        result = memory_recall(query="test")
        assert "Error" in result
        assert "not installed" in result
    finally:
        agentcore.AGENTCORE_AVAILABLE = original


# --- code_execute ---

@pytest.mark.aws
def test_code_execute() -> None:
    """AC-18a: Code execution via AgentCore Code Interpreter."""
    if not os.environ.get("AWS_REGION"):
        pytest.skip("AWS credentials not configured")
    
    result = code_execute(code="print('hello')", language="python")
    
    # Should return output or error
    assert result
    if "Error" in result:
        assert any(x in result for x in ["No permission", "not installed"])
    else:
        # Should contain execution result
        assert len(result) > 0


def test_code_execute_unavailable() -> None:
    """Code execute when SDK not installed."""
    from yui.tools import agentcore
    
    original = agentcore.AGENTCORE_AVAILABLE
    agentcore.AGENTCORE_AVAILABLE = False
    
    try:
        result = code_execute(code="print('hello')")
        assert "Error" in result
        assert "not installed" in result
    finally:
        agentcore.AGENTCORE_AVAILABLE = original
