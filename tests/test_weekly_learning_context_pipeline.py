from __future__ import annotations

from datetime import date
from pathlib import Path

from src.workflow.block_parser import normalize_block, parse_block_tree
from src.workflow.podcast_query import query_podcast_pages
from src.workflow.schema_validator import validate_weekly_learning_context
from src.workflow.weekly_learning_context_pipeline import (
    build_weekly_learning_context,
    save_weekly_learning_context,
)


class FakeQueryResponse:
    def __init__(self, results, has_more=False, next_cursor=None):
        self.results = results
        self.has_more = has_more
        self.next_cursor = next_cursor

    def get(self, key, default=None):
        if key == "results":
            return self.results
        if key == "has_more":
            return self.has_more
        if key == "next_cursor":
            return self.next_cursor
        return default


class FakeDataSources:
    def __init__(self, responses):
        self.responses = list(responses)
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.responses:
            return self.responses.pop(0)
        return FakeQueryResponse([])


class FakeBlocks:
    def __init__(self, children_by_block_id):
        self.children_by_block_id = children_by_block_id
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return {"results": self.children_by_block_id.get(kwargs["block_id"], [])}


class FakeNotion:
    def __init__(self, query_responses, blocks_by_id):
        self.data_sources = FakeDataSources(query_responses)
        self.blocks = type("Blocks", (), {"children": FakeBlocks(blocks_by_id)})()
        self.pages = type("Pages", (), {"retrieve": lambda self, **kwargs: {}})()


def _podcast_page(page_id: str, title: str = "Episode One") -> dict:
    return {
        "id": page_id,
        "properties": {
            "Title": {"title": [{"plain_text": title, "text": {"content": title}}]},
            "Date": {"date": {"start": "2026-07-19"}},
            "Topic": {"select": {"name": "Negotiation"}},
            "Difficulty": {"select": {"name": "Intermediate"}},
            "URL": {"url": "https://example.com/episode"},
        },
    }


def _table_row(*cells: str) -> dict:
    return {
        "id": "table_row_1",
        "type": "table_row",
        "has_children": False,
        "table_row": {
            "cells": [
                [
                    {
                        "plain_text": cell,
                        "text": {"content": cell},
                        "annotations": {"color": "default"},
                    }
                ]
                for cell in cells
            ]
        },
    }


