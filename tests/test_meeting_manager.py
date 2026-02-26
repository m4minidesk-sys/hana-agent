"""Tests for yui.meeting.manager — AC-40, AC-41, AC-48, AC-49, AC-51.

Uses mock recorder/transcriber (DI) — no real audio/ML needed.
"""

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from yui.meeting.manager import (
    MeetingAlreadyRecordingError,
    MeetingManager,
    MeetingNotRecordingError,
)
from yui.meeting.models import MeetingStatus, TranscriptChunk


class MockRecorder:
    """Mock AudioRecorder for testing."""

    def __init__(self, chunks=None):
        self._chunks = list(chunks or [])
        self._chunk_index = 0
        self._running = False
        self._start_time = 0.0

    def start(self):
        self._running = True
        self._start_time = time.time()

    def stop(self):
        self._running = False

    def get_chunk(self, timeout=1.0):
        if self._chunk_index < len(self._chunks):
            chunk = self._chunks[self._chunk_index]
            self._chunk_index += 1
            return chunk
        return None

    @property
    def is_recording(self):
        return self._running

    @property
    def elapsed_seconds(self):
        if not self._running:
            return 0.0
        return time.time() - self._start_time


class MockTranscriber:
    """Mock WhisperTranscriber for testing."""

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self._call_index = 0

    def transcribe_chunk(self, audio_data, sample_rate=16000, chunk_start_time=0.0):
        if self._call_index < len(self._responses):
            resp = self._responses[self._call_index]
            self._call_index += 1
            return resp
        return None


def make_config(tmp_path):
    """Create a test config with tmp transcript dir."""
    return {
        "meeting": {
            "audio": {
                "capture_method": "screencapturekit",
                "include_mic": True,
                "sample_rate": 16000,
                "channels": 1,
            },
            "whisper": {
                "engine": "mlx",
                "model": "large-v3-turbo",
                "language": "auto",
                "chunk_seconds": 5,
                "vad_enabled": True,
            },
            "output": {
                "transcript_dir": str(tmp_path / "meetings"),
                "format": "markdown",
                "save_audio": False,
            },
            "retention_days": 90,
        }
    }


class TestMeetingManagerStart:
    """AC-40: yui meeting start begins audio capture and Whisper transcription."""

    def test_start_creates_meeting(self, tmp_path):
        """Start creates a Meeting with correct initial state."""
        config = make_config(tmp_path)
        chunks = [np.random.randn(16000, 1).astype(np.float32)]
        responses = [
            TranscriptChunk(text="Hello", start_time=0.0, end_time=5.0)
        ]
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(chunks=chunks),
            transcriber=MockTranscriber(responses=responses),
        )

        meeting = manager.start(name="Test Meeting")
        assert meeting.name == "Test Meeting"
        assert meeting.status == MeetingStatus.RECORDING
        assert meeting.meeting_id
        time.sleep(0.5)  # Let transcription thread work
        manager.stop()

    def test_start_creates_output_directory(self, tmp_path):
        """Start creates the meeting output directory."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        meeting = manager.start()
        meeting_dir = tmp_path / "meetings" / meeting.meeting_id
        assert meeting_dir.exists()
        manager.stop()

    def test_start_saves_initial_metadata(self, tmp_path):
        """Start saves metadata.json."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        meeting = manager.start()
        meta_path = tmp_path / "meetings" / meeting.meeting_id / "metadata.json"
        assert meta_path.exists()

        meta = json.loads(meta_path.read_text())
        assert meta["meeting_id"] == meeting.meeting_id
        assert meta["status"] == "recording"
        manager.stop()

    def test_start_raises_if_already_recording(self, tmp_path):
        """E-18: Starting while recording raises MeetingAlreadyRecordingError."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        manager.start()
        with pytest.raises(MeetingAlreadyRecordingError):
            manager.start()
        manager.stop()


class TestMeetingManagerStop:
    """AC-41: yui meeting stop stops recording."""

    def test_stop_finalizes_meeting(self, tmp_path):
        """Stop sets status and timestamps."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        manager.start()
        time.sleep(0.3)
        meeting = manager.stop()

        # Status is COMPLETED because auto-minutes generation runs on stop
        assert meeting.status == MeetingStatus.COMPLETED
        assert meeting.stop_time is not None
        assert meeting.duration_seconds > 0

    def test_stop_saves_transcript(self, tmp_path):
        """Stop saves transcript.md."""
        config = make_config(tmp_path)
        chunks = [np.random.randn(16000, 1).astype(np.float32)]
        responses = [
            TranscriptChunk(text="Hello from test", start_time=0.0, end_time=5.0)
        ]
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(chunks=chunks),
            transcriber=MockTranscriber(responses=responses),
        )

        meeting = manager.start()
        time.sleep(0.5)
        meeting = manager.stop()

        transcript_path = tmp_path / "meetings" / meeting.meeting_id / "transcript.md"
        assert transcript_path.exists()

    def test_stop_saves_final_metadata(self, tmp_path):
        """Stop updates metadata.json with final state."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        meeting = manager.start()
        time.sleep(0.3)
        meeting = manager.stop()

        meta_path = tmp_path / "meetings" / meeting.meeting_id / "metadata.json"
        meta = json.loads(meta_path.read_text())
        # Status is "completed" because auto-minutes generation runs on stop
        assert meta["status"] == "completed"
        assert meta["stop_time"] is not None

    def test_stop_raises_if_not_recording(self, tmp_path):
        """Stopping when not recording raises MeetingNotRecordingError."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        with pytest.raises(MeetingNotRecordingError):
            manager.stop()


