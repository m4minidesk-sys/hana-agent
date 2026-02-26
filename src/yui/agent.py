"""Agent setup with Strands + Bedrock."""

import atexit
import logging
from pathlib import Path
from typing import Optional

import strands_tools.file_read as file_read_tool
import strands_tools.file_write as file_write_tool
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands_tools.editor import editor

from yui.tools.mcp_integration import MCPManager, connect_mcp_servers
from yui.tools.safe_shell import create_safe_shell

logger = logging.getLogger(__name__)

# Module-level MCP manager for CLI access
_mcp_manager: Optional[MCPManager] = None


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
    # Load system prompt from workspace files (AC-05)
    workspace = Path(config["tools"]["file"]["workspace_root"]).expanduser()
    system_prompt = _load_system_prompt(workspace)

    # Create Bedrock model (AC-02, AC-20)
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
    
    model = BedrockModel(**model_kwargs)

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

    # Kiro CLI tool (check binary exists)
    kiro_path = Path(config["tools"]["kiro"]["binary_path"]).expanduser()
    if kiro_path.exists():
        try:
            from yui.tools.kiro_delegate import kiro_delegate
            tools.append(kiro_delegate)
            logger.info("Registered kiro_delegate")
        except ImportError:
            logger.warning("kiro_delegate not available")
    else:
        logger.info("Kiro CLI not found at %s — skipping kiro_delegate", kiro_path)

    # AgentCore tools (check boto3 available)
    try:
        from yui.tools.agentcore import code_execute, memory_recall, memory_store, set_region, web_browse
        set_region(config["model"]["region"])
        tools.extend([web_browse, memory_store, memory_recall, code_execute])
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
