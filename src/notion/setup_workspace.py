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
from typing import Any, Callable, Mapping, Optional

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
    WORKSPACE_DATABASE_ORDER,
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
    return {
        "relation": {
            "data_source_id": data_source_id,
            "single_property": {},
        }
    }


def podcast_library_properties() -> dict[str, Any]:
    return {
        "Title": title_property(),
        "URL": {"url": {}},
        "Source Type": select_property(SOURCE_TYPES),
        "Date": {"date": {}},
        "Topic": select_property([]),
        "Difficulty": select_property([]),
        "Short Summary": rich_text_property(),
    }


def expression_database_properties(podcast_library_id: str) -> dict[str, Any]:
    return {
        "Expression": title_property(),
        "Category": select_property([*EXPRESSION_CATEGORIES]),
        "Commonness": select_property(COMMONNESS_LEVELS),
        "Review Status": select_property(REVIEW_STATUSES),
        "Source Podcast": relation_property(podcast_library_id),
    }


def vocabulary_database_properties(podcast_library_id: str) -> dict[str, Any]:
    return {
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
    }


def weekly_review_properties(podcast_library_id: str) -> dict[str, Any]:
    return {
        "Week": title_property(),
        "Date": {"date": {}},
        "Podcasts": relation_property(podcast_library_id),
    }


def _property_type(property_definition: Mapping[str, Any]) -> str:
    property_types = [
        key
        for key in property_definition
        if key not in {"id", "name", "type"}
    ]
    if len(property_types) != 1:
        raise WorkspaceSetupError("Notion property definition is invalid.")
    return property_types[0]


def retrieve_data_source(
    notion: Client,
    data_source_id: str,
    database_name: str,
) -> dict[str, Any]:
    try:
        return notion.data_sources.retrieve(data_source_id=data_source_id)
    except APIResponseError as exc:
        raise WorkspaceSetupError(
            f"Failed to retrieve Notion database '{database_name}': {exc}"
        ) from exc


def _validate_data_source_properties(
    database_name: str,
    data_source: Mapping[str, Any],
    expected_properties: Mapping[str, Mapping[str, Any]],
) -> None:
    actual_properties = data_source.get("properties") or {}

    for property_name, definition in expected_properties.items():
        expected_type = _property_type(definition)
        actual = actual_properties.get(property_name)
        if actual is None:
            raise WorkspaceSetupError(
                f"Notion database '{database_name}' is missing property "
                f"'{property_name}'."
            )
        if actual.get("type") != expected_type:
            raise WorkspaceSetupError(
                f"Notion database '{database_name}' property '{property_name}' "
                f"has type '{actual.get('type')}', expected '{expected_type}'."
            )

        if expected_type == "relation":
            actual_relation = actual.get("relation") or {}
            expected_relation = definition["relation"]
            if (
                actual_relation.get("data_source_id")
                != expected_relation["data_source_id"]
                or "single_property" not in actual_relation
                or "dual_property" in actual_relation
            ):
                raise WorkspaceSetupError(
                    f"Notion database '{database_name}' relation "
                    f"'{property_name}' is incompatible with the required "
                    "single-property relation."
                )

    title_properties = [
        property_data
        for property_data in actual_properties.values()
        if property_data.get("type") == "title"
    ]
    if len(title_properties) != 1:
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' must contain exactly one title "
            "property."
        )


def create_database(
    notion: Client,
    parent_page_id: str,
    name: str,
    properties: dict[str, Any],
    on_data_source_created: Optional[Callable[[str], None]] = None,
) -> str:
    try:
        response = notion.databases.create(
            parent={"type": "page_id", "page_id": parent_page_id},
            title=[{"type": "text", "text": {"content": name}}],
            initial_data_source={"properties": properties},
        )
    except APIResponseError as exc:
        raise WorkspaceSetupError(
            f"Failed to create Notion database '{name}': {exc}"
        ) from exc

    data_sources = response.get("data_sources") or []
    data_source_id = data_sources[0].get("id") if data_sources else None
    if not data_source_id:
        raise WorkspaceSetupError(
            f"Notion did not return a data source ID for database '{name}'."
        )

    if on_data_source_created is not None:
        on_data_source_created(data_source_id)

    data_source = retrieve_data_source(notion, data_source_id, name)
    _validate_data_source_properties(name, data_source, properties)
    return data_source_id


def update_database_properties(
    notion: Client,
    data_source_id: str,
    properties: dict[str, Any],
    database_name: str,
) -> None:
    try:
        notion.data_sources.update(
            data_source_id=data_source_id,
            properties=properties,
        )
    except APIResponseError as exc:
        raise WorkspaceSetupError(
            f"Failed to update Notion database '{database_name}': {exc}"
        ) from exc


