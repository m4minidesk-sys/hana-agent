"""HANA daemon runner — macOS launchd background service.

This module provides daemon mode for HANA, running as a background
service managed by macOS launchd.  Windows Service support is
intentionally excluded from scope.
"""

from __future__ import annotations

import json
import logging
import os
import plistlib
import signal
import sys
import time
from pathlib import Path
from typing import Any

from strands import Agent

from hana.channels.slack_adapter import SlackAdapter
from hana.runtime.heartbeat import Heartbeat

logger = logging.getLogger(__name__)

LAUNCHD_LABEL = "com.hana.agent"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"


class DaemonRunner:
    """HANA daemon runner for macOS launchd.

    Manages the agent as a background service with:
    - Slack channel adapter
    - Heartbeat for periodic tasks
    - Graceful shutdown on SIGTERM/SIGINT
    - PID file management
    - launchd plist generation

    Args:
        agent: Configured Strands Agent instance.
        config: HANA configuration dictionary.
    """

    def __init__(self, agent: Agent, config: dict[str, Any]) -> None:
        self.agent = agent
        self.config = config
        self.pid_file = Path(config.get("workspace", {}).get("root", "~/.hana")).expanduser() / "hana.pid"
        self._slack: SlackAdapter | None = None
        self._heartbeat: Heartbeat | None = None
        self._running = False

    def run(self) -> None:
        """Start the daemon — blocks until terminated.

        Registers signal handlers, starts Slack adapter and heartbeat,
        then waits for a termination signal.
        """
        logger.info("HANA daemon starting (pid=%d)", os.getpid())

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Write PID file
        self._write_pid()

        self._running = True

        try:
            # Start heartbeat
            hb_config = self.config.get("heartbeat", {})
            if hb_config.get("enabled", False):
                self._heartbeat = Heartbeat(
                    config=self.config,
                    on_tick=self._on_heartbeat_tick,
                )
                self._heartbeat.start()

            # Start Slack adapter (blocking)
            slack_config = self.config.get("channels", {}).get("slack", {})
            if slack_config.get("enabled", False) and slack_config.get("bot_token"):
                self._slack = SlackAdapter(agent=self.agent, config=self.config)
                self._slack.run()  # Blocks
            else:
                # No Slack — just run heartbeat loop
                logger.info("No Slack configured — running heartbeat-only mode")
                while self._running:
                    time.sleep(1)

        except Exception as exc:
            logger.exception("Daemon error: %s", exc)
        finally:
            self._shutdown()

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Handle termination signals.

        Args:
            signum: Signal number.
            frame: Current stack frame.
        """
        sig_name = signal.Signals(signum).name
        logger.info("Received %s — shutting down", sig_name)
        self._running = False

    def _write_pid(self) -> None:
        """Write PID file for process management."""
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self.pid_file.write_text(str(os.getpid()))
        logger.info("PID file: %s", self.pid_file)

    def _on_heartbeat_tick(self, config: dict[str, Any]) -> None:
        """Heartbeat callback — runs periodic tasks.

        Args:
            config: HANA configuration dictionary.
        """
        logger.info("Heartbeat tick — running scheduled tasks")
        # Future: execute configured heartbeat tasks via the agent

    def _shutdown(self) -> None:
        """Clean shutdown — stop heartbeat, remove PID file."""
        logger.info("Daemon shutting down...")

        if self._heartbeat:
            self._heartbeat.stop()

        if self.pid_file.exists():
            self.pid_file.unlink()
            logger.info("Removed PID file")

        logger.info("Daemon shutdown complete")

    @staticmethod
    def generate_plist(
        config_path: str = "~/.hana/config.yaml",
        python_path: str | None = None,
        log_dir: str = "~/.hana/logs",
    ) -> str:
        """Generate a launchd plist for the HANA daemon.

        Args:
            config_path: Path to HANA config file.
            python_path: Path to Python interpreter (auto-detected if None).
            log_dir: Directory for log files.

        Returns:
            The path to the written plist file.
        """
        if python_path is None:
            python_path = sys.executable

        config_path_expanded = str(Path(config_path).expanduser())
        log_dir_expanded = str(Path(log_dir).expanduser())
        Path(log_dir_expanded).mkdir(parents=True, exist_ok=True)

        plist = {
            "Label": LAUNCHD_LABEL,
            "ProgramArguments": [
                python_path,
                "-m", "hana",
                "--daemon",
                "--config", config_path_expanded,
            ],
            "RunAtLoad": True,
            "KeepAlive": True,
            "StandardOutPath": f"{log_dir_expanded}/hana-stdout.log",
            "StandardErrorPath": f"{log_dir_expanded}/hana-stderr.log",
            "EnvironmentVariables": {
                "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
                "HOME": str(Path.home()),
            },
            "ThrottleInterval": 30,
        }

        PLIST_DIR.mkdir(parents=True, exist_ok=True)
        plist_path = PLIST_DIR / f"{LAUNCHD_LABEL}.plist"

        with open(plist_path, "wb") as f:
            plistlib.dump(plist, f)

        logger.info("Generated launchd plist: %s", plist_path)
        return str(plist_path)

    @staticmethod
    def install_service() -> str:
        """Install and load the launchd service.

        Returns:
            Status message.
        """
        plist_path = PLIST_DIR / f"{LAUNCHD_LABEL}.plist"

        if not plist_path.exists():
            return f"Plist not found at {plist_path} — run generate_plist first"

        # Load the service
        os.system(f"launchctl bootout gui/$(id -u) {plist_path} 2>/dev/null")
        result = os.system(f"launchctl bootstrap gui/$(id -u) {plist_path}")

        if result == 0:
            return f"Service installed and started: {LAUNCHD_LABEL}"
        else:
            return f"Failed to install service (exit code {result})"

    @staticmethod
    def uninstall_service() -> str:
        """Stop and unload the launchd service.

        Returns:
            Status message.
        """
        plist_path = PLIST_DIR / f"{LAUNCHD_LABEL}.plist"
        result = os.system(f"launchctl bootout gui/$(id -u) {plist_path} 2>/dev/null")

        if plist_path.exists():
            plist_path.unlink()

        return f"Service uninstalled: {LAUNCHD_LABEL}"
