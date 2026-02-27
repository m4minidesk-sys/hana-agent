"""Contract tests for AWS Bedrock Converse API.

Tests Bedrock API response structure and error handling with mocked responses.
"""

import pytest
from botocore.exceptions import ClientError, ReadTimeoutError


@pytest.mark.integration
def test_bedrock_converse__normal_response__returns_valid_message_structure(bedrock_client):
    """正常レスポンスが有効なメッセージ構造を返す."""
    # Arrange
    bedrock_client.converse.return_value = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": "Hello! How can I help you?"}]
            }
        },
        "usage": {"inputTokens": 10, "outputTokens": 20}
    }
    
    # Act
    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=[{"role": "user", "content": [{"text": "Hello"}]}],
    )
    
    # Assert
    assert "output" in response
    assert "message" in response["output"]
    assert "content" in response["output"]["message"]
    assert isinstance(response["output"]["message"]["content"], list)
    assert len(response["output"]["message"]["content"]) > 0


@pytest.mark.integration
def test_bedrock_converse__with_system_prompt__includes_system_in_request(bedrock_client):
    """システムプロンプト付きリクエストが正常に処理される."""
    # Arrange
    bedrock_client.converse.return_value = {
        "output": {"message": {"role": "assistant", "content": [{"text": "4"}]}}
    }
    
    # Act
    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=[{"role": "user", "content": [{"text": "What is 2+2?"}]}],
        system=[{"text": "You are a math tutor."}],
    )
    
    # Assert
    assert "output" in response
    assert "message" in response["output"]


@pytest.mark.integration
def test_bedrock_converse__streaming_response__yields_content_blocks(bedrock_client):
    """ストリーミングレスポンスがコンテンツブロックを返す."""
    # Arrange
    bedrock_client.converse_stream.return_value = {
        "stream": [
            {"contentBlockDelta": {"delta": {"text": "1"}}},
            {"contentBlockDelta": {"delta": {"text": " 2"}}},
            {"contentBlockDelta": {"delta": {"text": " 3"}}}
        ]
    }
    
    # Act
    response = bedrock_client.converse_stream(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=[{"role": "user", "content": [{"text": "Count to 3"}]}],
    )
    
    # Assert
    chunks = list(response["stream"])
    assert len(chunks) > 0
    has_content = any("contentBlockDelta" in chunk for chunk in chunks)
    assert has_content


@pytest.mark.integration
def test_bedrock_converse__invalid_model_id__raises_validation_exception(bedrock_client):
    """無効なモデルIDでValidationExceptionが発生する."""
    # Arrange
    bedrock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ValidationException", "Message": "Invalid model ID"}},
        "Converse"
    )
    
    # Act & Assert
    with pytest.raises(ClientError) as exc_info:
        bedrock_client.converse(
            modelId="invalid-model-id",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    assert exc_info.value.response["Error"]["Code"] == "ValidationException"


@pytest.mark.integration
def test_bedrock_converse__throttling_error__raises_throttling_exception(bedrock_client):
    """スロットリングエラーでThrottlingExceptionが発生する."""
    # Arrange
    bedrock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Converse"
    )
    
    # Act & Assert
    with pytest.raises(ClientError) as exc_info:
        bedrock_client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"


@pytest.mark.integration
def test_bedrock_converse__access_denied__raises_access_denied_exception(bedrock_client):
    """アクセス拒否でAccessDeniedExceptionが発生する."""
    # Arrange
    bedrock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Access denied"}},
        "Converse"
    )
    
    # Act & Assert
    with pytest.raises(ClientError) as exc_info:
        bedrock_client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    assert exc_info.value.response["Error"]["Code"] == "AccessDeniedException"


@pytest.mark.integration
def test_bedrock_converse__timeout_30s__raises_read_timeout_error(bedrock_client):
    """30秒タイムアウトでReadTimeoutErrorが発生する."""
    # Arrange
    bedrock_client.converse.side_effect = ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")
    
    # Act & Assert
    with pytest.raises(ReadTimeoutError):
        bedrock_client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )


@pytest.mark.integration
def test_bedrock_converse__503_service_unavailable__raises_service_exception(bedrock_client):
    """503 Service UnavailableでServiceExceptionが発生する."""
    # Arrange
    bedrock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ServiceUnavailableException", "Message": "Service unavailable"}},
        "Converse"
    )
    
    # Act & Assert
    with pytest.raises(ClientError) as exc_info:
        bedrock_client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    assert exc_info.value.response["Error"]["Code"] == "ServiceUnavailableException"


@pytest.mark.integration
def test_bedrock_converse__rate_limited__retries_with_backoff(bedrock_client):
    """レート制限時にバックオフ付きリトライが実行される."""
    # Arrange
    bedrock_client.converse.side_effect = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate limit exceeded"}},
        "Converse"
    )
    
    # Act & Assert
    with pytest.raises(ClientError) as exc_info:
        bedrock_client.converse(
            modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
            messages=[{"role": "user", "content": [{"text": "Hello"}]}],
        )
    assert exc_info.value.response["Error"]["Code"] == "ThrottlingException"


@pytest.mark.integration
def test_bedrock_converse__usage_metrics__returns_token_counts(bedrock_client):
    """使用量メトリクスがトークン数を返す."""
    # Arrange
    bedrock_client.converse.return_value = {
        "output": {"message": {"role": "assistant", "content": [{"text": "Hi"}]}},
        "usage": {"inputTokens": 5, "outputTokens": 3}
    }
    
    # Act
    response = bedrock_client.converse(
        modelId="us.anthropic.claude-3-5-haiku-20241022-v1:0",
        messages=[{"role": "user", "content": [{"text": "Hello"}]}],
    )
    
    # Assert
    assert "usage" in response
    assert "inputTokens" in response["usage"]
    assert "outputTokens" in response["usage"]
    assert response["usage"]["inputTokens"] > 0
    assert response["usage"]["outputTokens"] > 0
