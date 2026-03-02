"""AgentCore Browser, Memory, and Code Interpreter tools.

Connects to real AWS Bedrock AgentCore SDK when available.
Falls back gracefully with clear error messages when AWS resources
are not provisioned.
"""

import logging
import os
import yaml
import urllib.parse

from strands import tool

logger = logging.getLogger(__name__)

# Additional imports for Knowledge Base and web search
try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

# AgentCore tools are optional — gracefully handle missing SDK
try:
    from bedrock_agentcore.tools.browser_client import browser_session
    from bedrock_agentcore.tools.code_interpreter_client import code_session
    from bedrock_agentcore.memory.client import MemoryClient
    AGENTCORE_AVAILABLE = True
except ImportError:
    AGENTCORE_AVAILABLE = False
    logger.warning("bedrock-agentcore SDK not available — AgentCore tools disabled")

# Playwright is required for Browser automation — optional dependency
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    logger.debug("playwright not installed — Browser automation unavailable")

# Default region — matches config.yaml model.region
_REGION = "us-east-1"


def set_region(region: str) -> None:
    """Set the AWS region for AgentCore tools."""
    global _REGION
    _REGION = region


@tool
def web_browse(url: str, task: str = "extract main content", timeout: int = 30) -> str:
    """Browse a web page using AgentCore cloud-managed Chrome browser.

    Creates a temporary browser session, navigates to the URL,
    and extracts content based on the task description.

    Args:
        url: URL to browse.
        task: What to extract from the page.
        timeout: Maximum execution time in seconds (default: 30).

    Returns:
        Extracted page content or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    if not PLAYWRIGHT_AVAILABLE:
        return (
            "Error: playwright not installed. "
            "Run: pip install playwright && playwright install chromium"
        )

    session_id = None
    _browse_result = None
    try:
        browser_identifier = os.environ.get("YUI_AGENTCORE_BROWSER_ID") or None
        try:
            with browser_session(region=_REGION, identifier=browser_identifier) as browser:
                session_id = browser.session_id
                logger.info("Browser session started: %s (identifier: %s)", session_id, browser_identifier)

                try:
                    ws_url, ws_headers = browser.generate_ws_headers()
                    with sync_playwright() as p:
                        b = p.chromium.connect_over_cdp(ws_url, headers=ws_headers)
                        try:
                            page = b.contexts[0].pages[0] if b.contexts and b.contexts[0].pages else b.new_page()
                            page.goto(url, timeout=timeout * 1000)
                            content_text = page.content()
                        finally:
                            b.close()
                    _browse_result = content_text[:5000] if content_text else "(no content)"
                except Exception as inner_e:
                    logger.error("Browser automation error (session: %s): %s", session_id, inner_e)
                    _browse_result = f"Error browsing {url}: {inner_e}"
        except Exception as ctx_e:
            # StopBrowserSession may fail with AccessDeniedException even when browse succeeded
            if _browse_result is not None:
                err_msg = str(ctx_e)
                if "StopBrowserSession" in err_msg or "AccessDeniedException" in err_msg:
                    logger.warning("Browser session cleanup failed (result already obtained): %s", ctx_e)
                else:
                    raise
        if _browse_result is not None:
            return _browse_result

    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return (
                "Error: No permission to use AgentCore Browser. "
                "Ensure IAM role has bedrock-agentcore:* permissions. "
                f"Session: {session_id or 'not started'}"
            )
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Browser not provisioned. "
                "Create a browser resource in AWS Bedrock Console first. "
                f"Region: {_REGION}"
            )
        if "Timeout" in error_msg or "timeout" in error_msg:
            return f"Error: Browser operation timed out after {timeout}s for {url}"
        logger.error("AgentCore Browser error (session: %s): %s", session_id, e)
        return f"Error browsing {url}: {e}"


# Memory client singleton (created on first use)
_memory_client = None


def _get_memory_client() -> "MemoryClient":
    """Get or create the memory client singleton."""
    global _memory_client
    if _memory_client is None:
        _memory_client = MemoryClient(region_name=_REGION)
    return _memory_client


@tool
def memory_store(key: str, value: str, category: str = "general", max_retries: int = 2) -> str:
    """Store a fact in AgentCore long-term memory.

    Memories persist across sessions and devices via AWS.

    Args:
        key: Memory key (e.g., "user_preference_theme").
        value: Memory value to store.
        category: Memory category for organization.
        max_retries: Maximum retry attempts on transient errors (default: 2).

    Returns:
        Confirmation message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            import uuid
            client = _get_memory_client()
            # Create or get memory store (idempotent)
            try:
                memory_info = client.create_or_get_memory(
                    name="yui_agent_memory",
                    description="YUI Agent long-term memory store",
                )
                memory_id = memory_info["memoryId"]
            except Exception as me:
                if "already exists" in str(me):
                    memories = client.list_memories()
                    mem = next((m for m in memories if m.get("name") == "yui_agent_memory"), None)
                    if mem:
                        memory_id = mem["memoryId"]
                    else:
                        raise
                else:
                    raise
            actor_id = "yui_agent"
            session_id = str(uuid.uuid4())
            # Store as an event with the key-value as a message pair
            client.create_event(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=[(f"store: {key} = {value} (category: {category})", "USER")],
                metadata={"key": {"stringValue": key}, "category": {"stringValue": category}},
            )
            logger.info("Memory stored: %s=%s (category: %s)", key, value[:50], category)
            return f"Stored memory '{key}' in category '{category}'"

        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            if "ResourceNotFoundException" in error_msg:
                return (
                    "Error: AgentCore Memory not provisioned. "
                    f"Create a memory store in AWS Bedrock Console first. Region: {_REGION}"
                )
            if "AccessDeniedException" in error_msg:
                return (
                    "Error: No permission to use AgentCore Memory. "
                    "Ensure IAM role has bedrock-agentcore:* permissions."
                )
            
            # Retry on transient errors
            if attempt < max_retries and any(x in error_msg for x in ["Throttling", "ServiceUnavailable", "InternalError"]):
                logger.warning("Memory store attempt %d failed (retrying): %s", attempt + 1, e)
                continue
            
            logger.error("Memory store error: %s", e)
            break

    return f"Error storing memory after {max_retries + 1} attempts: {last_error}"


