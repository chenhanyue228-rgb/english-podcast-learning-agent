"""Application settings for English Podcast Learning Agent.

The settings layer stays intentionally small. It centralizes environment
loading for extraction, transcription, generated artifacts, and Notion access.
AI reasoning is handled by the Codex Skill workflow, not by a Python API key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional


DEFAULT_ENV_PATH = Path(".env")


class SettingsError(RuntimeError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True)
class AppSettings:
    """Runtime settings shared by the CLI pipeline modules."""

    environment: str
    log_level: str
    data_dir: Path
    audio_output_dir: Path
    transcript_output_dir: Path
    notion_token: Optional[str]
    notion_parent_page_id: Optional[str]
    notion_podcast_database_id: Optional[str]


def load_env_file(path: Path = DEFAULT_ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from .env without overriding shell values."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _get_path(env: Mapping[str, str], key: str, default: str) -> Path:
    return Path(env.get(key, default)).expanduser()


def load_settings(
    env: Optional[Mapping[str, str]] = None,
    dotenv_path: Path = DEFAULT_ENV_PATH,
) -> AppSettings:
    """Load application settings from environment variables and .env."""
    if env is None:
        load_env_file(dotenv_path)
        env = os.environ

    data_dir = _get_path(env, "EPLA_DATA_DIR", "data")
    return AppSettings(
        environment=env.get("EPLA_ENV", "development"),
        log_level=env.get("EPLA_LOG_LEVEL", "INFO"),
        data_dir=data_dir,
        audio_output_dir=_get_path(env, "EPLA_AUDIO_OUTPUT_DIR", str(data_dir / "audio")),
        transcript_output_dir=_get_path(
            env,
            "EPLA_TRANSCRIPT_OUTPUT_DIR",
            str(data_dir / "transcripts"),
        ),
        notion_token=env.get("NOTION_TOKEN"),
        notion_parent_page_id=env.get("NOTION_PARENT_PAGE_ID"),
        notion_podcast_database_id=env.get("NOTION_PODCAST_LIBRARY_DATABASE_ID"),
    )
