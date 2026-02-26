"""Global hotkeys for Yui Meeting.

Requires optional dependency: pip install yui-agent[hotkey]

Default bindings (configurable in config.yaml):
  - ⌘⇧R: Toggle recording (start/stop)
  - ⌘⇧S: Stop + generate minutes
  - ⌘⇧M: Open latest minutes

Can be enabled/disabled via config.yaml:
  meeting:
    hotkeys:
      enabled: true
"""

from __future__ import annotations

import logging
import subprocess
import threading
from pathlib import Path
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _check_pynput() -> None:
    """Check that pynput is available."""
    try:
        import pynput  # noqa: F401
    except ImportError:
        raise ImportError(
            "Global hotkeys require 'pynput'. "
            "Install with: pip install yui-agent[hotkey]"
        )


class HotkeyConfig:
    """Hotkey configuration extracted from config.yaml.

    Attributes:
        enabled: Whether hotkeys are active.
        toggle_recording: Key combo for toggle recording (default: ⌘⇧R).
        stop_generate: Key combo for stop + generate (default: ⌘⇧S).
        open_minutes: Key combo for open latest minutes (default: ⌘⇧M).
    """

    def __init__(
        self,
        enabled: bool = True,
        toggle_recording: str = "<cmd>+<shift>+r",
        stop_generate: str = "<cmd>+<shift>+s",
        open_minutes: str = "<cmd>+<shift>+m",
    ) -> None:
        self.enabled = enabled
        self.toggle_recording = toggle_recording
        self.stop_generate = stop_generate
        self.open_minutes = open_minutes

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> HotkeyConfig:
        """Extract hotkey config from main config dict.

        Args:
            config: Main Yui config dict.

        Returns:
            HotkeyConfig instance.
        """
        hotkeys = config.get("meeting", {}).get("hotkeys", {})
        return cls(
            enabled=hotkeys.get("enabled", True),
            toggle_recording=hotkeys.get(
                "toggle_recording", "<cmd>+<shift>+r"
            ),
            stop_generate=hotkeys.get("stop_generate", "<cmd>+<shift>+s"),
            open_minutes=hotkeys.get("open_minutes", "<cmd>+<shift>+m"),
        )


class GlobalHotkeys:
    """Global hotkey listener for meeting controls.

    Uses pynput to listen for keyboard shortcuts and dispatch actions
    via IPC to the daemon or directly to a callback.

    Args:
        config: Main Yui config dict.
        ipc_client: Optional IPCClient for daemon communication.
        on_toggle_recording: Optional callback for toggle recording.
        on_stop_generate: Optional callback for stop + generate.
        on_open_minutes: Optional callback for open minutes.
    """

    def __init__(
        self,
        config: Optional[dict[str, Any]] = None,
        ipc_client: Optional[Any] = None,
        on_toggle_recording: Optional[Callable[[], None]] = None,
        on_stop_generate: Optional[Callable[[], None]] = None,
        on_open_minutes: Optional[Callable[[], None]] = None,
    ) -> None:
        _check_pynput()

        self._config = config or {}
        self._hotkey_config = HotkeyConfig.from_config(self._config)
        self._ipc = ipc_client
        self._listener: Any = None  # pynput.keyboard.GlobalHotKeys
        self._running = False

        # Callbacks
        self._on_toggle_recording = on_toggle_recording or self._default_toggle
        self._on_stop_generate = on_stop_generate or self._default_stop_generate
        self._on_open_minutes = on_open_minutes or self._default_open_minutes

    @property
    def is_running(self) -> bool:
        """Check if hotkey listener is active."""
        return self._running

    @property
    def hotkey_config(self) -> HotkeyConfig:
        """Return the hotkey configuration."""
        return self._hotkey_config

    def _ensure_ipc(self) -> Any:
        """Lazily create IPC client if not injected."""
        if self._ipc is None:
            from yui.meeting.ipc import IPCClient
            self._ipc = IPCClient()
        return self._ipc

    def start(self) -> None:
        """Start listening for global hotkeys.

        Does nothing if hotkeys are disabled in config.
        """
        if not self._hotkey_config.enabled:
            logger.info("Global hotkeys disabled in config")
            return

        from pynput.keyboard import GlobalHotKeys

        hotkey_map = {
            self._hotkey_config.toggle_recording: self._on_toggle_recording,
            self._hotkey_config.stop_generate: self._on_stop_generate,
            self._hotkey_config.open_minutes: self._on_open_minutes,
        }

        self._listener = GlobalHotKeys(hotkey_map)
        self._listener.start()
        self._running = True
        logger.info("Global hotkeys started")

    def stop(self) -> None:
        """Stop listening for global hotkeys."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._running = False
        logger.info("Global hotkeys stopped")

    def _default_toggle(self) -> None:
        """Default toggle recording via IPC."""
        try:
            ipc = self._ensure_ipc()
            status = ipc.meeting_status()

            if status.get("status") == "recording":
                ipc.meeting_stop()
                logger.info("Hotkey: stopped recording")
            else:
                ipc.meeting_start()
                logger.info("Hotkey: started recording")
        except Exception as e:
            logger.error(f"Hotkey toggle failed: {e}")

    def _default_stop_generate(self) -> None:
        """Default stop + generate minutes via IPC."""
        try:
            ipc = self._ensure_ipc()
            ipc.meeting_stop()
            ipc.meeting_generate_minutes()
            logger.info("Hotkey: stop + generate minutes")
        except Exception as e:
            logger.error(f"Hotkey stop+generate failed: {e}")

    def _default_open_minutes(self) -> None:
        """Default open latest minutes file."""
        try:
            transcript_dir = Path(
                self._config.get("meeting", {})
                .get("output", {})
                .get("transcript_dir", "~/.yui/meetings/")
            ).expanduser()

            if not transcript_dir.exists():
                logger.warning("No meetings directory found")
                return

            transcripts = sorted(
                transcript_dir.glob("*/transcript.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )

            if not transcripts:
                logger.warning("No meeting transcripts found")
                return

            subprocess.Popen(["open", str(transcripts[0])])
            logger.info(f"Hotkey: opened {transcripts[0]}")

        except Exception as e:
            logger.error(f"Hotkey open minutes failed: {e}")
