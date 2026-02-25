"""Tests for session manager."""

import tempfile
from pathlib import Path

import pytest

from yui.session import Message, SessionManager


@pytest.fixture
def session_manager() -> SessionManager:
    """Create session manager with temp database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_sessions.db"
        yield SessionManager(str(db_path), compaction_threshold=5, keep_recent=2)


def test_get_or_create_session(session_manager: SessionManager) -> None:
    """Test session creation."""
    session_manager.get_or_create_session("test-session", {"user": "alice"})
    # Should not raise on duplicate
    session_manager.get_or_create_session("test-session", {"user": "alice"})


def test_add_message(session_manager: SessionManager) -> None:
    """Test adding messages."""
    session_manager.get_or_create_session("test-session")
    session_manager.add_message("test-session", "user", "Hello")
    session_manager.add_message("test-session", "assistant", "Hi there")

    messages = session_manager.get_messages("test-session")
    assert len(messages) == 2
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hi there"


def test_get_messages_with_limit(session_manager: SessionManager) -> None:
    """Test message retrieval with limit."""
    session_manager.get_or_create_session("test-session")
    for i in range(10):
        session_manager.add_message("test-session", "user", f"Message {i}")

    messages = session_manager.get_messages("test-session", limit=3)
    assert len(messages) == 3


def test_get_message_count(session_manager: SessionManager) -> None:
    """Test message count."""
    session_manager.get_or_create_session("test-session")
    assert session_manager.get_message_count("test-session") == 0

    session_manager.add_message("test-session", "user", "Hello")
    assert session_manager.get_message_count("test-session") == 1


def test_compact_session(session_manager: SessionManager) -> None:
    """Test session compaction."""
    session_manager.get_or_create_session("test-session")

    # Add 6 messages (threshold is 5, keep_recent is 2)
    for i in range(6):
        session_manager.add_message("test-session", "user", f"Message {i}")

    def mock_summarizer(messages: list[Message]) -> str:
        return f"Summary of {len(messages)} messages"

    session_manager.compact_session("test-session", mock_summarizer)

    messages = session_manager.get_messages("test-session")
    # Should have 1 summary + 2 recent messages = 3 total
    assert len(messages) == 3
    assert messages[0].role == "system"
    assert "Summary of 4 messages" in messages[0].content


def test_compact_session_below_threshold(session_manager: SessionManager) -> None:
    """Test compaction does nothing when below threshold."""
    session_manager.get_or_create_session("test-session")
    session_manager.add_message("test-session", "user", "Hello")

    def mock_summarizer(messages: list[Message]) -> str:
        return "Should not be called"

    session_manager.compact_session("test-session", mock_summarizer)

    messages = session_manager.get_messages("test-session")
    assert len(messages) == 1
    assert messages[0].content == "Hello"