def _relation_requires_repair(
    *,
    database_name: str,
    property_name: str,
    actual_relation: Mapping[str, Any],
    expected_relation: Mapping[str, Any],
) -> bool:
    """Return whether a one-way relation is safely repairable in place."""
    if "dual_property" in actual_relation:
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' relation '{property_name}' "
            "uses a dual-property relation mode. No existing relation was "
            "changed."
        )

    target_id = actual_relation.get("data_source_id")
    if target_id and target_id != expected_relation["data_source_id"]:
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' relation '{property_name}' "
            "points to a different data source. No existing relation was "
            "changed."
        )

    return target_id is None or "single_property" not in actual_relation


def ensure_data_source_schema(
    notion: Client,
    data_source_id: str,
    database_name: str,
    expected_properties: Mapping[str, Mapping[str, Any]],
) -> None:
    """Add or repair known properties without deleting user-defined fields."""
    data_source = retrieve_data_source(notion, data_source_id, database_name)
    actual_properties = data_source.get("properties") or {}
    title_entries = [
        (name, property_data)
        for name, property_data in actual_properties.items()
        if property_data.get("type") == "title"
    ]
    if len(title_entries) != 1:
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' must contain exactly one title "
            "property before it can be repaired."
        )

    expected_title_names = [
        name
        for name, definition in expected_properties.items()
        if _property_type(definition) == "title"
    ]
    if len(expected_title_names) != 1:
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' has an invalid title schema."
        )

    expected_title_name = expected_title_names[0]
    current_title_name, current_title = title_entries[0]
    relations_to_repair: set[str] = set()
    conflicting_title_name = actual_properties.get(expected_title_name)
    if (
        current_title_name != expected_title_name
        and conflicting_title_name is not None
        and conflicting_title_name.get("type") != "title"
    ):
        raise WorkspaceSetupError(
            f"Notion database '{database_name}' cannot rename its title to "
            f"'{expected_title_name}' because that name is already used."
        )

    for property_name, definition in expected_properties.items():
        actual = actual_properties.get(property_name)
        if actual is None:
            continue
        expected_type = _property_type(definition)
        if actual.get("type") != expected_type:
            raise WorkspaceSetupError(
                f"Notion database '{database_name}' property '{property_name}' "
                f"has type '{actual.get('type')}', expected '{expected_type}'. "
                "No existing property was changed."
            )
        if expected_type == "relation":
            actual_relation = actual.get("relation") or {}
            expected_relation = definition["relation"]
            if _relation_requires_repair(
                database_name=database_name,
                property_name=property_name,
                actual_relation=actual_relation,
                expected_relation=expected_relation,
            ):
                relations_to_repair.add(property_name)

    updates: dict[str, Any] = {}
    if current_title_name != expected_title_name:
        title_key = current_title.get("id") or current_title_name
        updates[title_key] = {"name": expected_title_name}

    for property_name, definition in expected_properties.items():
        if _property_type(definition) == "title":
            continue

        actual = actual_properties.get(property_name)
        if actual is None:
            updates[property_name] = dict(definition)
            continue

        if property_name in relations_to_repair:
            updates[property_name] = dict(definition)

    if updates:
        update_database_properties(
            notion=notion,
            data_source_id=data_source_id,
            database_name=database_name,
            properties=updates,
        )

    repaired_data_source = retrieve_data_source(
        notion,
        data_source_id,
        database_name,
    )
    _validate_data_source_properties(
        database_name,
        repaired_data_source,
        expected_properties,
    )


def create_base_databases(
    notion: Client,
    parent_page_id: str,
    existing_ids: Optional[Mapping[str, str]] = None,
    on_database_created: Optional[Callable[[str, str], None]] = None,
) -> dict[str, str]:
    """Create only missing databases and optionally report each successful ID.

    Existing callers may omit both optional arguments and retain the original
    all-four creation behavior. The callback lets first-time setup persist
    progress immediately after each successful Notion API response.
    """
    database_ids = {
        key: value
        for key, value in (existing_ids or {}).items()
        if value
    }

    def get_or_create(
        env_key: str,
        name: str,
        properties: dict[str, Any],
    ) -> str:
        existing_id = database_ids.get(env_key, "")
        if existing_id:
            return existing_id

        database_id = create_database(
            notion=notion,
            parent_page_id=parent_page_id,
            name=name,
            properties=properties,
            on_data_source_created=(
                None
                if on_database_created is None
                else lambda data_source_id: on_database_created(
                    env_key,
                    data_source_id,
                )
            ),
        )
        database_ids[env_key] = database_id
        return database_id

    podcast_library_id = get_or_create(
        "NOTION_PODCAST_LIBRARY_DATABASE_ID",
        "Podcast Library",
        podcast_library_properties(),
    )

    get_or_create(
        "NOTION_EXPRESSION_DATABASE_ID",
        "Expression Database",
        expression_database_properties(podcast_library_id),
    )

    get_or_create(
        "NOTION_VOCABULARY_DATABASE_ID",
        "Vocabulary Database",
        vocabulary_database_properties(podcast_library_id),
    )

    get_or_create(
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
        "Weekly Review",
        weekly_review_properties(podcast_library_id),
    )

    return database_ids


