"""Tests for AgentCore tools — AC-17, AC-18, AC-18a."""

from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from yui.tools.agentcore import code_execute, memory_recall, memory_store, web_browse

pytestmark = pytest.mark.component



# --- web_browse ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.PLAYWRIGHT_AVAILABLE", True)
@patch("yui.tools.agentcore.sync_playwright", create=True)
@patch("yui.tools.agentcore.browser_session")
def test_web_browse(mock_session, mock_playwright) -> None:
    """AC-17: Web browse via AgentCore Browser + Playwright."""
    mock_browser_client = MagicMock()
    mock_browser_client.session_id = "session-123"
    mock_browser_client.generate_ws_headers.return_value = (
        "wss://example.com/browser", {"Authorization": "SigV4 xxx"}
    )
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser_client)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    mock_page = MagicMock()
    mock_page.content.return_value = "Example content from page"
    mock_pw_browser = MagicMock()
    mock_pw_browser.contexts = [MagicMock(pages=[mock_page])]
    mock_playwright.return_value.__enter__.return_value.chromium.connect_over_cdp.return_value = mock_pw_browser

    result = web_browse(url="https://example.com", task="extract content")
    assert "Example content from page" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_web_browse_unavailable() -> None:
    """Web browse when SDK not installed."""
    result = web_browse(url="https://example.com")
    assert "Error" in result
    assert "not installed" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.PLAYWRIGHT_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_browse_permission_denied(mock_session) -> None:
    """Web browse with AccessDeniedException."""
    mock_session.return_value.__enter__ = MagicMock(
        side_effect=Exception("AccessDeniedException: User is not authorized")
    )
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    result = web_browse(url="https://example.com")
    assert "No permission" in result


