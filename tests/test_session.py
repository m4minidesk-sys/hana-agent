"""Tests for session manager."""

import tempfile
from pathlib import Path

import pytest

from yui.session import Message, SessionManager

pytestmark = pytest.mark.unit



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


# ──────────────────────────────────────────────
# Issue #74: 異常系・境界値テスト追加
# ──────────────────────────────────────────────

def test_add_message_nonexistent_session(session_manager: SessionManager) -> None:
    """add_message to non-existent session raises ValueError."""
    with pytest.raises(ValueError, match="Session .* does not exist"):
        session_manager.add_message("nonexistent-session", "user", "Hello")


def test_get_messages_nonexistent_session(session_manager: SessionManager) -> None:
    """get_messages for non-existent session returns empty list (no implicit creation)."""
    messages = session_manager.get_messages("nonexistent-session")
    assert messages == []


def test_get_message_count_nonexistent_session(session_manager: SessionManager) -> None:
    """get_message_count for non-existent session returns 0."""
    count = session_manager.get_message_count("nonexistent-session")
    assert count == 0


def test_get_or_create_session_empty_id(session_manager: SessionManager) -> None:
    """get_or_create_session with empty string raises ValueError."""
    with pytest.raises(ValueError, match="session_id cannot be empty"):
        session_manager.get_or_create_session("")


def test_get_or_create_session_none_id(session_manager: SessionManager) -> None:
    """get_or_create_session with None raises TypeError or ValueError."""
    with pytest.raises((TypeError, ValueError)):
        session_manager.get_or_create_session(None)


def test_compact_session_at_threshold_boundary(session_manager: SessionManager) -> None:
    """compact_session triggers when messages > keep_recent."""
    session_manager.get_or_create_session("test-session")
    # threshold=5, keep_recent=2. Add exactly 5 messages.
    for i in range(5):
        session_manager.add_message("test-session", "user", f"Message {i}")

    summarizer_called = []

    def tracking_summarizer(messages: list) -> str:
        summarizer_called.append(len(messages))
        return f"Summary of {len(messages)} messages"

    # 5 > keep_recent=2 → should compact
    session_manager.compact_session("test-session", tracking_summarizer)
    messages = session_manager.get_messages("test-session")
    # 3 old → summary, 2 recent kept = 3 total
    assert len(messages) == 3
    assert messages[0].role == "system"
    assert len(summarizer_called) == 1


def test_compact_session_exact_keep_recent(session_manager: SessionManager) -> None:
    """compact_session does nothing when messages count == keep_recent."""
    session_manager.get_or_create_session("test-session")
    # keep_recent=2, add exactly 2 messages
    session_manager.add_message("test-session", "user", "Message 0")
    session_manager.add_message("test-session", "user", "Message 1")

    summarizer_called = []

    def tracking_summarizer(messages: list) -> str:
        summarizer_called.append(True)
        return "Summary"

    session_manager.compact_session("test-session", tracking_summarizer)
    # 2 <= keep_recent=2 → should NOT compact
    assert len(summarizer_called) == 0
    assert session_manager.get_message_count("test-session") == 2


def test_add_message_very_long_content(session_manager: SessionManager) -> None:
    """add_message handles very long content without truncation."""
    session_manager.get_or_create_session("test-session")
    long_content = "A" * 100_000
    session_manager.add_message("test-session", "user", long_content)
    messages = session_manager.get_messages("test-session")
    assert len(messages) == 1
    assert len(messages[0].content) == 100_000


def test_get_messages_limit_exceeds_count(session_manager: SessionManager) -> None:
    """get_messages with limit larger than message count returns all messages."""
    session_manager.get_or_create_session("test-session")
    session_manager.add_message("test-session", "user", "Hello")
    messages = session_manager.get_messages("test-session", limit=100)
    assert len(messages) == 1
