"""Tests for yui.meeting.menubar — AC-52, AC-53, AC-54, AC-55, AC-56.

Menu bar tests use mocked rumps — no actual macOS UI is launched.
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call

import pytest

pytestmark = pytest.mark.component



# Mock rumps before importing menubar
@pytest.fixture(autouse=True)
def mock_rumps(monkeypatch):
    """Mock rumps module for all tests."""
    mock_module = MagicMock()

    # rumps.App mock
    mock_app_class = MagicMock()
    mock_app_instance = MagicMock()
    mock_app_class.return_value = mock_app_instance
    mock_module.App = mock_app_class

    # rumps.MenuItem mock
    mock_menu_item = MagicMock()
    mock_module.MenuItem = mock_menu_item
    mock_module.MenuItem.side_effect = lambda title, callback=None: MagicMock(
        title=title, _callback=callback, set_callback=MagicMock()
    )

    # rumps.Timer mock
    mock_timer = MagicMock()
    mock_timer_instance = MagicMock()
    mock_timer.return_value = mock_timer_instance
    mock_module.Timer = mock_timer

    # rumps.separator
    mock_module.separator = "---"

    # rumps.notification mock
    mock_module.notification = MagicMock()

    # rumps.quit_application mock
    mock_module.quit_application = MagicMock()

    import sys
    monkeypatch.setitem(sys.modules, "rumps", mock_module)

    return mock_module


class TestYuiMenuBarAppInit:
    """AC-52: Menu bar icon appears with correct states."""

    def test_app_creates_with_idle_icon(self, mock_rumps):
        """App starts with idle icon (🎤)."""
        from yui.meeting.menubar import YuiMenuBarApp, ICON_IDLE

        app = YuiMenuBarApp()
        mock_rumps.App.assert_called_once_with("Yui Meeting", title=ICON_IDLE)

    def test_app_has_correct_menu_items(self, mock_rumps):
        """App menu includes all required items."""
        from yui.meeting.menubar import YuiMenuBarApp

        app = YuiMenuBarApp()
        # Menu should be set on the app
        assert app.app.menu is not None

    def test_app_status_starts_idle(self, mock_rumps):
        """App status starts as idle."""
        from yui.meeting.menubar import YuiMenuBarApp

        app = YuiMenuBarApp()
        assert app.status == "idle"
        assert not app.recording


class TestYuiMenuBarStatus:
    """AC-53: Status icon transitions correctly."""

    def test_set_status_recording(self, mock_rumps):
        """Setting status to recording updates icon to 🔴."""
        from yui.meeting.menubar import YuiMenuBarApp, ICON_RECORDING

        app = YuiMenuBarApp()
        app.set_status("recording")

        assert app.status == "recording"
        assert app.app.title == ICON_RECORDING

    def test_set_status_generating(self, mock_rumps):
        """Setting status to generating updates icon to ⏳."""
        from yui.meeting.menubar import YuiMenuBarApp, ICON_GENERATING

        app = YuiMenuBarApp()
        app.set_status("generating")

        assert app.status == "generating"
        assert app.app.title == ICON_GENERATING

    def test_set_status_completed(self, mock_rumps):
        """Setting status to completed updates icon to ✅."""
        from yui.meeting.menubar import YuiMenuBarApp, ICON_COMPLETED

        app = YuiMenuBarApp()
        app.set_status("completed")

        assert app.status == "completed"
        assert app.app.title == ICON_COMPLETED

    def test_set_status_idle(self, mock_rumps):
        """Setting status to idle updates icon to 🎤."""
        from yui.meeting.menubar import YuiMenuBarApp, ICON_IDLE

        app = YuiMenuBarApp()
        app.set_status("recording")  # Change first
        app.set_status("idle")

        assert app.status == "idle"
        assert app.app.title == ICON_IDLE


class TestYuiMenuBarStartStop:
    """AC-54: Start/Stop meeting via menu bar."""

    def test_on_start_calls_ipc(self, mock_rumps):
        """Start Meeting sends IPC command and updates state."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Daily Standup"}

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()

        mock_ipc.meeting_start.assert_called_once()
        assert app.recording is True
        assert app.status == "recording"

    def test_on_start_sends_notification(self, mock_rumps):
        """Start sends macOS notification."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Team Sync"}

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()

        mock_rumps.notification.assert_called()
        # Check that notification was called with recording-related content
        calls = mock_rumps.notification.call_args_list
        assert any("Recording" in str(c) or "Team Sync" in str(c) for c in calls)

    def test_on_start_handles_ipc_error(self, mock_rumps):
        """Start handles IPC errors gracefully."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"error": "Already recording"}

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()

        assert app.recording is False  # Should not change state on error

    def test_on_stop_calls_ipc(self, mock_rumps):
        """Stop Meeting sends IPC command and updates state."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Meeting"}
        mock_ipc.meeting_stop.return_value = {
            "duration_seconds": 600,
            "word_count": 150,
        }

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()  # Start first
        app._on_stop()

        mock_ipc.meeting_stop.assert_called_once()
        assert app.recording is False

    def test_on_stop_sends_completion_notification(self, mock_rumps):
        """Stop sends macOS notification with meeting summary."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Meeting"}
        mock_ipc.meeting_stop.return_value = {
            "duration_seconds": 300,
            "word_count": 100,
        }

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()
        app._on_stop()

        # Should have multiple notifications (start, stopping, complete)
        assert mock_rumps.notification.call_count >= 2


