"""Detect Podcast Library pages that were edited since the last sync."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


@dataclass(frozen=True)
class ChangedPodcastPage:
    page_id: str
    last_edited_time: str


def _parse_notion_timestamp(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _query_pages(
    notion: Any,
    database_id: str,
    checkpoint: str,
    page_size: int = 100,
) -> Iterable[Mapping[str, Any]]:
    query_kwargs: dict[str, Any] = {
        "page_size": page_size,
        "sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}],
    }
    if checkpoint.strip():
        query_kwargs["filter"] = {
            "timestamp": "last_edited_time",
            "last_edited_time": {"after": checkpoint.strip()},
        }

    cursor: Optional[str] = None
    while True:
        current_kwargs = dict(query_kwargs)
        if cursor:
            current_kwargs["start_cursor"] = cursor

        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
            current_kwargs["data_source_id"] = database_id
            response = notion.data_sources.query(**current_kwargs)
        else:
            current_kwargs["database_id"] = database_id
            response = notion.databases.query(**current_kwargs)

        results = response.get("results", [])
        if isinstance(results, list):
            for page in results:
                if isinstance(page, Mapping):
                    yield page

        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        if not isinstance(cursor, str) or not cursor.strip():
            break


def scan_changed_podcast_pages(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    last_scan_time: str = "",
) -> list[ChangedPodcastPage]:
    """Return Podcast Library pages edited after the last successful scan."""
    if notion is None or podcast_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id

    latest_checkpoint = _parse_notion_timestamp(last_scan_time)
    changed: list[ChangedPodcastPage] = []

    for page in _query_pages(notion, podcast_database_id, last_scan_time):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        edited_at = str(page.get("last_edited_time") or page.get("created_time") or "").strip()
        if latest_checkpoint is not None:
            page_timestamp = _parse_notion_timestamp(edited_at)
            if page_timestamp is not None and page_timestamp <= latest_checkpoint:
                continue
        changed.append(ChangedPodcastPage(page_id=page_id, last_edited_time=edited_at))

    return changed
