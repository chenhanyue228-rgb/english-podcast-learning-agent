"""Speech-to-text transcription using faster-whisper."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Union


LOGGER = logging.getLogger(__name__)


class TranscriptionError(RuntimeError):
    """Raised when audio transcription fails."""


@dataclass(frozen=True)
class TranscriptSegment:
    """One timestamped transcript segment."""

    start: float
    end: float
    text: str


@dataclass(frozen=True)
class TranscriptResult:
    """Timestamped transcript output compatible with transcript.json."""

    segments: list[TranscriptSegment]
    language: str

    def to_dict(self) -> dict[str, Any]:
        """Return the public transcript JSON shape."""
        return {
            "segments": [asdict(segment) for segment in self.segments],
            "language": self.language,
        }


def validate_audio_path(audio_path: Union[Path, str]) -> Path:
    """Validate that the input audio file exists before transcription."""
    path = Path(audio_path).expanduser()
    if not path.exists():
        raise TranscriptionError(f"Audio file does not exist: {audio_path}")
    if not path.is_file():
        raise TranscriptionError(f"Audio path is not a file: {audio_path}")
    if path.stat().st_size <= 0:
        raise TranscriptionError(f"Audio file is empty: {audio_path}")
    return path.resolve()


def load_whisper_model(
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "default",
):
    """Load faster-whisper model lazily so tests can inject a fake model."""
    try:
        from faster_whisper import WhisperModel
    except ModuleNotFoundError as exc:
        raise TranscriptionError(
            "Missing dependency faster-whisper. Run python3 scripts/bootstrap_environment.py."
        ) from exc

    LOGGER.info(
        "Loading faster-whisper model: model_size=%s device=%s compute_type=%s",
        model_size,
        device,
        compute_type,
    )
    return WhisperModel(model_size, device=device, compute_type=compute_type)


def normalize_segments(raw_segments: Iterable[Any]) -> list[TranscriptSegment]:
    """Convert faster-whisper segment objects into transcript JSON segments."""
    segments: list[TranscriptSegment] = []
    for segment in raw_segments:
        text = getattr(segment, "text", "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start=float(getattr(segment, "start")),
                end=float(getattr(segment, "end")),
                text=text,
            )
        )
    return segments


def transcribe_audio(
    audio_path: Union[Path, str],
    model: Optional[Any] = None,
    model_size: str = "base",
    device: str = "auto",
    compute_type: str = "default",
    beam_size: int = 5,
) -> TranscriptResult:
    """Convert an audio file into timestamped English transcript segments.

    faster-whisper streams segments lazily, which lets the caller handle long
    audio without loading the entire transcript into memory at once.
    """
    validated_audio_path = validate_audio_path(audio_path)
    whisper_model = model or load_whisper_model(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
    )

    LOGGER.info("Starting transcription: %s", validated_audio_path)
    try:
        raw_segments, info = whisper_model.transcribe(
            str(validated_audio_path),
            language="en",
            task="transcribe",
            beam_size=beam_size,
            vad_filter=True,
        )
        segments = normalize_segments(raw_segments)
    except Exception as exc:
        raise TranscriptionError(f"Failed to transcribe audio: {exc}") from exc

    detected_language = getattr(info, "language", "en") or "en"
    if detected_language != "en":
        LOGGER.warning("Expected English audio but detected language=%s", detected_language)

    LOGGER.info("Transcription complete: %s segments", len(segments))
    return TranscriptResult(segments=segments, language=detected_language)


def save_transcript_json(result: TranscriptResult, output_path: Union[Path, str]) -> Path:
    """Write transcript result to transcript.json format."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path.resolve()
