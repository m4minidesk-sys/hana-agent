"""HANA Slack adapter — Slack Socket Mode integration."""

from __future__ import annotations

import logging
import re
from typing import Any

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from slack_sdk import WebClient
from strands import Agent

logger = logging.getLogger(__name__)


class SlackAdapter:
    """Slack Socket Mode adapter for HANA.

    Connects to Slack using Socket Mode (no public URL needed),
    listens for messages, and routes them to the Strands Agent.

    Args:
        agent: Configured Strands Agent instance.
        config: HANA configuration dictionary.
    """

    def __init__(self, agent: Agent, config: dict[str, Any]) -> None:
        self.agent = agent
        self.config = config

        slack_config = config.get("channels", {}).get("slack", {})
        self.bot_token = slack_config.get("bot_token", "")
        self.app_token = slack_config.get("app_token", "")
        self.default_channel = slack_config.get("default_channel", "")

        if not self.bot_token or not self.app_token:
            raise ValueError(
                "Slack bot_token and app_token must be set in config or environment"
            )

        self.app = App(token=self.bot_token)
        self.client = WebClient(token=self.bot_token)

        # Get bot user ID for mention detection
        self._bot_user_id: str | None = None

        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register Slack event handlers."""

        @self.app.event("message")
        def handle_message(event: dict, say: Any) -> None:
            """Handle incoming messages."""
            self._on_message(event, say)

        @self.app.event("app_mention")
        def handle_mention(event: dict, say: Any) -> None:
            """Handle @mentions of the bot."""
            self._on_message(event, say)

    def _get_bot_user_id(self) -> str:
        """Get the bot's Slack user ID (cached)."""
        if self._bot_user_id is None:
            try:
                resp = self.client.auth_test()
                self._bot_user_id = resp.get("user_id", "")
            except Exception:
                self._bot_user_id = ""
        return self._bot_user_id

    def _strip_mention(self, text: str) -> str:
        """Remove bot mention from message text.

        Args:
            text: Raw message text.

        Returns:
            Cleaned message text.
        """
        bot_id = self._get_bot_user_id()
        if bot_id:
            text = re.sub(rf"<@{bot_id}>\s*", "", text)
        return text.strip()

    def _on_message(self, event: dict, say: Any) -> None:
        """Process an incoming Slack message.

        Args:
            event: Slack event payload.
            say: Function to send a reply.
        """
        # Ignore bot's own messages
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return

        text = event.get("text", "")
        if not text:
            return

        user = event.get("user", "unknown")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts") or event.get("ts")

        cleaned_text = self._strip_mention(text)
        if not cleaned_text:
            return

        logger.info("Slack message from %s in %s: %s", user, channel, cleaned_text[:100])

        try:
            # Add eyes reaction
            try:
                self.client.reactions_add(
                    channel=channel,
                    name="eyes",
                    timestamp=event.get("ts", ""),
                )
            except Exception:
                pass  # Reaction failure is non-critical

            # Invoke agent
            result = self.agent(cleaned_text)
            response_text = self._extract_response(result)

            if response_text:
                say(text=response_text, thread_ts=thread_ts)

            # Add check mark
            try:
                self.client.reactions_add(
                    channel=channel,
                    name="white_check_mark",
                    timestamp=event.get("ts", ""),
                )
            except Exception:
                pass

        except Exception as exc:
            logger.exception("Agent invocation failed for Slack message")
            say(
                text=f"⚠️ Error: {exc}",
                thread_ts=thread_ts,
            )

    def _extract_response(self, result: Any) -> str:
        """Extract printable text from an AgentResult.

        Args:
            result: The result object from agent invocation.

        Returns:
            Extracted text string.
        """
        if result is None:
            return ""

        if hasattr(result, "message"):
            message = result.message
            if isinstance(message, dict) and "content" in message:
                parts = []
                for block in message["content"]:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                return "\n".join(parts)

        text = str(result)
        return text if text and text != "None" else ""

    def run(self) -> None:
        """Start the Slack Socket Mode handler.

        This blocks until the process is terminated.
        """
        logger.info("Starting Slack Socket Mode adapter...")
        handler = SocketModeHandler(self.app, self.app_token)

        bot_id = self._get_bot_user_id()
        if bot_id:
            logger.info("Bot user ID: %s", bot_id)

        handler.start()
