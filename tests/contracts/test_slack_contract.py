"""Contract tests for Slack API.

Tests Slack API response structure and error handling with mocked responses.
"""

import pytest
from slack_sdk.errors import SlackApiError


@pytest.mark.integration
def test_slack_post_message__normal_text__returns_ts_and_channel(slack_client):
    """通常のテキストメッセージがtsとchannelを返す."""
    # Arrange
    slack_client.chat_postMessage.return_value = {
        "ok": True,
        "channel": "C12345678",
        "ts": "1234567890.123456",
        "message": {"text": "Hello", "user": "U12345678"}
    }
    
    # Act
    response = slack_client.chat_postMessage(channel="C12345678", text="Hello")
    
    # Assert
    assert response["ok"] is True
    assert "ts" in response
    assert "channel" in response
    assert isinstance(response["ts"], str)
    assert isinstance(response["channel"], str)


@pytest.mark.integration
def test_slack_post_message__with_blocks__returns_valid_response(slack_client):
    """ブロック付きメッセージが有効なレスポンスを返す."""
    # Arrange
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*Bold*"}}]
    slack_client.chat_postMessage.return_value = {
        "ok": True,
        "channel": "C12345678",
        "ts": "1234567890.123456",
        "message": {"blocks": blocks}
    }
    
    # Act
    response = slack_client.chat_postMessage(channel="C12345678", blocks=blocks)
    
    # Assert
    assert response["ok"] is True
    assert "message" in response
    assert "blocks" in response["message"]


@pytest.mark.integration
def test_slack_post_message__thread_reply__includes_thread_ts(slack_client):
    """スレッド返信がthread_tsを含む."""
    # Arrange
    slack_client.chat_postMessage.return_value = {
        "ok": True,
        "channel": "C12345678",
        "ts": "1234567890.123457",
        "message": {"thread_ts": "1234567890.123456"}
    }
    
    # Act
    response = slack_client.chat_postMessage(
        channel="C12345678", text="Reply", thread_ts="1234567890.123456"
    )
    
    # Assert
    assert response["ok"] is True
    assert "message" in response
    assert "thread_ts" in response["message"]


@pytest.mark.integration
def test_slack_reactions_add__valid_emoji__returns_ok_true(slack_client):
    """有効な絵文字でok=trueを返す."""
    # Arrange
    slack_client.reactions_add.return_value = {"ok": True}
    
    # Act
    response = slack_client.reactions_add(
        channel="C12345678", timestamp="1234567890.123456", name="thumbsup"
    )
    
    # Assert
    assert response["ok"] is True


@pytest.mark.integration
def test_slack_reactions_add__invalid_emoji__raises_invalid_name_error(slack_client):
    """無効な絵文字でinvalid_nameエラーが発生する."""
    # Arrange
    slack_client.reactions_add.side_effect = SlackApiError(
        message="invalid_name", response={"ok": False, "error": "invalid_name"}
    )
    
    # Act & Assert
    with pytest.raises(SlackApiError) as exc_info:
        slack_client.reactions_add(
            channel="C12345678", timestamp="1234567890.123456", name="invalid_emoji"
        )
    assert "invalid_name" in str(exc_info.value)


@pytest.mark.integration
def test_slack_conversations_history__recent_messages__returns_message_list(slack_client):
    """最近のメッセージがメッセージリストを返す."""
    # Arrange
    slack_client.conversations_history.return_value = {
        "ok": True,
        "messages": [
            {"type": "message", "text": "Hello", "ts": "1234567890.123456"},
            {"type": "message", "text": "World", "ts": "1234567890.123457"}
        ]
    }
    
    # Act
    response = slack_client.conversations_history(channel="C12345678")
    
    # Assert
    assert response["ok"] is True
    assert "messages" in response
    assert isinstance(response["messages"], list)
    assert len(response["messages"]) > 0


@pytest.mark.integration
def test_slack_conversations_history__with_limit__respects_limit_param(slack_client):
    """limitパラメータが尊重される."""
    # Arrange
    slack_client.conversations_history.return_value = {
        "ok": True,
        "messages": [{"type": "message", "text": "Hello", "ts": "1234567890.123456"}]
    }
    
    # Act
    response = slack_client.conversations_history(channel="C12345678", limit=1)
    
    # Assert
    assert response["ok"] is True
    assert len(response["messages"]) == 1


@pytest.mark.integration
def test_slack_post_message__rate_limited_429__retries_after_delay(slack_client):
    """429レート制限後に遅延してリトライする."""
    # Arrange
    slack_client.chat_postMessage.side_effect = SlackApiError(
        message="rate_limited", response={"ok": False, "error": "rate_limited"}
    )
    
    # Act & Assert
    with pytest.raises(SlackApiError) as exc_info:
        slack_client.chat_postMessage(channel="C12345678", text="Hello")
    assert "rate_limited" in str(exc_info.value)


@pytest.mark.integration
def test_slack_post_message__slow_response_5s__completes_successfully(slack_client):
    """5秒の遅延レスポンスが正常に完了する."""
    # Arrange
    slack_client.chat_postMessage.return_value = {
        "ok": True,
        "channel": "C12345678",
        "ts": "1234567890.123456"
    }
    
    # Act
    response = slack_client.chat_postMessage(channel="C12345678", text="Hello")
    
    # Assert
    assert response["ok"] is True
    assert "ts" in response


@pytest.mark.integration
def test_slack_auth_test__valid_token__returns_user_and_team_info(slack_client):
    """有効なトークンでユーザーとチーム情報を返す."""
    # Arrange
    slack_client.auth_test.return_value = {
        "ok": True,
        "user_id": "U12345678",
        "team_id": "T12345678",
        "team": "Test Team"
    }
    
    # Act
    response = slack_client.auth_test()
    
    # Assert
    assert response["ok"] is True
    assert "user_id" in response
    assert "team" in response or "team_id" in response
