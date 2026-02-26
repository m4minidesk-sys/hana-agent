"""Tests for yui.meeting.hotkeys — AC-59, AC-60, AC-61.

Global hotkey tests use mocked pynput — no actual key listening.
"""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest


# Mock pynput before importing hotkeys
@pytest.fixture(autouse=True)
def mock_pynput(monkeypatch):
    """Mock pynput module for all tests."""
    mock_module = MagicMock()
    mock_keyboard = MagicMock()
    mock_module.keyboard = mock_keyboard

    # GlobalHotKeys mock
    mock_global_hotkeys = MagicMock()
    mock_global_hotkeys_instance = MagicMock()
    mock_global_hotkeys.return_value = mock_global_hotkeys_instance
    mock_keyboard.GlobalHotKeys = mock_global_hotkeys

    import sys
    monkeypatch.setitem(sys.modules, "pynput", mock_module)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", mock_keyboard)

    return mock_module


class TestHotkeyConfig:
    """AC-60: Hotkey configuration from config.yaml."""

    def test_default_config(self, mock_pynput):
        """Default config has correct key bindings."""
        from yui.meeting.hotkeys import HotkeyConfig

        config = HotkeyConfig()
        assert config.enabled is True
        assert config.toggle_recording == "<cmd>+<shift>+r"
        assert config.stop_generate == "<cmd>+<shift>+s"
        assert config.open_minutes == "<cmd>+<shift>+m"

    def test_from_config_default(self, mock_pynput):
        """from_config returns defaults when no hotkeys section."""
        from yui.meeting.hotkeys import HotkeyConfig

        config = HotkeyConfig.from_config({})
        assert config.enabled is True
        assert config.toggle_recording == "<cmd>+<shift>+r"

    def test_from_config_custom(self, mock_pynput):
        """from_config reads custom bindings."""
        from yui.meeting.hotkeys import HotkeyConfig

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

    def test_from_config_partial(self, mock_pynput):
        """from_config with partial config uses defaults for missing fields."""
        from yui.meeting.hotkeys import HotkeyConfig

        config = HotkeyConfig.from_config({
            "meeting": {
                "hotkeys": {
                    "enabled": False,
                }
            }
        })
        assert config.enabled is False
        assert config.toggle_recording == "<cmd>+<shift>+r"  # default


class TestGlobalHotkeysInit:
    """AC-59: GlobalHotkeys initialization."""

    def test_init_default(self, mock_pynput):
        """GlobalHotkeys initializes with defaults."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys()
        assert not hk.is_running
        assert hk.hotkey_config.enabled is True

    def test_init_with_config(self, mock_pynput):
        """GlobalHotkeys reads config."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys(config={
            "meeting": {"hotkeys": {"enabled": False}}
        })
        assert hk.hotkey_config.enabled is False


class TestGlobalHotkeysStartStop:
    """AC-59: Start/stop hotkey listener."""

    def test_start_creates_listener(self, mock_pynput):
        """Start creates and starts pynput GlobalHotKeys listener."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys()
        hk.start()

        assert hk.is_running
        mock_pynput.keyboard.GlobalHotKeys.assert_called_once()
        mock_pynput.keyboard.GlobalHotKeys.return_value.start.assert_called_once()

    def test_start_registers_correct_hotkeys(self, mock_pynput):
        """Start registers the configured hotkey combos."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys()
        hk.start()

        call_args = mock_pynput.keyboard.GlobalHotKeys.call_args
        hotkey_map = call_args[0][0]  # First positional arg

        assert "<cmd>+<shift>+r" in hotkey_map
        assert "<cmd>+<shift>+s" in hotkey_map
        assert "<cmd>+<shift>+m" in hotkey_map

    def test_start_disabled_does_nothing(self, mock_pynput):
        """Start does nothing when hotkeys disabled in config."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys(config={
            "meeting": {"hotkeys": {"enabled": False}}
        })
        hk.start()

        assert not hk.is_running
        mock_pynput.keyboard.GlobalHotKeys.assert_not_called()

    def test_stop(self, mock_pynput):
        """Stop stops the listener."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys()
        hk.start()
        hk.stop()

        assert not hk.is_running
        mock_pynput.keyboard.GlobalHotKeys.return_value.stop.assert_called_once()

    def test_stop_when_not_started(self, mock_pynput):
        """Stop when not started doesn't crash."""
        from yui.meeting.hotkeys import GlobalHotkeys

        hk = GlobalHotkeys()
        hk.stop()  # Should not raise
        assert not hk.is_running


