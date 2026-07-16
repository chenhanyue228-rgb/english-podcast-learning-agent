"""Configuration helpers for Notion integrations.

This module centralizes all Notion environment loading and validation so
publishers, reporters, and setup scripts use the same database ID contract.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, TypedDict


ENV_PATH = Path(".env")

NOTION_TOKEN_ENV = "NOTION_TOKEN"
NOTION_PARENT_PAGE_ID_ENV = "NOTION_PARENT_PAGE_ID"
PODCAST_DATABASE_ID_ENV = "NOTION_PODCAST_LIBRARY_DATABASE_ID"
EXPRESSION_DATABASE_ID_ENV = "NOTION_EXPRESSION_DATABASE_ID"
WEEKLY_DATABASE_ID_ENV = "NOTION_WEEKLY_REVIEW_DATABASE_ID"


class NotionConfigError(RuntimeError):
    """Raised when required Notion configuration is missing or invalid."""


class NotionDatabaseMapping(TypedDict):
    """Runtime database IDs used by Notion integration modules."""

    podcast_database_id: str
    expression_database_id: str
    weekly_database_id: str


@dataclass(frozen=True)
class NotionConfig:
    """Validated Notion configuration loaded from environment variables."""

    token: str
    podcast_database_id: str
    expression_database_id: str
    weekly_database_id: str

    @property
    def database_mapping(self) -> NotionDatabaseMapping:
        """Return the project database IDs with stable internal key names."""
        return {
            "podcast_database_id": self.podcast_database_id,
            "expression_database_id": self.expression_database_id,
            "weekly_database_id": self.weekly_database_id,
        }


def load_dotenv(path: Path = ENV_PATH) -> None:
    """Load simple KEY=VALUE pairs from a .env file into os.environ.

    Existing environment variables win over .env values. This keeps CI,
    shell exports, and secret managers authoritative.
    """
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_env(
    env: Mapping[str, str],
    variable_name: str,
    help_text: str,
) -> str:
    """Return a non-empty environment value or raise a clear config error."""
    value = env.get(variable_name, "").strip()
    if value:
        return value

    raise NotionConfigError(
        f"Missing required environment variable {variable_name}. {help_text}"
    )


def load_notion_config(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path = ENV_PATH,
) -> NotionConfig:
    """Load and validate all Notion configuration needed after setup.

    Required variables:
    - NOTION_TOKEN
    - NOTION_PODCAST_LIBRARY_DATABASE_ID
    - NOTION_EXPRESSION_DATABASE_ID
    - NOTION_WEEKLY_REVIEW_DATABASE_ID
    """
    if env is None:
        load_dotenv(dotenv_path)
        env = os.environ

    return NotionConfig(
        token=require_env(
            env,
            NOTION_TOKEN_ENV,
            "Create a Notion integration token and add it to .env.",
        ),
        podcast_database_id=require_env(
            env,
            PODCAST_DATABASE_ID_ENV,
            "Run python -m src.notion.setup_workspace to create the workspace.",
        ),
        expression_database_id=require_env(
            env,
            EXPRESSION_DATABASE_ID_ENV,
            "Run python -m src.notion.setup_workspace to create the workspace.",
        ),
        weekly_database_id=require_env(
            env,
            WEEKLY_DATABASE_ID_ENV,
            "Run python -m src.notion.setup_workspace to create the workspace.",
        ),
    )


def get_database_mapping(
    env: Mapping[str, str] | None = None,
    dotenv_path: Path = ENV_PATH,
) -> NotionDatabaseMapping:
    """Return only the validated Notion database ID mapping."""
    return load_notion_config(env=env, dotenv_path=dotenv_path).database_mapping
