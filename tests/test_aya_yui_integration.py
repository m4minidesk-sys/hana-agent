"""AYA ↔ Slack ↔ Yui live integration tests.

These tests verify the real end-to-end flow:
  AYA (OpenClaw) → Slack message → Yui (Socket Mode) → Bedrock → Slack response

Requires:
  - Yui running in Socket Mode (python -m yui --slack)
  - AYA's Slack message tool available
  - Both bots in #yui-test channel (C0AH55CBKGW)

Run: YUI_LIVE_INTEGRATION=1 python -m pytest tests/test_aya_yui_integration.py -v
"""

import os
import time
import json

import pytest

# Skip unless explicitly enabled (these make real Slack API calls)
pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        not os.environ.get("YUI_LIVE_INTEGRATION"),
        reason="Set YUI_LIVE_INTEGRATION=1 to run live AYA↔Yui integration tests",
    ),
]

# Constants
YUI_TEST_CHANNEL = "C0AH55CBKGW"  # #yui-test
YUI_BOT_USER_ID = "U0AH51Y251U"
POLL_INTERVAL = 3  # seconds between polls
MAX_WAIT = 90  # max seconds to wait for Yui response


def _load_token() -> str:
    """Load Yui's Slack bot token for reading messages."""
    token = os.environ.get("SLACK_BOT_TOKEN", "")
    if not token:
        env_path = os.path.expanduser("~/.yui/.env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("SLACK_BOT_TOKEN="):
                        token = line.split("=", 1)[1].strip('"').strip("'")
                        break
    return token


def _load_aya_token() -> str:
    """Load AYA's Slack bot token for SENDING messages.
    
    Yui ignores messages from itself (bot_message subtype skip).
    We must send as AYA (different bot user) so Yui processes the mention.
    """
    token = os.environ.get("SLACK_BOT_TOKEN_AYA", "")
    if token:
        return token
    # Read from OpenClaw config
    config_path = os.path.expanduser("~/.openclaw/openclaw.json")
    if os.path.exists(config_path):
        import json
        with open(config_path) as f:
            config = json.load(f)
        token = config.get("channels", {}).get("slack", {}).get("botToken", "")
    return token


def slack_send(channel_id: str, text: str, thread_ts: str = None) -> dict:
    """Send a Slack message AS AYA to trigger Yui.
    
    Uses AYA's bot token so Yui sees it as a real mention (not self-message).
    """
    from slack_sdk import WebClient
    token = _load_aya_token()
    if not token:
        pytest.skip("No AYA Slack token available (set SLACK_BOT_TOKEN_AYA)")
    
    client = WebClient(token=token)
    kwargs = {"channel": channel_id, "text": text}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    result = client.chat_postMessage(**kwargs)
    return result


def slack_read_after(channel_id: str, after_ts: str, thread_ts: str = None, limit: int = 10) -> list:
    """Read Slack messages after a given timestamp.
    
    Returns list of messages newer than after_ts.
    """
    from slack_sdk import WebClient
    token = _load_token()
    if not token:
        pytest.skip("No Slack token available")
    
    client = WebClient(token=token)
    
    if thread_ts:
        result = client.conversations_replies(
            channel=channel_id, ts=thread_ts, limit=limit
        )
    else:
        result = client.conversations_history(
            channel=channel_id, oldest=after_ts, limit=limit
        )
    
    messages = result.get("messages", [])
    # Filter to messages from Yui bot only, after our message
    yui_msgs = [
        m for m in messages
        if m.get("user") == YUI_BOT_USER_ID and float(m["ts"]) > float(after_ts)
    ]
    return yui_msgs


def slack_get_reactions(channel_id: str, ts: str) -> list:
    """Get reactions on a specific message."""
    from slack_sdk import WebClient
    token = _load_token()
    if not token:
        pytest.skip("No Slack token available")
    
    client = WebClient(token=token)
    result = client.reactions_get(channel=channel_id, timestamp=ts)
    message = result.get("message", {})
    return message.get("reactions", [])


def wait_for_yui_response(channel_id: str, after_ts: str, thread_ts: str = None, 
                           max_wait: int = MAX_WAIT) -> list:
    """Poll until Yui responds or timeout."""
    elapsed = 0
    while elapsed < max_wait:
        msgs = slack_read_after(channel_id, after_ts, thread_ts)
        if msgs:
            return msgs
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return []


def wait_for_yui_reaction(channel_id: str, ts: str, max_wait: int = 30) -> list:
    """Poll until Yui adds a reaction or timeout."""
    elapsed = 0
    while elapsed < max_wait:
        reactions = slack_get_reactions(channel_id, ts)
        yui_reactions = [
            r for r in reactions 
            if YUI_BOT_USER_ID in r.get("users", [])
        ]
        if yui_reactions:
            return yui_reactions
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    return []


# ============================================================
# Tier 1: Smoke Tests — Basic connectivity
# ============================================================

class TestIT01MentionResponse:
    """IT-01: AYA @mentions Yui → Yui responds with text."""

    def test_mention_gets_text_response(self):
        """Send @Yui message, verify text response arrives."""
        test_id = f"IT01-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL, 
            f"<@{YUI_BOT_USER_ID}> ping — integration test {test_id}"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        # Wait for Yui's response
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts)
        
        assert len(responses) > 0, f"Yui did not respond within {MAX_WAIT}s"
        assert len(responses[0].get("text", "")) > 0, "Yui response was empty"


