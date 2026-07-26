from __future__ import annotations

from src.agent.notion_page_scanner import (
    overlap_checkpoint,
    scan_changed_podcast_pages,
    scan_podcast_pages_with_overlap,
)
from src.notion.pagination import (
    NOTION_PAGINATION_INVALID,
    NotionPaginationError,
)

import pytest


class FakeDataSources:
    def __init__(self) -> None:
        self.query_calls = []
        self.responses = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return {"results": [], "has_more": False}


class FakeNotion:
    def __init__(self) -> None:
        self.data_sources = FakeDataSources()


def test_scan_changed_podcast_pages_filters_by_checkpoint_and_paginates() -> None:
    notion = FakeNotion()
    notion.data_sources.responses = [
        {
            "results": [
                {"id": "page_1", "last_edited_time": "2026-07-18T10:00:00Z"},
            ],
            "has_more": True,
            "next_cursor": "cursor_1",
        },
        {
            "results": [
                {"id": "page_2", "last_edited_time": "2026-07-19T10:00:00Z"},
            ],
            "has_more": False,
        },
    ]

    changed = scan_changed_podcast_pages(
        notion=notion,
        podcast_database_id="podcast_db",
        last_scan_time="2026-07-18T12:00:00Z",
    )

    assert [item.page_id for item in changed] == ["page_2"]
    assert notion.data_sources.query_calls[0]["data_source_id"] == "podcast_db"
    assert notion.data_sources.query_calls[0]["filter"][
        "last_edited_time"
    ]["after"] == "2026-07-18T12:00:00Z"
    assert notion.data_sources.query_calls[1]["start_cursor"] == "cursor_1"


def test_overlap_checkpoint_defaults_to_five_minutes() -> None:
    assert overlap_checkpoint("2026-07-18T12:00:00Z") == (
        "2026-07-18T11:55:00Z"
    )


def test_overlap_scan_requeries_checkpoint_equality() -> None:
    notion = FakeNotion()
    notion.data_sources.responses = [
        {
            "results": [
                {
                    "id": "page_equal",
                    "last_edited_time": "2026-07-18T12:00:00Z",
                }
            ],
            "has_more": False,
        }
    ]

    changed = scan_podcast_pages_with_overlap(
        notion=notion,
        podcast_database_id="podcast_db",
        watermark="2026-07-18T12:00:00Z",
    )

    assert [item.page_id for item in changed] == ["page_equal"]
    assert notion.data_sources.query_calls[0]["filter"][
        "last_edited_time"
    ]["after"] == "2026-07-18T11:55:00Z"


def test_overlap_scan_without_watermark_queries_all_pages() -> None:
    notion = FakeNotion()

    assert scan_podcast_pages_with_overlap(
        notion=notion,
        podcast_database_id="podcast_db",
    ) == []
    assert "filter" not in notion.data_sources.query_calls[0]


def test_overlap_scan_ignores_items_older_than_overlap_window() -> None:
    notion = FakeNotion()
    notion.data_sources.responses = [
        {
            "results": [
                {
                    "id": "too_old",
                    "last_edited_time": "2026-07-18T11:54:59Z",
                },
                {
                    "id": "boundary",
                    "last_edited_time": "2026-07-18T11:55:00Z",
                },
            ],
            "has_more": False,
        }
    ]

    changed = scan_podcast_pages_with_overlap(
        notion=notion,
        podcast_database_id="podcast_db",
        watermark="2026-07-18T12:00:00Z",
    )

    assert [item.page_id for item in changed] == ["boundary"]


@pytest.mark.parametrize("next_cursor", [None, "", "   "])
def test_data_source_pagination_missing_or_blank_cursor_fails_closed(
    next_cursor,
) -> None:
    notion = FakeNotion()
    notion.data_sources.responses = [
        {
            "results": [
                {
                    "id": "partial-page",
                    "last_edited_time": "2026-07-18T12:00:00Z",
                }
            ],
            "has_more": True,
            "next_cursor": next_cursor,
        }
    ]

    with pytest.raises(NotionPaginationError) as raised:
        scan_podcast_pages_with_overlap(
            notion=notion,
            podcast_database_id="podcast_db",
        )

    assert raised.value.code == NOTION_PAGINATION_INVALID
    assert str(raised.value) == NOTION_PAGINATION_INVALID


def test_data_source_pagination_repeated_cursor_fails_closed() -> None:
    notion = FakeNotion()
    notion.data_sources.responses = [
        {
            "results": [],
            "has_more": True,
            "next_cursor": "cursor_1",
        },
        {
            "results": [],
            "has_more": True,
            "next_cursor": "cursor_1",
        },
    ]

    with pytest.raises(NotionPaginationError):
        scan_podcast_pages_with_overlap(
            notion=notion,
            podcast_database_id="podcast_db",
        )


def test_legacy_database_query_pagination_also_fails_closed() -> None:
    legacy = type("LegacyNotion", (), {})()
    legacy.databases = FakeDataSources()
    legacy.databases.responses = [
        {
            "results": [],
            "has_more": True,
            "next_cursor": "",
        }
    ]

    with pytest.raises(NotionPaginationError):
        scan_podcast_pages_with_overlap(
            notion=legacy,
            podcast_database_id="podcast_db",
        )