def reconcile_workspace_schema(
    notion: Client,
    database_ids: Mapping[str, str],
) -> None:
    """Repair known non-relation fields in existing data sources in place."""
    podcast_library_id = database_ids["NOTION_PODCAST_LIBRARY_DATABASE_ID"]
    schemas = (
        (
            database_ids["NOTION_PODCAST_LIBRARY_DATABASE_ID"],
            "Podcast Library",
            podcast_library_properties(),
        ),
        (
            database_ids["NOTION_EXPRESSION_DATABASE_ID"],
            "Expression Database",
            expression_database_properties(podcast_library_id),
        ),
        (
            database_ids["NOTION_VOCABULARY_DATABASE_ID"],
            "Vocabulary Database",
            vocabulary_database_properties(podcast_library_id),
        ),
        (
            database_ids.get(
                "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
                database_ids.get("NOTION_WEEKLY_REVIEW_DATABASE_ID", ""),
            ),
            "Weekly Review",
            weekly_review_properties(podcast_library_id),
        ),
    )

    for data_source_id, database_name, properties in schemas:
        non_relation_properties = {
            name: definition
            for name, definition in properties.items()
            if _property_type(definition) != "relation"
        }
        ensure_data_source_schema(
            notion=notion,
            data_source_id=data_source_id,
            database_name=database_name,
            expected_properties=non_relation_properties,
        )


def wire_database_relations(notion: Client, database_ids: dict[str, str]) -> None:
    podcast_library_id = database_ids["NOTION_PODCAST_LIBRARY_DATABASE_ID"]
    expression_database_id = database_ids["NOTION_EXPRESSION_DATABASE_ID"]
    weekly_review_id = database_ids.get(
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
        database_ids.get("NOTION_WEEKLY_REVIEW_DATABASE_ID", ""),
    )
    vocabulary_database_id = database_ids["NOTION_VOCABULARY_DATABASE_ID"]

    ensure_data_source_schema(
        notion=notion,
        data_source_id=expression_database_id,
        database_name="Expression Database",
        expected_properties={
            "Expression": title_property(),
            "Source Podcast": relation_property(podcast_library_id),
        },
    )

    ensure_data_source_schema(
        notion=notion,
        data_source_id=vocabulary_database_id,
        database_name="Vocabulary Database",
        expected_properties={
            "Name": title_property(),
            "Source": relation_property(podcast_library_id),
        },
    )

    ensure_data_source_schema(
        notion=notion,
        data_source_id=weekly_review_id,
        database_name="Weekly Review",
        expected_properties={
            "Week": title_property(),
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


def setup_workspace(parent_page_id: str, notion: Optional[Client] = None) -> dict[str, str]:
    notion_client = notion or create_notion_client()
    normalized_parent_page_id = normalize_notion_id(parent_page_id)
    update_env_file({NOTION_PARENT_PAGE_ID_ENV: normalized_parent_page_id})
    database_ids = create_base_databases(notion_client, normalized_parent_page_id)
    reconcile_workspace_schema(notion_client, database_ids)
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
        help="Print the supported Notion onboarding flow and exit.",
    )
    return parser.parse_args()


def print_onboarding() -> None:
    """Print the supported Notion onboarding flow for new users."""
    print(
        "\n".join(
            [
                "Notion onboarding:",
                "",
                "1. Create .venv: python3 -m venv .venv",
                "2. Install dependencies: ./.venv/bin/python scripts/bootstrap_environment.py",
                "3. Copy .env.example to .env.",
                "4. Create a Notion internal integration and copy its token.",
                "5. Add NOTION_TOKEN to .env.",
                "6. Create a parent Notion page and share it with the integration.",
                "7. Run: ./.venv/bin/python -m src.notion.setup_workspace --parent-page-id <page_url_or_id>",
                "8. Run: ./.venv/bin/python -m src.notion.check_workspace",
                "",
                "The setup creates Podcast Library, Expression Database, Vocabulary Database, and Weekly Review.",
                "Weekly Review stores the Weekly Reflection learning note.",
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

        setup_workspace(parent_page_id=args.parent_page_id)
        print("Notion workspace setup completed:")
        for database_name in WORKSPACE_DATABASE_ORDER:
            print(f"- {database_name}: complete")
    except (WorkspaceSetupError, NotionConfigError):
        print(
            "Workspace setup failed. No configuration values were displayed. "
            "Check the integration permissions, parent page access, and "
            "network, then retry.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
