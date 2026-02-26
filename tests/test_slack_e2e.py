"""Slack E2E tests — mock-based comprehensive Slack adapter testing.

Tests the full Slack event handling pipeline with mocked dependencies.
No real Slack API calls — runs in CI.

Covers: AC-09 (Socket Mode), AC-10 (mention → thread), AC-11 (DM),
AC-12 (session persistence), AC-13 (compaction), AC-14 (context preservation),
plus dedup (#17), concurrency (#11), error handling.
"""

import threading
import time
from unittest.mock import MagicMock, call, patch

import pytest

from yui.slack_adapter import SlackHandler, _load_tokens, _summarize_messages


@pytest.fixture
def mock_agent():
    """Mock agent that returns predictable responses."""
    agent = MagicMock()
    agent.return_value = "Hello! I'm Yui."
    return agent


@pytest.fixture
def mock_session_manager():
    """Mock session manager."""
    sm = MagicMock()
    sm.get_message_count.return_value = 5  # Below compaction threshold
    return sm


@pytest.fixture
def mock_client():
    """Mock Slack client."""
    return MagicMock()


@pytest.fixture
def handler(mock_agent, mock_session_manager, mock_client):
    """SlackHandler with all mocked dependencies."""
    return SlackHandler(
        agent=mock_agent,
        session_manager=mock_session_manager,
        slack_client=mock_client,
        compaction_threshold=50,
        bot_user_id="U_BOT_123",
    )


# --- SE-01: Mention triggers response ---

class TestMentionResponse:
    """SE-01: @mention → agent call → thread reply."""

    def test_mention_triggers_response(self, handler, mock_agent):
        """AC-10: @Yui mention triggers agent response in thread."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> hello",
            "ts": "1234567890.123456",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        mock_agent.assert_called_once_with("<@U_BOT_123> hello")
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts="1234567890.123456")

    def test_mention_in_thread_replies_to_thread(self, handler):
        """SE-03: Message in thread → reply in same thread."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "<@U_BOT_123> follow up",
            "ts": "1234567890.999999",
            "thread_ts": "1234567890.000001",  # Existing thread
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Should reply to the thread, not the individual message
        say.assert_called_once_with(text="Hello! I'm Yui.", thread_ts="1234567890.000001")


# --- SE-02: DM triggers response ---

