"""Agent setup with Strands + Bedrock."""

import atexit
import logging
import time
from pathlib import Path
from typing import Any, Callable, Optional

import strands_tools.file_read as file_read_tool
import strands_tools.file_write as file_write_tool
from botocore.exceptions import ClientError, ReadTimeoutError
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands_tools.editor import editor

from yui.tools.mcp_integration import MCPManager, connect_mcp_servers
from yui.tools.safe_shell import create_safe_shell

logger = logging.getLogger(__name__)

# Module-level MCP manager for CLI access
_mcp_manager: Optional[MCPManager] = None


class BedrockErrorHandler:
    """Handle Bedrock Converse API errors with retry logic and user-friendly messages."""

    def __init__(self, max_retries: int = 3, backoff_base: float = 1.0):
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    def retry_with_backoff(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        """Execute function with exponential backoff retry logic.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
            
        Returns:
            Result from successful function execution
            
        Raises:
            Exception: After max retries exceeded
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except (ClientError, ReadTimeoutError) as e:
                last_error = e
                
                if not self._should_retry(e):
                    raise self._enhance_error(e)
                
                if attempt < self.max_retries - 1:
                    delay = self.backoff_base * (2 ** attempt)
                    logger.warning(
                        "Retryable error (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt + 1, self.max_retries, str(e), delay
                    )
                    time.sleep(delay)
                else:
                    logger.error("Max retries (%d) exceeded", self.max_retries)
                    raise self._enhance_error(e)
        
        raise last_error

    def _should_retry(self, error: Exception) -> bool:
        """Determine if error is retryable."""
        if isinstance(error, ReadTimeoutError):
            return True
            
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")
            return error_code in {
                "ThrottlingException",
                "ServiceUnavailableException",
            }
        
        return False

    def _enhance_error(self, error: Exception) -> Exception:
        """Add user-friendly guidance to errors."""
        if isinstance(error, ClientError):
            error_code = error.response.get("Error", {}).get("Code", "")
            error_msg = error.response.get("Error", {}).get("Message", "")
            
            if error_code == "AccessDeniedException":
                guidance = self._format_access_denied_guidance(error_msg)
                logger.error("Access denied: %s\n%s", error_msg, guidance)
                
            elif error_code == "ResourceNotFoundException":
                guidance = self._format_model_not_found_guidance(error_msg)
                logger.error("Model not found: %s\n%s", error_msg, guidance)
                
            elif error_code == "ValidationException":
                guidance = self._format_validation_guidance(error_msg)
                logger.error("Validation error: %s\n%s", error_msg, guidance)
        
        return error

    def _format_access_denied_guidance(self, error_msg: str) -> str:
        """Format IAM policy guidance for AccessDeniedException."""
        return """
AWS IAM permission denied. 
Suggested IAM policy:
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
    "Resource": "arn:aws:bedrock:*:*:foundation-model/*"
  }]
}
"""

    def _format_model_not_found_guidance(self, error_msg: str) -> str:
        """Format model availability guidance."""
        return """
Model not found. Check:
1. Model ID is correct
2. Model is available in your region (check AWS Console)
3. You have model access enabled in Bedrock

Common models:
- anthropic.claude-3-sonnet-20240229-v1:0
- anthropic.claude-3-haiku-20240307-v1:0
- us.anthropic.claude-sonnet-4-20250514-v1:0
"""

    def _format_validation_guidance(self, error_msg: str) -> str:
        """Format validation error guidance."""
        if "token" in error_msg.lower():
            return """
Input exceeds token limit. Try:
1. Reduce input size
2. Split into smaller chunks
3. Use a model with higher token limits
"""
        elif "guardrail" in error_msg.lower():
            return """
