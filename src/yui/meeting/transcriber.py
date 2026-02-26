"""Real-time Whisper transcription using mlx-whisper.

Processes audio chunks from AudioRecorder and produces TranscriptChunks.
Supports VAD (Voice Activity Detection) to skip silence.
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import numpy as np

from yui.meeting.models import TranscriptChunk

logger = logging.getLogger(__name__)

# RMS threshold for Voice Activity Detection
# Audio below this is considered silence and skipped
DEFAULT_VAD_THRESHOLD = 0.01


class WhisperEngineProtocol(Protocol):
    """Protocol for Whisper engines — enables DI/mocking."""

    def transcribe(
        self, audio: Any, **kwargs: Any
    ) -> dict[str, Any]: ...


class MlxWhisperEngine:
    """Real mlx-whisper engine wrapper."""

    def __init__(self, model: str = "mlx-community/whisper-large-v3-turbo") -> None:
        try:
            import mlx_whisper
        except ImportError:
            raise ImportError(
                "mlx-whisper is required for transcription. "
                "Install it with: pip install yui-agent[meeting]"
            )
        self._mlx_whisper = mlx_whisper
        self.model = model

    def transcribe(self, audio: Any, **kwargs: Any) -> dict[str, Any]:
        """Transcribe audio using mlx-whisper.

        Args:
            audio: Path to audio file or numpy array.
            **kwargs: Additional kwargs passed to mlx_whisper.transcribe().

        Returns:
            Dict with 'text', 'segments', 'language' keys.
        """
        return self._mlx_whisper.transcribe(audio, path_or_hf_repo=self.model, **kwargs)


class WhisperTranscriber:
    """Transcribes audio chunks using Whisper (mlx-whisper by default).

    Designed with Dependency Injection: accepts a whisper_engine
    to enable easy mocking in tests.

    Args:
        model: Whisper model name/path.
        language: Language code or 'auto' for auto-detection.
        vad_enabled: Whether to skip silence chunks.
        vad_threshold: RMS amplitude threshold for VAD.
        whisper_engine: WhisperEngineProtocol implementation.
            If None, uses MlxWhisperEngine.
    """

    def __init__(
        self,
        model: str = "mlx-community/whisper-large-v3-turbo",
        language: str = "auto",
        vad_enabled: bool = True,
        vad_threshold: float = DEFAULT_VAD_THRESHOLD,
        whisper_engine: Optional[WhisperEngineProtocol] = None,
    ) -> None:
        self.model = model
        self.language = language
        self.vad_enabled = vad_enabled
        self.vad_threshold = vad_threshold
        self._engine = whisper_engine or MlxWhisperEngine(model=model)
        self._chunk_offset: float = 0.0

    def transcribe_chunk(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000,
        chunk_start_time: float = 0.0,
    ) -> Optional[TranscriptChunk]:
        """Transcribe a single audio chunk.

        Args:
            audio_data: numpy array of audio samples (float32, mono).
            sample_rate: Sample rate of the audio.
            chunk_start_time: Offset from meeting start in seconds.

        Returns:
            TranscriptChunk if speech detected, None if silence/empty.
        """
        # VAD: skip silence
        if self.vad_enabled and self._is_silence(audio_data):
            logger.debug(f"Chunk at {chunk_start_time:.1f}s: silence, skipping")
            return None

        # Ensure mono float32
        audio = self._prepare_audio(audio_data)

        # Transcribe
        kwargs: dict[str, Any] = {}
        if self.language != "auto":
            kwargs["language"] = self.language

        try:
            result = self._engine.transcribe(audio, **kwargs)
        except Exception as e:
            logger.error(f"Transcription error at {chunk_start_time:.1f}s: {e}")
            return None

        text = result.get("text", "").strip()
        if not text:
            return None

        # Calculate end time
        duration = len(audio_data) / sample_rate
        end_time = chunk_start_time + duration

        # Detect language
        detected_lang = result.get("language", self.language)

        return TranscriptChunk(
            text=text,
            start_time=chunk_start_time,
            end_time=end_time,
            language=detected_lang if detected_lang else "unknown",
        )

    def _is_silence(self, audio_data: np.ndarray) -> bool:
        """Check if audio chunk is silence using RMS amplitude."""
        if len(audio_data) == 0:
            return True
        # Flatten to 1D if multichannel
        flat = audio_data.flatten()
        rms = np.sqrt(np.mean(flat**2))
        return float(rms) < self.vad_threshold

    def _prepare_audio(self, audio_data: np.ndarray) -> np.ndarray:
        """Prepare audio for Whisper: mono float32."""
        audio = audio_data.astype(np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        return audio

    def reset(self) -> None:
        """Reset transcriber state for a new meeting."""
        self._chunk_offset = 0.0
