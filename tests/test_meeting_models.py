"""Tests for yui.meeting.models — AC-40, AC-48."""

import json
import tempfile
from pathlib import Path

import pytest

from yui.meeting.models import (
    Meeting,
    MeetingConfig,
    MeetingStatus,
    TranscriptChunk,
)


class TestTranscriptChunk:
    """Test TranscriptChunk data model."""

    def test_create_chunk(self):
        """Basic chunk creation."""
        chunk = TranscriptChunk(
            text="Hello world",
            start_time=0.0,
            end_time=5.0,
            language="en",
        )
        assert chunk.text == "Hello world"
        assert chunk.start_time == 0.0
        assert chunk.end_time == 5.0
        assert chunk.language == "en"

    def test_chunk_defaults(self):
        """Defaults are set correctly."""
        chunk = TranscriptChunk(text="test", start_time=0, end_time=5)
        assert chunk.language == "auto"
        assert chunk.confidence == 0.0
        assert chunk.timestamp  # auto-generated

    def test_to_dict(self):
        """Serialization to dict."""
        chunk = TranscriptChunk(
            text="test", start_time=1.0, end_time=6.0, language="ja"
        )
        d = chunk.to_dict()
        assert d["text"] == "test"
        assert d["start_time"] == 1.0
        assert d["language"] == "ja"

    def test_from_dict(self):
        """Deserialization from dict."""
        d = {
            "text": "hello",
            "start_time": 0.0,
            "end_time": 5.0,
            "language": "en",
            "confidence": 0.95,
        }
        chunk = TranscriptChunk.from_dict(d)
        assert chunk.text == "hello"
        assert chunk.confidence == 0.95

    def test_from_dict_ignores_extra_keys(self):
        """Extra keys in dict are ignored."""
        d = {
            "text": "hello",
            "start_time": 0.0,
            "end_time": 5.0,
            "extra_key": "ignored",
        }
        chunk = TranscriptChunk.from_dict(d)
        assert chunk.text == "hello"


class TestMeeting:
    """Test Meeting data model."""

    def test_create_meeting(self):
        """Basic meeting creation."""
        m = Meeting(name="Test Meeting")
        assert m.name == "Test Meeting"
        assert m.status == MeetingStatus.RECORDING
        assert len(m.meeting_id) == 12
        assert m.word_count == 0
        assert m.chunks == []

    def test_add_chunk(self):
        """Adding chunks updates word count."""
        m = Meeting()
        chunk = TranscriptChunk(text="hello world test", start_time=0, end_time=5)
        m.add_chunk(chunk)
        assert m.word_count == 3
        assert len(m.chunks) == 1

    def test_add_multiple_chunks(self):
        """Word count accumulates across chunks."""
        m = Meeting()
        m.add_chunk(TranscriptChunk(text="hello world", start_time=0, end_time=5))
        m.add_chunk(TranscriptChunk(text="foo bar baz", start_time=5, end_time=10))
        assert m.word_count == 5
        assert len(m.chunks) == 2

    def test_get_full_transcript(self):
        """Full transcript concatenates chunks."""
        m = Meeting()
        m.add_chunk(TranscriptChunk(text="Hello.", start_time=0, end_time=5))
        m.add_chunk(TranscriptChunk(text="World.", start_time=5, end_time=10))
        transcript = m.get_full_transcript()
        assert "Hello." in transcript
        assert "World." in transcript

    def test_get_full_transcript_skips_empty(self):
        """Empty chunks are skipped in full transcript."""
        m = Meeting()
        m.add_chunk(TranscriptChunk(text="Hello.", start_time=0, end_time=5))
        m.add_chunk(TranscriptChunk(text="   ", start_time=5, end_time=10))
        m.add_chunk(TranscriptChunk(text="World.", start_time=10, end_time=15))
        transcript = m.get_full_transcript()
        lines = [l for l in transcript.split("\n") if l.strip()]
        assert len(lines) == 2

    def test_to_metadata(self):
        """Metadata serialization."""
        m = Meeting(name="Standup", meeting_id="abc123")
        m.add_chunk(TranscriptChunk(text="test chunk", start_time=0, end_time=5))
        meta = m.to_metadata()
        assert meta["meeting_id"] == "abc123"
        assert meta["name"] == "Standup"
        assert meta["chunk_count"] == 1
        assert meta["word_count"] == 2

    def test_save_and_load_metadata(self, tmp_path):
        """Round-trip: save → load metadata."""
        m = Meeting(name="Roundtrip", meeting_id="test123")
        m.add_chunk(TranscriptChunk(text="hello world", start_time=0, end_time=5))

        meta_path = tmp_path / "test123" / "metadata.json"
        m.save_metadata(meta_path)
        assert meta_path.exists()

        loaded = Meeting.from_metadata(meta_path)
        assert loaded.meeting_id == "test123"
        assert loaded.name == "Roundtrip"
        assert loaded.word_count == 2

    def test_save_transcript(self, tmp_path):
        """Transcript saved as markdown."""
        m = Meeting(name="Test", meeting_id="tx123")
        m.add_chunk(TranscriptChunk(text="First chunk", start_time=0, end_time=5))
        m.add_chunk(TranscriptChunk(text="Second chunk", start_time=65, end_time=70))

        path = tmp_path / "tx123" / "transcript.md"
        m.save_transcript(path)
        assert path.exists()

        content = path.read_text()
        assert "# Meeting Transcript" in content
        assert "[00:00]" in content  # First chunk at 0:00
        assert "[01:05]" in content  # Second chunk at 1:05
        assert "First chunk" in content
        assert "Second chunk" in content


class TestMeetingConfig:
    """Test MeetingConfig extraction from main config."""

    def test_defaults(self):
        """Empty config → all defaults."""
        cfg = MeetingConfig.from_config({})
        assert cfg.sample_rate == 16000
        assert cfg.channels == 1
        assert cfg.chunk_seconds == 5
        assert cfg.whisper_model == "large-v3-turbo"
        assert cfg.language == "auto"
        assert cfg.vad_enabled is True

    def test_custom_config(self):
        """Custom meeting config overrides defaults."""
        cfg = MeetingConfig.from_config({
            "meeting": {
                "audio": {"sample_rate": 44100, "channels": 2},
                "whisper": {"model": "small", "language": "ja"},
            }
        })
        assert cfg.sample_rate == 44100
        assert cfg.channels == 2
        assert cfg.whisper_model == "small"
        assert cfg.language == "ja"

    def test_get_meeting_dir(self):
        """Meeting directory is constructed correctly."""
        cfg = MeetingConfig(transcript_dir="/tmp/test_meetings/")
        path = cfg.get_meeting_dir("abc123")
        assert str(path) == "/tmp/test_meetings/abc123"

    def test_get_meeting_dir_expands_tilde(self):
        """~ is expanded in transcript_dir."""
        cfg = MeetingConfig()
        path = cfg.get_meeting_dir("test")
        assert "~" not in str(path)


class TestMeetingStatus:
    """Test MeetingStatus enum."""

    def test_values(self):
        assert MeetingStatus.RECORDING.value == "recording"
        assert MeetingStatus.STOPPED.value == "stopped"
        assert MeetingStatus.COMPLETED.value == "completed"
        assert MeetingStatus.ERROR.value == "error"

    def test_from_string(self):
        assert MeetingStatus("recording") == MeetingStatus.RECORDING
        assert MeetingStatus("stopped") == MeetingStatus.STOPPED
