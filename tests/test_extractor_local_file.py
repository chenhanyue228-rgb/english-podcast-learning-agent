from pathlib import Path

import pytest

from src.extractor.local_file import LocalFileExtractionError, extract_local_audio


def test_extract_local_audio_returns_absolute_path(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.mp3"
    audio_path.write_bytes(b"audio")

    assert extract_local_audio(str(audio_path)) == audio_path.resolve()


def test_extract_local_audio_accepts_webm(tmp_path: Path) -> None:
    audio_path = tmp_path / "sample.webm"
    audio_path.write_bytes(b"audio")

    assert extract_local_audio(str(audio_path)) == audio_path.resolve()


def test_extract_local_audio_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(LocalFileExtractionError, match="does not exist"):
        extract_local_audio(str(tmp_path / "missing.mp3"))


def test_extract_local_audio_rejects_directory(tmp_path: Path) -> None:
    with pytest.raises(LocalFileExtractionError, match="not a file"):
        extract_local_audio(str(tmp_path))


def test_extract_local_audio_rejects_unsupported_extension(tmp_path: Path) -> None:
    text_path = tmp_path / "sample.txt"
    text_path.write_text("not audio", encoding="utf-8")

    with pytest.raises(LocalFileExtractionError, match="Unsupported audio"):
        extract_local_audio(str(text_path))
