"""Shared media configuration for source detection and audio handling."""

from __future__ import annotations


SUPPORTED_AUDIO_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".webm"})


def is_supported_audio_extension(extension: str) -> bool:
    """Return True when extension is supported by source handling."""
    return extension.lower() in SUPPORTED_AUDIO_EXTENSIONS
