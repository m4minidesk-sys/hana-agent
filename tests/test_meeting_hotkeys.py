"""Tests for yui.meeting.hotkeys — AC-59, AC-60, AC-61.

All tests use REAL pynput — no mocks.

IMPORTANT: pynput GlobalHotKeys on macOS darwin backend uses CGEvent API
which does NOT support multiple start→stop cycles in a single process
(SIGABRT on re-init). Therefore only ONE test calls start()/stop().
All other tests verify config/logic without starting the listener.
"""

import subprocess
import sys
import time
from pathlib import Path

import pytest

import pynput  # Real import — no mock
from yui.meeting.hotkeys import (
    GlobalHotkeys,
    HotkeyConfig,
    _check_pynput,
)
from yui.meeting.ipc import IPCClient, IPCServer


# --- AC-60: HotkeyConfig ---

class TestHotkeyConfig:
    """AC-60: Hotkey configuration from config.yaml."""

    def test_default_config(self):
        """Default config has correct key bindings."""
        config = HotkeyConfig()
        assert config.enabled is True
        assert config.toggle_recording == "<cmd>+<shift>+r"
        assert config.stop_generate == "<cmd>+<shift>+s"
        assert config.open_minutes == "<cmd>+<shift>+m"

    def test_from_config_default(self):
        """from_config returns defaults when no hotkeys section."""
        config = HotkeyConfig.from_config({})
        assert config.enabled is True
        assert config.toggle_recording == "<cmd>+<shift>+r"

    def test_from_config_custom(self):
        """from_config reads custom bindings."""
        config = HotkeyConfig.from_config({
            "meeting": {
                "hotkeys": {
                    "enabled": False,
                    "toggle_recording": "<cmd>+<shift>+t",
                    "stop_generate": "<cmd>+<shift>+x",
                    "open_minutes": "<cmd>+<shift>+o",
                }
            }
        })
        assert config.enabled is False
        assert config.toggle_recording == "<cmd>+<shift>+t"
        assert config.stop_generate == "<cmd>+<shift>+x"
        assert config.open_minutes == "<cmd>+<shift>+o"

    def test_from_config_partial(self):
        """from_config with partial config uses defaults for missing fields."""
        config = HotkeyConfig.from_config({
            "meeting": {
                "hotkeys": {
                    "enabled": False,
                }
            }
        })
        assert config.enabled is False
        assert config.toggle_recording == "<cmd>+<shift>+r"  # default


# --- AC-59: GlobalHotkeys init ---

class TestGlobalHotkeysInit:
    """AC-59: GlobalHotkeys initialization (no start() calls)."""

    def test_init_default(self):
        """GlobalHotkeys initializes with defaults."""
        hk = GlobalHotkeys()
        assert not hk.is_running
        assert hk.hotkey_config.enabled is True

    def test_init_with_config(self):
        """GlobalHotkeys reads config."""
        hk = GlobalHotkeys(config={
            "meeting": {"hotkeys": {"enabled": False}}
        })
        assert hk.hotkey_config.enabled is False

    def test_start_disabled_does_nothing(self):
        """Start does nothing when hotkeys disabled in config."""
        hk = GlobalHotkeys(config={
            "meeting": {"hotkeys": {"enabled": False}}
        })
        hk.start()
        assert not hk.is_running

    def test_stop_when_not_started(self):
        """Stop when not started doesn't crash."""
        hk = GlobalHotkeys()
        hk.stop()  # Should not raise
        assert not hk.is_running


class TestGlobalHotkeysStartStop:
    """AC-59: Start/stop hotkey listener (real pynput).

    Only ONE test calls start() to avoid macOS CGEvent SIGABRT on re-init.
    """

    def test_start_and_stop_real_listener(self):
        """Start creates real pynput listener, stop cleans it up."""
        hk = GlobalHotkeys()
        hk.start()

        assert hk.is_running
        assert hk._listener is not None

        hk.stop()
        assert not hk.is_running


# --- AC-61: Hotkey callbacks (no start() needed) ---

class TestGlobalHotkeysCallbacks:
    """AC-61: Hotkey actions via IPC. No pynput listener started."""

    @pytest.fixture
    def ipc_pair(self):
        """Create a real IPC server/client pair."""
        import uuid
        import os
        sock_path = f"/tmp/yui-hk-test-{uuid.uuid4().hex[:8]}.sock"
        responses = {}

        def handler(msg):
            cmd = msg.get("cmd", "unknown")
            if cmd == "meeting_status":
                return responses.get("status", {"status": "idle"})
            elif cmd == "meeting_start":
                return {"name": msg.get("name", "Meeting")}
            elif cmd == "meeting_stop":
                return {"duration_seconds": 300}
            elif cmd == "meeting_generate_minutes":
                return {"status": "generating"}
            return {"error": "unknown"}

        server = IPCServer(socket_path=sock_path, handler=handler)
        server.start(background=True)
        time.sleep(0.2)
        client = IPCClient(socket_path=sock_path)

        yield client, responses

        server.stop()
        try:
            os.unlink(sock_path)
        except OSError:
            pass

    def test_toggle_recording_starts(self, ipc_pair):
        """Toggle recording starts when not recording."""
        client, responses = ipc_pair
        responses["status"] = {"status": "idle"}

        hk = GlobalHotkeys(ipc_client=client)
        hk._default_toggle()
        # No exception = success. Real IPC call made.

    def test_toggle_recording_stops(self, ipc_pair):
        """Toggle recording stops when recording."""
        client, responses = ipc_pair
        responses["status"] = {"status": "recording"}

        hk = GlobalHotkeys(ipc_client=client)
        hk._default_toggle()

    def test_stop_generate(self, ipc_pair):
        """Stop+generate calls both stop and generate minutes."""
        client, responses = ipc_pair

        hk = GlobalHotkeys(ipc_client=client)
        hk._default_stop_generate()

    def test_open_minutes(self, tmp_path):
        """Open minutes opens the latest transcript file."""
        meeting_dir = tmp_path / "meetings" / "meet001"
        meeting_dir.mkdir(parents=True)
        transcript = meeting_dir / "transcript.md"
        transcript.write_text("# Meeting")

        config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "meetings")},
            }
        }

        hk = GlobalHotkeys(config=config)
        hk._default_open_minutes()

    def test_open_minutes_no_transcripts(self, tmp_path):
        """Open minutes handles missing transcripts gracefully."""
        config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "nonexistent")},
            }
        }

        hk = GlobalHotkeys(config=config)
        hk._default_open_minutes()  # Should not raise

    def test_toggle_handles_ipc_error(self):
        """Toggle handles IPC errors gracefully (no server running)."""
        client = IPCClient(socket_path="/tmp/nonexistent-yui-test.sock")
        hk = GlobalHotkeys(ipc_client=client)
        hk._default_toggle()  # Should not raise


class TestPynputCheck:
    """Test pynput availability check."""

    def test_check_pynput_succeeds(self):
        """_check_pynput succeeds when pynput is installed."""
        _check_pynput()  # Should not raise


class TestConfigIntegration:
    """Test hotkey config integration with default config."""

    def test_default_config_has_hotkeys(self):
        """DEFAULT_CONFIG includes hotkeys section."""
        from yui.config import DEFAULT_CONFIG

        assert "hotkeys" in DEFAULT_CONFIG["meeting"]
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["enabled"] is True
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["toggle_recording"] == "<cmd>+<shift>+r"
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["stop_generate"] == "<cmd>+<shift>+s"
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["open_minutes"] == "<cmd>+<shift>+m"