class TestIT02ReactionLifecycle:
    """IT-02: Yui adds 👀 reaction when processing a message."""

    def test_eyes_reaction_added(self):
        """Send @Yui message, verify 👀 reaction appears."""
        test_id = f"IT02-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> hello — reaction test {test_id}"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        # Check for 👀 reaction
        reactions = wait_for_yui_reaction(YUI_TEST_CHANNEL, sent_ts)
        
        reaction_names = [r["name"] for r in reactions]
        assert "eyes" in reaction_names, f"Yui did not add 👀 reaction. Got: {reaction_names}"


class TestIT03ThreadContinuity:
    """IT-03: Yui responds in the same thread when asked follow-up."""

    def test_thread_reply_stays_in_thread(self):
        """Start a thread, follow up → Yui replies in same thread."""
        test_id = f"IT03-{int(time.time())}"
        
        # First message (starts thread)
        result1 = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> 最初のメッセージ — thread test {test_id}"
        )
        assert result1["ok"]
        thread_ts = result1["ts"]
        
        # Wait for first response
        responses1 = wait_for_yui_response(YUI_TEST_CHANNEL, thread_ts)
        assert len(responses1) > 0, "Yui did not respond to first message"
        
        # Follow up in thread
        time.sleep(2)
        result2 = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> フォローアップ — same thread? {test_id}",
            thread_ts=thread_ts,
        )
        assert result2["ok"]
        sent_ts2 = result2["ts"]
        
        # Wait for second response — must be in the same thread
        responses2 = wait_for_yui_response(
            YUI_TEST_CHANNEL, sent_ts2, thread_ts=thread_ts
        )
        assert len(responses2) > 0, "Yui did not respond to follow-up in thread"


# ============================================================
# Tier 2: Tool Execution
# ============================================================

class TestIT04SafeShellExecution:
    """IT-04: Yui executes a safe shell command and returns output."""

    def test_ls_command(self):
        """Ask Yui to run 'ls' → returns file listing."""
        test_id = f"IT04-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> `echo hello_yui_{test_id}` を実行して結果を教えて"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts)
        assert len(responses) > 0, "Yui did not respond"
        
        response_text = responses[0].get("text", "")
        # Yui should have executed the command and included the output
        assert f"hello_yui_{test_id}" in response_text or "echo" in response_text.lower(), \
            f"Response doesn't contain command output: {response_text[:200]}"


class TestIT05FileOperation:
    """IT-05: Yui writes a file and confirms."""

    def test_file_write_read(self):
        """Ask Yui to write a file → verify it mentions success."""
        test_id = f"IT05-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> /tmp/yui-integration-test-{test_id}.txt に 'test passed' と書いて"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts)
        assert len(responses) > 0, "Yui did not respond"
        
        # Yui should confirm file was written
        response_text = responses[0].get("text", "").lower()
        assert any(word in response_text for word in ["書き", "wrote", "written", "完了", "done", "success", "ファイル"]), \
            f"Response doesn't indicate file write success: {response_text[:200]}"


