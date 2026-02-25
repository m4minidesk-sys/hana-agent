"""HANA CLI adapter — Terminal REPL with history and rich formatting."""

from __future__ import annotations

import logging
import readline
import sys
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown

from strands import Agent

logger = logging.getLogger(__name__)


class CLIAdapter:
    """Interactive CLI REPL for HANA.

    Provides a terminal-based interface with readline history,
    rich text output, and graceful shutdown handling.

    Args:
        agent: Configured Strands Agent instance.
        config: HANA configuration dictionary.
    """

    def __init__(self, agent: Agent, config: dict[str, Any]) -> None:
        self.agent = agent
        self.config = config
        self.console = Console()

        cli_config = config.get("channels", {}).get("cli", {})
        self.prompt = cli_config.get("prompt", "hana> ")
        self.history_file = cli_config.get("history_file", "~/.hana/history")

    def _setup_history(self) -> None:
        """Set up readline history from file."""
        history_path = Path(self.history_file).expanduser()
        history_path.parent.mkdir(parents=True, exist_ok=True)

        if history_path.exists():
            try:
                readline.read_history_file(str(history_path))
            except OSError:
                pass  # History file corrupt or inaccessible

        readline.set_history_length(1000)

    def _save_history(self) -> None:
        """Save readline history to file."""
        history_path = Path(self.history_file).expanduser()
        try:
            readline.write_history_file(str(history_path))
        except OSError:
            pass

    def _print_welcome(self) -> None:
        """Print welcome banner."""
        self.console.print()
        self.console.print("[bold cyan]🌸 HANA[/bold cyan] — Helpful Autonomous Networked Agent")
        self.console.print("[dim]Type your message, or 'exit'/'quit' to leave.[/dim]")
        self.console.print()

    def run(self) -> None:
        """Start the interactive REPL loop.

        Reads user input, sends it to the agent, and prints the response.
        Handles Ctrl-C and Ctrl-D gracefully.
        """
        self._setup_history()
        self._print_welcome()

        try:
            while True:
                try:
                    user_input = input(self.prompt).strip()
                except EOFError:
                    # Ctrl-D
                    self.console.print("\n[dim]Goodbye! 👋[/dim]")
                    break

                if not user_input:
                    continue

                if user_input.lower() in ("exit", "quit", "q"):
                    self.console.print("[dim]Goodbye! 👋[/dim]")
                    break

                if user_input.lower() in ("help", "?"):
                    self._print_help()
                    continue

                if user_input.lower() == "status":
                    self._print_status()
                    continue

                # Send to agent
                try:
                    result = self.agent(user_input)

                    # Extract text from the result
                    response_text = self._extract_response(result)
                    if response_text:
                        self.console.print()
                        self.console.print(Markdown(response_text))
                        self.console.print()

                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Interrupted.[/yellow]")
                    continue
                except Exception as exc:
                    self.console.print(f"\n[red]Error:[/red] {exc}")
                    logger.exception("Agent invocation failed")

        except KeyboardInterrupt:
            self.console.print("\n[dim]Goodbye! 👋[/dim]")
        finally:
            self._save_history()

    def _extract_response(self, result: Any) -> str:
        """Extract printable text from an AgentResult.

        Args:
            result: The result object from agent invocation.

        Returns:
            Extracted text string.
        """
        if result is None:
            return ""

        # AgentResult has a message attribute with content blocks
        if hasattr(result, "message"):
            message = result.message
            if isinstance(message, dict) and "content" in message:
                parts = []
                for block in message["content"]:
                    if isinstance(block, dict) and "text" in block:
                        parts.append(block["text"])
                return "\n".join(parts)

        # Fallback: try str conversion
        text = str(result)
        if text and text != "None":
            return text
        return ""

    def _print_help(self) -> None:
        """Print help information."""
        self.console.print()
        self.console.print("[bold]Commands:[/bold]")
        self.console.print("  [cyan]exit[/cyan] / [cyan]quit[/cyan] — Exit HANA")
        self.console.print("  [cyan]status[/cyan] — Show agent status")
        self.console.print("  [cyan]help[/cyan] / [cyan]?[/cyan] — Show this help")
        self.console.print()
        self.console.print("[dim]Everything else is sent to the agent.[/dim]")
        self.console.print()

    def _print_status(self) -> None:
        """Print agent status."""
        agent_config = self.config.get("agent", {})
        self.console.print()
        self.console.print("[bold]Agent Status[/bold]")
        self.console.print(f"  Model: {agent_config.get('model_id', 'unknown')}")
        self.console.print(f"  Region: {agent_config.get('region', 'unknown')}")
        self.console.print(f"  Workspace: {self.config.get('workspace', {}).get('root', 'unknown')}")

        tools_config = self.config.get("tools", {})
        enabled_tools = [name for name, cfg in tools_config.items() if isinstance(cfg, dict) and cfg.get("enabled")]
        self.console.print(f"  Tools: {', '.join(enabled_tools) if enabled_tools else 'none'}")
        self.console.print()
