"""Meeting transcription package for Yui.

Provides audio capture, Whisper transcription, meeting lifecycle management,
menu bar UI, global hotkeys, and IPC communication.
Requires optional dependencies: pip install yui-agent[meeting,ui,hotkey]
"""

__all__ = [
    "MeetingManager",
    "AudioRecorder",
    "WhisperTranscriber",
    "Meeting",
    "TranscriptChunk",
    "MeetingConfig",
    "IPCServer",
    "IPCClient",
    "YuiMenuBarApp",
    "GlobalHotkeys",
    "post_meeting_minutes",
    "real_time_analysis",
]


def _check_meeting_deps() -> None:
    """Check that meeting optional dependencies are installed."""
    missing = []
    try:
        import numpy  # noqa: F401
    except ImportError:
        missing.append("numpy")
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        missing.append("sounddevice")
    try:
        import mlx_whisper  # noqa: F401
    except ImportError:
        missing.append("mlx-whisper")

    if missing:
        raise ImportError(
            f"Meeting feature requires additional packages: {', '.join(missing)}. "
            "Install them with: pip install yui-agent[meeting]"
        )


# Models are always available (no extra deps)
from yui.meeting.models import Meeting, MeetingConfig, TranscriptChunk  # noqa: E402

# Manager is always importable (guards deps internally via lazy init)
from yui.meeting.manager import MeetingManager  # noqa: E402


def __getattr__(name: str):
    """Lazy import for AudioRecorder, WhisperTranscriber, and optional UI/IPC.

    These require extra dependencies, so only import on access.
    """
    if name == "AudioRecorder":
        from yui.meeting.recorder import AudioRecorder
        return AudioRecorder
    if name == "WhisperTranscriber":
        from yui.meeting.transcriber import WhisperTranscriber
        return WhisperTranscriber
    if name == "IPCServer":
        from yui.meeting.ipc import IPCServer
        return IPCServer
    if name == "IPCClient":
        from yui.meeting.ipc import IPCClient
        return IPCClient
    if name == "YuiMenuBarApp":
        from yui.meeting.menubar import YuiMenuBarApp
        return YuiMenuBarApp
    if name == "GlobalHotkeys":
        from yui.meeting.hotkeys import GlobalHotkeys
        return GlobalHotkeys
    if name == "post_meeting_minutes":
        from yui.meeting.minutes import post_meeting_minutes
        return post_meeting_minutes
    if name == "real_time_analysis":
        from yui.meeting.minutes import real_time_analysis
        return real_time_analysis
    raise AttributeError(f"module 'yui.meeting' has no attribute {name!r}")
