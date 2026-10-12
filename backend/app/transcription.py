"""Local speech-to-text with faster-whisper. Audio never leaves this machine.

faster-whisper runs Whisper models on CTranslate2 with int8 quantization, which keeps
CPU-only transcription practical. It is an optional dependency (requirements-ai.txt)
and is imported only when a transcription actually runs.
"""

import io
from dataclasses import dataclass
from functools import lru_cache

from .services.errors import ServiceError


@dataclass(frozen=True)
class Transcript:
    text: str
    duration_seconds: float
    language: str


class TranscriptionUnavailable(RuntimeError):
    """faster-whisper is not installed or the model could not be loaded."""


@lru_cache(maxsize=1)
def load_model(name: str, compute_type: str):
    try:
        # Optional dependency from requirements-ai.txt; absent in the base install and CI.
        from faster_whisper import WhisperModel  # pyright: ignore[reportMissingImports]
    except ImportError as exc:
        raise TranscriptionUnavailable("Install backend/requirements-ai.txt to enable transcription") from exc
    return WhisperModel(name, device="cpu", compute_type=compute_type)


def transcribe(audio: bytes, *, model_name: str, compute_type: str, max_seconds: int) -> Transcript:
    model = load_model(model_name, compute_type)
    # Segments are produced lazily, so the duration check runs before any heavy decoding.
    # VAD skips long silences, which saves CPU on real meetings.
    segments, info = model.transcribe(io.BytesIO(audio), vad_filter=True)
    if info.duration > max_seconds:
        raise ServiceError(
            status_code=413,
            error=f"Audio is longer than the {max_seconds // 60}-minute limit",
            where="client",
        )
    lines = [segment.text.strip() for segment in segments if segment.text.strip()]
    if not lines:
        raise ServiceError(status_code=422, error="No speech was detected in the audio", where="client")
    return Transcript(text="\n".join(lines), duration_seconds=info.duration, language=info.language)
