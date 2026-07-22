"""Sync the Vocabulary Database schema for an existing Notion workspace.

This script is intentionally narrower than ``setup_workspace``. It is meant
for the case where Podcast Library, Expression Database, and Weekly Review
already exist, and Vocabulary Database needs to be created or brought into
schema alignment without touching Podcast Library or Expression Database.

The script does not run automatically. It only creates the database when
invoked manually.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Optional

from notion_client import APIResponseError, Client

from src.notion.config import (
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    EXPRESSION_DATABASE_ID_ENV,
    WEEKLY_DATABASE_ID_ENV,
    PODCAST_DATABASE_ID_ENV,
    VOCABULARY_DATABASE_ID_ENV,
    load_dotenv,
)
from src.notion.setup_workspace import (
    create_notion_client,
    rich_text_property,
    select_property,
    title_property,
    update_env_file,
)
from src.notion.schema import REVIEW_STATUSES, VOCABULARY_CATEGORIES


class VocabularyDatabaseSetupError(RuntimeError):
    """Raised when the Vocabulary Database cannot be created."""


def _require_env(variable_name: str) -> str:
    value = os.getenv(variable_name, "").strip()
    if not value:
        raise VocabularyDatabaseSetupError(
            f"Missing required environment variable {variable_name}."
        )
    return value


def _relation_property(target_data_source_id: str, relation_name: str) -> dict[str, Any]:
    return {
        "relation": {
            "data_source_id": target_data_source_id,
            "single_property": {
                "synced_property_name": relation_name,
            },
            "dual_property": {
                "synced_property_name": relation_name,
            },
        }
    }


def _create_database(
    notion: Client,
    parent_page_id: str,
    podcast_library_id: str,
) -> str:
    try:
        response = notion.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": "Vocabulary Database"}}],
            properties={
                "Name": title_property(),
                "Original Context": rich_text_property(),
                "Meaning": rich_text_property(),
                "Professional Category": select_property(VOCABULARY_CATEGORIES),
                "Source": _relation_property(podcast_library_id, "Vocabulary"),
                "Source Page ID": rich_text_property(),
                "First Seen": {"date": {}},
                "Review Status": select_property(REVIEW_STATUSES),
                "Last Review": {"date": {}},
                "Usage Example": rich_text_property(),
                "Personal Note": rich_text_property(),
            },
        )
    except APIResponseError as exc:
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        raise VocabularyDatabaseSetupError(
            f"Failed to create Vocabulary Database: {exc.code} {detail}"
        ) from exc

    data_sources = response.get("data_sources") or []
    database_id = data_sources[0].get("id") if data_sources else response.get("id")
    if not database_id:
        raise VocabularyDatabaseSetupError(
            "Notion did not return a data source ID for Vocabulary Database."
        )
    return str(database_id)


def _update_database(
    notion: Client,
    database_id: str,
    podcast_library_id: str,
) -> None:
    try:
        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "update"):
            notion.data_sources.update(
                data_source_id=database_id,
                properties={
                    "Name": title_property(),
                    "Original Context": rich_text_property(),
                    "Meaning": rich_text_property(),
                    "Professional Category": select_property(VOCABULARY_CATEGORIES),
                    "Source": _relation_property(podcast_library_id, "Vocabulary"),
                    "Source Page ID": rich_text_property(),
                    "First Seen": {"date": {}},
                    "Review Status": select_property(REVIEW_STATUSES),
                    "Last Review": {"date": {}},
                    "Usage Example": rich_text_property(),
                    "Personal Note": rich_text_property(),
                },
            )
        else:
            notion.databases.update(
                database_id=database_id,
                properties={
                    "Name": title_property(),
                    "Original Context": rich_text_property(),
                    "Meaning": rich_text_property(),
                    "Professional Category": select_property(VOCABULARY_CATEGORIES),
                    "Source": _relation_property(podcast_library_id, "Vocabulary"),
                    "Source Page ID": rich_text_property(),
                    "First Seen": {"date": {}},
                    "Review Status": select_property(REVIEW_STATUSES),
                    "Last Review": {"date": {}},
                    "Usage Example": rich_text_property(),
                    "Personal Note": rich_text_property(),
                },
            )
    except APIResponseError as exc:
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        raise VocabularyDatabaseSetupError(
            f"Failed to update Vocabulary Database: {exc.code} {detail}"
        ) from exc


def create_vocabulary_database(parent_page_id: str, notion: Optional[Client] = None) -> str:
    load_dotenv()
    notion_client = notion or create_notion_client()
    podcast_library_id = _require_env(PODCAST_DATABASE_ID_ENV)
    database_id = _create_database(notion_client, parent_page_id, podcast_library_id)
    update_env_file({VOCABULARY_DATABASE_ID_ENV: database_id})
    return database_id


def sync_vocabulary_database_schema(
    notion: Optional[Client] = None,
    parent_page_id: Optional[str] = None,
) -> str:
    """Create or update the Vocabulary Database and wire it to Weekly Review."""
    load_dotenv()
    notion_client = notion or create_notion_client()
    podcast_library_id = _require_env(PODCAST_DATABASE_ID_ENV)
    vocabulary_database_id = os.getenv(VOCABULARY_DATABASE_ID_ENV, "").strip()
    weekly_review_database_id = os.getenv(WEEKLY_DATABASE_ID_ENV, "").strip()
    expression_database_id = os.getenv(EXPRESSION_DATABASE_ID_ENV, "").strip()

    if vocabulary_database_id:
        _update_database(notion_client, vocabulary_database_id, podcast_library_id)
    else:
        if not parent_page_id:
            raise VocabularyDatabaseSetupError(
                f"Missing required environment variable {VOCABULARY_DATABASE_ID_ENV} "
                "and no parent page id was provided for creation."
            )
        vocabulary_database_id = _create_database(
            notion_client,
            parent_page_id,
            podcast_library_id,
        )
        update_env_file({VOCABULARY_DATABASE_ID_ENV: vocabulary_database_id})

    if weekly_review_database_id:
        try:
            if hasattr(notion_client, "data_sources") and hasattr(notion_client.data_sources, "update"):
                notion_client.data_sources.update(
                    data_source_id=weekly_review_database_id,
                    properties={
                        "Vocabulary": _relation_property(vocabulary_database_id, "Vocabulary")
                    },
                )
            else:
                notion_client.databases.update(
                    database_id=weekly_review_database_id,
                    properties={
                        "Vocabulary": _relation_property(vocabulary_database_id, "Vocabulary")
                    },
                )
        except APIResponseError as exc:
            detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
            raise VocabularyDatabaseSetupError(
                f"Failed to update Weekly Review relation: {exc.code} {detail}"
            ) from exc

    if expression_database_id:
        # No schema changes are required for Expression Database in this step.
        pass

    return vocabulary_database_id


def main() -> int:
    try:
        load_dotenv()
        parent_page_id = os.getenv(NOTION_PARENT_PAGE_ID_ENV, "").strip() or None
        database_id = sync_vocabulary_database_schema(parent_page_id=parent_page_id)
    except Exception as exc:
        print(f"Vocabulary Database setup failed: {exc}", file=sys.stderr)
        return 1

    print("Vocabulary Database synced:")
    print(f"{VOCABULARY_DATABASE_ID_ENV}={database_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
