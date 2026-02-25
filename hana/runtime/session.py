"""HANA session management — SQLite local storage + S3 sync."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class SessionStore:
    """SQLite-backed session store with optional S3 sync.

    Manages conversation history persistence across restarts.

    Args:
        config: HANA configuration dictionary.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        session_config = config.get("session", {})
        self.db_path = Path(session_config.get("db_path", "~/.hana/sessions.db")).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.s3_sync_enabled = session_config.get("s3_sync", {}).get("enabled", False)
        self.s3_bucket = session_config.get("s3_sync", {}).get("bucket", "")
        self.s3_prefix = session_config.get("s3_sync", {}).get("prefix", "hana/sessions/")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize the SQLite database schema."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    channel TEXT NOT NULL DEFAULT 'cli',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    metadata TEXT DEFAULT '{}',
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_session
                ON messages(session_id, timestamp)
            """)
            conn.commit()
        logger.info("Session DB initialized at %s", self.db_path)

    def create_session(
        self,
        session_id: str,
        channel: str = "cli",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        """Create a new session.

        Args:
            session_id: Unique session identifier.
            channel: Channel type (cli, slack).
            metadata: Optional metadata dictionary.

        Returns:
            Session record dictionary.
        """
        now = time.time()
        meta_json = json.dumps(metadata or {})

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO sessions
                   (session_id, channel, created_at, updated_at, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, channel, now, now, meta_json),
            )
            conn.commit()

        logger.info("Created session: %s", session_id)
        return {
            "session_id": session_id,
            "channel": channel,
            "created_at": now,
            "updated_at": now,
            "metadata": metadata or {},
        }

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict | None = None,
    ) -> None:
        """Add a message to a session.

        Args:
            session_id: Session identifier.
            role: Message role (user, assistant, system).
            content: Message content.
            metadata: Optional metadata.
        """
        now = time.time()
        meta_json = json.dumps(metadata or {})

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO messages
                   (session_id, role, content, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, role, content, now, meta_json),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()

    def get_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve messages for a session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of messages to retrieve.

        Returns:
            List of message dictionaries ordered by timestamp.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT role, content, timestamp, metadata
                   FROM messages
                   WHERE session_id = ?
                   ORDER BY timestamp DESC
                   LIMIT ?""",
                (session_id, limit),
            )
            rows = cursor.fetchall()

        messages = []
        for row in reversed(rows):
            messages.append({
                "role": row["role"],
                "content": row["content"],
                "timestamp": row["timestamp"],
                "metadata": json.loads(row["metadata"]),
            })
        return messages

    def list_sessions(self, limit: int = 20) -> list[dict[str, Any]]:
        """List recent sessions.

        Args:
            limit: Maximum number of sessions.

        Returns:
            List of session dictionaries.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """SELECT session_id, channel, created_at, updated_at, metadata
                   FROM sessions
                   ORDER BY updated_at DESC
                   LIMIT ?""",
                (limit,),
            )
            rows = cursor.fetchall()

        return [
            {
                "session_id": row["session_id"],
                "channel": row["channel"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "metadata": json.loads(row["metadata"]),
            }
            for row in rows
        ]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its messages.

        Args:
            session_id: Session identifier.

        Returns:
            True if a session was deleted.
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            cursor = conn.execute(
                "DELETE FROM sessions WHERE session_id = ?", (session_id,),
            )
            conn.commit()
            deleted = cursor.rowcount > 0

        if deleted:
            logger.info("Deleted session: %s", session_id)
        return deleted

    def sync_to_s3(self, session_id: str | None = None) -> bool:
        """Sync session data to S3.

        Args:
            session_id: Specific session to sync.  If None, syncs all.

        Returns:
            True if sync succeeded.
        """
        if not self.s3_sync_enabled:
            logger.debug("S3 sync disabled — skipping")
            return False

        try:
            import boto3

            s3 = boto3.client("s3")

            if session_id:
                sessions = [{"session_id": session_id}]
            else:
                sessions = self.list_sessions(limit=1000)

            for session in sessions:
                sid = session["session_id"]
                messages = self.get_messages(sid, limit=10000)

                key = f"{self.s3_prefix}{sid}.json"
                body = json.dumps({
                    "session": session,
                    "messages": messages,
                }, indent=2)

                s3.put_object(
                    Bucket=self.s3_bucket,
                    Key=key,
                    Body=body.encode("utf-8"),
                    ContentType="application/json",
                )
                logger.info("Synced session %s to s3://%s/%s", sid, self.s3_bucket, key)

            return True

        except Exception as exc:
            logger.error("S3 sync failed: %s", exc)
            return False
