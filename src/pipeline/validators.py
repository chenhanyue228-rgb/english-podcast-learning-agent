"""Validation gates for pipeline artifacts before expensive downstream work."""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


LOGGER = logging.getLogger(__name__)

MIN_AUDIO_FILE_SIZE_BYTES = 1024
MIN_AUDIO_DURATION_SECONDS = 1.0
MAX_AUDIO_DURATION_SECONDS = 6 * 60 * 60


class AudioValidationError(RuntimeError):
    """Raised when an audio file should not continue to transcription."""


@dataclass(frozen=True)
class AudioValidationResult:
    """Validated audio metadata used for logging and safety checks."""

    path: Path
    size_bytes: int
    duration_seconds: Optional[float]


def _get_audio_duration_seconds(audio_path: Path) -> float:
    ffprobe_path = shutil.which("ffprobe")
    if not ffprobe_path:
        raise FileNotFoundError("ffprobe")

    command = [
        ffprobe_path,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(audio_path),
    ]

    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or exc.stdout or "").strip()
        raise AudioValidationError(
            f"Cannot read audio duration. The downloaded file may be invalid: {message}"
        ) from exc

    raw_duration = completed.stdout.strip()
    try:
        return float(raw_duration)
    except ValueError as exc:
        raise AudioValidationError(
            f"Cannot parse audio duration from ffprobe output: {raw_duration!r}"
        ) from exc


def validate_audio_source(
    audio_path: Union[Path, str],
    min_size_bytes: int = MIN_AUDIO_FILE_SIZE_BYTES,
    min_duration_seconds: float = MIN_AUDIO_DURATION_SECONDS,
    max_duration_seconds: float = MAX_AUDIO_DURATION_SECONDS,
) -> AudioValidationResult:
    """Validate a local audio file before Whisper transcription starts.

    This gate prevents failed downloads, empty files, and suspiciously short or
    long audio from creating downstream transcripts or Notion pages.
    """
    path = Path(audio_path).expanduser()
    if not path.exists():
        raise AudioValidationError(f"Audio file does not exist: {audio_path}")
    if not path.is_file():
        raise AudioValidationError(f"Audio path is not a file: {audio_path}")

    size_bytes = path.stat().st_size
    if size_bytes <= 0:
        raise AudioValidationError(f"Audio file is empty: {audio_path}")
    if size_bytes < min_size_bytes:
        raise AudioValidationError(
            "Audio file is too small to be a valid podcast episode. "
            "This may indicate a failed download or wrong episode."
        )

    try:
        duration_seconds: Optional[float] = _get_audio_duration_seconds(path)
    except FileNotFoundError:
        LOGGER.warning("ffprobe unavailable, skip duration validation")
        duration_seconds = None
    else:
        if duration_seconds < min_duration_seconds:
            raise AudioValidationError(
                "Audio duration is too short to be a valid podcast episode. "
                "This may indicate a failed download or wrong episode."
            )
        if duration_seconds > max_duration_seconds:
            raise AudioValidationError(
                "Audio duration is longer than the supported MVP limit. "
                "Please verify the source before transcription."
            )

    result = AudioValidationResult(
        path=path.resolve(),
        size_bytes=size_bytes,
        duration_seconds=duration_seconds,
    )
    if result.duration_seconds is None:
        LOGGER.info(
            "Audio validation passed: path=%s size=%.1f MB duration=skipped",
            result.path,
            result.size_bytes / (1024 * 1024),
        )
    else:
        LOGGER.info(
            "Audio validation passed: path=%s size=%.1f MB duration=%.1f sec",
            result.path,
            result.size_bytes / (1024 * 1024),
            result.duration_seconds,
        )
    return result
