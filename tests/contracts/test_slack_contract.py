"""Contract tests for Slack API.

Tests real Slack API responses and error handling.
"""

import pytest


@pytest.mark.integration
def test_slack_post_message__normal_text__returns_ts_and_channel(slack_client):
    """通常のテキストメッセージがtsとchannelを返す（スタブ）."""
    # Arrange - 実際のチャンネルIDが必要
    # Act - スキップ（実際のSlackチャンネルへの投稿が必要）
    pytest.skip("Requires real Slack channel ID")


@pytest.mark.integration
def test_slack_post_message__with_blocks__returns_valid_response(slack_client):
    """ブロック付きメッセージが有効なレスポンスを返す（スタブ）."""
    # Arrange - 実際のチャンネルIDが必要
    # Act - スキップ
    pytest.skip("Requires real Slack channel ID")


@pytest.mark.integration
def test_slack_post_message__thread_reply__includes_thread_ts(slack_client):
    """スレッド返信がthread_tsを含む（スタブ）."""
    # Arrange - 実際のチャンネルIDとスレッドTSが必要
    # Act - スキップ
    pytest.skip("Requires real Slack channel ID and thread_ts")


@pytest.mark.integration
def test_slack_reactions_add__valid_emoji__returns_ok_true(slack_client):
    """有効な絵文字でok=trueを返す（スタブ）."""
    # Arrange - 実際のチャンネルIDとメッセージTSが必要
    # Act - スキップ
    pytest.skip("Requires real Slack message")


@pytest.mark.integration
def test_slack_reactions_add__invalid_emoji__raises_invalid_name_error(slack_client):
    """無効な絵文字でinvalid_nameエラーが発生する（スタブ）."""
    # Arrange - 実際のチャンネルIDとメッセージTSが必要
    # Act - スキップ
    pytest.skip("Requires real Slack message")


@pytest.mark.integration
def test_slack_conversations_history__recent_messages__returns_message_list(slack_client):
    """最近のメッセージがメッセージリストを返す（スタブ）."""
    # Arrange - 実際のチャンネルIDが必要
    # Act - スキップ
    pytest.skip("Requires real Slack channel ID")


@pytest.mark.integration
def test_slack_conversations_history__with_limit__respects_limit_param(slack_client):
    """limitパラメータが尊重される（スタブ）."""
    # Arrange - 実際のチャンネルIDが必要
    # Act - スキップ
    pytest.skip("Requires real Slack channel ID")


@pytest.mark.integration
def test_slack_post_message__rate_limited_429__retries_after_delay(slack_client):
    """429レート制限後に遅延してリトライする（スタブ）."""
    # Arrange - 実際のレート制限は再現困難
    # Act - スキップ
    pytest.skip("Rate limiting difficult to reproduce")


@pytest.mark.integration
def test_slack_post_message__slow_response_5s__completes_successfully(slack_client):
    """5秒の遅延レスポンスが正常に完了する（スタブ）."""
    # Arrange - 実際の遅延は再現困難
    # Act - スキップ
    pytest.skip("Slow response difficult to reproduce")


@pytest.mark.integration
def test_slack_auth_test__valid_token__returns_user_and_team_info(slack_client):
    """有効なトークンでユーザーとチーム情報を返す."""
    # Arrange & Act
    response = slack_client.auth_test()
    
    # Assert
    assert response["ok"] is True
    assert "user_id" in response
    assert "team" in response or "team_id" in response
