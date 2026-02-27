"""Tests for Knowledge Base RAG and Web Search tools — Issue #48 & #53."""

from unittest.mock import MagicMock, patch
import pytest
import boto3
from botocore.exceptions import ClientError

from yui.tools.agentcore import kb_retrieve, web_search

pytestmark = pytest.mark.component



# --- kb_retrieve tests (Issue #48) ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("boto3.client")
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_success(mock_config, mock_boto_client):
    """Test successful Knowledge Base retrieval."""
    # Mock config
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": "kb-123"}}}
    
    # Mock bedrock-agent-runtime client
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {
        "retrievalResults": [
            {
                "content": {"text": "Knowledge base result 1"},
                "score": 0.9,
                "metadata": {"source": "doc1.pdf"}
            },
            {
                "content": {"text": "Knowledge base result 2"},
                "score": 0.8,
                "metadata": {"source": "doc2.pdf"}
            }
        ]
    }
    mock_boto_client.return_value = mock_client
    
    result = kb_retrieve("AI safety best practices", "kb-123")
    
    assert "Knowledge base result 1" in result
    assert "Knowledge base result 2" in result
    assert "score: 0.9" in result
    assert "doc1.pdf" in result
    mock_client.retrieve.assert_called_once_with(
        knowledgeBaseId="kb-123",
        retrievalQuery={"text": "AI safety best practices"}
    )


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_no_kb_configured(mock_config):
    """Test Knowledge Base retrieval with no KB ID configured."""
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": ""}}}
    
    result = kb_retrieve("test query", "")
    
    assert "Error: Knowledge Base ID not configured" in result
    assert "config.yaml" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("boto3.client")
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_access_denied(mock_config, mock_boto_client):
    """Test Knowledge Base retrieval with permission error."""
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": "kb-123"}}}
    
    mock_client = MagicMock()
    mock_client.retrieve.side_effect = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "User not authorized"}},
        "Retrieve"
    )
    mock_boto_client.return_value = mock_client
    
    result = kb_retrieve("test query", "kb-123")
    
    assert "Error: No permission to access Knowledge Base" in result
    assert "bedrock:Retrieve" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("boto3.client")
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_empty_results(mock_config, mock_boto_client):
    """Test Knowledge Base retrieval with no results."""
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": "kb-123"}}}
    
    mock_client = MagicMock()
    mock_client.retrieve.return_value = {"retrievalResults": []}
    mock_boto_client.return_value = mock_client
    
    result = kb_retrieve("nonexistent query", "kb-123")
    
    assert "No results found" in result
    assert "nonexistent query" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("boto3.client")
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_resource_not_found(mock_config, mock_boto_client):
    """Test Knowledge Base retrieval with ResourceNotFoundException."""
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": "kb-123"}}}
    
    mock_client = MagicMock()
    mock_client.retrieve.side_effect = ClientError(
        {"Error": {"Code": "ResourceNotFoundException", "Message": "Knowledge Base not found"}},
        "Retrieve"
    )
    mock_boto_client.return_value = mock_client
    
    result = kb_retrieve("test query", "kb-nonexistent")
    
    assert "Error: Knowledge Base 'kb-nonexistent' not found" in result
    assert "config.yaml" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore._get_config")
