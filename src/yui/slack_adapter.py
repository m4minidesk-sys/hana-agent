"""Slack Socket Mode adapter."""

import logging
import os
import threading
import traceback
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from yui.agent import create_agent
from yui.config import load_config
from yui.session import SessionManager

logger = logging.getLogger(__name__)


def _load_tokens(config: dict) -> tuple[str, str]:
    """Load Slack tokens from env vars, .env file, or config.

    Priority: env vars > ~/.yui/.env > config.yaml

    Returns:
        Tuple of (bot_token, app_token).

    Raises:
        ValueError: If tokens are missing.
    """
    # Load from ~/.yui/.env if exists
    env_file = Path("~/.yui/.env").expanduser()
    if env_file.exists():
        load_dotenv(env_file)

    bot_token = os.getenv("SLACK_BOT_TOKEN") or config.get("slack", {}).get("bot_token")
    app_token = os.getenv("SLACK_APP_TOKEN") or config.get("slack", {}).get("app_token")

    if not bot_token or not app_token:
        raise ValueError(
            "Missing Slack tokens. Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN in env or ~/.yui/.env"
        )

    return bot_token, app_token


def run_slack(config: Optional[dict] = None) -> None:
    """Start Slack Socket Mode handler.

    Args:
        config: Pre-loaded config dict. If None, loads from default path.
    """
    if config is None:
        config = load_config()
    bot_token, app_token = _load_tokens(config)

    app = App(token=bot_token)
    agent = create_agent(config)

    # Session manager
    session_config = config.get("runtime", {}).get("session", {})
    db_path = session_config.get("db_path", "~/.yui/sessions.db")
    compaction_threshold = session_config.get("compaction_threshold", 50)
    keep_recent = session_config.get("keep_recent_messages", 5)
    session_manager = SessionManager(db_path, compaction_threshold, keep_recent)

    # Lock to prevent concurrent agent invocations (Strands SDK limitation)
    agent_lock = threading.Lock()

    def _safe_react(channel: str, timestamp: str, name: str) -> None:
        """Add reaction, ignoring already_reacted errors."""
        try:
            app.client.reactions_add(channel=channel, timestamp=timestamp, name=name)
        except Exception as e:
            if "already_reacted" not in str(e):
                logger.warning("Failed to add reaction %s: %s", name, e)

    @app.event("app_mention")
    def handle_mention(event: dict, say: callable) -> None:
        """Handle @Yui mentions."""
        try:
            channel = event["channel"]
            user = event["user"]
            text = event["text"]
            thread_ts = event.get("thread_ts") or event["ts"]

            # Acknowledge
            _safe_react(channel, event["ts"], "eyes")

            # Session ID
            session_id = f"slack:{channel}:{user}"
            session_manager.get_or_create_session(session_id, {"channel": channel, "user": user})

            # Add user message
            session_manager.add_message(session_id, "user", text)

            # Get response (serialized — Strands Agent is not thread-safe)
            acquired = agent_lock.acquire(timeout=120)
            if not acquired:
                say(text="⏳ 他のリクエストを処理中です。少々お待ちください…", thread_ts=thread_ts)
                return
            try:
                result = agent(text)
                response = str(result)
            finally:
                agent_lock.release()

            # Add assistant message
            session_manager.add_message(session_id, "assistant", response)

            # Post response in thread
            say(text=response, thread_ts=thread_ts)

            # Mark done
            _safe_react(channel, event["ts"], "white_check_mark")

            # Check compaction
            if session_manager.get_message_count(session_id) > compaction_threshold:
                session_manager.compact_session(session_id, _summarize_messages)

        except Exception as e:
            logger.error("Error handling mention: %s", traceback.format_exc())
            say(text=f"Error: {e}", thread_ts=thread_ts)

    @app.event("message")
    def handle_dm(event: dict, say: callable) -> None:
        """Handle DMs."""
        # Skip bot messages and threaded replies
        if event.get("subtype") or event.get("thread_ts"):
            return

        try:
            channel = event["channel"]
            user = event["user"]
            text = event["text"]

            # Acknowledge
            _safe_react(channel, event["ts"], "eyes")

            # Session ID
            session_id = f"slack:dm:{user}"
            session_manager.get_or_create_session(session_id, {"user": user})

            # Add user message
            session_manager.add_message(session_id, "user", text)

            # Get response (serialized — Strands Agent is not thread-safe)
            acquired = agent_lock.acquire(timeout=120)
            if not acquired:
                say(text="⏳ 他のリクエストを処理中です。少々お待ちください…")
                return
            try:
                result = agent(text)
                response = str(result)
            finally:
                agent_lock.release()

            # Add assistant message
            session_manager.add_message(session_id, "assistant", response)

            # Post response
            say(text=response)

            # Mark done
            _safe_react(channel, event["ts"], "white_check_mark")

            # Check compaction
            if session_manager.get_message_count(session_id) > compaction_threshold:
                session_manager.compact_session(session_id, _summarize_messages)

        except Exception as e:
            logger.error("Error handling DM: %s", traceback.format_exc())
            say(text=f"Error: {e}")

    logger.info("Starting Slack Socket Mode...")
    handler = SocketModeHandler(app, app_token)
    handler.start()


def _summarize_messages(messages: list) -> str:
    """Summarize old messages into a system message."""
    summary_parts = ["[Conversation summary]"]
    for msg in messages:
        summary_parts.append(f"{msg.role}: {msg.content[:100]}")
    return "\n".join(summary_parts)
