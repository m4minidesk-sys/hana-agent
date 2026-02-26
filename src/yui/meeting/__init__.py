"""Meeting transcription package for Yui.

Provides audio capture, Whisper transcription, and meeting lifecycle management.
Requires optional dependencies: pip install yui-agent[meeting]
"""

__all__ = [
    "MeetingManager",
    "AudioRecorder",
    "WhisperTranscriber",
    "Meeting",
    "TranscriptChunk",
    "MeetingConfig",
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
    """Lazy import for AudioRecorder and WhisperTranscriber.

    These require numpy/sounddevice/mlx-whisper, so only import on access.
    """
    if name == "AudioRecorder":
        from yui.meeting.recorder import AudioRecorder
        return AudioRecorder
    if name == "WhisperTranscriber":
        from yui.meeting.transcriber import WhisperTranscriber
        return WhisperTranscriber
    raise AttributeError(f"module 'yui.meeting' has no attribute {name!r}")
