"""Tests for yui.meeting.recorder — AC-40, AC-42, AC-43, AC-44.

Uses mock audio streams (DI pattern) — no real audio device needed.
"""

import queue
import threading
import time

import numpy as np
import pytest

from yui.meeting.recorder import AudioRecorder


class MockAudioStream:
    """Mock audio stream for testing — generates fake audio data."""

    def __init__(self, callback=None, samplerate=16000, channels=1, **kwargs):
        self._callback = callback
        self._samplerate = samplerate
        self._channels = channels
        self._active = False
        self._thread = None

    def start(self):
        self._active = True
        # Generate audio in background
        self._thread = threading.Thread(target=self._generate, daemon=True)
        self._thread.start()

    def stop(self):
        self._active = False
        if self._thread:
            self._thread.join(timeout=2)

    def close(self):
        self._active = False

    @property
    def active(self):
        return self._active

    def _generate(self):
        """Generate fake audio data via callback."""
        block_size = self._samplerate // 10  # 100ms blocks
        while self._active:
            data = np.random.randn(block_size, self._channels).astype(np.float32) * 0.1
            if self._callback:
                self._callback(data, block_size, None, None)
            time.sleep(0.05)  # Don't flood


class SilentMockStream(MockAudioStream):
    """Mock stream that produces silence."""

    def _generate(self):
        block_size = self._samplerate // 10
        while self._active:
            data = np.zeros((block_size, self._channels), dtype=np.float32)
            if self._callback:
                self._callback(data, block_size, None, None)
            time.sleep(0.05)


def mock_stream_factory(**kwargs):
    """Factory that creates MockAudioStream."""
    return MockAudioStream(**kwargs)


def silent_stream_factory(**kwargs):
    """Factory that creates SilentMockStream."""
    return SilentMockStream(**kwargs)


class TestAudioRecorder:
    """Test AudioRecorder with mock streams (AC-40)."""

    def test_start_and_stop(self):
        """Recorder starts and stops cleanly."""
        recorder = AudioRecorder(
            sample_rate=16000,
            channels=1,
            chunk_seconds=1,
            stream_factory=mock_stream_factory,
        )
        recorder.start()
        assert recorder.is_recording is True
        time.sleep(0.5)
        recorder.stop()
        assert recorder.is_recording is False

    def test_produces_chunks(self):
        """Recorder produces audio chunks of expected size."""
        recorder = AudioRecorder(
            sample_rate=16000,
            channels=1,
            chunk_seconds=1,
            stream_factory=mock_stream_factory,
        )
        recorder.start()
        # Wait for at least one chunk (1 second)
        time.sleep(1.5)
        chunk = recorder.get_chunk(timeout=2.0)
        recorder.stop()

        assert chunk is not None
        # Chunk should be ~16000 samples (1 sec at 16kHz)
        assert len(chunk) == 16000

    def test_chunk_is_correct_shape(self):
        """Audio chunks have correct shape (samples, channels)."""
        recorder = AudioRecorder(
            sample_rate=16000,
            channels=1,
            chunk_seconds=1,
            stream_factory=mock_stream_factory,
        )
        recorder.start()
        time.sleep(1.5)
        chunk = recorder.get_chunk(timeout=2.0)
        recorder.stop()

        assert chunk is not None
        assert chunk.shape[1] == 1  # mono

    def test_elapsed_seconds(self):
        """elapsed_seconds tracks recording duration."""
        recorder = AudioRecorder(
            stream_factory=mock_stream_factory,
        )
        assert recorder.elapsed_seconds == 0.0
        recorder.start()
        time.sleep(0.5)
        assert recorder.elapsed_seconds > 0.3
        recorder.stop()
        assert recorder.elapsed_seconds == 0.0

    def test_already_recording_raises(self):
        """Starting while already recording raises RuntimeError."""
        recorder = AudioRecorder(
            stream_factory=mock_stream_factory,
        )
        recorder.start()
        with pytest.raises(RuntimeError, match="already in progress"):
            recorder.start()
        recorder.stop()

    def test_stop_when_not_recording_is_safe(self):
        """Stopping when not recording is a no-op."""
        recorder = AudioRecorder(
            stream_factory=mock_stream_factory,
        )
        recorder.stop()  # Should not raise

    def test_get_chunk_returns_none_when_empty(self):
        """get_chunk returns None when no chunks available."""
        recorder = AudioRecorder(
            stream_factory=mock_stream_factory,
        )
        chunk = recorder.get_chunk(timeout=0.1)
        assert chunk is None

    def test_multiple_chunks_queued(self):
        """Multiple chunks accumulate in queue."""
        recorder = AudioRecorder(
            sample_rate=16000,
            channels=1,
            chunk_seconds=1,
            stream_factory=mock_stream_factory,
        )
        recorder.start()
        time.sleep(2.5)  # Should produce ~2 chunks
        recorder.stop()

        chunks = []
        while True:
            chunk = recorder.get_chunk(timeout=0.5)
            if chunk is None:
                break
            chunks.append(chunk)

        assert len(chunks) >= 2


class TestAudioRecorderDI:
    """Test DI pattern — custom stream factory."""

    def test_custom_factory_called(self):
        """Custom stream factory is invoked."""
        factory_called = False

        def custom_factory(**kwargs):
            nonlocal factory_called
            factory_called = True
            return MockAudioStream(**kwargs)

        recorder = AudioRecorder(stream_factory=custom_factory)
        recorder.start()
        assert factory_called is True
        recorder.stop()

    def test_silent_stream_factory(self):
        """Silent stream factory produces no audio (for VAD testing)."""
        recorder = AudioRecorder(
            chunk_seconds=1,
            stream_factory=silent_stream_factory,
        )
        recorder.start()
        time.sleep(1.5)
        # Chunks may be produced even if silent (silence detection is in transcriber)
        recorder.stop()


class TestImportGuard:
    """AC-51: Meeting feature is opt-in — requires pip install yui-agent[meeting]."""

    def test_sounddevice_import_error(self):
        """SoundDeviceStream raises ImportError when sounddevice missing."""
        import importlib
        import sys

        # Temporarily remove sounddevice from import path
        sd_module = sys.modules.get("sounddevice")
        sys.modules["sounddevice"] = None  # type: ignore
        try:
            from yui.meeting.recorder import SoundDeviceStream

            with pytest.raises(ImportError, match="yui-agent\\[meeting\\]"):
                SoundDeviceStream()
        finally:
            if sd_module:
                sys.modules["sounddevice"] = sd_module
            else:
                sys.modules.pop("sounddevice", None)
