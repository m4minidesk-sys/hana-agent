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
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # Daemon subcommand (AC-23, AC-25)
    daemon_parser = subparsers.add_parser("daemon", help="Manage Yui daemon")
    daemon_parser.add_argument("action", choices=["start", "stop", "status"], help="Daemon action")

    # Menubar subcommand (AC-52 through AC-61)
    menubar_parser = subparsers.add_parser("menubar", help="Menu bar UI for meetings")
    menubar_parser.add_argument(
        "--install", action="store_true", help="Install LaunchAgent for auto-start"
    )
    menubar_parser.add_argument(
        "--uninstall", action="store_true", help="Remove LaunchAgent"
    )

    # Meeting subcommand (AC-40 through AC-51)
    meeting_parser = subparsers.add_parser("meeting", help="Meeting transcription")
    meeting_sub = meeting_parser.add_subparsers(dest="meeting_action", help="Meeting actions")

    start_parser = meeting_sub.add_parser("start", help="Start meeting recording")
    start_parser.add_argument("--name", default="", help="Meeting name")

    meeting_sub.add_parser("stop", help="Stop meeting recording")
    meeting_sub.add_parser("status", help="Show current meeting status")

    list_parser = meeting_sub.add_parser("list", help="List past meetings")
    list_parser.add_argument("--limit", type=int, default=20, help="Max meetings to show")

    search_parser = meeting_sub.add_parser("search", help="Search meeting transcripts")
    search_parser.add_argument("keyword", help="Search keyword")
    search_parser.add_argument("--limit", type=int, default=20, help="Max results")

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

    # Handle menubar commands (AC-52 through AC-61)
    if args.command == "menubar":
        _handle_menubar(args, config)
        return

    # Handle meeting commands (AC-40 through AC-51)
    if args.command == "meeting":
        _handle_meeting(args, config)
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


def _handle_menubar(args: argparse.Namespace, config: dict) -> None:
    """Handle menubar subcommands (AC-52 through AC-61)."""
    try:
        from yui.meeting.menubar import (
            install_launchd,
            run_menubar,
            uninstall_launchd,
        )
    except ImportError as e:
        print(
            f"[yui] Menu bar requires additional packages: {e}\n"
            "Install with: pip install yui-agent[ui]",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.install:
        plist_path = install_launchd()
        print(f"✅ LaunchAgent installed: {plist_path}")
        print("   Yui menu bar will start automatically on login.")
        return

    if args.uninstall:
        removed = uninstall_launchd()
        if removed:
            print("✅ LaunchAgent removed. Menu bar will no longer auto-start.")
        else:
            print("ℹ️  LaunchAgent not found — nothing to remove.")
        return

    # Default: run menu bar app
    print("🎤 Starting Yui menu bar…")
    run_menubar(config)


def _handle_meeting(args: argparse.Namespace, config: dict) -> None:
    """Handle meeting subcommands (AC-40 through AC-51)."""
    if not args.meeting_action:
        print("Usage: yui meeting {start|stop|status|list|search}", file=sys.stderr)
        sys.exit(1)

    try:
        from yui.meeting.manager import (
            MeetingAlreadyRecordingError,
            MeetingManager,
            MeetingNotRecordingError,
        )
    except ImportError as e:
        print(
            f"[yui] Meeting feature requires additional packages: {e}\n"
            "Install them with: pip install yui-agent[meeting]",
            file=sys.stderr,
        )
        sys.exit(1)

    # MeetingManager is a singleton per session — for CLI we create fresh
    manager = MeetingManager(config)

    if args.meeting_action == "start":
        try:
            meeting = manager.start(name=args.name)
            print(f"🎤 Meeting started: {meeting.name}")
            print(f"   ID: {meeting.meeting_id}")
            print(f"   Press Ctrl+C to stop recording...\n")
            # Block until Ctrl+C
            try:
                while True:
                    status = manager.status()
                    if status:
                        duration = status["duration_seconds"]
                        words = status["word_count"]
                        mins = int(duration // 60)
                        secs = int(duration % 60)
                        print(
                            f"\r   ⏱ {mins:02d}:{secs:02d} | 📝 {words} words",
                            end="",
                            flush=True,
                        )
                    import time
                    time.sleep(2)
            except KeyboardInterrupt:
                print("\n")
                meeting = manager.stop()
                print(f"⏹ Meeting stopped: {meeting.name}")
                print(f"   Duration: {meeting.duration_seconds:.0f}s")
                print(f"   Words: {meeting.word_count}")
                if meeting.transcript_path:
                    print(f"   Transcript: {meeting.transcript_path}")
        except MeetingAlreadyRecordingError as e:
            print(f"[yui] {e}", file=sys.stderr)
            sys.exit(1)
        except ImportError as e:
            print(
                f"[yui] {e}\n"
                "Install meeting dependencies: pip install yui-agent[meeting]",
                file=sys.stderr,
            )
            sys.exit(1)

    elif args.meeting_action == "stop":
        try:
            meeting = manager.stop()
            print(f"⏹ Meeting stopped: {meeting.name}")
            print(f"   Duration: {meeting.duration_seconds:.0f}s")
            print(f"   Words: {meeting.word_count}")
        except MeetingNotRecordingError as e:
            print(f"[yui] {e}", file=sys.stderr)
            sys.exit(1)

    elif args.meeting_action == "status":
        status = manager.status()
        if status is None:
            print("No meeting currently recording.")
        else:
            print(f"🔴 Recording: {status['name']}")
            print(f"   ID: {status['meeting_id']}")
            duration = status["duration_seconds"]
            mins = int(duration // 60)
            secs = int(duration % 60)
            print(f"   Duration: {mins:02d}:{secs:02d}")
            print(f"   Words: {status['word_count']}")

    elif args.meeting_action == "list":
        meetings = manager.list_meetings(limit=args.limit)
        if not meetings:
            print("No past meetings found.")
        else:
            print(f"{'ID':<14} {'Name':<30} {'Date':<20} {'Duration':<10} {'Words':<8}")
            print("-" * 82)
            for m in meetings:
                mid = m.get("meeting_id", "?")[:12]
                name = (m.get("name", "")[:28] or "Untitled")
                start = m.get("start_time", "")[:19]
                dur = m.get("duration_seconds", 0)
                words = m.get("word_count", 0)
                mins = int(dur // 60)
                secs = int(dur % 60)
                print(f"{mid:<14} {name:<30} {start:<20} {mins:02d}:{secs:02d}     {words:<8}")

    elif args.meeting_action == "search":
        results = manager.search(args.keyword, limit=args.limit)
        if not results:
            print(f"No results for '{args.keyword}'.")
        else:
            for r in results:
                print(f"📋 {r['name'] or r['meeting_id']} ({r['match_count']} matches)")
                for line in r["matching_lines"]:
                    print(f"   {line}")
                print()


if __name__ == "__main__":
    main()