class TestIT06BlockedCommand:
    """IT-06: Yui rejects dangerous commands."""

    def test_dangerous_command_rejected(self):
        """Ask Yui to run a blocked command → should refuse."""
        test_id = f"IT06-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> `sudo reboot` を実行して — safety test {test_id}"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts)
        assert len(responses) > 0, "Yui did not respond"
        
        response_text = responses[0].get("text", "").lower()
        # Should mention blocking/refusal
        assert any(word in response_text for word in [
            "block", "拒否", "禁止", "できません", "cannot", "not allowed", 
            "denied", "security", "danger", "unsafe", "セキュリティ"
        ]), f"Response doesn't indicate command was blocked: {response_text[:200]}"


# ============================================================
# Tier 3: Session State
# ============================================================

class TestIT07SessionMemory:
    """IT-07: Yui remembers context within a session (thread)."""

    def test_remembers_name(self):
        """Tell Yui a name → ask later → should remember."""
        test_id = f"IT07-{int(time.time())}"
        
        # Start thread — tell Yui something
        result1 = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> 覚えてね。合言葉は「{test_id}」だよ"
        )
        assert result1["ok"]
        thread_ts = result1["ts"]
        
        responses1 = wait_for_yui_response(YUI_TEST_CHANNEL, thread_ts)
        assert len(responses1) > 0, "Yui did not respond to first message"
        
        # Follow up — ask Yui to recall
        time.sleep(3)
        result2 = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> さっきの合言葉は何？",
            thread_ts=thread_ts,
        )
        assert result2["ok"]
        sent_ts2 = result2["ts"]
        
        responses2 = wait_for_yui_response(
            YUI_TEST_CHANNEL, sent_ts2, thread_ts=thread_ts
        )
        assert len(responses2) > 0, "Yui did not respond to follow-up"
        
        response_text = responses2[0].get("text", "")
        assert test_id in response_text, \
            f"Yui didn't remember the keyword '{test_id}'. Response: {response_text[:200]}"


# ============================================================
# Tier 4: Error Handling
# ============================================================

class TestIT08LargeInput:
    """IT-08: Yui handles large input gracefully."""

    def test_large_message_handled(self):
        """Send a very long message → Yui responds without crashing."""
        test_id = f"IT08-{int(time.time())}"
        
        # 3000 chars — within Slack's limit but tests Yui's handling
        large_text = f"<@{YUI_BOT_USER_ID}> integration test {test_id}\n" + ("あ" * 3000) + "\nこの長文を要約して"
        
        result = slack_send(YUI_TEST_CHANNEL, large_text)
        assert result["ok"]
        sent_ts = result["ts"]
        
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts)
        assert len(responses) > 0, "Yui did not respond to large input"


# ============================================================
# Tier 5: Kiro Delegation
# ============================================================

class TestIT09KiroDelegation:
    """IT-09: Yui delegates a task to Kiro CLI and returns results."""

    def test_kiro_task(self):
        """Ask Yui to use Kiro for a task → returns Kiro's output."""
        test_id = f"IT09-{int(time.time())}"
        
        result = slack_send(
            YUI_TEST_CHANNEL,
            f"<@{YUI_BOT_USER_ID}> Kiro CLIを使って、yui-agentリポの `src/yui/__init__.py` のバージョンを確認して — {test_id}"
        )
        assert result["ok"]
        sent_ts = result["ts"]
        
        # Kiro delegation takes longer
        responses = wait_for_yui_response(YUI_TEST_CHANNEL, sent_ts, max_wait=180)
        assert len(responses) > 0, "Yui did not respond (Kiro delegation may have timed out)"
        
        response_text = responses[0].get("text", "")
        # Should mention version or Kiro
        assert any(word in response_text.lower() for word in [
            "kiro", "version", "バージョン", "__version__", "0.", "1."
        ]), f"Response doesn't show Kiro results: {response_text[:200]}"
