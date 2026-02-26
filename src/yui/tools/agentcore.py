"""AgentCore Browser, Memory, and Code Interpreter tools.

Connects to real AWS Bedrock AgentCore SDK when available.
Falls back gracefully with clear error messages when AWS resources
are not provisioned.
"""

import logging

from strands import tool

logger = logging.getLogger(__name__)

# AgentCore tools are optional — gracefully handle missing SDK
try:
    from bedrock_agentcore.tools.browser_client import browser_session
    from bedrock_agentcore.tools.code_interpreter_client import code_session
    from bedrock_agentcore.memory.client import MemoryClient
    AGENTCORE_AVAILABLE = True
except ImportError:
    AGENTCORE_AVAILABLE = False
    logger.warning("bedrock-agentcore SDK not available — AgentCore tools disabled")

# Default region — matches config.yaml model.region
_REGION = "us-east-1"


def set_region(region: str) -> None:
    """Set the AWS region for AgentCore tools."""
    global _REGION
    _REGION = region


@tool
def web_browse(url: str, task: str = "extract main content") -> str:
    """Browse a web page using AgentCore cloud-managed Chrome browser.

    Creates a temporary browser session, navigates to the URL,
    and extracts content based on the task description.

    Args:
        url: URL to browse.
        task: What to extract from the page.

    Returns:
        Extracted page content or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed. Run: pip install bedrock-agentcore"

    try:
        with browser_session(region=_REGION) as browser:
            session_id = browser.start()
            logger.info("Browser session started: %s", session_id)

            # Navigate and extract — the browser provides automation stream
            # For now, use the session to get page content
            result = browser.invoke("navigate", {"url": url})
            content = browser.invoke("extract", {"task": task})

            browser.stop()
            logger.info("Browser session stopped")

            if isinstance(content, dict):
                return content.get("text", str(content))
            return str(content)

    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return (
                "Error: No permission to use AgentCore Browser. "
                "Ensure IAM role has bedrock-agentcore:* permissions."
            )
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Browser not provisioned. "
                "Create a browser resource in AWS Bedrock Console first."
            )
        logger.error("AgentCore Browser error: %s", e)
        return f"Error browsing {url}: {e}"


# Memory client singleton (created on first use)
_memory_client = None


def _get_memory_client() -> "MemoryClient":
    """Get or create the memory client singleton."""
    global _memory_client
    if _memory_client is None:
        _memory_client = MemoryClient(region=_REGION)
    return _memory_client


@tool
def memory_store(key: str, value: str, category: str = "general") -> str:
    """Store a fact in AgentCore long-term memory.

    Memories persist across sessions and devices via AWS.

    Args:
        key: Memory key (e.g., "user_preference_theme").
        value: Memory value to store.
        category: Memory category for organization.

    Returns:
        Confirmation message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed."

    try:
        client = _get_memory_client()
        # Store as a memory event
        client.add_memory(
            namespace=category,
            content=f"{key}: {value}",
            metadata={"key": key, "category": category},
        )
        logger.info("Memory stored: %s=%s (category: %s)", key, value[:50], category)
        return f"Stored memory '{key}' in category '{category}'"

    except Exception as e:
        error_msg = str(e)
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Memory not provisioned. "
                "Create a memory store in AWS Bedrock Console first."
            )
        logger.error("Memory store error: %s", e)
        return f"Error storing memory: {e}"


@tool
def memory_recall(query: str, limit: int = 5) -> str:
    """Recall facts from AgentCore long-term memory.

    Searches across all stored memories using semantic search.

    Args:
        query: Search query.
        limit: Maximum number of results to return.

    Returns:
        Retrieved memories or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed."

    try:
        client = _get_memory_client()
        results = client.search_memory(
            query=query,
            max_results=limit,
        )

        if not results:
            return f"No memories found for query: {query}"

        output_lines = [f"Found {len(results)} memories for '{query}':"]
        for i, result in enumerate(results, 1):
            content = result.get("content", str(result))
            score = result.get("score", "N/A")
            output_lines.append(f"  {i}. [{score}] {content}")

        return "\n".join(output_lines)

    except Exception as e:
        error_msg = str(e)
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Memory not provisioned. "
                "Create a memory store in AWS Bedrock Console first."
            )
        logger.error("Memory recall error: %s", e)
        return f"Error recalling memory: {e}"


@tool
def code_execute(code: str, language: str = "python") -> str:
    """Execute code in AgentCore sandboxed Code Interpreter.

    Runs code in an isolated cloud environment with no access
    to the host filesystem.

    Args:
        code: Code to execute.
        language: Programming language (python, javascript, typescript).

    Returns:
        Execution output or error message.
    """
    if not AGENTCORE_AVAILABLE:
        return "Error: bedrock-agentcore SDK not installed."

    try:
        with code_session(region=_REGION) as interpreter:
            session_id = interpreter.start()
            logger.info("Code interpreter session started: %s", session_id)

            result = interpreter.execute_code(code=code, language=language)

            interpreter.stop()
            logger.info("Code interpreter session stopped")

            # Extract output from result
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            output = stdout
            if stderr:
                output += f"\nSTDERR: {stderr}"

            return output.strip() if output.strip() else "(no output)"

    except Exception as e:
        error_msg = str(e)
        if "AccessDeniedException" in error_msg:
            return (
                "Error: No permission to use AgentCore Code Interpreter. "
                "Ensure IAM role has bedrock-agentcore:* permissions."
            )
        if "ResourceNotFoundException" in error_msg:
            return (
                "Error: AgentCore Code Interpreter not provisioned. "
                "Create a code interpreter in AWS Bedrock Console first."
            )
        logger.error("Code interpreter error: %s", e)
        return f"Error executing code: {e}"
