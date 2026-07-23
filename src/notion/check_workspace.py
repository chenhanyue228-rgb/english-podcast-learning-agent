"""Validate the Notion workspace schema for English Audio Learning Agent.

Usage:
    python -m src.notion.check_workspace

The script reads database IDs from environment variables via
src.notion.config, retrieves each database from Notion, and verifies that the
required properties exist with the expected Notion property types.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from src.notion.config import NotionConfigError, load_notion_config
from src.notion.schema import REQUIRED_DATABASE_PROPERTIES, WORKSPACE_DATABASE_ORDER

if TYPE_CHECKING:
    from notion_client import Client


@dataclass
class DatabaseValidationResult:
    """Validation state for one Notion database."""

    name: str
    exists: bool = False
    missing_properties: list[str] = field(default_factory=list)
    type_mismatches: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return (
            self.exists
            and not self.missing_properties
            and not self.type_mismatches
            and self.error is None
        )


def fetch_database(notion: "Client", database_id: str, name: str) -> dict[str, Any]:
    """Retrieve a Notion data source/database or raise a readable error."""
    from notion_client import APIResponseError

    try:
        if hasattr(notion, "data_sources"):
            return notion.data_sources.retrieve(data_source_id=database_id)
        return notion.databases.retrieve(database_id=database_id)
    except APIResponseError as exc:
        raise RuntimeError(f"{name} could not be retrieved: {exc}") from exc


def validate_database(
    name: str,
    database: dict[str, Any],
    required_properties: dict[str, str],
) -> DatabaseValidationResult:
    """Validate that a database has each required property with the right type."""
    result = DatabaseValidationResult(name=name, exists=True)
    actual_properties = database.get("properties", {})

    for property_name, expected_type in required_properties.items():
        actual_property = actual_properties.get(property_name)
        if actual_property is None:
            result.missing_properties.append(f"{name}.{property_name}")
            continue

        actual_type = actual_property.get("type")
        if actual_type != expected_type:
            result.type_mismatches.append(
                f"{name}.{property_name}: expected {expected_type}, got {actual_type}"
            )

    return result


def validate_workspace() -> list[DatabaseValidationResult]:
    """Connect to Notion and validate the configured workspace databases."""
    try:
        from notion_client import Client
    except ModuleNotFoundError as exc:
        raise NotionConfigError(
            "Missing dependency notion-client. Install dependencies with "
            "pip install -r requirements.txt."
        ) from exc

    config = load_notion_config()
    notion = Client(auth=config.token)
    database_ids = {
        "Podcast Library": config.podcast_database_id,
        "Expression Database": config.expression_database_id,
        "Vocabulary Database": config.vocabulary_database_id,
        "Weekly Review": config.weekly_database_id,
    }

    results: list[DatabaseValidationResult] = []

    for name in WORKSPACE_DATABASE_ORDER:
        database_id = database_ids[name]
        try:
            database = fetch_database(notion, database_id, name)
            results.append(
                validate_database(name, database, REQUIRED_DATABASE_PROPERTIES[name])
            )
        except RuntimeError as exc:
            results.append(DatabaseValidationResult(name=name, error=str(exc)))

    return results


def format_validation_report(results: list[DatabaseValidationResult]) -> str:
    """Create a human-readable validation report."""
    lines: list[str] = []
    missing: list[str] = []
    mismatches: list[str] = []
    errors: list[str] = []

    for result in results:
        lines.append(f"{'✓' if result.is_valid else '✗'} {result.name}")
        missing.extend(result.missing_properties)
        mismatches.extend(result.type_mismatches)
        if result.error:
            errors.append(result.error)

    lines.append("")
    lines.append("Missing:")
    lines.extend(missing or ["None"])

    if mismatches:
        lines.append("")
        lines.append("Type mismatches:")
        lines.extend(mismatches)

    if errors:
        lines.append("")
        lines.append("Errors:")
        lines.extend(errors)

    return "\n".join(lines)


def main() -> int:
    try:
        results = validate_workspace()
    except NotionConfigError as exc:
        print(f"Workspace validation failed: {exc}", file=sys.stderr)
        return 1

    print(format_validation_report(results))
    return 0 if all(result.is_valid for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
