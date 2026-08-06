"""Safely align Vocabulary schema in an already-bound Notion workspace.

Workspace creation belongs to ``src.notion.setup_workspace``. This legacy
entrypoint remains only for compatibility and refuses to create databases or
repair a partially configured workspace.
"""

from __future__ import annotations

import sys
from typing import Any, Optional

from notion_client import APIResponseError, Client

from src.notion.config import NotionConfig, load_notion_config
from src.notion.schema import (
    PODCAST_LIBRARY,
    REVIEW_STATUSES,
    VOCABULARY_DATABASE,
)
from src.notion.setup_workspace import (
    create_notion_client,
    select_property,
    title_property,
)
from src.notion.target_binding import (
    TARGET_PARENT_MISMATCH,
    NotionTargetBindingError,
    ensure_notion_target_binding_for_write,
    normalize_notion_id,
)


LEGACY_VOCABULARY_DATABASE_CREATION_DISABLED = (
    "legacy_vocabulary_database_creation_disabled"
)
VOCABULARY_SCHEMA_UPDATE_FAILED = "vocabulary_schema_update_failed"
VOCABULARY_SCHEMA_SYNC_FAILED = "vocabulary_schema_sync_failed"


class VocabularyDatabaseSetupError(RuntimeError):
    """A stable, redacted failure from the legacy schema compatibility CLI."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _relation_property(target_data_source_id: str) -> dict[str, Any]:
    return {
        "relation": {
            "data_source_id": target_data_source_id,
            "single_property": {},
        }
    }


def _vocabulary_properties(podcast_library_id: str) -> dict[str, Any]:
    return {
        "Name": title_property(),
        "Source": _relation_property(podcast_library_id),
        "First Seen": {"date": {}},
        "Review Status": select_property(REVIEW_STATUSES),
        "Last Review": {"date": {}},
    }


def _create_database(
    notion: Client,
    parent_page_id: str,
    podcast_library_id: str,
) -> str:
    del notion, parent_page_id, podcast_library_id
    raise VocabularyDatabaseSetupError(
        LEGACY_VOCABULARY_DATABASE_CREATION_DISABLED
    )


def _update_database(
    notion: Client,
    database_id: str,
    podcast_library_id: str,
    *,
    config: Optional[NotionConfig] = None,
) -> None:
    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={
            VOCABULARY_DATABASE: database_id,
            PODCAST_LIBRARY: podcast_library_id,
        },
        config=config,
    )
    if not hasattr(notion, "data_sources") or not hasattr(
        notion.data_sources,
        "update",
    ):
        raise VocabularyDatabaseSetupError(VOCABULARY_SCHEMA_UPDATE_FAILED)

    try:
        notion.data_sources.update(
            data_source_id=database_id,
            properties=_vocabulary_properties(podcast_library_id),
        )
    except APIResponseError:
        raise VocabularyDatabaseSetupError(
            VOCABULARY_SCHEMA_UPDATE_FAILED
        ) from None
    except Exception:
        raise VocabularyDatabaseSetupError(
            VOCABULARY_SCHEMA_UPDATE_FAILED
        ) from None


def create_vocabulary_database(
    parent_page_id: str,
    notion: Optional[Client] = None,
) -> str:
    del parent_page_id, notion
    raise VocabularyDatabaseSetupError(
        LEGACY_VOCABULARY_DATABASE_CREATION_DISABLED
    )


def sync_vocabulary_database_schema(
    notion: Optional[Client] = None,
    parent_page_id: Optional[str] = None,
) -> str:
    """Update Vocabulary schema only after the complete target proof passes."""
    config = load_notion_config()
    if parent_page_id and normalize_notion_id(parent_page_id) != (
        normalize_notion_id(config.target_parent_page_id)
    ):
        raise NotionTargetBindingError(TARGET_PARENT_MISMATCH)

    notion_client = notion or create_notion_client(config.token)
    ensure_notion_target_binding_for_write(notion_client, config=config)
    _update_database(
        notion_client,
        config.vocabulary_database_id,
        config.podcast_database_id,
        config=config,
    )
    return config.vocabulary_database_id


def main() -> int:
    try:
        sync_vocabulary_database_schema()
    except NotionTargetBindingError as exc:
        print(f"Vocabulary Database setup failed: {exc.code}", file=sys.stderr)
        return 1
    except VocabularyDatabaseSetupError as exc:
        print(f"Vocabulary Database setup failed: {exc.code}", file=sys.stderr)
        return 1
    except Exception:
        print(
            f"Vocabulary Database setup failed: {VOCABULARY_SCHEMA_SYNC_FAILED}",
            file=sys.stderr,
        )
        return 1

    print("Vocabulary Database schema synced.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
