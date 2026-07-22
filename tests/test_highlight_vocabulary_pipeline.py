from __future__ import annotations

from src.workflow.highlight_vocabulary_pipeline import (
    build_highlight_vocabulary_preview,
    preview_highlight_vocabulary,
)


class FakeBlockChildren:
    def __init__(self, results):
        self.results = results

    def list(self, **kwargs):
        return {"results": self.results}


class FakeNotion:
    def __init__(self, results):
        self.blocks = type("Blocks", (), {"children": FakeBlockChildren(results)})()


def test_preview_highlight_vocabulary_maps_pink_highlights() -> None:
    notion = FakeNotion(
        [
            {
                "id": "block_1",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "conversation",
                            "text": {"content": "conversation"},
                            "annotations": {"color": "pink_background"},
                        },
                        {
                            "plain_text": " also shows how to negotiate with investors.",
                            "text": {"content": " also shows how to negotiate with investors."},
                            "annotations": {"color": "default"},
                        },
                    ]
                },
            }
        ]
    )

    preview = build_highlight_vocabulary_preview("11111111111111111111111111111111", notion=notion)
    payload = preview.to_json()

    assert payload["count"] == 1
    assert payload["items"][0]["word"] == "conversation"
    assert payload["items"][0]["context"] == "conversation also shows how to negotiate with investors."
    assert payload["items"][0]["source_page_id"] == "11111111111111111111111111111111"


def test_preview_highlight_vocabulary_returns_json_serializable_dict() -> None:
    notion = FakeNotion([])

    payload = preview_highlight_vocabulary("page_1", notion=notion)

    assert payload == {
        "page_id": "page_1",
        "total_highlights": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "approved": [],
        "rejected": [],
    }


def test_preview_highlight_vocabulary_applies_candidate_filter() -> None:
    notion = FakeNotion(
        [
            {
                "id": "block_1",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "Christensen",
                            "text": {"content": "Christensen"},
                            "annotations": {"color": "pink_background"},
                        },
                        {
                            "plain_text": " explains the idea.",
                            "text": {"content": " explains the idea."},
                            "annotations": {"color": "default"},
                        },
                    ]
                },
            },
            {
                "id": "block_2",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "conversation",
                            "text": {"content": "conversation"},
                            "annotations": {"color": "pink_background"},
                        },
                        {
                            "plain_text": " also shows how to negotiate with investors.",
                            "text": {"content": " also shows how to negotiate with investors."},
                            "annotations": {"color": "default"},
                        },
                    ]
                },
            },
        ]
    )

    payload = preview_highlight_vocabulary("11111111111111111111111111111111", notion=notion)

    assert payload["total_highlights"] == 2
    assert payload["approved_count"] == 1
    assert payload["rejected_count"] == 1
    assert payload["approved"][0]["word"] == "conversation"
    assert payload["rejected"][0]["word"] == "Christensen"
    assert payload["rejected"][0]["reason"] == "person name"
