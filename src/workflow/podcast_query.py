"""Query Podcast Library pages for weekly learning extraction."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from src.workflow.notion_client import NotionReaderError, query_database


class PodcastQueryError(RuntimeError):
    """Raised when Podcast Library pages cannot be queried."""


def _query_pages(
    notion: Any,
    database_id: str,
    start_date: str,
    end_date: str,
    start_cursor: Optional[str] = None,
) -> Mapping[str, Any]:
    query_filter = {
        "and": [
            {"property": "Date", "date": {"on_or_after": start_date}},
            {"property": "Date", "date": {"on_or_before": end_date}},
        ]
    }
    kwargs: dict[str, Any] = {"filter": query_filter}
    if start_cursor:
        kwargs["start_cursor"] = start_cursor
    return query_database(notion, database_id, **kwargs)


def query_podcast_pages(
    notion: Any,
    database_id: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    """Return Podcast Library page stubs for the requested date range."""
    pages: list[dict[str, Any]] = []
    start_cursor: Optional[str] = None

    while True:
        try:
            response = _query_pages(
                notion=notion,
                database_id=database_id,
                start_date=start_date,
                end_date=end_date,
                start_cursor=start_cursor,
            )
        except NotionReaderError as exc:
            raise PodcastQueryError(str(exc)) from exc
        except Exception as exc:
            raise PodcastQueryError(f"Failed to query Podcast Library pages: {exc}") from exc

        results = response.get("results", [])
        if isinstance(results, list):
            for page in results:
                if not isinstance(page, Mapping):
                    continue
                page_id = str(page.get("id", "")).strip()
                if not page_id:
                    continue
                pages.append(
                    {
                        "page_id": page_id,
                        "properties": dict(page.get("properties", {}))
                        if isinstance(page.get("properties", {}), Mapping)
                        else {},
                    }
                )

        if not response.get("has_more"):
            break
        start_cursor = str(response.get("next_cursor", "")).strip() or None
        if not start_cursor:
            break

    return pages
