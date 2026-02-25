"""Tests for AgentCore tools."""

from unittest.mock import patch

import pytest

from yui.tools.agentcore import code_execute, memory_recall, memory_store, web_browse


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_web_browse() -> None:
    """Test web browse tool."""
    result = web_browse("https://example.com", "extract content")
    assert "AgentCore Browser" in result
    assert "example.com" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_web_browse_unavailable() -> None:
    """Test web browse when AgentCore unavailable."""
    result = web_browse("https://example.com")
    assert "Error" in result
    assert "not available" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_memory_store() -> None:
    """Test memory store tool."""
    result = memory_store("key1", "value1", "general")
    assert "AgentCore Memory" in result
    assert "key1" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_memory_store_unavailable() -> None:
    """Test memory store when AgentCore unavailable."""
    result = memory_store("key1", "value1")
    assert "Error" in result
    assert "not available" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_memory_recall() -> None:
    """Test memory recall tool."""
    result = memory_recall("test query", limit=5)
    assert "AgentCore Memory" in result
    assert "test query" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_memory_recall_unavailable() -> None:
    """Test memory recall when AgentCore unavailable."""
    result = memory_recall("test query")
    assert "Error" in result
    assert "not available" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_code_execute() -> None:
    """Test code execute tool."""
    result = code_execute("print('hello')", "python")
    assert "AgentCore Code Interpreter" in result
    assert "python" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_code_execute_unavailable() -> None:
    """Test code execute when AgentCore unavailable."""
    result = code_execute("print('hello')")
    assert "Error" in result
    assert "not available" in result
