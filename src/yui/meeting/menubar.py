"""macOS Menu Bar UI for Yui Meeting.

Requires optional dependency: pip install yui-agent[ui]

Provides a status-bar icon with meeting controls:
  - 🎤 Idle / 🔴 Recording / ⏳ Generating / ✅ Completed
  - Start Meeting / Stop Meeting / Last Minutes / Settings / Quit
  - Recording elapsed time display
  - macOS native notifications
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Status icons
ICON_IDLE = "🎤"
ICON_RECORDING = "🔴"
ICON_GENERATING = "⏳"
ICON_COMPLETED = "✅"

# macOS notification sounds
NOTIFICATION_SOUND = "default"


def _check_rumps() -> None:
    """Check that rumps is available."""
    try:
        import rumps  # noqa: F401
    except ImportError:
        raise ImportError(
            "Menu bar feature requires 'rumps'. "
            "Install with: pip install yui-agent[ui]"
        )


class YuiMenuBarApp:
    """macOS menu bar application for meeting controls.

    Communicates with the Yui daemon via IPC (Unix socket).

    Args:
        ipc_client: Optional IPCClient instance for daemon communication.
        config: Optional config dict.
    """

    def __init__(
        self,
        ipc_client: Optional[Any] = None,
        config: Optional[dict[str, Any]] = None,
    ) -> None:
        _check_rumps()
        import rumps

        self._config = config or {}
        self._ipc = ipc_client
        self._recording = False
        self._recording_start: Optional[float] = None
        self._elapsed_seconds: float = 0.0
        self._status = "idle"  # idle / recording / generating / completed

        # Build rumps app
        self._app = rumps.App("Yui Meeting", title=ICON_IDLE)

        # Menu items
        self._start_item = rumps.MenuItem("Start Meeting", callback=self._on_start)
        self._stop_item = rumps.MenuItem("Stop Meeting", callback=self._on_stop)
        self._stop_item.set_callback(None)  # Disabled initially

        self._elapsed_item = rumps.MenuItem("⏱ --:--")
        self._elapsed_item.set_callback(None)  # Non-clickable display

        self._separator1 = rumps.separator

        self._last_minutes_item = rumps.MenuItem(
            "Last Minutes", callback=self._on_last_minutes
        )
        self._settings_item = rumps.MenuItem("Settings…", callback=self._on_settings)

        self._separator2 = rumps.separator

        self._quit_item = rumps.MenuItem("Quit Yui", callback=self._on_quit)

        self._app.menu = [
            self._start_item,
            self._stop_item,
            self._elapsed_item,
            self._separator1,
            self._last_minutes_item,
            self._settings_item,
            self._separator2,
            self._quit_item,
        ]

        # Timer for elapsed time updates
        self._timer: Optional[rumps.Timer] = None
        self._timer = rumps.Timer(self._update_elapsed, 1)

    @property
    def app(self) -> Any:
        """Return the underlying rumps.App."""
        return self._app

    @property
    def status(self) -> str:
        """Current app status: idle/recording/generating/completed."""
        return self._status

    @property
    def recording(self) -> bool:
        """Whether currently recording."""
        return self._recording

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed recording time in seconds."""
        return self._elapsed_seconds

    def _ensure_ipc(self) -> Any:
        """Lazily create IPC client if not injected."""
        if self._ipc is None:
            from yui.meeting.ipc import IPCClient
            self._ipc = IPCClient()
        return self._ipc

    def run(self) -> None:
        """Start the menu bar app (blocks)."""
        self._app.run()

    def set_status(self, status: str) -> None:
        """Update the menu bar status icon.

        Args:
            status: One of 'idle', 'recording', 'generating', 'completed'.
        """
        icon_map = {
            "idle": ICON_IDLE,
            "recording": ICON_RECORDING,
            "generating": ICON_GENERATING,
            "completed": ICON_COMPLETED,
        }
        self._status = status
        self._app.title = icon_map.get(status, ICON_IDLE)

        # Update menu item states
        if status == "recording":
            self._start_item.set_callback(None)
            self._stop_item.set_callback(self._on_stop)
        elif status in ("idle", "completed"):
            self._start_item.set_callback(self._on_start)
            self._stop_item.set_callback(None)
        else:  # generating
            self._start_item.set_callback(None)
            self._stop_item.set_callback(None)

    def _notify(self, title: str, message: str) -> None:
        """Send macOS notification.

        Args:
            title: Notification title.
            message: Notification body.
        """
        try:
            import rumps
            rumps.notification(
                title="Yui Meeting",
                subtitle=title,
                message=message,
                sound=True,
            )
        except Exception as e:
            logger.warning(f"Notification failed: {e}")

    def _on_start(self, _: Any = None) -> None:
        """Handle Start Meeting click."""
        try:
            ipc = self._ensure_ipc()
            response = ipc.meeting_start()

            if response.get("error"):
                self._notify("Error", response["error"])
                return

            self._recording = True
            self._recording_start = time.time()
            self._elapsed_seconds = 0.0
            self.set_status("recording")

            # Start elapsed timer
            if self._timer:
                self._timer.start()

            meeting_name = response.get("name", "Meeting")
            self._notify("Recording Started", f"🔴 {meeting_name}")

        except Exception as e:
            logger.error(f"Start meeting failed: {e}")
            self._notify("Error", f"Failed to start: {e}")

    def _on_stop(self, _: Any = None) -> None:
        """Handle Stop Meeting click."""
        try:
            # Stop timer first
            if self._timer:
                self._timer.stop()

            self.set_status("generating")
            self._notify("Stopping", "⏳ Generating meeting minutes…")

            ipc = self._ensure_ipc()
            response = ipc.meeting_stop()

            if response.get("error"):
                self._notify("Error", response["error"])
                self.set_status("idle")
                return

            self._recording = False
            self._recording_start = None
            self.set_status("completed")

            duration = response.get("duration_seconds", 0)
            words = response.get("word_count", 0)
            mins = int(duration // 60)
            secs = int(duration % 60)
            self._notify(
                "Meeting Complete",
                f"✅ {mins:02d}:{secs:02d} | {words} words",
            )

            # Reset to idle after a delay
            threading.Timer(5.0, lambda: self.set_status("idle")).start()

        except Exception as e:
            logger.error(f"Stop meeting failed: {e}")
            self._notify("Error", f"Failed to stop: {e}")
            self.set_status("idle")

    def _on_last_minutes(self, _: Any = None) -> None:
        """Handle Last Minutes click — open the most recent transcript."""
        try:
            transcript_dir = Path(
                self._config.get("meeting", {})
                .get("output", {})
                .get("transcript_dir", "~/.yui/meetings/")
            ).expanduser()

            if not transcript_dir.exists():
                self._notify("No Minutes", "No meeting minutes found.")
                return

            # Find most recent transcript
            transcripts = sorted(
                transcript_dir.glob("*/transcript.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            if not transcripts:
                self._notify("No Minutes", "No meeting transcripts found.")
                return

            # Open in default editor
            subprocess.Popen(["open", str(transcripts[0])])

        except Exception as e:
            logger.error(f"Open last minutes failed: {e}")
            self._notify("Error", f"Cannot open minutes: {e}")

    def _on_settings(self, _: Any = None) -> None:
        """Handle Settings click — open config file."""
        config_path = Path("~/.yui/config.yaml").expanduser()
        if config_path.exists():
            subprocess.Popen(["open", str(config_path)])
        else:
            self._notify("Settings", "Config file not found: ~/.yui/config.yaml")

    def _on_quit(self, _: Any = None) -> None:
        """Handle Quit click."""
        import rumps

        if self._recording:
            # Stop recording first
            try:
                self._on_stop()
            except Exception:
                pass

        if self._timer:
            self._timer.stop()

        rumps.quit_application()

    def _update_elapsed(self, _: Any = None) -> None:
        """Timer callback — update elapsed time display."""
        if self._recording and self._recording_start is not None:
            self._elapsed_seconds = time.time() - self._recording_start
            mins = int(self._elapsed_seconds // 60)
            secs = int(self._elapsed_seconds % 60)
            self._elapsed_item.title = f"⏱ {mins:02d}:{secs:02d}"


def create_launchd_plist() -> str:
    """Generate LaunchAgent plist content for auto-start.

    Returns:
        plist XML string.
    """
    import sys

    python_path = sys.executable
    module_path = "yui.meeting.menubar"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.yui.menubar</string>
    <key>ProgramArguments</key>
    <array>
        <string>{python_path}</string>
        <string>-m</string>
        <string>{module_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/tmp/yui-menubar.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/yui-menubar.stderr.log</string>
</dict>
</plist>"""


def install_launchd() -> Path:
    """Install LaunchAgent plist for auto-start on login.

    Returns:
        Path to the installed plist file.
    """
    plist_dir = Path("~/Library/LaunchAgents").expanduser()
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.yui.menubar.plist"

    plist_content = create_launchd_plist()
    plist_path.write_text(plist_content)

    # Load immediately
    subprocess.run(["launchctl", "load", str(plist_path)], check=False)

    return plist_path


def uninstall_launchd() -> bool:
    """Remove LaunchAgent plist.

    Returns:
        True if plist was found and removed.
    """
    plist_path = Path("~/Library/LaunchAgents/com.yui.menubar.plist").expanduser()

    if not plist_path.exists():
        return False

    # Unload first
    subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
    plist_path.unlink()
    return True


def run_menubar(config: Optional[dict[str, Any]] = None) -> None:
    """Entry point — create and run the menu bar app.

    Args:
        config: Optional Yui config dict.
    """
    app = YuiMenuBarApp(config=config)
    app.run()


if __name__ == "__main__":
    from yui.config import load_config

    cfg = load_config()
    run_menubar(cfg)
