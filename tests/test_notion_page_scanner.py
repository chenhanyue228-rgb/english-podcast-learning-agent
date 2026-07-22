from __future__ import annotations

from src.agent.notion_page_scanner import scan_changed_podcast_pages


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
    assert notion.data_sources.query_calls[0]["filter"]["last_edited_time"]["after"] == "2026-07-18T12:00:00Z"
    assert notion.data_sources.query_calls[1]["start_cursor"] == "cursor_1"