class TestDMResponse:
    """SE-02: DM → agent call → reply."""

    def test_dm_triggers_response(self, handler, mock_agent):
        """AC-11: DM to bot triggers agent response."""
        event = {
            "channel": "D_DM_CHANNEL",
            "user": "U_USER",
            "text": "hello from DM",
            "ts": "1234567890.111111",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_called_once_with("hello from DM")
        say.assert_called_once_with(text="Hello! I'm Yui.")


# --- SE-04: Reaction lifecycle ---

class TestReactionLifecycle:
    """SE-04: eyes → process → white_check_mark."""

    def test_reaction_lifecycle(self, handler, mock_client):
        """Mention adds eyes first, then white_check_mark after response."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "test",
            "ts": "1234567890.123456",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # Verify reaction order: eyes first, then white_check_mark
        calls = mock_client.reactions_add.call_args_list
        assert len(calls) == 2
        assert calls[0] == call(channel="C_TEST", timestamp="1234567890.123456", name="eyes")
        assert calls[1] == call(
            channel="C_TEST", timestamp="1234567890.123456", name="white_check_mark"
        )


# --- SE-05: Already reacted ignored ---

class TestSafeReact:
    """SE-05: already_reacted error → silently ignored."""

    def test_already_reacted_ignored(self, handler, mock_client):
        """already_reacted error does not raise."""
        mock_client.reactions_add.side_effect = Exception("already_reacted")

        # Should not raise
        handler.safe_react("C_TEST", "123.456", "eyes")

    def test_other_reaction_error_logged(self, handler, mock_client):
        """Other reaction errors are logged but don't raise."""
        mock_client.reactions_add.side_effect = Exception("channel_not_found")

        # Should not raise
        handler.safe_react("C_TEST", "123.456", "eyes")


# --- SE-06: Concurrent requests lock ---

class TestConcurrencyLock:
    """SE-06: Two concurrent requests → serialized via Lock."""

    def test_concurrent_requests_serialized(self, mock_session_manager, mock_client):
        """AC-09: Concurrent agent calls are serialized."""
        call_order = []

        def slow_agent(text):
            call_order.append(f"start:{text}")
            time.sleep(0.1)
            call_order.append(f"end:{text}")
            return f"response to {text}"

        handler = SlackHandler(
            agent=slow_agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event1 = {"channel": "C", "user": "U1", "text": "first", "ts": "1.0"}
        event2 = {"channel": "C", "user": "U2", "text": "second", "ts": "2.0"}
        say1 = MagicMock()
        say2 = MagicMock()

        t1 = threading.Thread(target=handler.handle_mention, args=(event1, say1))
        t2 = threading.Thread(target=handler.handle_mention, args=(event2, say2))

        t1.start()
        time.sleep(0.01)  # Ensure t1 acquires lock first
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        # Both should complete (serialized)
        say1.assert_called_once()
        say2.assert_called_once()

        # Verify serialization: first must complete before second starts
        assert call_order.index("end:first") < call_order.index("start:second")


# --- SE-07: Lock timeout → processing message ---

class TestLockTimeout:
    """SE-07: Lock acquisition timeout → processing message."""

    def test_lock_timeout_sends_processing_message(self, mock_session_manager, mock_client):
        """When lock times out, user gets 'processing' message."""
        agent = MagicMock(return_value="ok")

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        # Manually acquire lock to simulate busy agent
        handler.agent_lock.acquire()

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        # Patch timeout to be very short
        original_acquire = handler.agent_lock.acquire
        handler.agent_lock = MagicMock()
        handler.agent_lock.acquire.return_value = False  # Simulate timeout

        handler.handle_mention(event, say)

        # Should send processing message
        say.assert_called_once()
        assert "処理中" in say.call_args[1]["text"]


# --- SE-08: Session persistence ---

class TestSessionPersistence:
    """SE-08: Messages saved to SessionManager."""

    def test_mention_saves_to_session(self, handler, mock_session_manager):
        """AC-12: User and assistant messages persisted."""
        event = {
            "channel": "C_TEST",
            "user": "U_USER",
            "text": "hello",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_mention(event, say)

        # User message saved
        mock_session_manager.add_message.assert_any_call("slack:C_TEST:U_USER", "user", "hello")
        # Assistant message saved
        mock_session_manager.add_message.assert_any_call(
            "slack:C_TEST:U_USER", "assistant", "Hello! I'm Yui."
        )

    def test_dm_saves_to_session(self, handler, mock_session_manager):
        """DM messages use dm: session prefix."""
        event = {"channel": "D_DM", "user": "U_USER", "text": "hi", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_session_manager.add_message.assert_any_call("slack:dm:U_USER", "user", "hi")


# --- SE-09: Session compaction trigger ---

class TestSessionCompaction:
    """SE-09: Compaction triggered when threshold exceeded."""

    def test_compaction_triggered(self, mock_agent, mock_client):
        """AC-13: Session compaction triggered at threshold."""
        sm = MagicMock()
        sm.get_message_count.return_value = 51  # Above threshold of 50

        handler = SlackHandler(
            agent=mock_agent,
            session_manager=sm,
            slack_client=mock_client,
            compaction_threshold=50,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        sm.compact_session.assert_called_once()

    def test_no_compaction_below_threshold(self, handler, mock_session_manager):
        """No compaction when below threshold."""
        mock_session_manager.get_message_count.return_value = 10

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        mock_session_manager.compact_session.assert_not_called()


# --- SE-10: Bot message skip ---

class TestBotMessageSkip:
    """SE-10: Bot/subtype messages are ignored."""

    def test_subtype_message_skipped(self, handler, mock_agent):
        """Messages with subtype (e.g., bot_message) are skipped."""
        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "bot text",
            "ts": "1.0",
            "subtype": "bot_message",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()
        say.assert_not_called()

    def test_threaded_dm_skipped(self, handler, mock_agent):
        """Threaded DM messages are skipped (handled by mention handler)."""
        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "thread reply",
            "ts": "1.0",
            "thread_ts": "0.9",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()


# --- SE-11: Dedup mention in DM ---

class TestDedupMention:
    """SE-11: DM with bot mention → skipped by handle_dm."""

    def test_mention_in_dm_skipped(self, handler, mock_agent):
        """#17 fix: Message containing <@bot_user_id> skipped by handle_dm."""
        event = {
            "channel": "D_MPIM",
            "user": "U_USER",
            "text": "<@U_BOT_123> hello yui",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_not_called()

    def test_no_bot_user_id_no_dedup(self, mock_agent, mock_session_manager, mock_client):
        """When bot_user_id is None, no dedup filtering."""
        handler = SlackHandler(
            agent=mock_agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id=None,  # Could not detect
        )

        event = {
            "channel": "D_DM",
            "user": "U_USER",
            "text": "<@U_SOMEONE> hello",
            "ts": "1.0",
        }
        say = MagicMock()

        handler.handle_dm(event, say)

        mock_agent.assert_called_once()


# --- SE-12: Agent error handling ---

class TestAgentErrorHandling:
    """SE-12: Agent exception → error message posted."""

    def test_mention_agent_error(self, mock_session_manager, mock_client):
        """Agent exception results in error message to user."""
        agent = MagicMock(side_effect=RuntimeError("LLM timeout"))

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        # Error message posted
        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]
        assert "LLM timeout" in say.call_args[1]["text"]

    def test_dm_agent_error(self, mock_session_manager, mock_client):
        """DM agent exception results in error message."""
        agent = MagicMock(side_effect=ValueError("bad input"))

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "D", "user": "U", "text": "bad", "ts": "1.0"}
        say = MagicMock()

        handler.handle_dm(event, say)

        say.assert_called_once()
        assert "Error" in say.call_args[1]["text"]


# --- SE-13: AgentResult to string ---

class TestAgentResultConversion:
    """SE-13: AgentResult object → str() for Slack posting."""

    def test_agent_result_stringified(self, mock_session_manager, mock_client):
        """AgentResult with custom __str__ is properly converted."""

        class FakeAgentResult:
            def __str__(self):
                return "Formatted response from agent"

        agent = MagicMock(return_value=FakeAgentResult())

        handler = SlackHandler(
            agent=agent,
            session_manager=mock_session_manager,
            slack_client=mock_client,
            bot_user_id="U_BOT",
        )

        event = {"channel": "C", "user": "U", "text": "test", "ts": "1.0"}
        say = MagicMock()

        handler.handle_mention(event, say)

        say.assert_called_once_with(text="Formatted response from agent", thread_ts="1.0")


# --- SE-14: Token load priority ---

class TestTokenPriority:
    """SE-14: Token loading priority: env > .env > config."""

    def test_env_over_config(self):
        """Environment variables take priority over config."""
        config = {"slack": {"bot_token": "xoxb-config", "app_token": "xapp-config"}}
        with patch.dict("os.environ", {"SLACK_BOT_TOKEN": "xoxb-env", "SLACK_APP_TOKEN": "xapp-env"}):
            bot, app = _load_tokens(config)
            assert bot == "xoxb-env"
            assert app == "xapp-env"


# --- SE-15: Missing tokens error ---

class TestMissingTokens:
    """SE-15: Missing tokens → ValueError."""

    def test_missing_tokens_raises(self):
        """ValueError when no tokens available."""
        with patch.dict("os.environ", {}, clear=True), \
             patch("yui.slack_adapter.load_dotenv"):
            with pytest.raises(ValueError, match="Missing Slack tokens"):
                _load_tokens({})


# --- SE-16: MPIM single response ---

class TestMPIMSingleResponse:
    """SE-16: Group DM mention → exactly one response (not two)."""

    def test_mpim_mention_handled_once(self, handler, mock_agent):
        """In group DM, mention is handled by handle_mention, skipped by handle_dm."""
        event = {
            "channel": "G_MPIM",
            "user": "U_USER",
            "text": "<@U_BOT_123> what's up",
            "ts": "1.0",
        }
        say = MagicMock()

        # handle_dm should skip (dedup)
        handler.handle_dm(event, say)
        assert mock_agent.call_count == 0

        # handle_mention should process
        handler.handle_mention(event, say)
        assert mock_agent.call_count == 1


# --- SE-18: Compaction summary format ---

class TestCompactionSummary:
    """SE-18: Compaction summary format."""

    def test_summarize_messages_format(self):
        """AC-14: Summary includes role and truncated content."""

        class FakeMsg:
            def __init__(self, role, content):
                self.role = role
                self.content = content

        messages = [
            FakeMsg("user", "Hello, how are you?"),
            FakeMsg("assistant", "I'm fine! " + "x" * 200),
        ]

        summary = _summarize_messages(messages)

        assert "[Conversation summary]" in summary
        assert "user: Hello, how are you?" in summary
        assert "assistant: I'm fine!" in summary
        # Content truncated to 100 chars
        assert len(summary.split("\n")[2]) <= 120


# --- SE-17: Socket Mode startup (smoke test) ---

class TestSocketModeStartup:
    """SE-17: run_slack creates SocketModeHandler and starts."""

    @patch("yui.slack_adapter.SocketModeHandler")
    @patch("yui.slack_adapter.App")
    @patch("yui.agent.create_agent")
    @patch("yui.slack_adapter.SessionManager")
    @patch("yui.slack_adapter._load_tokens", return_value=("xoxb-t", "xapp-t"))
    def test_run_slack_starts_handler(self, mock_tokens, mock_sm, mock_agent, mock_app, mock_smh):
        """AC-09: Socket Mode handler created and started."""
        mock_app_instance = MagicMock()
        mock_app_instance.client.auth_test.return_value = {"user_id": "U_BOT"}
        mock_app.return_value = mock_app_instance
        mock_agent.return_value = MagicMock()

        from yui.slack_adapter import run_slack
        run_slack(config={"runtime": {"session": {}}})

        mock_smh.assert_called_once()
        mock_smh.return_value.start.assert_called_once()
