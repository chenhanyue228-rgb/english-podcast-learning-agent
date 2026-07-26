from __future__ import annotations

from src.notion.highlight_reader import (
    debug_print_pink_highlights,
    read_pink_highlight_occurrences,
    read_pink_highlights,
)


class FakeBlockChildren:
    def __init__(self, results_by_block_id):
        self.results_by_block_id = results_by_block_id
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        block_id = kwargs["block_id"]
        cursor = kwargs.get("start_cursor")
        value = self.results_by_block_id.get((block_id, cursor))
        if value is None:
            value = self.results_by_block_id.get(block_id, [])
        if isinstance(value, dict):
            return value
        return {"results": value}


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


def test_read_pink_highlights_reads_all_paginated_children() -> None:
    first_page = [
        {
            "id": f"plain_{index}",
            "type": "paragraph",
            "paragraph": {"rich_text": []},
        }
        for index in range(100)
    ]
    highlighted = {
        "id": "highlighted_101",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {
                    "plain_text": "exact target",
                    "annotations": {"color": "pink"},
                }
            ]
        },
    }
    notion = FakeNotion(
        {
            ("page_1", None): {
                "results": first_page,
                "has_more": True,
                "next_cursor": "cursor_2",
            },
            ("page_1", "cursor_2"): {
                "results": [highlighted],
                "has_more": False,
                "next_cursor": None,
            },
        }
    )

    highlights = read_pink_highlights("page_1", notion=notion)

    assert [item["text"] for item in highlights] == ["exact target"]
    assert notion.blocks.children.list_calls[-1]["start_cursor"] == "cursor_2"


def test_nested_child_pagination_is_complete() -> None:
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "toggle_1",
                    "type": "toggle",
                    "has_children": True,
                    "toggle": {"rich_text": []},
                }
            ],
            ("toggle_1", None): {
                "results": [],
                "has_more": True,
                "next_cursor": "nested_cursor",
            },
            ("toggle_1", "nested_cursor"): {
                "results": [
                    {
                        "id": "nested_highlight",
                        "type": "quote",
                        "quote": {
                            "rich_text": [
                                {
                                    "plain_text": "nested exact",
                                    "annotations": {
                                        "color": "pink_background"
                                    },
                                }
                            ]
                        },
                    }
                ],
                "has_more": False,
            },
        }
    )

    highlights = read_pink_highlights("page_1", notion=notion)

    assert [item["text"] for item in highlights] == ["nested exact"]


def test_occurrence_preserves_exact_text_and_rich_text_span() -> None:
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "block_1",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "Before ",
                                "annotations": {"color": "default"},
                            },
                            {
                                "plain_text": "Fundraising!",
                                "annotations": {"color": "pink"},
                            },
                        ]
                    },
                }
            ]
        }
    )

    occurrence = read_pink_highlight_occurrences(
        "page_1",
        notion=notion,
    )[0]

    assert occurrence.text == "Fundraising!"
    assert occurrence.rich_text_index == 1
    assert occurrence.start_offset == len("Before ")
    assert occurrence.end_offset == len("Before Fundraising!")
    assert occurrence.position_descriptor.endswith("span=7:19")


def test_table_occurrence_keeps_row_cell_and_item_position() -> None:
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
                    "id": "row_0",
                    "type": "table_row",
                    "table_row": {"cells": [[]]},
                },
                {
                    "id": "row_1",
                    "type": "table_row",
                    "table_row": {
                        "cells": [
                            [],
                            [
                                {
                                    "plain_text": "lead ",
                                    "annotations": {"color": "default"},
                                },
                                {
                                    "plain_text": "joint problem solving",
                                    "annotations": {
                                        "color": "pink_background"
                                    },
                                },
                            ],
                        ]
                    },
                },
            ],
        }
    )

    occurrence = read_pink_highlight_occurrences(
        "page_1",
        notion=notion,
    )[0]

    assert occurrence.text == "joint problem solving"
    assert occurrence.row_index == 1
    assert occurrence.cell_index == 1
    assert occurrence.rich_text_index == 1
    assert "row=1;cell=1;rich_text=1" in occurrence.position_descriptor


def test_same_text_in_two_positions_remains_two_occurrences() -> None:
    item = {
        "plain_text": "assumption",
        "annotations": {"color": "pink"},
    }
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "block_1",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [item]},
                },
                {
                    "id": "block_2",
                    "type": "paragraph",
                    "paragraph": {"rich_text": [item]},
                },
            ]
        }
    )

    occurrences = read_pink_highlight_occurrences(
        "page_1",
        notion=notion,
    )

    assert len(occurrences) == 2
    assert occurrences[0].text == occurrences[1].text
    assert occurrences[0].block_id != occurrences[1].block_id


def test_same_text_twice_in_one_block_has_distinct_spans() -> None:
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "block_1",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "assumption",
                                "annotations": {"color": "pink"},
                            },
                            {
                                "plain_text": " / ",
                                "annotations": {"color": "default"},
                            },
                            {
                                "plain_text": "assumption",
                                "annotations": {"color": "pink"},
                            },
                        ]
                    },
                }
            ]
        }
    )

    occurrences = read_pink_highlight_occurrences(
        "page_1",
        notion=notion,
    )

    assert len(occurrences) == 2
    assert occurrences[0].rich_text_index == 0
    assert occurrences[1].rich_text_index == 2
    assert occurrences[0].start_offset != occurrences[1].start_offset


def test_non_pink_annotations_are_ignored_by_occurrence_reader() -> None:
    notion = FakeNotion(
        {
            "page_1": [
                {
                    "id": "block_1",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "business phrase",
                                "annotations": {"color": "blue_background"},
                            }
                        ]
                    },
                }
            ]
        }
    )

    assert read_pink_highlight_occurrences("page_1", notion=notion) == []
