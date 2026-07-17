"""Podcast audio download.

This module downloads already-resolved playable audio URLs. Podcast page
resolution lives in src.extractor.podcast_resolver.
"""

from __future__ import annotations

import re
import logging
from pathlib import Path
from typing import Union
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from src.config.media import is_supported_audio_extension
from src.extractor.podcast_resolver import resolve_podcast_audio_url


LOGGER = logging.getLogger(__name__)


class PodcastExtractionError(RuntimeError):
    """Raised when podcast audio cannot be resolved or downloaded."""


def is_direct_audio_url(url: str) -> bool:
    return is_supported_audio_extension(Path(urlparse(url).path).suffix)


def safe_filename_from_url(url: str, fallback: str = "podcast_audio") -> str:
    raw_name = Path(unquote(urlparse(url).path)).name or fallback
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    return safe_name or fallback


def download_audio_file(audio_url: str, output_dir: Union[Path, str]) -> Path:
    """Download an audio URL to output_dir and return its local path."""
    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    destination = audio_dir / safe_filename_from_url(audio_url)

    request = Request(audio_url, headers={"User-Agent": "EnglishPodcastLearningAgent/0.1"})
    LOGGER.info("Downloading podcast audio")
    try:
        with urlopen(request, timeout=60) as response:
            content_type = response.headers.get("Content-Type", "")
            if not (content_type.startswith("audio/") or is_direct_audio_url(audio_url)):
                raise PodcastExtractionError(
                    f"Podcast URL did not return audio content: {content_type or 'unknown'}"
                )

            with destination.open("wb") as output_file:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output_file.write(chunk)
    except PodcastExtractionError:
        raise
    except Exception as exc:
        raise PodcastExtractionError(f"Failed to download podcast audio: {exc}") from exc

    return destination.resolve()


def extract_podcast_audio(source_url: str, output_dir: Union[Path, str]) -> Path:
    """Resolve a podcast input URL to playable audio and download it."""
    audio_url = resolve_podcast_audio_url(source_url)
    return download_audio_file(audio_url, output_dir)
