from __future__ import annotations

from src.notion.discussion_reader import normalize_comment_event, normalize_comment_events


def test_normalize_comment_event_preserves_public_rest_comment_shape() -> None:
    events = normalize_comment_event(
        {
            "id": "comment_1",
            "created_time": "2026-07-18T20:00:00.000Z",
            "discussion_id": "discussion_1",
            "highlighted_text": "assumptions",
            "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
            "parent": {"type": "block_id", "block_id": "block_1"},
        },
        page_id="page_1",
        block_id="block_1",
    )

    assert len(events) == 1
    event = events[0]
    assert event.page_id == "page_1"
    assert event.block_id == "block_1"
    assert event.comment_id == "comment_1"
    assert event.discussion_id == "discussion_1"
    assert event.comment_text == "3"
    assert event.highlighted_text == "assumptions"
    assert event.to_mapping()["anchor_text"] == "assumptions"


def test_normalize_comment_events_expands_discussion_comments() -> None:
    events = normalize_comment_events(
        [
            {
                "id": "discussion_1",
                "discussion": {
                    "id": "discussion_1",
                    "rangeText": "assumptions",
                    "comments": [
                        {
                            "id": "comment_1",
                            "text": "3",
                        }
                    ],
                },
            }
        ],
        page_id="page_1",
        block_id="block_1",
    )

    assert len(events) == 1
    event = events[0]
    assert event.comment_id == "comment_1"
    assert event.discussion_id == "discussion_1"
    assert event.comment_text == "3"
    assert event.highlighted_text == "assumptions"
    mapped = event.to_mapping()
    assert mapped["discussion"]["rangeText"] == "assumptions"
    assert mapped["rich_text"][0]["plain_text"] == "3"