@tool
def memory_recall(query: str, limit: int = 5, max_retries: int = 2) -> str:
    """Recall facts from AgentCore long-term memory.

    Searches across all stored memories using semantic search.

    Args:
        query: Search query.
        limit: Maximum number of results to return.
        max_retries: Maximum retry attempts on transient errors (default: 2).

    Returns:
        Retrieved memories or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            client = _get_memory_client()
            # Create or get memory store (idempotent)
            try:
                memory_info = client.create_or_get_memory(
                    name="yui_agent_memory",
                    description="YUI Agent long-term memory store",
                )
                memory_id = memory_info["memoryId"]
            except Exception as me:
                if "already exists" in str(me):
                    memories = client.list_memories()
                    mem = next((m for m in memories if m.get("name") == "yui_agent_memory"), None)
                    if mem:
                        memory_id = mem["memoryId"]
                    else:
                        raise
                else:
                    raise
            results = client.retrieve_memories(
                memory_id=memory_id,
                namespace="DEFAULT",
                query=query,
                top_k=limit,
            )

            if not results:
                return f"No memories found for query: {query}"

            output_lines = [f"Found {len(results)} memories for '{query}':"]
            for i, result in enumerate(results, 1):
                mem_content = result.get("content", {})
                if isinstance(mem_content, dict):
                    text = mem_content.get("text", str(result))
                else:
                    text = str(mem_content)
                score = result.get("score", "N/A")
                output_lines.append(f"  {i}. [{score}] {text}")

            return "\n".join(output_lines)

        except Exception as e:
            last_error = e
            error_msg = str(e)
            
            if "ResourceNotFoundException" in error_msg:
                return (
                    "Error: AgentCore Memory not provisioned. "
                    f"Create a memory store in AWS Bedrock Console first. Region: {_REGION}"
                )
            if "AccessDeniedException" in error_msg:
                return (
                    "Error: No permission to use AgentCore Memory. "
                    "Ensure IAM role has bedrock-agentcore:* permissions."
                )
            
            # Retry on transient errors
            if attempt < max_retries and any(x in error_msg for x in ["Throttling", "ServiceUnavailable", "InternalError"]):
                logger.warning("Memory recall attempt %d failed (retrying): %s", attempt + 1, e)
                continue
            
            logger.error("Memory recall error: %s", e)
            break

    return f"Error recalling memory after {max_retries + 1} attempts: {last_error}"


@tool
def code_execute(code: str, language: str = "python", timeout: int = 60) -> str:
    """Execute code in AgentCore sandboxed Code Interpreter.

    Runs code in an isolated cloud environment with no access
    to the host filesystem.

    Args:
        code: Code to execute.
        language: Programming language (python, javascript, typescript).
        timeout: Maximum execution time in seconds (default: 60).

    Returns:
        Execution output or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    session_id = None
    try:
        with code_session(region=_REGION) as interpreter:
            session_id = interpreter.start()
            logger.info("Code interpreter session started: %s", session_id)

            try:
                result = interpreter.execute_code(code=code, language=language)

                # SDK returns EventStream in result["stream"]
                # Each event: {"result": {"structuredContent": {"stdout": ..., "stderr": ..., "exitCode": ...}}}
                stream = result.get("stream")
                stdout_parts = []
                stderr_parts = []
                if stream:
                    for event in stream:
                        evt_result = event.get("result", {})
                        structured = evt_result.get("structuredContent", {})
                        if structured.get("stdout"):
                            stdout_parts.append(structured["stdout"])
                        if structured.get("stderr"):
                            stderr_parts.append(structured["stderr"])
                        # Fallback: content array
                        for content_item in evt_result.get("content", []):
                            if content_item.get("type") == "text" and content_item.get("text"):
                                if not structured:
                                    stdout_parts.append(content_item["text"])
                else:
                    # Fallback for direct dict response
                    stdout_parts.append(result.get("stdout", ""))
                    stderr_parts.append(result.get("stderr", ""))

                stdout = "\n".join(filter(None, stdout_parts))
                stderr = "\n".join(filter(None, stderr_parts))
                output = stdout
                if stderr:
                    output += f"\nSTDERR: {stderr}"

                return output.strip() if output.strip() else "(no output)"
            finally:
                try:
                    interpreter.stop()
                    logger.info("Code interpreter session stopped: %s", session_id)
                except Exception as cleanup_error:
                    logger.warning("Failed to stop code interpreter session %s: %s", session_id, cleanup_error)

    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return (
                "Error: No permission to use AgentCore Code Interpreter. "
                "Ensure IAM role has bedrock-agentcore:* permissions. "
                f"Session: {session_id or 'not started'}"
            )
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Code Interpreter not provisioned. "
                "Create a code interpreter in AWS Bedrock Console first. "
                f"Region: {_REGION}"
            )
        if "Timeout" in error_msg or "timeout" in error_msg:
            return f"Error: Code execution timed out after {timeout}s. Session: {session_id}"
        logger.error("Code interpreter error (session: %s): %s", session_id, e)
        return f"Error executing code: {e}"


