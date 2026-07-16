"""Initialize the Notion workspace databases for English Podcast Learning Agent.

Usage:
    python -m src.notion.setup_workspace --parent-page-id <notion_page_id>

Environment:
    NOTION_TOKEN is required.
    NOTION_PARENT_PAGE_ID can be used instead of the CLI argument.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from notion_client import APIResponseError, Client

from src.notion.config import (
    ENV_PATH,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    NotionConfigError,
    load_dotenv,
)
from src.notion.schema import EXPRESSION_CATEGORIES, REVIEW_STATUSES, SOURCE_TYPES


class WorkspaceSetupError(RuntimeError):
    """Raised when the Notion workspace cannot be initialized."""


def create_notion_client(token: str | None = None) -> Client:
    notion_token = token or os.getenv(NOTION_TOKEN_ENV)
    if not notion_token:
        raise WorkspaceSetupError(
            "NOTION_TOKEN is required. Add it to .env or export it before running."
        )

    return Client(auth=notion_token)


def title_property() -> dict[str, Any]:
    return {"title": {}}


def rich_text_property() -> dict[str, Any]:
    return {"rich_text": {}}


def select_property(options: list[str]) -> dict[str, Any]:
    return {"select": {"options": [{"name": option} for option in options]}}


def relation_property(data_source_id: str) -> dict[str, Any]:
    return {"relation": {"data_source_id": data_source_id}}


def create_database(
    notion: Client,
    parent_page_id: str,
    name: str,
    properties: dict[str, Any],
) -> str:
    try:
        response = notion.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": name}}],
            properties=properties,
        )
    except APIResponseError as exc:
        raise WorkspaceSetupError(
            f"Failed to create Notion database '{name}': {exc.code} {exc.message}"
        ) from exc

    data_sources = response.get("data_sources") or []
    data_source_id = data_sources[0].get("id") if data_sources else response.get("id")
    if not data_source_id:
        raise WorkspaceSetupError(
            f"Notion did not return a data source ID for database '{name}'."
        )

    return data_source_id


def update_database_properties(
    notion: Client,
    database_id: str,
    properties: dict[str, Any],
    database_name: str,
) -> None:
    try:
        if hasattr(notion, "data_sources"):
            notion.data_sources.update(data_source_id=database_id, properties=properties)
        else:
            notion.databases.update(database_id=database_id, properties=properties)
    except APIResponseError as exc:
        raise WorkspaceSetupError(
            f"Failed to update Notion database '{database_name}': "
            f"{exc.code} {exc.message}"
        ) from exc


def create_base_databases(notion: Client, parent_page_id: str) -> dict[str, str]:
    podcast_library_id = create_database(
        notion=notion,
        parent_page_id=parent_page_id,
        name="Podcast Library",
        properties={
            "Title": title_property(),
            "URL": {"url": {}},
            "Source Type": select_property(SOURCE_TYPES),
            "Date": {"date": {}},
            "Topic": select_property([]),
            "Difficulty": select_property([]),
            "Short Summary": rich_text_property(),
        },
    )

    expression_database_id = create_database(
        notion=notion,
        parent_page_id=parent_page_id,
        name="Expression Database",
        properties={
            "Expression": title_property(),
            "Category": select_property(
                [
                    *EXPRESSION_CATEGORIES,
                ]
            ),
            "Review Status": select_property(REVIEW_STATUSES),
        },
    )

    weekly_review_id = create_database(
        notion=notion,
        parent_page_id=parent_page_id,
        name="Weekly Review",
        properties={
            "Week": title_property(),
            "Date": {"date": {}},
            "Expression Count": {"number": {"format": "number"}},
            "Vocabulary Count": {"number": {"format": "number"}},
            "AI Summary": rich_text_property(),
        },
    )

    return {
        "NOTION_PODCAST_LIBRARY_DATABASE_ID": podcast_library_id,
        "NOTION_EXPRESSION_DATABASE_ID": expression_database_id,
        "NOTION_WEEKLY_REVIEW_DATABASE_ID": weekly_review_id,
    }


def wire_database_relations(notion: Client, database_ids: dict[str, str]) -> None:
    podcast_library_id = database_ids["NOTION_PODCAST_LIBRARY_DATABASE_ID"]
    expression_database_id = database_ids["NOTION_EXPRESSION_DATABASE_ID"]
    weekly_review_id = database_ids["NOTION_WEEKLY_REVIEW_DATABASE_ID"]

    update_database_properties(
        notion=notion,
        database_id=expression_database_id,
        database_name="Expression Database",
        properties={"Source Podcast": relation_property(podcast_library_id)},
    )

    update_database_properties(
        notion=notion,
        database_id=weekly_review_id,
        database_name="Weekly Review",
        properties={
            "Podcasts": relation_property(podcast_library_id),
        },
    )


def update_env_file(values: dict[str, str], path: Path = ENV_PATH) -> None:
    existing: dict[str, str] = {}
    ordered_keys: list[str] = []

    if path.exists():
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            if "=" not in raw_line or raw_line.strip().startswith("#"):
                continue
            key, value = raw_line.split("=", 1)
            key = key.strip()
            existing[key] = value.strip()
            ordered_keys.append(key)

    existing.update(values)

    for key in values:
        if key not in ordered_keys:
            ordered_keys.append(key)

    content = "\n".join(f"{key}={existing[key]}" for key in ordered_keys)
    path.write_text(f"{content}\n", encoding="utf-8")


def setup_workspace(parent_page_id: str, notion: Client | None = None) -> dict[str, str]:
    notion_client = notion or create_notion_client()
    database_ids = create_base_databases(notion_client, parent_page_id)
    wire_database_relations(notion_client, database_ids)
    update_env_file(database_ids)
    return database_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the Notion databases required by English Podcast Learning Agent."
    )
    parser.add_argument(
        "--parent-page-id",
        default=os.getenv(NOTION_PARENT_PAGE_ID_ENV),
        help="Notion page ID where the databases should be created.",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    try:
        if not args.parent_page_id:
            raise WorkspaceSetupError(
                "A parent Notion page ID is required. Pass --parent-page-id or set "
                "NOTION_PARENT_PAGE_ID in .env."
            )

        database_ids = setup_workspace(parent_page_id=args.parent_page_id)
        print("Created Notion databases:")
        for key, value in database_ids.items():
            print(f"{key}={value}")
    except (WorkspaceSetupError, NotionConfigError) as exc:
        print(f"Workspace setup failed: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
