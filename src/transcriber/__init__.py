"""Speech-to-text package."""

from src.transcriber.whisper import (
    TranscriptResult,
    TranscriptSegment,
    TranscriptionError,
    save_transcript_json,
    transcribe_audio,
)

__all__ = [
    "TranscriptResult",
    "TranscriptSegment",
    "TranscriptionError",
    "save_transcript_json",
    "transcribe_audio",
]