# --- Config helper ---

def _get_config() -> dict:
    """Load configuration from config.yaml."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "config.yaml")
    if not os.path.exists(config_path):
        # Try alternate path
        config_path = "config.yaml"
        if not os.path.exists(config_path):
            return {}
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Could not load config.yaml: %s", e)
        return {}


# --- Knowledge Base RAG (Issue #48) ---

@tool
def kb_retrieve(query: str, knowledge_base_id: str = "") -> str:
    """Retrieve knowledge from Bedrock Knowledge Base using semantic search.

    Uses AWS Bedrock Agent Runtime retrieve API to search indexed documents.
    Requires Knowledge Base to be provisioned and configured in config.yaml.

    Args:
        query: Search query text.
        knowledge_base_id: Knowledge Base ID (optional, reads from config if empty).

    Returns:
        Retrieved knowledge content or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"
    
    if not BOTO3_AVAILABLE:
        return "Error: boto3 not installed. Run: pip install boto3"
    
    # Validate query
    if not query or not query.strip():
        return "Error: Query cannot be empty"
    
    # Get Knowledge Base ID from config if not provided
    if not knowledge_base_id:
        config = _get_config()
        kb_id = config.get("tools", {}).get("web_search", {}).get("knowledge_base_id", "")
        if not kb_id:
            return (
                "Error: Knowledge Base ID not configured. "
                "Set 'tools.web_search.knowledge_base_id' in config.yaml"
            )
        knowledge_base_id = kb_id

    try:
        # Create bedrock-agent-runtime client
        client = boto3.client("bedrock-agent-runtime", region_name=_REGION)
        
        # Call retrieve API
        response = client.retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": query.strip()}
        )
        
        retrieval_results = response.get("retrievalResults", [])
        
        if not retrieval_results:
            return f"No results found for query: {query}"
        
        # Format results
        output_lines = [f"Found {len(retrieval_results)} results for '{query}':"]
        for i, result in enumerate(retrieval_results, 1):
            content = result.get("content", {}).get("text", "")
            score = result.get("score", 0)
            metadata = result.get("metadata", {})
            source = metadata.get("source", "unknown")
            
            output_lines.append(f"  {i}. [score: {score:.2f}] {content}")
            if source != "unknown":
                output_lines.append(f"     Source: {source}")
        
        return "\n".join(output_lines)
        
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "AccessDeniedException":
            return (
                "Error: No permission to access Knowledge Base. "
                "Ensure IAM role has bedrock:Retrieve permission."
            )
        elif error_code == "ResourceNotFoundException":
            return (
                f"Error: Knowledge Base '{knowledge_base_id}' not found. "
                "Verify Knowledge Base ID in config.yaml."
            )
        else:
            return f"Error accessing Knowledge Base: {e}"
    
    except Exception as e:
        logger.error("Knowledge Base retrieve error: %s", e)
        return f"Error retrieving from Knowledge Base: {e}"


