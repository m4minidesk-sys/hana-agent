"""Live Slack integration tests.

Requires: YUI_TEST_SLACK=1, SLACK_BOT_TOKEN, YUI_TEST_SLACK_CHANNEL

These tests make real Slack API calls. Run manually:
    YUI_TEST_SLACK=1 YUI_TEST_SLACK_CHANNEL=C0AH55CBKGW .venv/bin/python3 -m pytest tests/test_slack_live.py -v
"""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("YUI_TEST_SLACK", ""),
    reason="Set YUI_TEST_SLACK=1 to run live Slack tests",
)


@pytest.fixture
def slack_client():
    """Real Slack WebClient."""
    from slack_sdk import WebClient

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    assert token, "SLACK_BOT_TOKEN required"
    return WebClient(token=token)


@pytest.fixture
def test_channel():
    """Test channel ID."""
    channel = os.environ.get("YUI_TEST_SLACK_CHANNEL", "C0AH55CBKGW")
    return channel


# --- SL-01: Auth test ---

class TestSlackAuth:
    """SL-01: Slack auth.test returns bot info."""

    def test_auth_test(self, slack_client):
        """Bot token is valid and returns user info."""
        result = slack_client.auth_test()
        assert result["ok"] is True
        assert result["user_id"]
        assert result["bot_id"]


# --- SL-02: Post message ---

class TestPostMessage:
    """SL-02: Post message to channel."""

    def test_post_message(self, slack_client, test_channel):
        """Can post a message to the test channel."""
        result = slack_client.chat_postMessage(
            channel=test_channel,
            text="🧪 Yui E2E test: SL-02 post_message",
        )
        assert result["ok"] is True
        assert result["message"]["text"] == "🧪 Yui E2E test: SL-02 post_message"

        # Cleanup: delete the message
        slack_client.chat_delete(channel=test_channel, ts=result["ts"])


# --- SL-03: Add reaction ---

class TestAddReaction:
    """SL-03: Add reaction to a message."""

    def test_add_reaction(self, slack_client, test_channel):
        """Can add a reaction emoji to a message."""
        # Post a message first
        msg = slack_client.chat_postMessage(
            channel=test_channel,
            text="🧪 Yui E2E test: SL-03 reaction target",
        )
        assert msg["ok"]

        # Add reaction
        result = slack_client.reactions_add(
            channel=test_channel,
            timestamp=msg["ts"],
            name="white_check_mark",
        )
        assert result["ok"] is True

        # Cleanup
        slack_client.chat_delete(channel=test_channel, ts=msg["ts"])


# --- SL-04: Thread reply ---

class TestThreadReply:
    """SL-04: Reply in a thread."""

    def test_thread_reply(self, slack_client, test_channel):
        """Can post a reply in a thread."""
        # Post parent message
        parent = slack_client.chat_postMessage(
            channel=test_channel,
            text="🧪 Yui E2E test: SL-04 thread parent",
        )
        assert parent["ok"]

        # Reply in thread
        reply = slack_client.chat_postMessage(
            channel=test_channel,
            text="🧪 Thread reply",
            thread_ts=parent["ts"],
        )
        assert reply["ok"]
        assert reply["message"]["thread_ts"] == parent["ts"]

        # Cleanup
        slack_client.chat_delete(channel=test_channel, ts=reply["ts"])
        slack_client.chat_delete(channel=test_channel, ts=parent["ts"])


# --- SL-05: Conversations info ---

class TestConversationsInfo:
    """SL-05: Get channel information."""

    def test_conversations_info(self, slack_client, test_channel):
        """Can retrieve channel information."""
        result = slack_client.conversations_info(channel=test_channel)
        assert result["ok"] is True
        assert result["channel"]["id"] == test_channel


# --- SL-06: Users info ---

class TestUsersInfo:
    """SL-06: Get user information."""

    def test_users_info(self, slack_client):
        """Can retrieve bot's own user info."""
        auth = slack_client.auth_test()
        user_id = auth["user_id"]

        result = slack_client.users_info(user=user_id)
        assert result["ok"] is True
        assert result["user"]["id"] == user_id


# --- SL-07: Full agent roundtrip (optional, slow) ---

class TestAgentRoundtrip:
    """SL-07: Full agent mention → response in thread."""

    @pytest.mark.skipif(
        not os.environ.get("YUI_TEST_AGENT_ROUNDTRIP", ""),
        reason="Set YUI_TEST_AGENT_ROUNDTRIP=1 for full agent test (requires running Yui)",
    )
    def test_mention_gets_response(self, slack_client, test_channel):
        """Post @mention, wait for Yui to respond in thread."""
        auth = slack_client.auth_test()
        bot_user_id = auth["user_id"]

        # Post mention
        msg = slack_client.chat_postMessage(
            channel=test_channel,
            text=f"<@{bot_user_id}> say 'e2e test passed'",
        )
        assert msg["ok"]

        # Wait for response (up to 30s)
        response_found = False
        for _ in range(15):
            time.sleep(2)
            replies = slack_client.conversations_replies(
                channel=test_channel,
                ts=msg["ts"],
            )
            if len(replies["messages"]) > 1:
                response_found = True
                break

        assert response_found, "Yui did not respond within 30 seconds"

        # Verify response is from bot
        reply = replies["messages"][1]
        assert reply.get("bot_id") or reply.get("user") == bot_user_id
