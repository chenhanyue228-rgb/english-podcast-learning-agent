"""Fail-closed helpers for Notion cursor pagination."""

from __future__ import annotations

from typing import Any, Mapping, Optional


NOTION_PAGINATION_INVALID = "notion_pagination_invalid"


class NotionPaginationError(RuntimeError):
    """A fixed-code pagination failure that never exposes cursor data."""

    def __init__(self) -> None:
        self.code = NOTION_PAGINATION_INVALID
        super().__init__(self.code)


def next_notion_cursor(
    response: Mapping[str, Any],
    *,
    current_cursor: Optional[str],
    visited_cursors: set[str],
) -> Optional[str]:
    """Return a progressing cursor or fail when a partial page is unsafe."""
    if not response.get("has_more"):
        return None

    raw_cursor = response.get("next_cursor")
    if not isinstance(raw_cursor, str):
        raise NotionPaginationError()
    next_cursor = raw_cursor.strip()
    if (
        not next_cursor
        or next_cursor == current_cursor
        or next_cursor in visited_cursors
    ):
        raise NotionPaginationError()
    visited_cursors.add(next_cursor)
    return next_cursor