class TestMeetingManagerStatus:
    """Meeting status API."""

    def test_status_when_recording(self, tmp_path):
        """Status returns meeting info during recording."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        manager.start(name="Status Test")
        status = manager.status()

        assert status is not None
        assert status["name"] == "Status Test"
        assert status["status"] == "recording"
        assert "meeting_id" in status
        manager.stop()

    def test_status_when_not_recording(self, tmp_path):
        """Status returns None when no meeting active."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        assert manager.status() is None


class TestMeetingManagerList:
    """AC-48: yui meeting list shows past meeting transcripts."""

    def test_list_empty(self, tmp_path):
        """List returns empty when no meetings exist."""
        config = make_config(tmp_path)
        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        assert manager.list_meetings() == []

    def test_list_returns_past_meetings(self, tmp_path):
        """List returns metadata of past meetings."""
        config = make_config(tmp_path)

        # Create fake past meetings
        meetings_dir = tmp_path / "meetings"
        for i, name in enumerate(["Meeting A", "Meeting B"]):
            mid = f"meet{i:04d}"
            (meetings_dir / mid).mkdir(parents=True)
            meta = {
                "meeting_id": mid,
                "name": name,
                "start_time": f"2026-02-26T{10+i}:00:00",
                "duration_seconds": 300 + i * 100,
                "word_count": 50 + i * 10,
                "status": "completed",
            }
            (meetings_dir / mid / "metadata.json").write_text(json.dumps(meta))

        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(),
            transcriber=MockTranscriber(),
        )

        results = manager.list_meetings()
        assert len(results) == 2
        # Sorted by start_time descending
        assert results[0]["name"] == "Meeting B"
        assert results[1]["name"] == "Meeting A"

    def test_list_respects_limit(self, tmp_path):
        """List respects limit parameter."""
        config = make_config(tmp_path)
        meetings_dir = tmp_path / "meetings"

        for i in range(5):
            mid = f"meet{i:04d}"
            (meetings_dir / mid).mkdir(parents=True)
            meta = {"meeting_id": mid, "name": f"M{i}", "start_time": f"2026-02-26T{10+i}:00:00"}
            (meetings_dir / mid / "metadata.json").write_text(json.dumps(meta))

        manager = MeetingManager(config=config, recorder=MockRecorder(), transcriber=MockTranscriber())
        results = manager.list_meetings(limit=3)
        assert len(results) == 3


