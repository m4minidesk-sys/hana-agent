"""Meeting lifecycle management.

Orchestrates AudioRecorder + WhisperTranscriber to provide
start/stop/status/list/search functionality.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from yui.meeting.models import (
    Meeting,
    MeetingConfig,
    MeetingStatus,
    TranscriptChunk,
)

logger = logging.getLogger(__name__)


class MeetingError(Exception):
    """Base exception for meeting operations."""


class MeetingAlreadyRecordingError(MeetingError):
    """E-18: Raised when trying to start a meeting while one is already recording."""


class MeetingNotRecordingError(MeetingError):
    """Raised when trying to stop while no meeting is recording."""


class AudioDeviceError(MeetingError):
    """E-17: Audio device not found."""


class PermissionDeniedError(MeetingError):
    """E-15: Screen Recording permission denied."""


class MeetingManager:
    """Manages meeting recording lifecycle.

    Coordinates AudioRecorder and WhisperTranscriber to provide
    a high-level start/stop/status/list/search API.

    Args:
        config: Main Yui config dict.
        recorder: Optional AudioRecorder instance (DI for testing).
        transcriber: Optional WhisperTranscriber instance (DI for testing).
    """

    def __init__(
        self,
        config: dict[str, Any],
        recorder: Optional[Any] = None,
        transcriber: Optional[Any] = None,
    ) -> None:
        self._config = config
        self._meeting_config = MeetingConfig.from_config(config)
        self._recorder = recorder
        self._transcriber = transcriber
        self._current_meeting: Optional[Meeting] = None
        self._transcription_thread: Optional[threading.Thread] = None
        self._running = False

    def _ensure_recorder(self) -> Any:
        """Lazily create AudioRecorder if not injected."""
        if self._recorder is None:
            from yui.meeting.recorder import AudioRecorder

            self._recorder = AudioRecorder(
                sample_rate=self._meeting_config.sample_rate,
                channels=self._meeting_config.channels,
                chunk_seconds=self._meeting_config.chunk_seconds,
            )
        return self._recorder

    def _ensure_transcriber(self) -> Any:
        """Lazily create WhisperTranscriber if not injected."""
        if self._transcriber is None:
            from yui.meeting.transcriber import WhisperTranscriber

            model_map = {
                "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
                "large-v3": "mlx-community/whisper-large-v3",
                "medium": "mlx-community/whisper-medium",
                "small": "mlx-community/whisper-small",
                "base": "mlx-community/whisper-base",
            }
            model_name = self._meeting_config.whisper_model
            model = model_map.get(model_name, model_name)

            self._transcriber = WhisperTranscriber(
                model=model,
                language=self._meeting_config.language,
                vad_enabled=self._meeting_config.vad_enabled,
            )
        return self._transcriber

    def start(self, name: str = "") -> Meeting:
        """Start a new meeting recording.

        Args:
            name: Optional human-readable name for the meeting.

        Returns:
            Meeting object for the new meeting.

        Raises:
            MeetingAlreadyRecordingError: If a meeting is already in progress (E-18).
        """
        if self._current_meeting and self._running:
            raise MeetingAlreadyRecordingError(
                "A meeting is already in progress. "
                f"Meeting ID: {self._current_meeting.meeting_id}. "
                "Stop it first with `yui meeting stop`."
            )

        # Create meeting
        meeting = Meeting(
            name=name or f"Meeting {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            config_used=self._meeting_config.__dict__,
        )

        # Prepare output directory
        meeting_dir = self._meeting_config.get_meeting_dir(meeting.meeting_id)
        meeting_dir.mkdir(parents=True, exist_ok=True)
        meeting.transcript_path = str(meeting_dir / "transcript.md")
        meeting.metadata_path = str(meeting_dir / "metadata.json")

        # Start recording
        recorder = self._ensure_recorder()
        try:
            recorder.start()
        except ImportError:
            raise
        except RuntimeError as e:
            raise AudioDeviceError(f"Failed to start audio capture: {e}") from e
        except Exception as e:
            raise AudioDeviceError(
                f"Audio device error: {e}. "
                "Check your audio settings and permissions."
            ) from e

        self._current_meeting = meeting
        self._running = True

        # Start transcription in background
        self._transcription_thread = threading.Thread(
            target=self._transcription_loop,
            daemon=True,
            name="yui-transcription",
        )
        self._transcription_thread.start()

        # Save initial metadata
        meeting.save_metadata(Path(meeting.metadata_path))

        logger.info(
            f"Meeting started: {meeting.meeting_id} ({meeting.name})"
        )
        return meeting

    def stop(self) -> Meeting:
        """Stop the current meeting recording.

        Returns:
            The completed Meeting object.

        Raises:
            MeetingNotRecordingError: If no meeting is in progress.
        """
        if not self._current_meeting or not self._running:
            raise MeetingNotRecordingError(
                "No meeting is currently recording. "
                "Start one with `yui meeting start`."
            )

        meeting = self._current_meeting
        self._running = False

        # Stop recorder
        recorder = self._ensure_recorder()
        recorder.stop()

        # Wait for transcription thread to finish
        if self._transcription_thread:
            self._transcription_thread.join(timeout=10.0)
            self._transcription_thread = None

        # Finalize meeting
        meeting.status = MeetingStatus.STOPPED
        meeting.stop_time = datetime.now().isoformat()
        if meeting.start_time:
            start = datetime.fromisoformat(meeting.start_time)
            stop = datetime.fromisoformat(meeting.stop_time)
            meeting.duration_seconds = (stop - start).total_seconds()

        # Save final transcript and metadata
        if meeting.transcript_path:
            meeting.save_transcript(Path(meeting.transcript_path))
        if meeting.metadata_path:
            meeting.save_metadata(Path(meeting.metadata_path))

        logger.info(
            f"Meeting stopped: {meeting.meeting_id} "
            f"({meeting.duration_seconds:.0f}s, {meeting.word_count} words)"
        )

        self._current_meeting = None
        return meeting

    def status(self) -> Optional[dict[str, Any]]:
        """Get current meeting status.

        Returns:
            Dict with meeting info, or None if no meeting active.
        """
        if not self._current_meeting:
            return None

        meeting = self._current_meeting
        recorder = self._recorder

        return {
            "meeting_id": meeting.meeting_id,
            "name": meeting.name,
            "status": meeting.status.value,
            "start_time": meeting.start_time,
            "duration_seconds": recorder.elapsed_seconds if recorder else 0.0,
            "word_count": meeting.word_count,
            "chunk_count": len(meeting.chunks),
        }

    def list_meetings(self, limit: int = 20) -> list[dict[str, Any]]:
        """List past meetings from the transcript directory.

        Args:
            limit: Maximum number of meetings to return.

        Returns:
            List of meeting metadata dicts, sorted by start_time descending.
        """
        meetings_dir = Path(self._meeting_config.transcript_dir).expanduser()
        if not meetings_dir.exists():
            return []

        meetings = []
        for meta_path in meetings_dir.glob("*/metadata.json"):
            try:
                with open(meta_path) as f:
                    meta = json.load(f)
                meetings.append(meta)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to read {meta_path}: {e}")
                continue

        # Sort by start_time descending
        meetings.sort(key=lambda m: m.get("start_time", ""), reverse=True)
        return meetings[:limit]

    def search(self, keyword: str, limit: int = 20) -> list[dict[str, Any]]:
        """Search across meeting transcripts for a keyword.

        Args:
            keyword: Search term (case-insensitive).
            limit: Maximum results to return.

        Returns:
            List of dicts with meeting_id, name, matching_lines.
        """
        meetings_dir = Path(self._meeting_config.transcript_dir).expanduser()
        if not meetings_dir.exists():
            return []

        keyword_lower = keyword.lower()
        results = []

        for transcript_path in meetings_dir.glob("*/transcript.md"):
            try:
                content = transcript_path.read_text()
            except OSError:
                continue

            matching_lines = [
                line.strip()
                for line in content.split("\n")
                if keyword_lower in line.lower()
            ]

            if matching_lines:
                # Try to load metadata
                meta_path = transcript_path.parent / "metadata.json"
                meeting_id = transcript_path.parent.name
                name = ""
                if meta_path.exists():
                    try:
                        with open(meta_path) as f:
                            meta = json.load(f)
                        meeting_id = meta.get("meeting_id", meeting_id)
                        name = meta.get("name", "")
                    except (json.JSONDecodeError, OSError):
                        pass

                results.append({
                    "meeting_id": meeting_id,
                    "name": name,
                    "matching_lines": matching_lines[:5],  # Limit preview lines
                    "match_count": len(matching_lines),
                })

        results.sort(key=lambda r: r["match_count"], reverse=True)
        return results[:limit]

    def _transcription_loop(self) -> None:
        """Background loop: pull audio chunks → transcribe → append to meeting."""
        recorder = self._ensure_recorder()
        transcriber = self._ensure_transcriber()
        chunk_index = 0

        while self._running:
            chunk = recorder.get_chunk(timeout=1.0)
            if chunk is None:
                continue

            chunk_start = chunk_index * self._meeting_config.chunk_seconds
            chunk_index += 1

            result = transcriber.transcribe_chunk(
                audio_data=chunk,
                sample_rate=self._meeting_config.sample_rate,
                chunk_start_time=chunk_start,
            )

            if result and self._current_meeting:
                self._current_meeting.add_chunk(result)
                logger.debug(
                    f"Chunk {chunk_index}: [{result.start_time:.1f}s] {result.text[:50]}..."
                )

        # Process remaining chunks after stop
        while True:
            chunk = recorder.get_chunk(timeout=0.5)
            if chunk is None:
                break

            chunk_start = chunk_index * self._meeting_config.chunk_seconds
            chunk_index += 1

            result = transcriber.transcribe_chunk(
                audio_data=chunk,
                sample_rate=self._meeting_config.sample_rate,
                chunk_start_time=chunk_start,
            )

            if result and self._current_meeting:
                self._current_meeting.add_chunk(result)
