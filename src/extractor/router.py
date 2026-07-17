"""Unified user input detection.

This module is intentionally independent. It does not download audio, call
external APIs, validate remote availability, or import extractor/resolver
modules. Later modules consume its normalized source type.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.parse import urlparse

from src.config.media import is_supported_audio_extension


class SourceType(str, Enum):
    """Supported source types accepted by the source pipeline."""

    YOUTUBE = "youtube"
    APPLE_PODCAST = "apple_podcast"
    PODCAST_RSS = "podcast_rss"
    DIRECT_AUDIO = "direct_audio"
    LOCAL_AUDIO = "local_audio"


class SourceRouterError(RuntimeError):
    """Raised when user input cannot be classified."""


@dataclass(frozen=True)
class SourceDetection:
    """Normalized source detection result."""

    type: SourceType
    source: str

    def to_dict(self) -> dict[str, str]:
        """Return the public API shape expected by callers."""
        return {"type": self.type.value}


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

APPLE_PODCAST_HOSTS = {
    "podcasts.apple.com",
    "itunes.apple.com",
}

RSS_EXTENSIONS = {
    ".atom",
    ".rss",
    ".xml",
}


def is_url(source: str) -> bool:
    """Return True when source is an HTTP(S) URL."""
    parsed = urlparse(source)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalized_host(source: str) -> str:
    return urlparse(source).netloc.lower()


def _url_path_suffix(source: str) -> str:
    return Path(urlparse(source).path.lower()).suffix


def is_youtube_url(source: str) -> bool:
    host = _normalized_host(source)
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def is_apple_podcast_url(source: str) -> bool:
    return _normalized_host(source) in APPLE_PODCAST_HOSTS


def is_direct_audio_url(source: str) -> bool:
    return is_supported_audio_extension(_url_path_suffix(source))


def is_podcast_rss_url(source: str) -> bool:
    parsed = urlparse(source)
    path = parsed.path.lower()
    return _url_path_suffix(source) in RSS_EXTENSIONS or "feed" in path or "rss" in path


def is_local_audio_path(source: str) -> bool:
    return is_supported_audio_extension(Path(source).expanduser().suffix)


def detect_source(source: str) -> SourceDetection:
    """Detect and normalize a user-provided source.

    The detector only classifies input. It does not check whether local files
    exist, whether URLs are reachable, or whether podcast feeds contain audio.
    """
    cleaned = source.strip()
    if not cleaned:
        raise SourceRouterError("Input source is empty.")

    if is_url(cleaned):
        if is_youtube_url(cleaned):
            source_type = SourceType.YOUTUBE
        elif is_apple_podcast_url(cleaned):
            source_type = SourceType.APPLE_PODCAST
        elif is_direct_audio_url(cleaned):
            source_type = SourceType.DIRECT_AUDIO
        elif is_podcast_rss_url(cleaned):
            source_type = SourceType.PODCAST_RSS
        else:
            raise SourceRouterError(
                "Unsupported URL type. The source pipeline supports YouTube URLs, "
                "Apple Podcasts page URLs, Podcast RSS URLs, direct audio URLs, "
                "and local audio files. Generic podcast platform pages are not "
                "supported yet."
            )

        return SourceDetection(type=source_type, source=cleaned)

    if is_local_audio_path(cleaned):
        return SourceDetection(type=SourceType.LOCAL_AUDIO, source=cleaned)

    raise SourceRouterError(
        "Unsupported local file type. Provide a supported audio file path."
    )


def detect_source_type(source: str) -> SourceType:
    """Return only the normalized source type."""
    return detect_source(source).type