class TestGlobalHotkeysCallbacks:
    """AC-61: Hotkey actions."""

    def test_toggle_recording_starts(self, mock_pynput):
        """Toggle recording starts when not recording."""
        from yui.meeting.hotkeys import GlobalHotkeys

        mock_ipc = MagicMock()
        mock_ipc.meeting_status.return_value = {"status": "idle"}
        mock_ipc.meeting_start.return_value = {"name": "Meeting"}

        hk = GlobalHotkeys(ipc_client=mock_ipc)
        hk._default_toggle()

        mock_ipc.meeting_start.assert_called_once()

    def test_toggle_recording_stops(self, mock_pynput):
        """Toggle recording stops when recording."""
        from yui.meeting.hotkeys import GlobalHotkeys

        mock_ipc = MagicMock()
        mock_ipc.meeting_status.return_value = {"status": "recording"}
        mock_ipc.meeting_stop.return_value = {"duration_seconds": 300}

        hk = GlobalHotkeys(ipc_client=mock_ipc)
        hk._default_toggle()

        mock_ipc.meeting_stop.assert_called_once()

    def test_stop_generate(self, mock_pynput):
        """Stop+generate calls both stop and generate minutes."""
        from yui.meeting.hotkeys import GlobalHotkeys

        mock_ipc = MagicMock()
        mock_ipc.meeting_stop.return_value = {"duration_seconds": 300}
        mock_ipc.meeting_generate_minutes.return_value = {"status": "generating"}

        hk = GlobalHotkeys(ipc_client=mock_ipc)
        hk._default_stop_generate()

        mock_ipc.meeting_stop.assert_called_once()
        mock_ipc.meeting_generate_minutes.assert_called_once()

    @patch("yui.meeting.hotkeys.subprocess.Popen")
    def test_open_minutes(self, mock_popen, mock_pynput, tmp_path):
        """Open minutes opens the latest transcript file."""
        from yui.meeting.hotkeys import GlobalHotkeys

        # Create fake transcript
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

        mock_popen.assert_called_once_with(["open", str(transcript)])

    def test_open_minutes_no_transcripts(self, mock_pynput, tmp_path):
        """Open minutes handles missing transcripts gracefully."""
        from yui.meeting.hotkeys import GlobalHotkeys

        config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "nonexistent")},
            }
        }

        hk = GlobalHotkeys(config=config)
        hk._default_open_minutes()  # Should not raise

    def test_custom_callbacks(self, mock_pynput):
        """Custom callbacks override defaults."""
        from yui.meeting.hotkeys import GlobalHotkeys

        toggle_called = []
        stop_called = []
        open_called = []

        hk = GlobalHotkeys(
            on_toggle_recording=lambda: toggle_called.append(True),
            on_stop_generate=lambda: stop_called.append(True),
            on_open_minutes=lambda: open_called.append(True),
        )
        hk.start()

        # Get registered callbacks from the GlobalHotKeys call
        call_args = mock_pynput.keyboard.GlobalHotKeys.call_args
        hotkey_map = call_args[0][0]

        # Invoke callbacks
        hotkey_map["<cmd>+<shift>+r"]()
        hotkey_map["<cmd>+<shift>+s"]()
        hotkey_map["<cmd>+<shift>+m"]()

        assert toggle_called == [True]
        assert stop_called == [True]
        assert open_called == [True]

    def test_toggle_handles_ipc_error(self, mock_pynput):
        """Toggle handles IPC errors gracefully."""
        from yui.meeting.hotkeys import GlobalHotkeys

        mock_ipc = MagicMock()
        mock_ipc.meeting_status.side_effect = Exception("Connection refused")

        hk = GlobalHotkeys(ipc_client=mock_ipc)
        hk._default_toggle()  # Should not raise


class TestHotkeyImportError:
    """Test graceful handling when pynput is not installed."""

    def test_check_pynput_raises_without_pynput(self, monkeypatch):
        """_check_pynput raises ImportError with guidance."""
        import sys

        monkeypatch.delitem(sys.modules, "pynput", raising=False)

        with patch.dict(sys.modules, {"pynput": None}):
            from yui.meeting.hotkeys import _check_pynput

            with pytest.raises(ImportError, match="pip install yui-agent"):
                _check_pynput()


class TestConfigIntegration:
    """Test hotkey config integration with default config."""

    def test_default_config_has_hotkeys(self, mock_pynput):
        """DEFAULT_CONFIG includes hotkeys section."""
        from yui.config import DEFAULT_CONFIG

        assert "hotkeys" in DEFAULT_CONFIG["meeting"]
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["enabled"] is True
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["toggle_recording"] == "<cmd>+<shift>+r"
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["stop_generate"] == "<cmd>+<shift>+s"
        assert DEFAULT_CONFIG["meeting"]["hotkeys"]["open_minutes"] == "<cmd>+<shift>+m"
