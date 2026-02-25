"""CLI REPL interface."""

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
    """Run CLI REPL."""
    # Load config (AC-06, AC-07)
    try:
        config = load_config()
    except Exception as e:
        print(f"[yui] Config error: {e}", file=sys.stderr)
        print("[yui] Fix ~/.yui/config.yaml or delete it to use defaults.", file=sys.stderr)
        sys.exit(1)

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
