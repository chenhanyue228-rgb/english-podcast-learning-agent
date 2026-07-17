from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.transcriber.whisper import (
    TranscriptionError,
    normalize_segments,
    save_transcript_json,
    transcribe_audio,
    validate_audio_path,
)


@dataclass
class FakeSegment:
    start: float
    end: float
    text: str


@dataclass
class FakeInfo:
    language: str = "en"


class FakeWhisperModel:
    def __init__(self, language: str = "en"):
        self.language = language
        self.calls = []

    def transcribe(self, audio_path: str, **kwargs):
        self.calls.append((audio_path, kwargs))
        return (
            [
                FakeSegment(0.0, 1.5, " Hello world "),
                FakeSegment(1.5, 3.0, "This is a test."),
                FakeSegment(3.0, 4.0, "   "),
            ],
            FakeInfo(language=self.language),
        )


def test_validate_audio_path_accepts_existing_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    assert validate_audio_path(audio_path) == audio_path.resolve()


def test_validate_audio_path_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError, match="does not exist"):
        validate_audio_path(tmp_path / "missing.mp3")


def test_validate_audio_path_rejects_empty_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "empty.mp3"
    audio_path.write_bytes(b"")

    with pytest.raises(TranscriptionError, match="empty"):
        validate_audio_path(audio_path)


def test_normalize_segments_preserves_timestamps_and_skips_empty_text() -> None:
    segments = normalize_segments(
        [
            FakeSegment(0, 1, " Hello "),
            FakeSegment(1, 2, "  "),
        ]
    )

    assert len(segments) == 1
    assert segments[0].start == 0.0
    assert segments[0].end == 1.0
    assert segments[0].text == "Hello"


def test_transcribe_audio_forces_english_and_preserves_segments(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    model = FakeWhisperModel()

    result = transcribe_audio(audio_path, model=model, beam_size=3)

    assert result.language == "en"
    assert result.to_dict() == {
        "segments": [
            {"start": 0.0, "end": 1.5, "text": "Hello world"},
            {"start": 1.5, "end": 3.0, "text": "This is a test."},
        ],
        "language": "en",
    }
    assert model.calls[0][1]["language"] == "en"
    assert model.calls[0][1]["task"] == "transcribe"
    assert model.calls[0][1]["vad_filter"] is True
    assert model.calls[0][1]["beam_size"] == 3


def test_transcribe_audio_allows_detected_language_warning_path(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    result = transcribe_audio(audio_path, model=FakeWhisperModel(language="zh"))

    assert result.language == "zh"


def test_transcribe_audio_wraps_model_errors(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")

    class BrokenModel:
        def transcribe(self, audio_path: str, **kwargs):
            raise RuntimeError("model failed")

    with pytest.raises(TranscriptionError, match="model failed"):
        transcribe_audio(audio_path, model=BrokenModel())


def test_save_transcript_json(tmp_path: Path) -> None:
    audio_path = tmp_path / "audio.mp3"
    audio_path.write_bytes(b"audio")
    result = transcribe_audio(audio_path, model=FakeWhisperModel())
    output_path = tmp_path / "transcript.json"

    saved_path = save_transcript_json(result, output_path)

    assert saved_path == output_path.resolve()
    assert json.loads(output_path.read_text(encoding="utf-8")) == result.to_dict()
