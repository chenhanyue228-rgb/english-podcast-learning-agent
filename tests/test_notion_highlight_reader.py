from __future__ import annotations

from src.notion.highlight_reader import debug_print_pink_highlights, read_pink_highlights


class FakeBlockChildren:
    def __init__(self, results_by_block_id):
        self.results_by_block_id = results_by_block_id
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        block_id = kwargs["block_id"]
        return {"results": self.results_by_block_id.get(block_id, [])}


class FakeNotion:
    def __init__(self, results_by_block_id):
        self.blocks = type("Blocks", (), {"children": FakeBlockChildren(results_by_block_id)})()


def test_read_pink_highlights_detects_pink_background_blocks() -> None:
    notion = FakeNotion(
        {
            "page_1": [
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
                                "plain_text": " explains that good negotiators listen.",
                                "text": {"content": " explains that good negotiators listen."},
                                "annotations": {"color": "default"},
                            },
                        ]
                    },
                },
                {
                    "id": "block_2",
                    "type": "quote",
                    "quote": {
                        "rich_text": [
                            {
                                "plain_text": "conversation",
                                "text": {"content": "conversation"},
                                "annotations": {"color": "pink"},
                            },
                            {
                                "plain_text": " also shows how to negotiate with investors.",
                                "text": {"content": " also shows how to negotiate with investors."},
                                "annotations": {"color": "default"},
                            },
                        ]
                    },
                },
                {
                    "id": "block_3",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "plain",
                                "text": {"content": "plain"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
            ]
        }
    )

    highlights = read_pink_highlights("page_1", notion=notion)

    assert len(highlights) == 2
    assert highlights[0]["text"] == "Christensen"
    assert highlights[0]["color"] == "pink_background"
    assert highlights[0]["block_id"] == "block_1"
    assert highlights[0]["context"] == "Christensen explains that good negotiators listen."
    assert highlights[1]["text"] == "conversation"
    assert highlights[1]["color"] == "pink"
    assert highlights[1]["context"] == "conversation also shows how to negotiate with investors."


def test_debug_print_pink_highlights_prints_no_result_when_empty(capsys) -> None:
    notion = FakeNotion({"page_1": []})

    highlights = debug_print_pink_highlights("page_1", notion=notion)
    captured = capsys.readouterr().out

    assert highlights == []
    assert "NO_PINK_HIGHLIGHT_FOUND" in captured


def test_read_pink_highlights_recurses_into_table_rows() -> None:
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "table_1",
                    "type": "table",
                    "has_children": True,
                    "table": {},
                }
            ],
            "table_1": [
                {
                    "id": "table_row_1",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [
                                {
                                    "plain_text": "fundraising",
                                    "text": {"content": "fundraising"},
                                    "annotations": {"color": "pink_background"},
                                }
                            ],
                            [
                                {
                                    "plain_text": "joint problem solving",
                                    "text": {"content": "joint problem solving"},
                                    "annotations": {"color": "default"},
                                }
                            ],
                        ]
                    },
                }
            ],
        }
    )

    highlights = read_pink_highlights("page_1", notion=notion)

    assert len(highlights) == 1
    assert highlights[0]["text"] == "fundraising"
    assert highlights[0]["color"] == "pink_background"
