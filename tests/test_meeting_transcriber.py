"""Tests for yui.meeting.transcriber — AC-42 (near-real-time transcription).

Uses mock Whisper engine — no real ML model needed.
"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from yui.meeting.transcriber import WhisperTranscriber

pytestmark = pytest.mark.component



class MockWhisperEngine:
    """Mock Whisper engine for testing."""

    def __init__(self, text="Hello world", language="en"):
        self.text = text
        self.language = language
        self.call_count = 0

    def transcribe(self, audio, **kwargs):
        self.call_count += 1
        return {
            "text": self.text,
            "language": self.language,
            "segments": [
                {"start": 0.0, "end": 5.0, "text": self.text}
            ],
        }


class EmptyWhisperEngine:
    """Mock engine that returns empty text."""

    def transcribe(self, audio, **kwargs):
        return {"text": "", "language": "en", "segments": []}


class ErrorWhisperEngine:
    """Mock engine that raises errors."""

    def transcribe(self, audio, **kwargs):
        raise RuntimeError("Model load failed")


class TestWhisperTranscriber:
    """Test WhisperTranscriber with mock engine (AC-42)."""

    def test_transcribe_chunk_basic(self):
        """Basic transcription returns TranscriptChunk."""
        engine = MockWhisperEngine(text="Hello from the meeting")
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        audio = np.random.randn(16000 * 5).astype(np.float32)  # 5 seconds
        result = transcriber.transcribe_chunk(audio, sample_rate=16000, chunk_start_time=0.0)

        assert result is not None
        assert result.text == "Hello from the meeting"
        assert result.start_time == 0.0
        assert result.end_time == 5.0
        assert result.language == "en"

    def test_transcribe_with_language_override(self):
        """Language override is passed to engine."""
        engine = MockWhisperEngine(text="こんにちは", language="ja")
        transcriber = WhisperTranscriber(
            whisper_engine=engine, language="ja", vad_enabled=False
        )

        audio = np.random.randn(16000 * 5).astype(np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is not None
        assert result.language == "ja"

    def test_transcribe_chunk_timing(self):
        """Chunk timing is calculated from start_time + duration."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        # 3 seconds of audio at 16kHz starting at 10s
        audio = np.random.randn(16000 * 3).astype(np.float32)
        result = transcriber.transcribe_chunk(
            audio, sample_rate=16000, chunk_start_time=10.0
        )

        assert result is not None
        assert result.start_time == 10.0
        assert result.end_time == 13.0  # 10 + 3

    def test_vad_skips_silence(self):
        """VAD skips silent audio chunks."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=True, vad_threshold=0.01
        )

        # Very quiet audio (silence)
        audio = np.zeros(16000 * 5, dtype=np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is None
        assert engine.call_count == 0  # Engine was never called

    def test_vad_passes_speech(self):
        """VAD passes through audio above threshold."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=True, vad_threshold=0.01
        )

        # Loud audio (above threshold)
        audio = np.random.randn(16000 * 5).astype(np.float32) * 0.5
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is not None
        assert engine.call_count == 1

    def test_vad_disabled(self):
        """With VAD disabled, even silence is transcribed."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        audio = np.zeros(16000 * 5, dtype=np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is not None
        assert engine.call_count == 1

    def test_empty_transcription_returns_none(self):
        """Empty transcription result returns None."""
        engine = EmptyWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        audio = np.random.randn(16000 * 5).astype(np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is None

    def test_error_returns_none(self):
        """Engine error returns None (graceful degradation)."""
        engine = ErrorWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        audio = np.random.randn(16000 * 5).astype(np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is None

    def test_multichannel_audio_converted_to_mono(self):
        """Multichannel audio is averaged to mono."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(
            whisper_engine=engine, vad_enabled=False
        )

        # Stereo audio
        audio = np.random.randn(16000 * 5, 2).astype(np.float32)
        result = transcriber.transcribe_chunk(audio, sample_rate=16000)

        assert result is not None

    def test_reset(self):
        """Reset clears internal state."""
        engine = MockWhisperEngine()
        transcriber = WhisperTranscriber(whisper_engine=engine)
        transcriber._chunk_offset = 100.0
        transcriber.reset()
        assert transcriber._chunk_offset == 0.0


class TestImportGuard:
    """AC-51: mlx-whisper import guard."""

    def test_mlx_whisper_import_error(self):
        """MlxWhisperEngine raises ImportError when mlx_whisper missing."""
        import sys

        mlx_module = sys.modules.get("mlx_whisper")
        sys.modules["mlx_whisper"] = None  # type: ignore
        try:
            from yui.meeting.transcriber import MlxWhisperEngine

            with pytest.raises(ImportError, match="yui-agent\\[meeting\\]"):
                MlxWhisperEngine()
        finally:
            if mlx_module:
                sys.modules["mlx_whisper"] = mlx_module
            else:
                sys.modules.pop("mlx_whisper", None)
