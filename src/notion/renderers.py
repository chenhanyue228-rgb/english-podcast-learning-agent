"""Notion block renderers for podcast and expression learning pages."""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from src.analyzer.highlight_mapper import map_highlights_to_paragraph_blocks
from src.notion.schema import HIGHLIGHT_LEGEND, category_color


def plain_text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def bold_text(text: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text},
        "annotations": {"bold": True},
    }


def highlighted_label(text: str, color: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text},
        "annotations": {"color": f"{color.lower()}_background"},
    }


def heading(level: int, text_items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": list(text_items)},
    }


def paragraph(text_items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": list(text_items)},
    }


def quote(text_items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": list(text_items)},
    }


def bullet(text_items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": list(text_items)},
    }


def table_of_contents() -> dict[str, Any]:
    return {
        "object": "block",
        "type": "table_of_contents",
        "table_of_contents": {"color": "default"},
    }


def table_cell(*rich_text: dict[str, Any]) -> list[dict[str, Any]]:
    return list(rich_text)


def expression_value(expression: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = expression.get(key)
        if value:
            return str(value)
    return ""


def expression_table_block(expressions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [
        {
            "type": "table_row",
            "table_row": {
                "cells": [
                    table_cell(plain_text("Expression")),
                    table_cell(plain_text("Meaning")),
                    table_cell(plain_text("Chinese Meaning")),
                    table_cell(plain_text("Usage Context")),
                    table_cell(plain_text("Commonness")),
                    table_cell(plain_text("Example")),
                ]
            },
        }
    ]

    for expression in expressions:
        rows.append(
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        table_cell(
                            bold_text(
                                expression_value(expression, "expression", "text")
                            )
                        ),
                        table_cell(plain_text(expression_value(expression, "meaning"))),
                        table_cell(
                            plain_text(expression_value(expression, "chinese_meaning"))
                        ),
                        table_cell(
                            plain_text(
                                expression_value(expression, "usage_context", "usage")
                            )
                        ),
                        table_cell(
                            plain_text(expression_value(expression, "commonness"))
                        ),
                        table_cell(
                            plain_text(
                                expression_value(
                                    expression,
                                    "example_sentence",
                                    "example",
                                )
                            )
                        ),
                    ]
                },
            }
        )

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 6,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def expression_category_table_blocks(
    expressions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    categories = []
    for expression in expressions:
        category = expression_value(expression, "category", "type")
        if category and category not in categories:
            categories.append(category)

    for category in categories:
        category_expressions = [
            expression
            for expression in expressions
            if expression_value(expression, "category", "type") == category
        ]
        blocks.append(
            heading(3, [highlighted_label(category, category_color(category))])
        )
        blocks.append(expression_table_block(category_expressions))

    return blocks


def highlight_legend_blocks() -> list[dict[str, Any]]:
    return [
        heading(2, [plain_text("Highlight Legend")]),
        *[
            bullet(
                [
                    highlighted_label(color, color),
                    plain_text(f" - {description}"),
                ]
            )
            for color, description in HIGHLIGHT_LEGEND
        ],
    ]


def highlight_inputs(expressions: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "text": expression_value(expression, "expression", "text"),
            "type": expression_value(expression, "category", "type"),
            "color": expression_value(expression, "color"),
        }
        for expression in expressions
    ]


def podcast_body_blocks(
    summary: str,
    transcript: str,
    expressions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    blocks = [
        table_of_contents(),
        heading(2, [plain_text("Summary")]),
        paragraph([plain_text(summary)]),
        heading(2, [plain_text("Expressions")]),
        *expression_category_table_blocks(expressions),
    ]

    blocks.extend(
        [
            *highlight_legend_blocks(),
            heading(2, [plain_text("Highlighted Transcript")]),
            *map_highlights_to_paragraph_blocks(
                transcript, highlight_inputs(expressions)
            ),
        ]
    )

    return blocks


def expression_body_blocks(
    expression: Mapping[str, Any],
    fallback_context_sentence: str,
) -> list[dict[str, Any]]:
    context_sentence = (
        expression_value(expression, "context") or fallback_context_sentence
    )
    example = expression_value(expression, "example") or context_sentence
    color = expression_value(expression, "color")

    return [
        heading(2, [plain_text("Meaning")]),
        paragraph([plain_text(expression_value(expression, "meaning"))]),
        heading(2, [plain_text("Chinese Meaning")]),
        paragraph([plain_text(expression_value(expression, "chinese_meaning"))]),
        heading(2, [plain_text("Usage Context")]),
        paragraph(
            [
                plain_text(
                    expression_value(expression, "usage_context", "usage")
                    or "Use this expression in real-world English contexts that match the original sentence."
                )
            ]
        ),
        heading(2, [plain_text("Commonness")]),
        paragraph([plain_text(expression_value(expression, "commonness"))]),
        heading(2, [plain_text("Context Sentence")]),
        quote([plain_text(context_sentence)]),
        heading(2, [plain_text("Example")]),
        paragraph([plain_text(example)]),
        heading(2, [plain_text("Highlight Color")]),
        paragraph([highlighted_label(color, color)]),
    ]
