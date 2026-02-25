"""HANA agent core — Strands Agent + BedrockModel initialization."""

from __future__ import annotations

import logging
from typing import Any

from strands import Agent
from strands.models.bedrock import BedrockModel

from hana.auth.aws_credentials import validate_aws_credentials
from hana.local_tools import exec_tool, file_ops
from hana.runtime.config_loader import load_workspace_files

logger = logging.getLogger(__name__)


def _build_system_prompt(config: dict[str, Any]) -> str:
    """Build the system prompt from workspace files and config.

    Loads AGENTS.md and SOUL.md from the workspace directory and
    combines them into a single system prompt.

    Args:
        config: HANA configuration dictionary.

    Returns:
        Complete system prompt string.
    """
    workspace_files = load_workspace_files(config)

    parts: list[str] = []

    if workspace_files.get("soul_md"):
        parts.append(workspace_files["soul_md"])

    if workspace_files.get("agents_md"):
        parts.append(workspace_files["agents_md"])

    if not parts:
        parts.append(
            "You are HANA, a helpful AI assistant. "
            "You have access to local tools for shell commands and file operations."
        )

    return "\n\n---\n\n".join(parts)


def _collect_tools(config: dict[str, Any]) -> list:
    """Collect and configure all enabled tools.

    Reads the tools section of the config and returns a list of
    Strands-compatible tool functions.

    Args:
        config: HANA configuration dictionary.

    Returns:
        List of tool functions to pass to the Agent.
    """
    tools = []
    tools_config = config.get("tools", {})

    # exec tool
    exec_config = tools_config.get("exec", {})
    if exec_config.get("enabled", True):
        exec_tool.configure(exec_config)
        tools.append(exec_tool.exec_command)
        logger.info("Loaded tool: exec_command")

    # file ops tools
    file_config = tools_config.get("file", {})
    if file_config.get("enabled", True):
        file_ops.configure(file_config)
        tools.extend([file_ops.read_file, file_ops.write_file, file_ops.edit_file])
        logger.info("Loaded tools: read_file, write_file, edit_file")

    return tools


def create_agent(config: dict[str, Any]) -> Agent:
    """Create and return a configured Strands Agent.

    Initializes the BedrockModel with config values, loads workspace
    system prompt, collects tools, and returns a ready-to-use Agent.

    Args:
        config: HANA configuration dictionary.

    Returns:
        Configured Strands Agent instance.

    Raises:
        RuntimeError: If AWS credentials are invalid.
    """
    # Validate AWS credentials
    cred_info = validate_aws_credentials(config)
    if not cred_info.get("valid"):
        error = cred_info.get("error", "Unknown credential error")
        raise RuntimeError(f"AWS credentials invalid: {error}")

    logger.info(
        "AWS credentials OK — account=%s, region=%s",
        cred_info.get("account"),
        cred_info.get("region"),
    )

    # Build Bedrock model
    agent_config = config.get("agent", {})
    model = BedrockModel(
        model_id=agent_config.get("model_id", "us.anthropic.claude-sonnet-4-20250514"),
        region_name=agent_config.get("region", "us-east-1"),
        max_tokens=agent_config.get("max_tokens", 4096),
        additional_request_fields={
            "inferenceConfig": {
                "temperature": agent_config.get("temperature", 0.7),
            },
        },
    )

    # Build system prompt
    system_prompt = _build_system_prompt(config)

    # Collect tools
    tools = _collect_tools(config)

    # Create agent
    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )

    logger.info(
        "Agent created — model=%s, tools=%d, system_prompt=%d chars",
        agent_config.get("model_id"),
        len(tools),
        len(system_prompt),
    )

    return agent
