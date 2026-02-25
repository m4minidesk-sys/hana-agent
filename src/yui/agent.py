"""Agent setup with Strands + Bedrock."""

import logging
from pathlib import Path

import strands_tools.file_read as file_read_tool
import strands_tools.file_write as file_write_tool
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands_tools.editor import editor

from yui.tools.safe_shell import create_safe_shell

logger = logging.getLogger(__name__)


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

    # Create Bedrock model (AC-02)
    model_config = config["model"]
    model = BedrockModel(
        model_id=model_config["model_id"],
        region_name=model_config["region"],
        max_tokens=model_config["max_tokens"],
    )

    # Create safe shell tool (AC-03)
    shell_config = config["tools"]["shell"]
    safe_shell = create_safe_shell(
        allowlist=shell_config["allowlist"],
        blocklist=shell_config["blocklist"],
        timeout=shell_config["timeout_seconds"],
    )

    # Register tools — file_read/file_write are module-level TOOL_SPEC tools (AC-04)
    tools = [safe_shell, file_read_tool, file_write_tool, editor]

    # Create agent
    agent = Agent(
        model=model,
        system_prompt=system_prompt,
        tools=tools,
    )

    return agent


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
