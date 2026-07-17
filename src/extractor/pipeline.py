"""Complete source extraction pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Union

from src.extractor.audio_downloader import (
    AudioDownloadError,
    convert_to_mp3,
    download_audio,
    validate_audio_file,
)
from src.extractor.local_file import extract_local_audio
from src.extractor.podcast_resolver import resolve_podcast_audio_url
from src.extractor.router import SourceRouterError, SourceType, detect_source


LOGGER = logging.getLogger(__name__)


class SourceExtractionError(RuntimeError):
    """Raised when the source extraction pipeline cannot produce local mp3."""


PathLike = Union[Path, str]
AudioDownloader = Callable[[str, PathLike], Path]
PodcastResolver = Callable[[str], str]
LocalValidator = Callable[[str], Path]
Mp3Converter = Callable[[Path], Path]


def normalize_local_audio_to_mp3(
    source_path: str,
    local_validator: LocalValidator = extract_local_audio,
    mp3_converter: Mp3Converter = convert_to_mp3,
) -> Path:
    """Validate a local audio file and return a local mp3 path."""
    local_audio_path = local_validator(source_path)
    if local_audio_path.suffix.lower() == ".mp3":
        return validate_audio_file(local_audio_path)
    return mp3_converter(local_audio_path)


def extract_audio_from_source(
    source: str,
    output_dir: PathLike = Path("data/audio"),
    audio_downloader: AudioDownloader = download_audio,
    podcast_resolver: PodcastResolver = resolve_podcast_audio_url,
    local_validator: LocalValidator = extract_local_audio,
    mp3_converter: Mp3Converter = convert_to_mp3,
) -> Path:
    """Convert any supported user source into a normalized local mp3 path."""
    try:
        detection = detect_source(source)
        LOGGER.info("Detected source type: %s", detection.type.value)

        if detection.type == SourceType.YOUTUBE:
            return audio_downloader(detection.source, output_dir)

        if detection.type in {SourceType.APPLE_PODCAST, SourceType.PODCAST_RSS}:
            audio_url = podcast_resolver(detection.source)
            LOGGER.info("Resolved podcast source to audio URL")
            return audio_downloader(audio_url, output_dir)

        if detection.type == SourceType.DIRECT_AUDIO:
            return audio_downloader(detection.source, output_dir)

        if detection.type == SourceType.LOCAL_AUDIO:
            return normalize_local_audio_to_mp3(
                detection.source,
                local_validator=local_validator,
                mp3_converter=mp3_converter,
            )

        raise SourceExtractionError(f"Unsupported source type: {detection.type.value}")
    except (SourceRouterError, AudioDownloadError) as exc:
        raise SourceExtractionError(f"Source extraction failed: {exc}") from exc
    except Exception as exc:
        if isinstance(exc, SourceExtractionError):
            raise
        raise SourceExtractionError(f"Source extraction failed: {exc}") from exc
