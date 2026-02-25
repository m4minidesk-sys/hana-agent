"""HANA entry point — CLI interface for the agent."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from hana.agent_core import create_agent
from hana.channels.cli_adapter import CLIAdapter
from hana.runtime.config_loader import load_config

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace.
    """
    parser = argparse.ArgumentParser(
        prog="hana",
        description="HANA: Lightweight AWS-optimized AI agent orchestrator",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml (default: ~/.hana/config.yaml)",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Single prompt to execute (non-interactive mode)",
    )
    parser.add_argument(
        "--channel",
        type=str,
        choices=["cli", "slack"],
        default="cli",
        help="Channel to use (default: cli)",
    )
    parser.add_argument(
        "--daemon",
        action="store_true",
        help="Run in daemon mode",
    )
    parser.add_argument(
        "--workspace",
        type=str,
        default=None,
        help="Workspace directory (default: ~/.hana/workspace)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {_get_version()}",
    )
    return parser.parse_args()


def _get_version() -> str:
    """Get the package version string."""
    from hana import __version__
    return __version__


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application.

    Args:
        verbose: If True, set log level to DEBUG.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    """Main entry point for HANA agent."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    # Load configuration
    config_path = args.config
    if config_path is None:
        default_config = Path.home() / ".hana" / "config.yaml"
        if default_config.exists():
            config_path = str(default_config)

    config = load_config(config_path)

    # Override workspace if specified
    if args.workspace:
        config["workspace"]["root"] = args.workspace

    logger.info("HANA agent starting...")

    if args.channel == "slack":
        _run_slack(config)
    elif args.daemon:
        _run_daemon(config)
    elif args.prompt:
        _run_single(config, args.prompt)
    else:
        _run_cli(config)


def _run_cli(config: dict) -> None:
    """Run the interactive CLI REPL.

    Args:
        config: Configuration dictionary.
    """
    agent = create_agent(config)
    adapter = CLIAdapter(agent=agent, config=config)
    adapter.run()


def _run_single(config: dict, prompt: str) -> None:
    """Execute a single prompt and exit.

    Args:
        config: Configuration dictionary.
        prompt: User prompt to execute.
    """
    from rich.console import Console

    console = Console()
    agent = create_agent(config)

    try:
        result = agent(prompt)
        console.print(f"\n{result}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)


def _run_slack(config: dict) -> None:
    """Run the Slack channel adapter.

    Args:
        config: Configuration dictionary.
    """
    from hana.channels.slack_adapter import SlackAdapter

    agent = create_agent(config)
    adapter = SlackAdapter(agent=agent, config=config)
    adapter.run()


def _run_daemon(config: dict) -> None:
    """Run in daemon mode with heartbeat.

    Args:
        config: Configuration dictionary.
    """
    from hana.runtime.daemon import DaemonRunner

    agent = create_agent(config)
    runner = DaemonRunner(agent=agent, config=config)
    runner.run()


if __name__ == "__main__":
    main()
