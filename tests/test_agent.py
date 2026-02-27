"""Tests for yui.agent — AC-02, AC-04, AC-05."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from yui.config import load_config
from yui.agent import create_agent, _load_system_prompt

pytestmark = pytest.mark.component



class TestSystemPrompt:
    """AC-05: System prompt includes content from AGENTS.md and SOUL.md."""

    def test_loads_both_files(self, tmp_path):
        """Both AGENTS.md and SOUL.md are concatenated into system prompt."""
        agents = tmp_path / "AGENTS.md"
        soul = tmp_path / "SOUL.md"
        agents.write_text("# Agent Rules\nBe safe.")
        soul.write_text("# Persona\nI am Yui.")

        prompt = _load_system_prompt(tmp_path)
        assert "Agent Rules" in prompt
        assert "Be safe" in prompt
        assert "Persona" in prompt
        assert "I am Yui" in prompt

    def test_missing_agents_md(self, tmp_path):
        """Missing AGENTS.md → still works, just SOUL.md."""
        soul = tmp_path / "SOUL.md"
        soul.write_text("# Persona\nI am Yui.")

        prompt = _load_system_prompt(tmp_path)
        assert "I am Yui" in prompt

    def test_missing_both(self, tmp_path):
        """Both missing → empty string (no crash)."""
        prompt = _load_system_prompt(tmp_path)
        assert prompt == ""


class TestCreateAgent:
    """AC-02: Agent is created with BedrockModel.
    AC-04: file_read, file_write, editor tools are registered.
    """

    def test_agent_has_correct_tools(self, tmp_path):
        """Agent registers safe_shell, file_read, file_write, editor."""
        # Set up workspace
        agents = tmp_path / "AGENTS.md"
        agents.write_text("# Rules")

        config = load_config(str(tmp_path / "nonexistent.yaml"))
        config["tools"]["file"]["workspace_root"] = str(tmp_path)

        agent = create_agent(config)
        tool_names = list(agent.tool_registry.registry.keys())

        assert "safe_shell" in tool_names, f"Tools: {tool_names}"
        assert "file_read" in tool_names, f"Tools: {tool_names}"
        assert "file_write" in tool_names, f"Tools: {tool_names}"
        assert "editor" in tool_names, f"Tools: {tool_names}"

    def test_agent_system_prompt_loaded(self, tmp_path):
        """Agent's system prompt contains workspace file content."""
        agents = tmp_path / "AGENTS.md"
        soul = tmp_path / "SOUL.md"
        agents.write_text("UNIQUE_AGENTS_TOKEN")
        soul.write_text("UNIQUE_SOUL_TOKEN")

        config = load_config(str(tmp_path / "nonexistent.yaml"))
        config["tools"]["file"]["workspace_root"] = str(tmp_path)

        agent = create_agent(config)

        assert "UNIQUE_AGENTS_TOKEN" in agent.system_prompt
        assert "UNIQUE_SOUL_TOKEN" in agent.system_prompt