def test_build_weekly_learning_context_extracts_real_sections(monkeypatch, tmp_path: Path) -> None:
    notion = FakeNotion(
        [FakeQueryResponse([_podcast_page("page_1")])],
        {
            "page_1": [
                {
                    "id": "summary_heading",
                    "type": "heading_2",
                    "has_children": False,
                    "heading_2": {
                        "rich_text": [
                            {
                                "plain_text": "Summary",
                                "text": {"content": "Summary"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "summary_english",
                    "type": "paragraph",
                    "has_children": False,
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "This episode reframes negotiation as relationship management.",
                                "text": {
                                    "content": "This episode reframes negotiation as relationship management."
                                },
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "summary_chinese",
                    "type": "paragraph",
                    "has_children": False,
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "这一集把谈判重新定义为关系管理。",
                                "text": {"content": "这一集把谈判重新定义为关系管理。"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "takeaway_1",
                    "type": "bulleted_list_item",
                    "has_children": False,
                    "bulleted_list_item": {
                        "rich_text": [
                            {
                                "plain_text": "Negotiation is relationship management.",
                                "text": {"content": "Negotiation is relationship management."},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "transcript_heading",
                    "type": "heading_2",
                    "has_children": False,
                    "heading_2": {
                        "rich_text": [
                            {
                                "plain_text": "Transcript",
                                "text": {"content": "Transcript"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "expressions_heading",
                    "type": "heading_2",
                    "has_children": False,
                    "heading_2": {
                        "rich_text": [
                            {
                                "plain_text": "Expressions",
                                "text": {"content": "Expressions"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "category_heading",
                    "type": "heading_3",
                    "has_children": False,
                    "heading_3": {
                        "rich_text": [
                            {
                                "plain_text": "Business Phrase",
                                "text": {"content": "Business Phrase"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "expression_table",
                    "type": "table",
                    "has_children": True,
                    "table": {
                        "table_width": 6,
                        "has_column_header": True,
                        "has_row_header": False,
                    },
                },
                {
                    "id": "highlight_heading",
                    "type": "heading_2",
                    "has_children": False,
                    "heading_2": {
                        "rich_text": [
                            {
                                "plain_text": "Highlight Transcript",
                                "text": {"content": "Highlight Transcript"},
                                "annotations": {"color": "default"},
                            }
                        ]
                    },
                },
                {
                    "id": "highlight_paragraph",
                    "type": "paragraph",
                    "has_children": False,
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "reframes",
                                "text": {"content": "reframes"},
                                "annotations": {"color": "green_background"},
                            },
                            {
                                "plain_text": " negotiation as relationship management.",
                                "text": {"content": " negotiation as relationship management."},
                                "annotations": {"color": "default"},
                            },
                        ]
                    },
                },
                {
                    "id": "pink_paragraph",
                    "type": "paragraph",
                    "has_children": False,
                    "paragraph": {
                        "rich_text": [
                            {
                                "plain_text": "fundraising",
                                "text": {"content": "fundraising"},
                                "annotations": {"color": "pink_background"},
                            },
                            {
                                "plain_text": " matters for growth.",
                                "text": {"content": " matters for growth."},
                                "annotations": {"color": "default"},
                            },
                        ]
                    },
                },
            ],
        },
    )
    notion.blocks.children.children_by_block_id = {
        "page_1": notion.blocks.children.children_by_block_id["page_1"],
        "expression_table": [
            {
                "id": "table_header_row",
                "type": "table_row",
                "has_children": False,
                "table_row": {
                    "cells": [
                        [{"plain_text": "Expression", "text": {"content": "Expression"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Category", "text": {"content": "Category"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Meaning", "text": {"content": "Meaning"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Chinese Meaning", "text": {"content": "Chinese Meaning"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Usage Context", "text": {"content": "Usage Context"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Example", "text": {"content": "Example"}, "annotations": {"color": "default"}}],
                        [{"plain_text": "Commonness", "text": {"content": "Commonness"}, "annotations": {"color": "default"}}],
                    ]
                },
            },
            _table_row(
                "take ownership",
                "Business Phrase",
                "Accept responsibility",
                "接受责任",
                "Use it when discussing accountability.",
                "We need to take ownership.",
                "High",
            ),
        ],
    }

    context, report = build_weekly_learning_context(
        notion=notion,
        podcast_database_id="podcast_db",
        today=date(2026, 7, 20),
        generated_at="2026-07-20T02:00:00+00:00",
    )

    assert context["metadata"]["period_start"] == "2026-07-13"
    assert context["metadata"]["generated_at"] == (
        "2026-07-20T02:00:00+00:00"
    )
    assert context["metadata"]["period_end"] == "2026-07-20"
    assert len(context["podcasts"]) == 1
    assert context["podcasts"][0]["title"] == "Episode One"
    assert context["podcasts"][0]["summary"]["english"] == "This episode reframes negotiation as relationship management."
    assert context["podcasts"][0]["summary"]["chinese"] == "这一集把谈判重新定义为关系管理。"
    assert context["podcasts"][0]["key_takeaways"] == ["Negotiation is relationship management."]
    assert len(context["learning_expressions"]) == 1
    assert context["learning_expressions"][0]["expression"] == "take ownership"
    assert context["learning_expressions"][0]["category"] == "Business Phrase"
    assert context["learning_expressions"][0]["meaning"] == "Accept responsibility"
    assert len(context["ai_highlights"]) == 1
    assert context["ai_highlights"][0]["text"] == "reframes"
    assert context["ai_highlights"][0]["category"] == "Native Expression"
    assert len(context["user_vocabulary"]) == 1
    assert context["user_vocabulary"][0]["word"] == "fundraising"
    assert report.podcast_pages_scanned == 1
    assert report.successfully_extracted == 1
    assert report.expressions_found == 1
    assert report.ai_highlights_found == 1
    assert report.pink_highlights_found == 1
    assert report.failures == 0

    saved = save_weekly_learning_context(context, tmp_path / "weekly_learning_context.json")
    assert saved.exists()


def test_block_parser_preserves_nested_table_rows() -> None:
    class FakeBlocks:
        def __init__(self):
            self.list_calls = []

        def list(self, **kwargs):
            self.list_calls.append(kwargs)
            if kwargs["block_id"] == "page_1":
                return {
                    "results": [
                        {
                            "id": "table_1",
                            "type": "table",
                            "has_children": True,
                            "table": {"table_width": 2, "has_column_header": True, "has_row_header": False},
                        }
                    ]
                }
            return {
                "results": [
                    {
                        "id": "row_1",
                        "type": "table_row",
                        "has_children": False,
                        "table_row": {
                            "cells": [
                                [{"plain_text": "conversation", "text": {"content": "conversation"}, "annotations": {"color": "pink_background"}}],
                                [{"plain_text": "context", "text": {"content": "context"}, "annotations": {"color": "default"}}],
                            ]
                        },
                    }
                ]
            }

    notion = type("Notion", (), {"blocks": type("BlocksContainer", (), {"children": FakeBlocks()})()})()
    tree = parse_block_tree(notion, "page_1")
    assert len(tree) == 1
    assert tree[0].type == "table"
    assert len(tree[0].children) == 1
    assert tree[0].children[0].type == "table_row"
    assert tree[0].children[0].text == "conversation context"


def test_validate_weekly_learning_context_rejects_missing_required_keys() -> None:
    bad = {
        "metadata": {"period_start": "", "period_end": "", "generated_at": "", "source": ""},
        "podcasts": [],
        "learning_expressions": [],
        "ai_highlights": [],
        "user_vocabulary": [],
    }
    try:
        validate_weekly_learning_context(bad)
    except Exception as exc:
        assert "period_start" in str(exc)
