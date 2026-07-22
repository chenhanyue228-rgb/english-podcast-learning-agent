"""Low-level Notion reader helpers for weekly learning extraction.

This module keeps read-only Notion access isolated from extraction logic.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from src.notion.uploader import create_notion_client as create_notion_sdk_client


class NotionReaderError(RuntimeError):
    """Raised when the Notion reader cannot complete a read operation."""


def create_notion_client(token: Optional[str] = None) -> Any:
    """Create the shared Notion SDK client."""
    return create_notion_sdk_client(token)


def query_database(
    notion: Any,
    database_id: str,
    **kwargs: Any,
) -> Mapping[str, Any]:
    """Query a Notion database/data source using whichever SDK method exists."""
    if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
        return notion.data_sources.query(data_source_id=database_id, **kwargs)
    if hasattr(notion, "databases") and hasattr(notion.databases, "query"):
        return notion.databases.query(database_id=database_id, **kwargs)
    raise NotionReaderError(
        "This Notion client does not support database queries."
    )


def retrieve_page(notion: Any, page_id: str) -> Mapping[str, Any]:
    """Retrieve a single Notion page."""
    if not hasattr(notion, "pages") or not hasattr(notion.pages, "retrieve"):
        raise NotionReaderError("This Notion client does not support page retrieval.")
    return notion.pages.retrieve(page_id=page_id)


def list_block_children(notion: Any, block_id: str, page_size: int = 100) -> Mapping[str, Any]:
    """List direct children blocks for one page or block."""
    if not hasattr(notion, "blocks") or not hasattr(notion.blocks, "children"):
        raise NotionReaderError("This Notion client does not support block listing.")
    if not hasattr(notion.blocks.children, "list"):
        raise NotionReaderError("This Notion client does not support block children listing.")
    return notion.blocks.children.list(block_id=block_id, page_size=page_size)