# --- Web Search (Issue #53) ---

@tool  
def web_search(query: str, num_results: int = 10, timeout: int = 30) -> str:
    """Search the web using AgentCore Browser with Google search.

    Performs web search via Google using cloud-managed browser automation.
    Alternative to external search APIs for VPC-compliant environments.

    Args:
        query: Search query text.
        num_results: Maximum number of results to return (default: 10, range: 1-100).
        timeout: Maximum execution time in seconds (default: 30).

    Returns:
        Search results or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    # Validate query (before playwright check so unit tests work without playwright)
    if not query or not query.strip():
        return "Error: Search query cannot be empty"
    
    # Validate num_results to prevent injection attacks
    if not isinstance(num_results, int) or num_results < 1 or num_results > 100:
        return f"Error: num_results must be an integer between 1 and 100, got: {num_results}"

    if not PLAYWRIGHT_AVAILABLE:
        return (
            "Error: playwright not installed. "
            "Run: pip install playwright && playwright install chromium"
        )

    session_id = None
    try:
        encoded_query = urllib.parse.quote_plus(query.strip())
        search_url = f"https://www.google.com/search?q={encoded_query}&num={num_results}"
        
        browser_identifier = os.environ.get("YUI_AGENTCORE_BROWSER_ID") or None
        with browser_session(region=_REGION, identifier=browser_identifier) as browser:
            session_id = browser.session_id
            logger.info("Browser session started for search: %s (identifier: %s)", session_id, browser_identifier)

            try:
                ws_url, ws_headers = browser.generate_ws_headers()
                with sync_playwright() as p:
                    b = p.chromium.connect_over_cdp(ws_url, headers=ws_headers)
                    try:
                        page = b.contexts[0].pages[0] if b.contexts and b.contexts[0].pages else b.new_page()
                        page.goto(search_url, timeout=timeout * 1000)
                        search_content = page.content()
                    finally:
                        b.close()
                
                if not search_content or not search_content.strip():
                    return f"No search results found for query: {query}"
                
                return f"Web search results for '{query}':\n{search_content[:5000]}"
            except Exception as inner_e:
                logger.error("Web search automation error (session: %s): %s", session_id, inner_e)
                return f"Error performing web search: {inner_e}"

    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return (
                "Error: No permission to use AgentCore Browser. "
                "Ensure IAM role has bedrock-agentcore:* permissions. "
                f"Session: {session_id or 'not started'}"
            )
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Browser not provisioned. "
                "Create a browser resource in AWS Bedrock Console first. "
                f"Region: {_REGION}"
            )
        if "Timeout" in error_msg or "timeout" in error_msg:
            return f"Error: Web search timed out after {timeout}s for query: {query}"
        logger.error("Web search error (session: %s): %s", session_id, e)
        return f"Error performing web search: {e}"