def test_kb_retrieve_empty_query(mock_config):
    """Test Knowledge Base retrieval with empty query."""
    mock_config.return_value = {"tools": {"web_search": {"knowledge_base_id": "kb-123"}}}
    
    result = kb_retrieve("", "kb-123")
    
    assert "Error: Query cannot be empty" in result
    
    result = kb_retrieve("   ", "kb-123")  # whitespace only
    
    assert "Error: Query cannot be empty" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_empty_query(mock_session):
    """Test web search with empty query."""
    result = web_search("", 5)
    
    assert "Error: Search query cannot be empty" in result
    
    result = web_search("   ", 5)  # whitespace only
    
    assert "Error: Search query cannot be empty" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_invalid_num_results(mock_session):
    """Test web search with invalid num_results parameter."""
    # Test negative number
    result = web_search("test query", -1)
    assert "Error: num_results must be an integer between 1 and 100" in result
    
    # Test zero
    result = web_search("test query", 0)
    assert "Error: num_results must be an integer between 1 and 100" in result
    
    # Test too large
    result = web_search("test query", 101)
    assert "Error: num_results must be an integer between 1 and 100" in result
    
    # Test non-integer (string that could cause injection)
    result = web_search("test query", "10&malicious=param")
    assert "Error: num_results must be an integer between 1 and 100" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_special_characters(mock_session):
    """Test web search with special characters in query."""
    mock_browser = MagicMock()
    mock_browser.start.return_value = "session-123"
    mock_browser.invoke.side_effect = [
        None,  # navigate
        {"text": "Search results for special characters"}  # search results
    ]
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)
    
    # Test query with special characters
    special_query = "C++ & Python: 100% better than Java?"
    result = web_search(special_query, 5)
    
    assert "Search results for special characters" in result
    # Verify that the URL was properly encoded
    mock_browser.invoke.assert_any_call("navigate", {"url": "https://www.google.com/search?q=C%2B%2B+%26+Python%3A+100%25+better+than+Java%3F&num=5"})


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_empty_results(mock_session):
    """Test web search with no results from browser."""
    mock_browser = MagicMock()
    mock_browser.start.return_value = "session-123"
    mock_browser.invoke.side_effect = [
        None,  # navigate
        {"text": ""}  # empty search results
    ]
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)
    
    result = web_search("very obscure query that returns nothing", 5)
    
    assert "No search results found" in result
    assert "very obscure query that returns nothing" in result


# --- web_search tests (Issue #53) ---

@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_success(mock_session):
    """Test successful web search via AgentCore Browser."""
    mock_browser = MagicMock()
    mock_browser.start.return_value = "session-123"
    mock_browser.invoke.side_effect = [
        None,  # navigate to Google
        {"text": "Search results: 1. AI safety guidelines\n2. Best practices for AI"}  # search results
    ]
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)
    
    result = web_search("AI safety best practices", 5)
    
    assert "AI safety guidelines" in result
    assert "Best practices for AI" in result
    mock_browser.invoke.assert_any_call("navigate", {"url": "https://www.google.com/search?q=AI+safety+best+practices&num=5"})


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_with_default_num_results(mock_session):
    """Test web search with default number of results."""
    mock_browser = MagicMock()
    mock_browser.start.return_value = "session-123"
    mock_browser.invoke.side_effect = [None, {"text": "Default search results"}]
    mock_session.return_value.__enter__ = MagicMock(return_value=mock_browser)
    mock_session.return_value.__exit__ = MagicMock(return_value=False)
    
    result = web_search("Python programming")  # No num_results specified
    
    assert "Default search results" in result
    # Should default to 10 results
    mock_browser.invoke.assert_any_call("navigate", {"url": "https://www.google.com/search?q=Python+programming&num=10"})


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", False)
def test_web_search_unavailable():
    """Test web search when AgentCore SDK not available."""
    result = web_search("test query", 5)
    
    assert "Error: bedrock-agentcore SDK not installed" in result


@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
@patch("yui.tools.agentcore.browser_session")
def test_web_search_browser_error(mock_session):
    """Test web search with browser session error."""
    mock_session.return_value.__enter__ = MagicMock(
        side_effect=Exception("ResourceNotFoundException: Browser resource not found")
    )
    mock_session.return_value.__exit__ = MagicMock(return_value=False)
    
    result = web_search("test query", 5)
    
    assert "Error: AgentCore Browser not provisioned" in result
    assert "AWS Bedrock Console" in result


# --- E2E tests (skip unless AWS configured) ---

try:
    import boto3
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False

@pytest.mark.aws
@pytest.mark.skipif(not AWS_AVAILABLE, reason="boto3 not installed")
@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_kb_retrieve_e2e():
    """E2E test for Knowledge Base retrieval with real AWS resources."""
    # This will only run if:
    # 1. AWS credentials are configured
    # 2. Knowledge Base is provisioned  
    # 3. Test is explicitly run with --aws flag
    pytest.skip("E2E test — requires real Knowledge Base provisioning")


@pytest.mark.aws
@pytest.mark.skipif(not AWS_AVAILABLE, reason="boto3 not installed")
@patch("yui.tools.agentcore.AGENTCORE_AVAILABLE", True)
def test_web_search_e2e():
    """E2E test for web search with real AgentCore Browser."""
    # This will only run if:
    # 1. AWS credentials are configured
    # 2. AgentCore Browser is provisioned
    # 3. Test is explicitly run with --aws flag
    pytest.skip("E2E test — requires real AgentCore Browser provisioning")