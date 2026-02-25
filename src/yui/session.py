"""SQLite session manager with WAL mode and compaction."""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Conversation message."""

    role: str
    content: str
    timestamp: str


class SessionManager:
    """Manages persistent conversation sessions in SQLite."""

    def __init__(self, db_path: str, compaction_threshold: int = 50, keep_recent: int = 5):
        """Initialize session manager.

        Args:
            db_path: Path to SQLite database file.
            compaction_threshold: Message count before compaction.
            keep_recent: Number of recent messages to keep after compaction.
        """
        self.db_path = Path(db_path).expanduser()
        self.compaction_threshold = compaction_threshold
        self.keep_recent = keep_recent
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database with schema and WAL mode."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT REFERENCES sessions(session_id),
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()

    def get_or_create_session(self, session_id: str, metadata: Optional[dict[str, Any]] = None) -> None:
        """Get or create a session.

        Args:
            session_id: Unique session identifier.
            metadata: Optional metadata (channel, user, etc.).
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT session_id FROM sessions WHERE session_id = ?", (session_id,))
            if cursor.fetchone() is None:
                conn.execute(
                    "INSERT INTO sessions (session_id, metadata) VALUES (?, ?)",
                    (session_id, json.dumps(metadata or {})),
                )
                conn.commit()
                logger.info("Created session: %s", session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        """Add a message to a session.

        Args:
            session_id: Session identifier.
            role: Message role (user, assistant, system, tool_use, tool_result).
            content: Message content (JSON-encoded for structured messages).
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                (session_id,),
            )
            conn.commit()

    def get_messages(self, session_id: str, limit: Optional[int] = None) -> list[Message]:
        """Get messages for a session.

        Args:
            session_id: Session identifier.
            limit: Optional limit on number of messages.

        Returns:
            List of messages ordered by timestamp.
        """
        with sqlite3.connect(self.db_path) as conn:
            query = "SELECT role, content, timestamp FROM messages WHERE session_id = ? ORDER BY timestamp"
            if limit:
                query += f" LIMIT {limit}"
            cursor = conn.execute(query, (session_id,))
            return [Message(role=row[0], content=row[1], timestamp=row[2]) for row in cursor.fetchall()]

    def get_message_count(self, session_id: str) -> int:
        """Get message count for a session."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,))
            return cursor.fetchone()[0]

    def compact_session(self, session_id: str, summarizer: Any) -> None:
        """Compact session by summarizing old messages.

        Args:
            session_id: Session identifier.
            summarizer: Callable that takes message list and returns summary string.
        """
        messages = self.get_messages(session_id)
        if len(messages) <= self.keep_recent:
            return

        old_messages = messages[:-self.keep_recent]
        recent_messages = messages[-self.keep_recent:]

        # Generate summary
        summary_text = summarizer(old_messages)

        # Get earliest timestamp for summary
        earliest_ts = old_messages[0].timestamp if old_messages else datetime.now().isoformat()

        # Replace old messages with summary
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, "system", summary_text, earliest_ts),
            )
            for msg in recent_messages:
                conn.execute(
                    "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                    (session_id, msg.role, msg.content, msg.timestamp),
                )
            conn.commit()

        logger.info("Compacted session %s: %d → %d messages", session_id, len(messages), self.keep_recent + 1)
