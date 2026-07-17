"""Local audio file validation."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from src.config.media import SUPPORTED_AUDIO_EXTENSIONS, is_supported_audio_extension


class LocalFileExtractionError(RuntimeError):
    """Raised when a local audio input is invalid."""


def extract_local_audio(
    source_path: str,
    output_dir: Optional[Union[Path, str]] = None,
) -> Path:
    """Validate a local audio file and return its normalized absolute path."""
    path = Path(source_path).expanduser()

    if not path.exists():
        raise LocalFileExtractionError(f"Local audio file does not exist: {source_path}")
    if not path.is_file():
        raise LocalFileExtractionError(f"Local audio path is not a file: {source_path}")
    if not is_supported_audio_extension(path.suffix):
        supported = ", ".join(sorted(SUPPORTED_AUDIO_EXTENSIONS))
        raise LocalFileExtractionError(
            f"Unsupported audio file type '{path.suffix}'. Supported: {supported}"
        )

    return path.resolve()