class TestMeetingManagerSearch:
    """AC-49: yui meeting search searches across meeting transcripts."""

    def test_search_no_meetings(self, tmp_path):
        """Search returns empty when no meetings exist."""
        config = make_config(tmp_path)
        manager = MeetingManager(config=config, recorder=MockRecorder(), transcriber=MockTranscriber())
        assert manager.search("keyword") == []

    def test_search_finds_matches(self, tmp_path):
        """Search finds keyword in transcripts."""
        config = make_config(tmp_path)
        meetings_dir = tmp_path / "meetings"

        # Create meeting with transcript
        mid = "search001"
        (meetings_dir / mid).mkdir(parents=True)
        (meetings_dir / mid / "transcript.md").write_text(
            "# Transcript\n[00:00] We discussed the deployment strategy.\n"
            "[00:05] The deployment will happen on Friday.\n"
        )
        (meetings_dir / mid / "metadata.json").write_text(
            json.dumps({"meeting_id": mid, "name": "Deploy Discussion"})
        )

        manager = MeetingManager(config=config, recorder=MockRecorder(), transcriber=MockTranscriber())
        results = manager.search("deployment")

        assert len(results) == 1
        assert results[0]["meeting_id"] == mid
        assert results[0]["match_count"] == 2

    def test_search_case_insensitive(self, tmp_path):
        """Search is case-insensitive."""
        config = make_config(tmp_path)
        meetings_dir = tmp_path / "meetings"

        mid = "search002"
        (meetings_dir / mid).mkdir(parents=True)
        (meetings_dir / mid / "transcript.md").write_text("[00:00] KAFKA is the choice.\n")
        (meetings_dir / mid / "metadata.json").write_text(
            json.dumps({"meeting_id": mid, "name": "Tech Choice"})
        )

        manager = MeetingManager(config=config, recorder=MockRecorder(), transcriber=MockTranscriber())
        results = manager.search("kafka")
        assert len(results) == 1

    def test_search_no_match(self, tmp_path):
        """Search returns empty when keyword not found."""
        config = make_config(tmp_path)
        meetings_dir = tmp_path / "meetings"

        mid = "search003"
        (meetings_dir / mid).mkdir(parents=True)
        (meetings_dir / mid / "transcript.md").write_text("[00:00] Hello world\n")
        (meetings_dir / mid / "metadata.json").write_text(
            json.dumps({"meeting_id": mid, "name": "Nope"})
        )

        manager = MeetingManager(config=config, recorder=MockRecorder(), transcriber=MockTranscriber())
        results = manager.search("nonexistent")
        assert len(results) == 0


class TestMeetingManagerTranscription:
    """AC-42: Whisper transcribes audio chunks in near-real-time."""

    def test_transcription_loop_processes_chunks(self, tmp_path):
        """Transcription loop processes audio chunks and adds to meeting."""
        config = make_config(tmp_path)
        chunks = [
            np.random.randn(16000 * 5, 1).astype(np.float32),
            np.random.randn(16000 * 5, 1).astype(np.float32),
        ]
        responses = [
            TranscriptChunk(text="First chunk text", start_time=0.0, end_time=5.0),
            TranscriptChunk(text="Second chunk text", start_time=5.0, end_time=10.0),
        ]

        manager = MeetingManager(
            config=config,
            recorder=MockRecorder(chunks=chunks),
            transcriber=MockTranscriber(responses=responses),
        )

        meeting = manager.start(name="Transcription Test")
        time.sleep(1.0)  # Let transcription thread process
        meeting = manager.stop()

        assert meeting.word_count >= 3  # At least some words transcribed
        assert len(meeting.chunks) >= 1


class TestMeetingConfigIntegration:
    """Test config.py meeting section integration."""

    def test_default_config_has_meeting(self):
        """DEFAULT_CONFIG includes meeting section."""
        from yui.config import DEFAULT_CONFIG

        assert "meeting" in DEFAULT_CONFIG
        assert DEFAULT_CONFIG["meeting"]["audio"]["sample_rate"] == 16000
        assert DEFAULT_CONFIG["meeting"]["whisper"]["model"] == "large-v3-turbo"
        assert DEFAULT_CONFIG["meeting"]["output"]["transcript_dir"] == "~/.yui/meetings/"

    def test_meeting_config_merges(self, tmp_path):
        """Custom meeting config merges with defaults."""
        import yaml
        from yui.config import load_config

        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(yaml.dump({
            "meeting": {
                "whisper": {"language": "ja"},
            }
        }))

        config = load_config(str(cfg_file))
        assert config["meeting"]["whisper"]["language"] == "ja"
        # Defaults preserved
        assert config["meeting"]["audio"]["sample_rate"] == 16000
        assert config["meeting"]["whisper"]["model"] == "large-v3-turbo"
