"""Data models for meeting transcription.

No external dependencies — always importable.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MeetingStatus(str, Enum):
    """Meeting lifecycle states."""

    RECORDING = "recording"
    STOPPED = "stopped"
    GENERATING_MINUTES = "generating_minutes"
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class TranscriptChunk:
    """A single chunk of transcribed audio.

    Attributes:
        text: Transcribed text content.
        start_time: Offset from meeting start in seconds.
        end_time: End offset from meeting start in seconds.
        language: Detected language code (e.g. 'ja', 'en').
        confidence: Transcription confidence (0.0-1.0), if available.
        timestamp: Wall-clock time when this chunk was transcribed.
    """

    text: str
    start_time: float
    end_time: float
    language: str = "auto"
    confidence: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TranscriptChunk:
        """Create from dictionary."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Meeting:
    """Represents a single meeting recording session.

    Attributes:
        meeting_id: Unique identifier for this meeting.
        name: Human-readable meeting name.
        status: Current lifecycle state.
        start_time: When recording started (ISO format).
        stop_time: When recording stopped (ISO format), or None if still active.
        duration_seconds: Total recording duration.
        word_count: Total words transcribed so far.
        chunks: List of transcribed chunks.
        config_used: Config snapshot at meeting start.
        transcript_path: Path to transcript.md file.
        metadata_path: Path to metadata.json file.
    """

    meeting_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    status: MeetingStatus = MeetingStatus.RECORDING
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    stop_time: Optional[str] = None
    duration_seconds: float = 0.0
    word_count: int = 0
    chunks: list[TranscriptChunk] = field(default_factory=list)
    config_used: dict[str, Any] = field(default_factory=dict)
    transcript_path: Optional[str] = None
    metadata_path: Optional[str] = None

    def add_chunk(self, chunk: TranscriptChunk) -> None:
        """Append a transcript chunk and update word count."""
        self.chunks.append(chunk)
        self.word_count += len(chunk.text.split())

    def get_full_transcript(self) -> str:
        """Get concatenated transcript text."""
        return "\n".join(c.text for c in self.chunks if c.text.strip())

    def to_metadata(self) -> dict[str, Any]:
        """Serialize meeting metadata (without full chunk data)."""
        return {
            "meeting_id": self.meeting_id,
            "name": self.name,
            "status": self.status.value,
            "start_time": self.start_time,
            "stop_time": self.stop_time,
            "duration_seconds": self.duration_seconds,
            "word_count": self.word_count,
            "chunk_count": len(self.chunks),
            "config_used": self.config_used,
        }

    def save_metadata(self, path: Path) -> None:
        """Save metadata to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_metadata(), f, indent=2, ensure_ascii=False)

    def save_transcript(self, path: Path) -> None:
        """Save full transcript to markdown file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"# Meeting Transcript — {self.name or self.meeting_id}\n"]
        lines.append(f"**Started**: {self.start_time}\n")
        if self.stop_time:
            lines.append(f"**Ended**: {self.stop_time}\n")
        lines.append("---\n")
        for chunk in self.chunks:
            if chunk.text.strip():
                mins = int(chunk.start_time // 60)
                secs = int(chunk.start_time % 60)
                lines.append(f"[{mins:02d}:{secs:02d}] {chunk.text}\n")
        with open(path, "w") as f:
            f.write("\n".join(lines))

    @classmethod
    def from_metadata(cls, path: Path) -> Meeting:
        """Load meeting from metadata JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls(
            meeting_id=data["meeting_id"],
            name=data.get("name", ""),
            status=MeetingStatus(data.get("status", "completed")),
            start_time=data.get("start_time", ""),
            stop_time=data.get("stop_time"),
            duration_seconds=data.get("duration_seconds", 0.0),
            word_count=data.get("word_count", 0),
            config_used=data.get("config_used", {}),
            metadata_path=str(path),
        )


@dataclass
class MeetingConfig:
    """Meeting-specific configuration extracted from main config.

    Attributes:
        capture_method: Audio capture method ('screencapturekit' or 'blackhole').
        include_mic: Whether to mix microphone input.
        sample_rate: Audio sample rate in Hz (default 16000).
        channels: Number of audio channels (default 1 = mono).
        whisper_engine: Whisper engine to use ('mlx', 'cpp', 'faster').
        whisper_model: Model name (default 'large-v3-turbo').
        language: Language code or 'auto' for auto-detection.
        chunk_seconds: Audio chunk size for transcription (default 5).
        vad_enabled: Whether to skip silence via VAD.
        transcript_dir: Directory to save meeting files.
        output_format: Output format ('markdown' or 'json').
        save_audio: Whether to save raw audio WAV.
        retention_days: Auto-delete after N days (0 = never).
    """

    capture_method: str = "screencapturekit"
    include_mic: bool = True
    sample_rate: int = 16000
    channels: int = 1
    whisper_engine: str = "mlx"
    whisper_model: str = "large-v3-turbo"
    language: str = "auto"
    chunk_seconds: int = 5
    vad_enabled: bool = True
    transcript_dir: str = "~/.yui/meetings/"
    output_format: str = "markdown"
    save_audio: bool = False
    retention_days: int = 90

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> MeetingConfig:
        """Extract MeetingConfig from main Yui config dict."""
        meeting = config.get("meeting", {})
        audio = meeting.get("audio", {})
        whisper = meeting.get("whisper", {})
        output = meeting.get("output", {})

        return cls(
            capture_method=audio.get("capture_method", "screencapturekit"),
            include_mic=audio.get("include_mic", True),
            sample_rate=audio.get("sample_rate", 16000),
            channels=audio.get("channels", 1),
            whisper_engine=whisper.get("engine", "mlx"),
            whisper_model=whisper.get("model", "large-v3-turbo"),
            language=whisper.get("language", "auto"),
            chunk_seconds=whisper.get("chunk_seconds", 5),
            vad_enabled=whisper.get("vad_enabled", True),
            transcript_dir=output.get("transcript_dir", "~/.yui/meetings/"),
            output_format=output.get("format", "markdown"),
            save_audio=output.get("save_audio", False),
            retention_days=meeting.get("retention_days", 90),
        )

    def get_meeting_dir(self, meeting_id: str) -> Path:
        """Get the directory for a specific meeting."""
        base = Path(self.transcript_dir).expanduser()
        return base / meeting_id
