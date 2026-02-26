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

    # Workshop subcommand (AC-82, AC-85)
    workshop_parser = subparsers.add_parser("workshop", help="Workshop testing")
    workshop_sub = workshop_parser.add_subparsers(dest="workshop_action", help="Workshop actions")

    ws_test_parser = workshop_sub.add_parser("test", help="Run a workshop test")
    ws_test_parser.add_argument("url", help="Workshop URL to test")
    ws_test_parser.add_argument("--record", action="store_true", help="Record video")
    ws_test_parser.add_argument("--cleanup", action="store_true", default=None, help="Cleanup AWS resources")
    ws_test_parser.add_argument("--no-cleanup", action="store_true", help="Skip resource cleanup")
    ws_test_parser.add_argument("--headed", action="store_true", help="Run browser in headed mode")
    ws_test_parser.add_argument("--dry-run", action="store_true", help="Plan steps without executing")
    ws_test_parser.add_argument("--steps", help="Step range (e.g. 1-5 or 1,3,5)")
    ws_test_parser.add_argument("--cron", action="store_true", help="Regression mode for periodic testing")

    ws_list_parser = workshop_sub.add_parser("list-tests", help="List past test runs")
    ws_list_parser.add_argument("--limit", type=int, default=20, help="Max results")

    ws_show_parser = workshop_sub.add_parser("show-report", help="Show a test report")
    ws_show_parser.add_argument("test_id", help="Test ID to show")

    # MCP subcommand
    mcp_parser = subparsers.add_parser("mcp", help="Manage MCP server connections")
    mcp_sub = mcp_parser.add_subparsers(dest="mcp_action", help="MCP actions")

    mcp_sub.add_parser("list", help="List configured MCP servers and their status")

    mcp_connect_parser = mcp_sub.add_parser("connect", help="Connect to an MCP server")
    mcp_connect_parser.add_argument("name", help="Server name from config")

    mcp_disconnect_parser = mcp_sub.add_parser("disconnect", help="Disconnect from an MCP server")
    mcp_disconnect_parser.add_argument("name", help="Server name to disconnect")

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

    # Handle workshop commands (AC-82 through AC-85)
    if args.command == "workshop":
        _handle_workshop(args, config)
        return

    # Handle MCP commands
    if args.command == "mcp":
        _handle_mcp(args, config)
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


def _handle_mcp(args: argparse.Namespace, config: dict) -> None:
    """Handle MCP subcommands."""
    if not args.mcp_action:
        print("Usage: yui mcp {list|connect|disconnect}", file=sys.stderr)
        sys.exit(1)

    from yui.tools.mcp_integration import (
        MCPConfigError,
        MCPConnectionError,
        MCPManager,
        connect_mcp_servers,
    )

    if args.mcp_action == "list":
        manager = MCPManager()
        mcp_config = config.get("mcp", {})
        try:
            manager.load_configs(mcp_config)
        except MCPConfigError as e:
            print(f"[yui] MCP config error: {e}", file=sys.stderr)
            sys.exit(1)

        servers = manager.list_servers()
        if not servers:
            print("No MCP servers configured.")
            print("Add servers to ~/.yui/config.yaml under 'mcp.servers'.")
            return

        print(f"{'Name':<20} {'Transport':<15} {'Auto':<8} {'Endpoint':<40}")
        print("-" * 83)
        for srv in servers:
            name = srv["name"][:18]
            transport = srv["transport"]
            auto = "yes" if srv["auto_connect"] else "no"
            endpoint = ""
            if srv.get("command"):
                endpoint = " ".join(srv["command"])[:38]
            elif srv.get("url"):
                endpoint = srv["url"][:38]
            print(f"{name:<20} {transport:<15} {auto:<8} {endpoint:<40}")

    elif args.mcp_action == "connect":
        manager = connect_mcp_servers(config)
        name = args.name
        try:
            manager.connect(name)
            print(f"✅ Connected to MCP server '{name}'")
        except MCPConfigError as e:
            print(f"[yui] {e}", file=sys.stderr)
            sys.exit(1)
        except MCPConnectionError as e:
            print(f"[yui] Connection failed: {e}", file=sys.stderr)
            sys.exit(1)
        finally:
            manager.disconnect_all()

    elif args.mcp_action == "disconnect":
        # For CLI disconnect, we inform the user but actual disconnect
        # only applies to a running agent process
        print(f"ℹ️  Disconnect is only applicable to a running agent process.")
        print(f"   Server '{args.name}' will be disconnected on next agent restart.")


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


def _handle_workshop(args: argparse.Namespace, config: dict) -> None:
    """Handle workshop subcommands (AC-82 through AC-85)."""
    if not args.workshop_action:
        print("Usage: yui workshop {test|list-tests|show-report}", file=sys.stderr)
        sys.exit(1)

    from yui.workshop.runner import WorkshopTestRunner

    runner = WorkshopTestRunner(config)

    if args.workshop_action == "test":
        import asyncio

        options: dict = {
            "dry_run": args.dry_run,
            "record": args.record,
            "headed": args.headed,
            "steps": args.steps,
            "cron": getattr(args, "cron", False),
        }
        if args.no_cleanup:
            options["cleanup"] = False
        elif args.cleanup is True:
            options["cleanup"] = True

        if args.dry_run:
            print("\U0001f50d Dry-run mode \u2014 planning steps without execution")
        if getattr(args, "cron", False):
            print("\U0001f504 Regression mode (cron) \u2014 automated periodic test")

        print(f"\U0001f680 Starting workshop test: {args.url}")
        test_run = asyncio.run(runner.run_test(args.url, options))

        from yui.workshop.reporter import WorkshopReporter
        reporter = WorkshopReporter()
        print()
        print(reporter.generate_slack_summary(test_run))

    elif args.workshop_action == "list-tests":
        tests = runner.list_tests()
        if not tests:
            print("No test runs found.")
            return

        limit = getattr(args, "limit", 20)
        tests = tests[:limit]

        hdr_tid = "Test ID"
        hdr_mod = "Modified"
        hdr_sz = "Size"
        print(f"{hdr_tid:<20} {hdr_mod:<25} {hdr_sz:<10}")
        print("-" * 55)
        for t in tests:
            tid = t["test_id"]
            mod = t["modified"][:19]
            sz = t["size"]
            print(f"{tid:<20} {mod:<25} {sz:<10}")

    elif args.workshop_action == "show-report":
        report_content = runner.show_report(args.test_id)
        if report_content is None:
            print(f"Report not found for test ID: {args.test_id}", file=sys.stderr)
            sys.exit(1)
        print(report_content)



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
