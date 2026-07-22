"""Download supported audio sources to local mp3 files."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Union
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from src.config.media import is_supported_audio_extension


LOGGER = logging.getLogger(__name__)

DOWNLOAD_CHUNK_SIZE_BYTES = 8192
DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_MAX_RETRIES = 3
DOWNLOAD_PROGRESS_INTERVAL_BYTES = 5 * 1024 * 1024
YOUTUBE_COOKIE_FILE_ENV = "YOUTUBE_COOKIE_FILE"


class AudioDownloadError(RuntimeError):
    """Raised when an audio source cannot be downloaded or converted."""


YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "youtu.be",
    "music.youtube.com",
}

def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    return host in YOUTUBE_HOSTS or host.endswith(".youtube.com")


def is_audio_url(url: str) -> bool:
    return is_supported_audio_extension(Path(urlparse(url).path).suffix)


def safe_filename_from_url(url: str, fallback: str = "audio") -> str:
    raw_name = Path(unquote(urlparse(url).path)).name or fallback
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", raw_name).strip("._")
    return safe_name or fallback


def validate_audio_file(path: Path) -> Path:
    """Validate that a downloaded or converted file exists and is non-empty."""
    if not path.exists():
        raise AudioDownloadError(f"Audio file was not created: {path}")
    if not path.is_file():
        raise AudioDownloadError(f"Audio output is not a file: {path}")
    if path.stat().st_size <= 0:
        raise AudioDownloadError(f"Audio file is empty: {path}")
    if path.suffix.lower() != ".mp3":
        raise AudioDownloadError(f"Audio output is not mp3: {path}")
    return path.resolve()


def _cleanup_partial_file(path: Path) -> None:
    if path.exists():
        path.unlink()


def _validate_remote_content_type(content_type: str) -> None:
    if content_type and not (
        content_type.startswith("audio/")
        or content_type in {"application/octet-stream", "binary/octet-stream"}
    ):
        raise AudioDownloadError(f"URL did not return audio content: {content_type}")


def _reuse_existing_audio(destination: Path) -> Optional[Path]:
    """Return an existing normalized mp3 path when local audio can be reused."""
    if destination.suffix.lower() == ".mp3" and destination.exists():
        LOGGER.info("Reusing existing remote audio: %s", destination)
        return validate_audio_file(destination)

    converted_mp3 = destination.with_suffix(".mp3")
    if converted_mp3.exists():
        LOGGER.info("Reusing existing converted audio: %s", converted_mp3)
        return validate_audio_file(converted_mp3)

    if destination.exists():
        LOGGER.info("Reusing existing downloaded audio before conversion: %s", destination)
        return convert_to_mp3(destination)

    return None


def _stream_response_to_file(response, destination: Path) -> None:
    bytes_written = 0
    next_progress_log = DOWNLOAD_PROGRESS_INTERVAL_BYTES

    with destination.open("wb") as output_file:
        while True:
            chunk = response.read(DOWNLOAD_CHUNK_SIZE_BYTES)
            if not chunk:
                break
            output_file.write(chunk)
            bytes_written += len(chunk)

            if bytes_written >= next_progress_log:
                LOGGER.info(
                    "Downloaded %.1f MB to %s",
                    bytes_written / (1024 * 1024),
                    destination.name,
                )
                next_progress_log += DOWNLOAD_PROGRESS_INTERVAL_BYTES

    if bytes_written <= 0:
        raise AudioDownloadError(f"Downloaded audio file is empty: {destination}")


def _download_remote_audio_once(
    url: str,
    destination: Path,
    timeout: int,
) -> None:
    request = Request(url, headers={"User-Agent": "EnglishPodcastLearningAgent/0.1"})
    with urlopen(request, timeout=timeout) as response:
        _validate_remote_content_type(response.headers.get("Content-Type", ""))
        _stream_response_to_file(response, destination)


def _resolve_ffmpeg_executable() -> str:
    """Return a usable system or project-bundled ffmpeg executable."""
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        bundled_ffmpeg = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except (ImportError, RuntimeError, OSError) as exc:
        raise AudioDownloadError(
            "YouTube conversion failed: ffmpeg is unavailable. Install ffmpeg or "
            "install project dependencies with pip install -r requirements.txt."
        ) from exc

    if not bundled_ffmpeg.is_file():
        raise AudioDownloadError(
            "YouTube conversion failed: the bundled ffmpeg executable was not found. "
            "Reinstall project dependencies with pip install -r requirements.txt."
        )
    return str(bundled_ffmpeg)


def _resolve_youtube_cookie_file() -> Optional[Path]:
    """Validate an explicitly supplied cookie file without reading its contents."""
    configured_path = os.getenv(YOUTUBE_COOKIE_FILE_ENV, "")
    if not configured_path:
        return None

    cookie_file = Path(configured_path).expanduser()
    if not cookie_file.is_file():
        raise AudioDownloadError(
            f"YouTube cookie configuration failed: {YOUTUBE_COOKIE_FILE_ENV} does not "
            "point to an existing file. Provide a user-exported Netscape cookie file "
            "or unset the variable."
        )
    return cookie_file.resolve()


def _classify_youtube_download_error(exc: Exception) -> str:
    """Return a safe, actionable error for common yt-dlp failures."""
    message = str(exc)
    lowered = message.lower()

    if (
        "sign in to confirm" in lowered
        or "not a bot" in lowered
        or "login required" in lowered
    ):
        return (
            "YouTube authentication is required by the platform's anti-bot checks. "
            "Retrying without a changed network may not help. Optionally set "
            f"{YOUTUBE_COOKIE_FILE_ENV} to a user-exported Netscape cookie file; "
            "never commit or share that file."
        )
    if "unsupported url" in lowered:
        return "The supplied URL is not supported by the YouTube downloader."
    if any(
        token in lowered
        for token in (
            "requested format is not available",
            "no video formats found",
            "no formats found",
            "does not have any formats",
        )
    ):
        return "YouTube did not expose a downloadable audio stream for this video."
    if any(
        token in lowered
        for token in (
            "unable to download",
            "connection",
            "network",
            "timed out",
            "temporary failure",
            "name or service not known",
        )
    ):
        return "YouTube download failed because of a network error; retry is reasonable."
    if "ffmpeg" in lowered or "postprocess" in lowered:
        return "YouTube audio conversion failed in ffmpeg. Verify the ffmpeg runtime."
    return f"YouTube audio download failed: {message}"


def download_youtube_audio(url: str, output_dir: Union[Path, str]) -> Path:
    """Experimental, non-v1 YouTube download and mp3 conversion path."""
    try:
        from yt_dlp import YoutubeDL
    except ModuleNotFoundError as exc:
        raise AudioDownloadError(
            "Missing dependency yt-dlp. Run python3 scripts/bootstrap_environment.py."
        ) from exc

    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(audio_dir / "%(title).200B-%(id)s.%(ext)s")
    ffmpeg_path = _resolve_ffmpeg_executable()
    cookie_file = _resolve_youtube_cookie_file()

    options = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_path,
        "retries": DOWNLOAD_MAX_RETRIES,
        "fragment_retries": DOWNLOAD_MAX_RETRIES,
        "socket_timeout": DOWNLOAD_TIMEOUT_SECONDS,
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
    if cookie_file:
        options["cookiefile"] = str(cookie_file)
        LOGGER.warning(
            "Using an explicit user-supplied YouTube cookie file. Keep it private "
            "and outside version control."
        )

    LOGGER.info("Downloading YouTube audio")
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            prepared_path = Path(ydl.prepare_filename(info))
    except Exception as exc:
        raise AudioDownloadError(_classify_youtube_download_error(exc)) from exc

    return validate_audio_file(prepared_path.with_suffix(".mp3"))


def download_remote_audio(
    url: str,
    output_dir: Union[Path, str],
    timeout: int = DOWNLOAD_TIMEOUT_SECONDS,
    max_retries: int = DOWNLOAD_MAX_RETRIES,
) -> Path:
    """Download a direct podcast enclosure or audio URL."""
    if not is_audio_url(url):
        raise AudioDownloadError(f"URL does not look like a supported audio file: {url}")
    if max_retries <= 0:
        raise AudioDownloadError("max_retries must be greater than 0.")

    audio_dir = Path(output_dir)
    audio_dir.mkdir(parents=True, exist_ok=True)
    destination = audio_dir / safe_filename_from_url(url, fallback="audio")
    existing_audio = _reuse_existing_audio(destination)
    if existing_audio:
        return existing_audio

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        LOGGER.info(
            "Downloading remote audio (attempt %s/%s): %s",
            attempt,
            max_retries,
            destination.name,
        )
        try:
            _download_remote_audio_once(url, destination, timeout)
            break
        except AudioDownloadError as exc:
            _cleanup_partial_file(destination)
            last_error = exc
            if "did not return audio content" in str(exc):
                raise
            LOGGER.warning(
                "Remote audio download attempt %s/%s failed: %s",
                attempt,
                max_retries,
                exc,
            )
        except (TimeoutError, URLError, OSError) as exc:
            _cleanup_partial_file(destination)
            last_error = exc
            LOGGER.warning(
                "Remote audio download attempt %s/%s failed: %s",
                attempt,
                max_retries,
                exc,
            )
        except Exception as exc:
            _cleanup_partial_file(destination)
            last_error = exc
            LOGGER.warning(
                "Remote audio download attempt %s/%s failed: %s",
                attempt,
                max_retries,
                exc,
            )
    else:
        raise AudioDownloadError(
            "Failed to download remote audio after "
            f"{max_retries} attempts: {last_error}"
        ) from last_error

    if destination.suffix.lower() == ".mp3":
        return validate_audio_file(destination)

    return convert_to_mp3(destination)


def convert_to_mp3(input_path: Path) -> Path:
    """Convert a local audio file to mp3 using ffmpeg."""
    if not input_path.exists() or input_path.stat().st_size <= 0:
        raise AudioDownloadError(f"Cannot convert missing or empty file: {input_path}")

    ffmpeg_path = _resolve_ffmpeg_executable()

    output_path = input_path.with_suffix(".mp3")
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(output_path),
    ]

    LOGGER.info("Converting audio to mp3")
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise AudioDownloadError(f"ffmpeg conversion failed: {exc.stderr}") from exc

    return validate_audio_file(output_path)


def download_audio(
    source_url: str,
    output_dir: Union[Path, str] = Path("data/audio"),
) -> Path:
    """Download any supported audio URL and return a normalized local mp3 path."""
    cleaned = source_url.strip()
    if not cleaned:
        raise AudioDownloadError("Audio URL is empty.")

    if is_youtube_url(cleaned):
        return download_youtube_audio(cleaned, output_dir)

    return download_remote_audio(cleaned, output_dir)