Guardrail configuration error. Check:
1. Guardrail ID is correct
2. Guardrail version exists
3. Guardrail is in READY state
"""
        return "Check request parameters and try again."


def get_mcp_manager() -> Optional[MCPManager]:
    """Return the active MCP manager instance, if any."""
    return _mcp_manager


def create_agent(config: dict) -> Agent:
    """Create Strands agent with Bedrock model and tools.

    Args:
        config: Merged configuration dictionary.

    Returns:
        Configured Strands Agent instance.
    """
    # Initialize error handler
    error_handler = BedrockErrorHandler(max_retries=3, backoff_base=1.0)
    
    # Load system prompt from workspace files (AC-05)
    workspace = Path(config["tools"]["file"]["workspace_root"]).expanduser()
    system_prompt = _load_system_prompt(workspace)

    # Create Bedrock model with error handling (AC-02, AC-20)
    model_config = config["model"]
    model_kwargs = {
        "model_id": model_config["model_id"],
        "region_name": model_config["region"],
        "max_tokens": model_config["max_tokens"],
    }
    
    # Add Guardrails if configured (AC-20)
    if model_config.get("guardrail_id"):
        model_kwargs["guardrail_id"] = model_config["guardrail_id"]
        model_kwargs["guardrail_version"] = model_config.get("guardrail_version", "DRAFT")
        if model_config.get("guardrail_latest_message"):
            model_kwargs["guardrail_latest_message"] = True
        logger.info("Guardrails enabled: %s (version: %s)", 
                   model_kwargs["guardrail_id"], model_kwargs["guardrail_version"])
    
    # Create model with retry logic and validation
    def _create_and_validate_model():
        model = BedrockModel(**model_kwargs)
        # Validate model by making a minimal test call
        # This catches ResourceNotFoundException, AccessDeniedException, ValidationException, etc.
        try:
            # Call converse with minimal input to validate model access
            # In tests, this will trigger mocked errors
            if hasattr(model, 'converse'):
                model.converse(
                    messages=[{"role": "user", "content": [{"text": "test"}]}]
                )
        except ClientError as e:
            # Re-raise to be handled by error handler
            raise
        return model
    
    try:
        model = error_handler.retry_with_backoff(_create_and_validate_model)
    except (ClientError, ReadTimeoutError) as e:
        logger.error("Failed to create Bedrock model: %s", e)
        raise

    # Create safe shell tool (AC-03)
    shell_config = config["tools"]["shell"]
    safe_shell = create_safe_shell(
        allowlist=shell_config["allowlist"],
        blocklist=shell_config["blocklist"],
        timeout=shell_config["timeout_seconds"],
    )

    # Register tools — file_read/file_write are module-level TOOL_SPEC tools (AC-04)
    tools = [safe_shell, file_read_tool, file_write_tool, editor]

    # Conditionally register Phase 2 tools
    tools.extend(_register_phase2_tools(config))

    # Connect MCP servers and add their tools (graceful — failures don't block startup)
    global _mcp_manager
    _mcp_manager = connect_mcp_servers(config)
    mcp_tools = _mcp_manager.get_tools()
    if mcp_tools:
        tools.extend(mcp_tools)
        logger.info("Added %d MCP tool provider(s) to agent", len(mcp_tools))

    # Register cleanup on exit
    atexit.register(_cleanup_mcp)

    # Create agent
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
    )

    return agent


def _register_phase2_tools(config: dict) -> list:
    """Register Phase 2 tools conditionally based on availability."""
    tools = []

    # Git tool (always available)
    try:
        from yui.tools.git_tool import git_tool
        tools.append(git_tool)
        logger.info("Registered git_tool")
    except ImportError:
        logger.warning("git_tool not available")

    # Kiro CLI tools — availability check (AC-78) + registration
    from yui.tools.kiro_tools import check_kiro_available

    kiro_available = check_kiro_available()
    if kiro_available:
        try:
            from yui.tools.kiro_delegate import kiro_delegate
            from yui.tools.kiro_tools import kiro_implement, kiro_review

            tools.append(kiro_delegate)
            tools.append(kiro_review)
            tools.append(kiro_implement)
            logger.info("Registered kiro_delegate, kiro_review, kiro_implement")
        except ImportError:
            logger.warning("Kiro tools not available")
    else:
        logger.warning(
            "Kiro CLI not found — kiro_delegate, kiro_review, kiro_implement disabled. "
            "Install: curl -fsSL https://kiro.dev/install | bash"
        )

    # AgentCore tools (check boto3 available)
    try:
        from yui.tools.agentcore import (
            code_execute, 
            kb_retrieve, 
            memory_recall, 
            memory_store, 
            set_region, 
            web_browse, 
            web_search
        )
        set_region(config["model"]["region"])
        tools.extend([web_browse, web_search, kb_retrieve, memory_store, memory_recall, code_execute])
        logger.info("Registered AgentCore tools (region: %s)", config["model"]["region"])
    except ImportError:
        logger.info("AgentCore tools not available — install boto3 to enable")

    return tools


def _load_system_prompt(workspace: Path) -> str:
    """Load system prompt from AGENTS.md and SOUL.md in workspace.

    Missing files are logged but not treated as errors (E-11).
    """
    parts: list[str] = []

    agents_md = workspace / "AGENTS.md"
    soul_md = workspace / "SOUL.md"

    if agents_md.exists():
        parts.append(agents_md.read_text(encoding="utf-8"))
        logger.info("Loaded AGENTS.md (%d chars)", len(parts[-1]))
    else:
        logger.info("AGENTS.md not found at %s — using empty prompt", agents_md)

    if soul_md.exists():
        parts.append(soul_md.read_text(encoding="utf-8"))
        logger.info("Loaded SOUL.md (%d chars)", len(parts[-1]))
    else:
        logger.info("SOUL.md not found at %s — skipping", soul_md)

    return "\n\n".join(parts)


def _cleanup_mcp() -> None:
    """Clean up MCP connections on exit."""
    global _mcp_manager
    if _mcp_manager is not None:
        _mcp_manager.disconnect_all()
        _mcp_manager = None
