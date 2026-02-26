"""Audio recording via sounddevice with DI pattern for testability.

Uses sounddevice.InputStream to capture 16kHz mono audio in chunks.
System audio capture uses ScreenCaptureKit (macOS 13+) or BlackHole fallback.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional, Protocol

import numpy as np

logger = logging.getLogger(__name__)


class AudioStreamProtocol(Protocol):
    """Protocol for audio input streams — enables DI/mocking."""

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def close(self) -> None: ...
    @property
    def active(self) -> bool: ...


class SoundDeviceStream:
    """Real sounddevice InputStream wrapper.

    Adapts sounddevice.InputStream to AudioStreamProtocol.
    """

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        dtype: str = "float32",
        blocksize: int = 0,
        device: Optional[int | str] = None,
        callback: Optional[Callable] = None,
    ) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            raise ImportError(
                "sounddevice is required for audio recording. "
                "Install it with: pip install yui-agent[meeting]"
            )

        self._stream = sd.InputStream(
            samplerate=samplerate,
            channels=channels,
            dtype=dtype,
            blocksize=blocksize,
            device=device,
            callback=callback,
        )

    def start(self) -> None:
        self._stream.start()

    def stop(self) -> None:
        self._stream.stop()

    def close(self) -> None:
        self._stream.close()

    @property
    def active(self) -> bool:
        return self._stream.active


class AudioRecorder:
    """Captures audio from input device in fixed-size chunks.

    Designed with Dependency Injection: accepts a stream_factory
    callable to create the audio stream, enabling easy mocking in tests.

    Args:
        sample_rate: Sample rate in Hz (default 16000 for Whisper).
        channels: Number of channels (default 1 = mono).
        chunk_seconds: Duration of each audio chunk in seconds.
        stream_factory: Callable that creates an AudioStreamProtocol.
            If None, uses SoundDeviceStream (real audio).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_seconds: int = 5,
        stream_factory: Optional[Callable[..., AudioStreamProtocol]] = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.chunk_seconds = chunk_seconds
        self._stream_factory = stream_factory or self._default_stream_factory

        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._chunk_queue: queue.Queue[np.ndarray] = queue.Queue()
        self._stream: Optional[AudioStreamProtocol] = None
        self._running = False
        self._chunk_thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0

    def _default_stream_factory(self, **kwargs: Any) -> AudioStreamProtocol:
        """Create a real SoundDeviceStream."""
        return SoundDeviceStream(**kwargs)

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: Any, status: Any
    ) -> None:
        """sounddevice callback — pushes audio data to queue."""
        if status:
            logger.warning(f"Audio stream status: {status}")
        self._audio_queue.put(indata.copy())

    def _chunk_worker(self) -> None:
        """Background thread: accumulates audio into chunk_seconds chunks."""
        samples_per_chunk = self.sample_rate * self.chunk_seconds
        buffer = np.empty((0, self.channels), dtype=np.float32)

        while self._running or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.5)
                buffer = np.concatenate([buffer, data])

                while len(buffer) >= samples_per_chunk:
                    chunk = buffer[:samples_per_chunk]
                    buffer = buffer[samples_per_chunk:]
                    self._chunk_queue.put(chunk)

            except queue.Empty:
                continue

        # Flush remaining buffer as final chunk
        if len(buffer) > 0:
            self._chunk_queue.put(buffer)

    def start(self) -> None:
        """Start audio recording.

        Raises:
            RuntimeError: If already recording.
            ImportError: If sounddevice is not installed.
        """
        if self._running:
            raise RuntimeError("Audio recording already in progress")

        self._running = True
        self._start_time = time.time()
        self._audio_queue = queue.Queue()
        self._chunk_queue = queue.Queue()

        # Create stream with DI factory
        self._stream = self._stream_factory(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            callback=self._audio_callback,
        )
        self._stream.start()

        # Start chunk accumulation thread
        self._chunk_thread = threading.Thread(
            target=self._chunk_worker, daemon=True, name="yui-audio-chunker"
        )
        self._chunk_thread.start()

        logger.info(
            f"Audio recording started: {self.sample_rate}Hz, "
            f"{self.channels}ch, {self.chunk_seconds}s chunks"
        )

    def stop(self) -> None:
        """Stop audio recording."""
        if not self._running:
            return

        self._running = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if self._chunk_thread:
            self._chunk_thread.join(timeout=5.0)
            self._chunk_thread = None

        logger.info("Audio recording stopped")

    def get_chunk(self, timeout: float = 1.0) -> Optional[np.ndarray]:
        """Get the next audio chunk from the queue.

        Args:
            timeout: Max seconds to wait for a chunk.

        Returns:
            numpy array of audio data, or None if no chunk available.
        """
        try:
            return self._chunk_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    @property
    def is_recording(self) -> bool:
        """Whether recording is currently active."""
        return self._running

    @property
    def elapsed_seconds(self) -> float:
        """Seconds since recording started."""
        if not self._running:
            return 0.0
        return time.time() - self._start_time

    @property
    def chunks_available(self) -> int:
        """Number of chunks waiting in the queue."""
        return self._chunk_queue.qsize()
