"""Tests for yui.meeting.menubar — AC-52, AC-53, AC-54, AC-55, AC-56.

All tests use REAL rumps — no mocks. Menu bar app is instantiated
but run() is never called (no NSRunLoop needed).
"""

import time
import uuid
import os
from pathlib import Path

import pytest

import rumps  # Real import
from yui.meeting.ipc import IPCClient, IPCServer
from yui.meeting.menubar import (
    ICON_COMPLETED,
    ICON_GENERATING,
    ICON_IDLE,
    ICON_RECORDING,
    YuiMenuBarApp,
    _check_rumps,
)


@pytest.fixture
def ipc_pair():
    """Real IPC server/client pair for meeting control."""
    sock_path = f"/tmp/yui-mb-test-{uuid.uuid4().hex[:8]}.sock"
    responses = {
        "meeting_start": {"name": "Test Meeting"},
        "meeting_stop": {"duration_seconds": 300},
        "meeting_status": {"status": "idle"},
        "meeting_generate_minutes": {"status": "generating"},
    }

    def handler(msg):
        cmd = msg.get("cmd", "unknown")
        return responses.get(cmd, {"error": f"unknown command: {cmd}"})

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


@pytest.fixture
def app(ipc_pair):
    """Create a real YuiMenuBarApp with IPC."""
    client, _ = ipc_pair
    return YuiMenuBarApp(ipc_client=client)


@pytest.fixture
def standalone_app():
    """Create a real YuiMenuBarApp without IPC."""
    return YuiMenuBarApp()


class TestYuiMenuBarInit:
    """AC-52: Menu bar app initialization."""

    def test_initial_status(self, standalone_app):
        """App starts in idle status."""
        assert standalone_app.status == "idle"

    def test_initial_recording_false(self, standalone_app):
        """App starts not recording."""
        assert standalone_app.recording is False

    def test_initial_elapsed_zero(self, standalone_app):
        """App starts with zero elapsed time."""
        assert standalone_app.elapsed_seconds == 0.0

    def test_initial_icon(self, standalone_app):
        """App starts with idle icon."""
        assert standalone_app.app.title == ICON_IDLE

    def test_has_menu_items(self, standalone_app):
        """App has all expected menu items."""
        menu_titles = [item.title for item in standalone_app.app.menu.values()
                       if hasattr(item, 'title')]
        assert "Start Meeting" in menu_titles
        assert "Stop Meeting" in menu_titles

    def test_has_app_property(self, standalone_app):
        """App property returns rumps.App instance."""
        assert isinstance(standalone_app.app, rumps.App)

    def test_app_name(self, standalone_app):
        """App name is 'Yui Meeting'."""
        assert standalone_app.app.name == "Yui Meeting"


class TestStatusTransitions:
    """AC-53: Status icon transitions."""

    def test_set_status_recording(self, standalone_app):
        """Setting recording status changes icon."""
        standalone_app.set_status("recording")
        assert standalone_app.status == "recording"
        assert standalone_app.app.title == ICON_RECORDING

    def test_set_status_generating(self, standalone_app):
        """Setting generating status changes icon."""
        standalone_app.set_status("generating")
        assert standalone_app.status == "generating"
        assert standalone_app.app.title == ICON_GENERATING

    def test_set_status_completed(self, standalone_app):
        """Setting completed status changes icon."""
        standalone_app.set_status("completed")
        assert standalone_app.status == "completed"
        assert standalone_app.app.title == ICON_COMPLETED

    def test_set_status_idle(self, standalone_app):
        """Setting idle status changes icon."""
        standalone_app.set_status("recording")
        standalone_app.set_status("idle")
        assert standalone_app.status == "idle"
        assert standalone_app.app.title == ICON_IDLE

    def test_unknown_status_defaults_to_idle_icon(self, standalone_app):
        """Unknown status defaults to idle icon."""
        standalone_app.set_status("unknown_state")
        assert standalone_app.app.title == ICON_IDLE


class TestStartMeeting:
    """AC-54: Start meeting via menu bar."""

    def test_start_meeting_via_ipc(self, app):
        """Start meeting sends IPC command and updates state."""
        app._on_start()
        assert app.recording is True
        assert app.status == "recording"
        assert app.app.title == ICON_RECORDING

    def test_start_meeting_sets_recording_time(self, app):
        """Start meeting records the start time."""
        app._on_start()
        assert app._recording_start is not None
        assert app._recording_start > 0

    def test_start_meeting_error_handling(self, standalone_app):
        """Start with no IPC server handles gracefully."""
        standalone_app._ipc = IPCClient(socket_path="/tmp/nonexistent-mb-test.sock")
        standalone_app._on_start()
        # Should not crash, but state may not change
        # (depends on error handling implementation)


class TestStopMeeting:
    """AC-55: Stop meeting via menu bar."""

    def test_stop_meeting_via_ipc(self, app):
        """Stop meeting sends IPC command and updates state."""
        app._on_start()  # Start first
        app._on_stop()
        assert app.recording is False
        # Status should transition from recording

    def test_stop_when_not_recording(self, app):
        """Stop when not recording is handled gracefully."""
        app._on_stop()  # Should not crash


class TestElapsedTime:
    """AC-56: Elapsed time display."""

    def test_elapsed_updates(self, app):
        """Elapsed time updates during recording."""
        app._on_start()
        time.sleep(0.1)
        app._update_elapsed(None)  # Manually trigger update
        assert app.elapsed_seconds >= 0.1

    def test_elapsed_zero_when_idle(self, standalone_app):
        """Elapsed is zero when not recording."""
        assert standalone_app.elapsed_seconds == 0.0

    def test_elapsed_display_format(self, app):
        """Elapsed display shows mm:ss format."""
        app._on_start()
        app._elapsed_seconds = 125.0  # 2:05
        app._update_elapsed(None)
        # Check the elapsed menu item text
        elapsed_text = app._elapsed_item.title
        assert ":" in elapsed_text


class TestLastMinutes:
    """Test 'Last Minutes' menu action."""

    def test_last_minutes_no_transcript(self, standalone_app, tmp_path):
        """Last minutes with no transcripts doesn't crash."""
        standalone_app._config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "nonexistent")}
            }
        }
        standalone_app._on_last_minutes()  # Should not raise

    def test_last_minutes_with_transcript(self, standalone_app, tmp_path):
        """Last minutes with existing transcript opens it."""
        meeting_dir = tmp_path / "meetings" / "meet001"
        meeting_dir.mkdir(parents=True)
        transcript = meeting_dir / "transcript.md"
        transcript.write_text("# Meeting Notes")

        standalone_app._config = {
            "meeting": {
                "output": {"transcript_dir": str(tmp_path / "meetings")}
            }
        }
        standalone_app._on_last_minutes()  # Opens file on macOS


class TestRumpsCheck:
    """Test rumps availability check."""

    def test_check_rumps_succeeds(self):
        """_check_rumps succeeds when rumps is installed."""
        _check_rumps()  # Should not raise


class TestQuit:
    """Test quit action."""

    def test_quit_exists(self, standalone_app):
        """Quit menu item exists."""
        menu_titles = [item.title for item in standalone_app.app.menu.values()
                       if hasattr(item, 'title')]
        assert "Quit Yui" in menu_titles