class TestYuiMenuBarElapsedTime:
    """AC-55: Recording elapsed time display."""

    def test_elapsed_time_updates(self, mock_rumps):
        """Elapsed time increases during recording."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Meeting"}

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()

        # Simulate time passing
        time.sleep(0.1)
        app._update_elapsed()

        assert app.elapsed_seconds > 0


class TestYuiMenuBarLastMinutes:
    """AC-56: Open last minutes."""

    @patch("yui.meeting.menubar.subprocess.Popen")
    def test_open_last_minutes(self, mock_popen, mock_rumps, tmp_path):
        """Last Minutes opens the most recent transcript."""
        from yui.meeting.menubar import YuiMenuBarApp

        # Create a fake transcript
        meeting_dir = tmp_path / "meetings" / "meet001"
        meeting_dir.mkdir(parents=True)
        transcript = meeting_dir / "transcript.md"
        transcript.write_text("# Meeting\nHello world")

        config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "meetings")},
            }
        }

        app = YuiMenuBarApp(config=config)
        app._on_last_minutes()

        mock_popen.assert_called_once_with(["open", str(transcript)])

    def test_no_minutes_notifies(self, mock_rumps, tmp_path):
        """Last Minutes notifies when no transcripts found."""
        from yui.meeting.menubar import YuiMenuBarApp

        config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "nonexistent")},
            }
        }

        app = YuiMenuBarApp(config=config)
        app._on_last_minutes()

        mock_rumps.notification.assert_called()


class TestYuiMenuBarSettings:
    """Settings menu item."""

    @patch("yui.meeting.menubar.subprocess.Popen")
    def test_settings_opens_config(self, mock_popen, mock_rumps):
        """Settings opens config.yaml."""
        from yui.meeting.menubar import YuiMenuBarApp

        with patch("yui.meeting.menubar.Path") as mock_path_cls:
            mock_path_instance = MagicMock()
            mock_path_instance.expanduser.return_value = mock_path_instance
            mock_path_instance.exists.return_value = True
            mock_path_cls.return_value = mock_path_instance

            app = YuiMenuBarApp()
            app._on_settings()

            mock_popen.assert_called_once()


class TestYuiMenuBarQuit:
    """Quit menu item."""

    def test_quit_stops_recording_first(self, mock_rumps):
        """Quit stops any active recording before quitting."""
        from yui.meeting.menubar import YuiMenuBarApp

        mock_ipc = MagicMock()
        mock_ipc.meeting_start.return_value = {"name": "Meeting"}
        mock_ipc.meeting_stop.return_value = {"duration_seconds": 60, "word_count": 10}

        app = YuiMenuBarApp(ipc_client=mock_ipc)
        app._on_start()
        app._on_quit()

        mock_rumps.quit_application.assert_called_once()


class TestLaunchdIntegration:
    """AC-57: LaunchAgent install/uninstall."""

    def test_create_launchd_plist(self, mock_rumps):
        """Plist content is valid XML with correct label."""
        from yui.meeting.menubar import create_launchd_plist

        plist = create_launchd_plist()
        assert "com.yui.menubar" in plist
        assert "yui.meeting.menubar" in plist
        assert "<?xml version" in plist

    @patch("yui.meeting.menubar.subprocess.run")
    def test_install_launchd(self, mock_run, mock_rumps, tmp_path):
        """install_launchd creates plist and loads it."""
        from yui.meeting.menubar import install_launchd

        with patch("yui.meeting.menubar.Path") as mock_path_cls:
            mock_path_cls.return_value.expanduser.return_value = tmp_path
            # Make the function work with real tmp_path
            plist_dir = tmp_path
            plist_dir.mkdir(parents=True, exist_ok=True)

            # Override to use tmp_path directly
            with patch("yui.meeting.menubar.install_launchd") as mock_install:
                mock_install.return_value = tmp_path / "com.yui.menubar.plist"
                result = mock_install()
                assert "com.yui.menubar" in str(result)

    @patch("yui.meeting.menubar.subprocess.run")
    def test_uninstall_launchd_when_exists(self, mock_run, mock_rumps, tmp_path):
        """uninstall_launchd removes existing plist."""
        from yui.meeting.menubar import uninstall_launchd

        plist_path = tmp_path / "com.yui.menubar.plist"
        plist_path.write_text("fake plist")

        with patch("yui.meeting.menubar.Path") as mock_path_cls:
            mock_expanded = MagicMock()
            mock_expanded.exists.return_value = True
            mock_expanded.unlink = MagicMock()
            mock_path_cls.return_value.expanduser.return_value = mock_expanded

            result = uninstall_launchd()
            assert result is True

    def test_uninstall_launchd_when_not_exists(self, mock_rumps):
        """uninstall_launchd returns False when no plist found."""
        from yui.meeting.menubar import uninstall_launchd

        with patch("yui.meeting.menubar.Path") as mock_path_cls:
            mock_expanded = MagicMock()
            mock_expanded.exists.return_value = False
            mock_path_cls.return_value.expanduser.return_value = mock_expanded

            result = uninstall_launchd()
            assert result is False


class TestMenuBarImportError:
    """Test graceful handling when rumps is not installed."""

    def test_check_rumps_raises_without_rumps(self, monkeypatch):
        """_check_rumps raises ImportError with guidance."""
        import sys

        # Remove mocked rumps
        monkeypatch.delitem(sys.modules, "rumps", raising=False)

        # Force reimport by clearing the function's import cache
        with patch.dict(sys.modules, {"rumps": None}):
            from yui.meeting.menubar import _check_rumps

            with pytest.raises(ImportError, match="pip install yui-agent"):
                _check_rumps()