# --- memory_store ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_store(mock_get_client) -> None:
    """AC-18: Memory store via AgentCore Memory (new SDK API)."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    mock_client.create_event.return_value = {"eventId": "evt-456"}
    mock_get_client.return_value = mock_client

    result = memory_store(key="preference", value="dark mode", category="user")
    assert "Stored" in result
    assert "preference" in result
    mock_client.create_or_get_memory.assert_called_once()
    mock_client.create_event.assert_called_once()


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_memory_store_unavailable() -> None:
    """Memory store when SDK not installed."""
    result = memory_store(key="k", value="v")
    assert "Error" in result
    assert "not installed" in result


# --- memory_recall ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_recall(mock_get_client) -> None:
    """AC-18: Memory recall via AgentCore Memory (new SDK API)."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    mock_client.retrieve_memories.return_value = [
        {"content": {"text": "dark mode preference"}, "score": 0.95},
    ]
    mock_get_client.return_value = mock_client

    result = memory_recall(query="user preference", limit=5)
    assert "dark mode" in result
    assert "1 memories" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_recall_empty(mock_get_client) -> None:
    """Memory recall with no results (new SDK API)."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    mock_client.retrieve_memories.return_value = []
    mock_get_client.return_value = mock_client

    result = memory_recall(query="nonexistent")
    assert "No memories found" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_memory_recall_unavailable() -> None:
    """Memory recall when SDK not installed."""
    result = memory_recall(query="test")
    assert "Error" in result
    assert "not installed" in result


# --- code_execute ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.code_session")
def test_code_execute(mock_session) -> None:
    """AC-18a: Code execution via AgentCore Code Interpreter."""
    mock_interpreter = MagicMock()
    mock_interpreter.start.return_value = "session-456"
    mock_interpreter.execute_code.return_value = {
        "stdout": "hello\n",
        "stderr": "",
    }
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_interpreter)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    result = code_execute(code="print('hello')", language="python")
    assert "hello" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_code_execute_unavailable() -> None:
    """Code execute when SDK not installed."""
    result = code_execute(code="print('hello')")
    assert "Error" in result
    assert "not installed" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.code_session")
def test_code_execute_permission_denied(mock_session) -> None:
    """Code execute with AccessDeniedException."""
    mock_session.return_value.__enter__ = MagicMock(
        side_effect=Exception("AccessDeniedException: No access")
    )
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    result = code_execute(code="print('hello')")
    assert "No permission" in result


# ──────────────────────────────────────────────
# Issue #74: 異常系・境界値テスト追加
# ──────────────────────────────────────────────

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.PLAYWRIGHT_AVAILABLE", True)
@patch("yui.tools.agentcore.sync_playwright", create=True)
@patch("yui.tools.agentcore.browser_session")
def test_web_browse_timeout(mock_session, mock_playwright) -> None:
    """web_browse returns error message when page.goto raises an exception (e.g. timeout)."""
    mock_browser_client = MagicMock()
    mock_browser_client.session_id = "session-123"
    mock_browser_client.generate_ws_headers.return_value = (
        "wss://example.com/browser", {"Authorization": "SigV4 xxx"}
    )
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser_client)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    mock_page = MagicMock()
    mock_page.goto.side_effect = Exception("Timeout: page.goto exceeded 30s")
    mock_pw_browser = MagicMock()
    mock_pw_browser.contexts = [MagicMock(pages=[mock_page])]
    mock_playwright.return_value.__enter__.return_value.chromium.connect_over_cdp.return_value = mock_pw_browser

    result = web_browse(url="https://example.com")
    assert "Error" in result
    # Playwright browser should still be closed (try/finally)
    mock_pw_browser.close.assert_called_once()


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_store_throttling_max_retries(mock_get_client) -> None:
    """memory_store returns error after max retries on ThrottlingException."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    # Always raises throttling
    mock_client.create_event.side_effect = Exception("ThrottlingException: Rate exceeded")
    mock_get_client.return_value = mock_client

    result = memory_store(key="k", value="v", max_retries=2)
    assert "Error" in result
    assert "attempts" in result
    # Should have retried (max_retries+1 = 3 times)
    assert mock_client.create_event.call_count == 3


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_recall_throttling_max_retries(mock_get_client) -> None:
    """memory_recall returns error after max retries on ThrottlingException."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    mock_client.retrieve_memories.side_effect = Exception("ThrottlingException: Rate exceeded")
    mock_get_client.return_value = mock_client

    result = memory_recall(query="test", max_retries=1)
    assert "Error" in result
    assert "attempts" in result
    # Should have retried (max_retries+1 = 2 times)
    assert mock_client.retrieve_memories.call_count == 2


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_memory_client")
def test_memory_store_access_denied_no_retry(mock_get_client) -> None:
    """memory_store returns error immediately on AccessDeniedException (no retry)."""
    mock_client = MagicMock()
    mock_client.create_or_get_memory.return_value = {"memoryId": "mem-123"}
    mock_client.create_event.side_effect = Exception("AccessDeniedException: Access denied")
    mock_get_client.return_value = mock_client

    result = memory_store(key="k", value="v", max_retries=3)
    # Should NOT retry for AccessDeniedException
    assert "No permission" in result
    assert mock_client.create_event.call_count == 1


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.code_session")
def test_code_execute_empty_output(mock_session) -> None:
    """code_execute returns '(no output)' when stdout and stderr are both empty."""
    mock_interpreter = MagicMock()
    mock_interpreter.execute_code.return_value = {"stdout": "", "stderr": ""}
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_interpreter)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    result = code_execute(code="x = 1 + 1")
    assert result == "(no output)"


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.code_session")
def test_code_execute_with_stderr(mock_session) -> None:
    """code_execute includes stderr in output."""
    mock_interpreter = MagicMock()
    mock_interpreter.execute_code.return_value = {
        "stdout": "42",
        "stderr": "DeprecationWarning: use new_func"
    }
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_interpreter)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)

    result = code_execute(code="print(42)")
    assert "42" in result
    assert "STDERR" in result
    assert "DeprecationWarning" in result
