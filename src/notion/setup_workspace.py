"""Initialize the Notion workspace databases for English Audio Learning Agent.

Usage:
    python -m src.notion.setup_workspace --parent-page-id <notion_page_id_or_url>

Environment:
    NOTION_TOKEN is required.
    NOTION_PARENT_PAGE_ID can be used instead of the CLI argument. It may be a
    raw Notion page ID or a copied Notion page URL.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from typing import Any, Optional

from notion_client import APIResponseError, Client

from src.notion.config import (
    ENV_PATH,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    NotionConfigError,
    load_dotenv,
)
from src.notion.schema import (
    COMMONNESS_LEVELS,
    EXPRESSION_CATEGORIES,
    REVIEW_STATUSES,
    SOURCE_TYPES,
    VOCABULARY_CATEGORIES,
)


class WorkspaceSetupError(RuntimeError):
    """Raised when the Notion workspace cannot be initialized."""


NOTION_ID_PATTERN = re.compile(r"([a-fA-F0-9]{32})")


def normalize_notion_id(value: str) -> str:
    """Return a dashed Notion ID from a raw ID or copied Notion URL.

    Notion page URLs usually contain a 32-character hex ID, while API calls
    accept either dashed or undashed IDs. We normalize to the dashed form to
    keep .env readable and consistent.
    """
    cleaned = value.strip()
    if not cleaned:
        raise WorkspaceSetupError("A Notion page ID or page URL is required.")

    compact = cleaned.replace("-", "")
    if re.fullmatch(r"[a-fA-F0-9]{32}", compact):
        raw_id = compact
    else:
        match = NOTION_ID_PATTERN.search(cleaned.replace("-", ""))
        if not match:
            raise WorkspaceSetupError(
                "Could not find a Notion page ID. Paste either the raw page ID "
                "or a copied Notion page URL."
            )
        raw_id = match.group(1)

    return (
        f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-"
        f"{raw_id[16:20]}-{raw_id[20:32]}"
    ).lower()


def create_notion_client(token: Optional[str] = None) -> Client:
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
            "Commonness": select_property(COMMONNESS_LEVELS),
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
        },
    )

    vocabulary_database_id = create_database(
        notion=notion,
        parent_page_id=parent_page_id,
        name="Vocabulary Database",
        properties={
            "Name": title_property(),
            "Original Context": rich_text_property(),
            "Meaning": rich_text_property(),
            "Professional Category": select_property(VOCABULARY_CATEGORIES),
            "Source": relation_property(podcast_library_id),
            "Source Page ID": rich_text_property(),
            "First Seen": {"date": {}},
            "Review Status": select_property(REVIEW_STATUSES),
            "Last Review": {"date": {}},
            "Usage Example": rich_text_property(),
            "Personal Note": rich_text_property(),
        },
    )

    return {
        "NOTION_PODCAST_LIBRARY_DATABASE_ID": podcast_library_id,
        "NOTION_EXPRESSION_DATABASE_ID": expression_database_id,
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID": weekly_review_id,
        "NOTION_VOCABULARY_DATABASE_ID": vocabulary_database_id,
    }


def wire_database_relations(notion: Client, database_ids: dict[str, str]) -> None:
    podcast_library_id = database_ids["NOTION_PODCAST_LIBRARY_DATABASE_ID"]
    expression_database_id = database_ids["NOTION_EXPRESSION_DATABASE_ID"]
    weekly_review_id = database_ids.get(
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
        database_ids.get("NOTION_WEEKLY_REVIEW_DATABASE_ID", ""),
    )
    vocabulary_database_id = database_ids["NOTION_VOCABULARY_DATABASE_ID"]

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

    update_database_properties(
        notion=notion,
        database_id=vocabulary_database_id,
        database_name="Vocabulary Database",
        properties={"Source": relation_property(podcast_library_id)},
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


def setup_workspace(parent_page_id: str, notion: Optional[Client] = None) -> dict[str, str]:
    notion_client = notion or create_notion_client()
    normalized_parent_page_id = normalize_notion_id(parent_page_id)
    update_env_file({NOTION_PARENT_PAGE_ID_ENV: normalized_parent_page_id})
    database_ids = create_base_databases(notion_client, normalized_parent_page_id)
    wire_database_relations(notion_client, database_ids)
    update_env_file(database_ids)
    return database_ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create the Notion databases required by English Audio Learning Agent."
    )
    parser.add_argument(
        "--parent-page-id",
        default=os.getenv(NOTION_PARENT_PAGE_ID_ENV),
        help=(
            "Notion parent page ID or copied page URL where the databases "
            "should be created."
        ),
    )
    parser.add_argument(
        "--print-onboarding",
        action="store_true",
        help="Print the recommended two-mode Notion onboarding flow and exit.",
    )
    return parser.parse_args()


def print_onboarding() -> None:
    """Print the supported Notion onboarding modes for new users."""
    print(
        "\n".join(
            [
                "Notion onboarding modes:",
                "",
                "Mode 1: Guided Local Setup",
                "1. Install dependencies: pip install -r requirements.txt",
                "2. Create a Notion internal integration and copy its token.",
                "3. Create a parent Notion page and share it with the integration.",
                "4. Add NOTION_TOKEN to .env.",
                "5. Run: python -m src.notion.setup_workspace --parent-page-id <page_url_or_id>",
                "6. Run: python -m src.notion.check_workspace",
                "",
                "Mode 2: Codex Assisted Setup",
                "1. Connect the Notion plugin in Codex.",
                "2. Ask Codex to create or inspect the Notion workspace.",
                "3. Sync the resulting database IDs into .env for local CLI runs.",
                "",
                "The local Python project still needs NOTION_TOKEN for independent CLI execution.",
            ]
        )
    )


def main() -> int:
    load_dotenv()
    args = parse_args()

    try:
        if args.print_onboarding:
            print_onboarding()
            return 0

        if not args.parent_page_id:
            raise WorkspaceSetupError(
                "A parent Notion page ID or URL is required. Pass "
                "--parent-page-id with a copied Notion page URL, or set "
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
