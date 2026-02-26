"""CLI REPL interface."""

import argparse
import atexit
import os
import readline
import sys
from pathlib import Path

from yui.agent import create_agent
from yui.config import load_config

# History file for readline persistence (AC-08)
HISTORY_DIR = Path("~/.yui").expanduser()
HISTORY_FILE = HISTORY_DIR / ".yui_history"
HISTORY_MAX_LENGTH = 1000


def _setup_readline() -> None:
    """Set up readline with persistent history."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        readline.read_history_file(HISTORY_FILE)
    except (FileNotFoundError, PermissionError, OSError):
        pass  # History file missing or unreadable — start fresh
    readline.set_history_length(HISTORY_MAX_LENGTH)
    atexit.register(readline.write_history_file, HISTORY_FILE)


def main() -> None:
    """Run CLI REPL or Slack adapter."""
    parser = argparse.ArgumentParser(description="結（Yui） — Your Unified Intelligence")
    parser.add_argument("--slack", action="store_true", help="Start Slack Socket Mode adapter")
    parser.add_argument("--config", help="Path to config file (default: ~/.yui/config.yaml)")
    
    # Daemon subcommand (AC-23, AC-25)
    subparsers = parser.add_subparsers(dest="command", help="Daemon management commands")
    daemon_parser = subparsers.add_parser("daemon", help="Manage Yui daemon")
    daemon_parser.add_argument("action", choices=["start", "stop", "status"], help="Daemon action")
    
    args = parser.parse_args()

    # Load config (AC-06, AC-07)
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"[yui] Config error: {e}", file=sys.stderr)
        print("[yui] Fix ~/.yui/config.yaml or delete it to use defaults.", file=sys.stderr)
        sys.exit(1)

    # Handle daemon commands
    if args.command == "daemon":
        from yui.daemon import daemon_start, daemon_status, daemon_stop
        if args.action == "start":
            daemon_start(config)
        elif args.action == "stop":
            daemon_stop(config)
        elif args.action == "status":
            daemon_status(config)
        return

    # Route to Slack or CLI
    if args.slack:
        from yui.slack_adapter import run_slack
        run_slack(config)
    else:
        _run_repl(config)


def _run_repl(config: dict) -> None:
    """Run CLI REPL."""
    # Create agent (AC-02, AC-05)
    try:
        agent = create_agent(config)
    except Exception as e:
        print(f"[yui] Agent creation failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Set up readline history (AC-08)
    _setup_readline()

    print("結（Yui） v0.1.0 — Your Unified Intelligence")
    print("Type your message or Ctrl+D to exit\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            response = agent(user_input)
            print(f"\nYui: {response}\n")

        except EOFError:
            print("\nGoodbye!")
            break
        except KeyboardInterrupt:
            print()  # newline after ^C
            continue
        except Exception as e:
            print(f"\n[yui] Error: {e}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
