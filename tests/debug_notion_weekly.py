"""Minimal Notion connectivity probe for Phase 4A weekly review debugging.

Run directly:

    python3 tests/debug_notion_weekly.py

This script uses the same Notion client initialization as Phase 3 publishing,
queries the Podcast Library and Expression Database directly, and prints the
first record metadata so we can distinguish connectivity problems from empty
result sets or filter mistakes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

from notion_client import APIResponseError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


def _query_database(notion: Any, database_id: str) -> Mapping[str, Any]:
    if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
        return notion.data_sources.query(data_source_id=database_id)
    return notion.databases.query(database_id=database_id)


def _print_database_probe(label: str, database_id: str, notion: Any) -> None:
    print(f"{label} database id: {database_id}")
    try:
        response = _query_database(notion, database_id)
    except APIResponseError as exc:
        status = getattr(exc, "status", "unknown")
        print(f"HTTP response status: {status}")
        print(f"Query error: {exc.code} {getattr(exc, 'message', str(exc))}")
        return
    except Exception as exc:
        print("HTTP response status: unknown")
        print(f"Query error: {exc}")
        return

    status = response.get("status", 200)
    results = response.get("results", [])
    print(f"HTTP response status: {status}")
    print(f"Returned record count: {len(results)}")
    if results:
        first = results[0]
        print("First record properties:")
        print(json.dumps(first.get("properties", {}), ensure_ascii=False, indent=2))
    else:
        print("First record properties: {}")


def main() -> int:
    config = load_notion_config()
    notion = create_notion_client(config.token)

    print("Phase 3 / Phase 4A Notion access comparison")
    print(f"NOTION_TOKEN configured: {bool(config.token)}")
    print()

    _print_database_probe("Podcast Library", config.podcast_database_id, notion)
    print()
    _print_database_probe("Expression Database", config.expression_database_id, notion)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
