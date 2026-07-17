from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from src.pipeline import validators


class FakeCompletedProcess:
    def __init__(self, stdout: str):
        self.stdout = stdout
        self.stderr = ""


def test_validate_audio_source_accepts_reasonable_audio(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"a" * 2048)

    monkeypatch.setattr(validators.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        validators.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess("120.5\n"),
    )

    result = validators.validate_audio_source(audio_path)

    assert result.path == audio_path.resolve()
    assert result.size_bytes == 2048
    assert result.duration_seconds == 120.5


def test_validate_audio_source_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(validators.AudioValidationError, match="does not exist"):
        validators.validate_audio_source(tmp_path / "missing.mp3")


def test_validate_audio_source_rejects_empty_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "empty.mp3"
    audio_path.write_bytes(b"")

    with pytest.raises(validators.AudioValidationError, match="empty"):
        validators.validate_audio_source(audio_path)


def test_validate_audio_source_rejects_too_small_file(tmp_path: Path) -> None:
    audio_path = tmp_path / "tiny.mp3"
    audio_path.write_bytes(b"tiny")

    with pytest.raises(validators.AudioValidationError, match="too small"):
        validators.validate_audio_source(audio_path)


def test_validate_audio_source_warns_and_continues_without_ffprobe(
    monkeypatch,
    caplog,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"a" * 2048)
    monkeypatch.setattr(validators.shutil, "which", lambda name: None)

    result = validators.validate_audio_source(audio_path)

    assert result.path == audio_path.resolve()
    assert result.size_bytes == 2048
    assert result.duration_seconds is None
    assert "ffprobe unavailable, skip duration validation" in caplog.text


def test_validate_audio_source_rejects_unreadable_duration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"a" * 2048)
    monkeypatch.setattr(validators.shutil, "which", lambda name: "/usr/bin/ffprobe")

    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            stderr="invalid data",
        )

    monkeypatch.setattr(validators.subprocess, "run", fail_run)

    with pytest.raises(validators.AudioValidationError, match="Cannot read audio duration"):
        validators.validate_audio_source(audio_path)


def test_validate_audio_source_rejects_too_short_duration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"a" * 2048)
    monkeypatch.setattr(validators.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        validators.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess("0.5\n"),
    )

    with pytest.raises(validators.AudioValidationError, match="too short"):
        validators.validate_audio_source(audio_path)


def test_validate_audio_source_rejects_too_long_duration(
    monkeypatch,
    tmp_path: Path,
) -> None:
    audio_path = tmp_path / "episode.mp3"
    audio_path.write_bytes(b"a" * 2048)
    monkeypatch.setattr(validators.shutil, "which", lambda name: "/usr/bin/ffprobe")
    monkeypatch.setattr(
        validators.subprocess,
        "run",
        lambda *args, **kwargs: FakeCompletedProcess("30000\n"),
    )

    with pytest.raises(validators.AudioValidationError, match="longer"):
        validators.validate_audio_source(audio_path)
