"""Experimental YouTube extraction retained outside the supported v1 product."""

from __future__ import annotations

from pathlib import Path
from typing import Union


class YouTubeExtractionError(RuntimeError):
    """Raised when YouTube audio extraction fails."""


def extract_youtube_audio(source_url: str, output_dir: Union[Path, str]) -> Path:
    """Experimentally download YouTube audio and convert it to mp3."""
    try:
        from yt_dlp import YoutubeDL
    except ModuleNotFoundError as exc:
        raise YouTubeExtractionError(
            "Missing dependency yt-dlp. Install dependencies with "
            "pip install -r requirements.txt."
        ) from exc

    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(audio_dir / "%(title).200B-%(id)s.%(ext)s")

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(source_url, download=True)
            prepared_path = Path(ydl.prepare_filename(info))
    except Exception as exc:  # yt-dlp raises several custom exception classes.
        raise YouTubeExtractionError(f"Failed to extract YouTube audio: {exc}") from exc

    mp3_path = prepared_path.with_suffix(".mp3")
    if not mp3_path.exists():
        raise YouTubeExtractionError(
            f"yt-dlp completed but mp3 output was not found: {mp3_path}"
        )

    return mp3_path
