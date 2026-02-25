"""Tests for HANA session store."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from hana.runtime.session import SessionStore


@pytest.fixture
def store(tmp_path: Path) -> SessionStore:
    """Create a SessionStore with a temporary database."""
    config = {
        "session": {
            "backend": "sqlite",
            "db_path": str(tmp_path / "test_sessions.db"),
            "s3_sync": {"enabled": False},
        }
    }
    return SessionStore(config)


class TestSessionStore:
    """Tests for SessionStore."""

    def test_create_session(self, store: SessionStore) -> None:
        session = store.create_session("test-1", channel="cli")
        assert session["session_id"] == "test-1"
        assert session["channel"] == "cli"
        assert session["created_at"] > 0

    def test_list_sessions(self, store: SessionStore) -> None:
        store.create_session("s1")
        store.create_session("s2")
        store.create_session("s3")

        sessions = store.list_sessions(limit=10)
        assert len(sessions) == 3

    def test_add_and_get_messages(self, store: SessionStore) -> None:
        store.create_session("s1")
        store.add_message("s1", "user", "Hello!")
        store.add_message("s1", "assistant", "Hi there!")

        messages = store.get_messages("s1")
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "Hello!"
        assert messages[1]["role"] == "assistant"

    def test_message_ordering(self, store: SessionStore) -> None:
        store.create_session("s1")
        store.add_message("s1", "user", "First")
        time.sleep(0.01)
        store.add_message("s1", "user", "Second")
        time.sleep(0.01)
        store.add_message("s1", "user", "Third")

        messages = store.get_messages("s1")
        assert [m["content"] for m in messages] == ["First", "Second", "Third"]

    def test_message_limit(self, store: SessionStore) -> None:
        store.create_session("s1")
        for i in range(20):
            store.add_message("s1", "user", f"Message {i}")

        messages = store.get_messages("s1", limit=5)
        assert len(messages) == 5
        # Should get the 5 most recent
        assert messages[-1]["content"] == "Message 19"

    def test_delete_session(self, store: SessionStore) -> None:
        store.create_session("s1")
        store.add_message("s1", "user", "test")

        deleted = store.delete_session("s1")
        assert deleted is True

        sessions = store.list_sessions()
        assert len(sessions) == 0

        messages = store.get_messages("s1")
        assert len(messages) == 0

    def test_delete_nonexistent(self, store: SessionStore) -> None:
        deleted = store.delete_session("nonexistent")
        assert deleted is False

    def test_session_metadata(self, store: SessionStore) -> None:
        meta = {"user": "han", "topic": "testing"}
        store.create_session("s1", metadata=meta)

        sessions = store.list_sessions()
        assert sessions[0]["metadata"] == meta

    def test_s3_sync_disabled(self, store: SessionStore) -> None:
        result = store.sync_to_s3()
        assert result is False  # Sync disabled in config
