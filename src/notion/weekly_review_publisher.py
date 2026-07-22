"""Publish weekly review analysis into Notion."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from notion_client import APIResponseError, Client

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


class WeeklyReviewPublisherError(RuntimeError):
    """Raised when a weekly review cannot be published."""


@dataclass(frozen=True)
class WeeklyReviewPublishPayload:
    week: str
    executive_summary: Mapping[str, Any]
    knowledge_insights: Sequence[Mapping[str, Any]]
    expression_upgrade: Sequence[Mapping[str, Any]]
    vocabulary_memory: Sequence[Mapping[str, Any]]
    career_reflection: Mapping[str, Any]
    next_learning_direction: Sequence[str]


@dataclass(frozen=True)
class WeeklyReviewPublishResult:
    page_id: str
    page_url: Optional[str] = None


def _title_property(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _rich_text_property(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]} if value else {"rich_text": []}


def _select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def _number_property(value: int) -> dict[str, Any]:
    return {"number": value}


def _heading(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _heading_one(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_1",
        "heading_1": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _paragraph(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}] if text else []},
    }


def _bullet(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _table_cell(*items: dict[str, Any]) -> list[dict[str, Any]]:
    return list(items)


def _table_row(*cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "table_row",
        "table_row": {
            "cells": list(cells),
        },
    }


def _toc_block() -> dict[str, Any]:
    return {
        "object": "block",
        "type": "table_of_contents",
        "table_of_contents": {"color": "default"},
    }


def _toc_entry(text: str) -> dict[str, Any]:
    return _bullet(text)


def _knowledge_insight_lines(knowledge_insights: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in knowledge_insights:
        what_happened = str(item.get("what_happened", "")).strip()
        why_it_matters = str(item.get("why_it_matters", "")).strip()
        my_interpretation = str(item.get("my_interpretation", "")).strip()
        application = str(item.get("application", "")).strip()
        parts = [part for part in [
            f"What happened: {what_happened}" if what_happened else "",
            f"Why it matters: {why_it_matters}" if why_it_matters else "",
            f"My interpretation: {my_interpretation}" if my_interpretation else "",
            f"Application: {application}" if application else "",
        ] if part]
        lines.append(" | ".join(parts))
    return lines


def _expression_rows(expression_upgrade: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell({"type": "text", "text": {"content": "Expression"}}),
            _table_cell({"type": "text", "text": {"content": "Meaning"}}),
            _table_cell({"type": "text", "text": {"content": "Context"}}),
            _table_cell({"type": "text", "text": {"content": "Example"}}),
        )
    ]
    for item in expression_upgrade:
        rows.append(
            _table_row(
                _table_cell({"type": "text", "text": {"content": str(item.get("expression", ""))}}),
                _table_cell({"type": "text", "text": {"content": str(item.get("meaning", ""))}}),
                _table_cell({"type": "text", "text": {"content": str(item.get("context", ""))}}),
                _table_cell({"type": "text", "text": {"content": str(item.get("example", ""))}}),
            )
        )
    return rows


def _table_block(rows: list[dict[str, Any]], table_width: int) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": table_width,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def _linked_database_block(database_id: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": f"Source podcasts are linked through the relation property. Database: {database_id}"}}
            ]
        },
    }


def _career_reflection_rows(
    career_reflection: Mapping[str, Any]
) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell({"type": "text", "text": {"content": "Insight"}}),
            _table_cell({"type": "text", "text": {"content": "Action"}}),
        )
    ]
    questions = [
        str(item).strip()
        for item in career_reflection.get("questions", [])
        if str(item).strip()
    ]
    applications = [
        str(item).strip()
        for item in career_reflection.get("possible_applications", [])
        if str(item).strip()
    ]
    max_len = max(len(questions), len(applications))
    if max_len == 0:
        rows.append(
            _table_row(
                _table_cell({"type": "text", "text": {"content": ""}}),
                _table_cell({"type": "text", "text": {"content": ""}}),
            )
        )
        return rows

    for idx in range(max_len):
        insight = questions[idx] if idx < len(questions) else ""
        action = applications[idx] if idx < len(applications) else ""
        rows.append(
            _table_row(
                _table_cell({"type": "text", "text": {"content": insight}}),
                _table_cell({"type": "text", "text": {"content": action}}),
            )
        )
    return rows


def _next_learning_direction_rows(
    next_learning_direction: Sequence[str],
) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell({"type": "text", "text": {"content": "Priority"}}),
            _table_cell({"type": "text", "text": {"content": "Learning Goal"}}),
            _table_cell({"type": "text", "text": {"content": "Reason"}}),
        )
    ]
    goals = [
        str(item).strip()
        for item in next_learning_direction
        if str(item).strip()
    ]
    if not goals:
        rows.append(
            _table_row(
                _table_cell({"type": "text", "text": {"content": ""}}),
                _table_cell({"type": "text", "text": {"content": ""}}),
                _table_cell({"type": "text", "text": {"content": ""}}),
            )
        )
        return rows

    for idx, goal in enumerate(goals, start=1):
        rows.append(
            _table_row(
                _table_cell({"type": "text", "text": {"content": str(idx)}}),
                _table_cell({"type": "text", "text": {"content": goal}}),
                _table_cell(
                    {"type": "text", "text": {"content": "Keep the next review focused and actionable."}}
                ),
            )
        )
    return rows


def _section_toc_items() -> list[str]:
    return [
        "Executive Summary",
        "Knowledge Insights",
        "Expression Upgrade",
        "Vocabulary Memory",
        "Career Reflection",
        "Next Learning Direction",
    ]


def weekly_review_body_blocks(
    payload: WeeklyReviewPublishPayload,
    vocabulary_database_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    knowledge_lines = _knowledge_insight_lines(payload.knowledge_insights)

    blocks: list[dict[str, Any]] = [_toc_block()]
    blocks.extend(_toc_entry(f"{idx}. {title}") for idx, title in enumerate(_section_toc_items(), start=1))
    blocks.extend(
        [
            _heading("Executive Summary"),
            _paragraph(str(payload.executive_summary.get("overview", ""))),
            _paragraph(str(payload.executive_summary.get("takeaway", ""))),
        ]
    )
    for highlight in payload.executive_summary.get("highlights", []):
        if str(highlight).strip():
            blocks.append(_bullet(str(highlight)))

    blocks.append(_heading("Knowledge Insights"))
    if knowledge_lines:
        blocks.extend(_bullet(line) for line in knowledge_lines)
    else:
        blocks.append(_paragraph("No knowledge insights provided."))

    blocks.extend(
        [
            _heading("Expression Upgrade"),
        ]
    )
    expression_rows = _expression_rows(payload.expression_upgrade)
    blocks.append(_table_block(expression_rows, table_width=4))

    blocks.extend(
        [
            _heading("Vocabulary Memory"),
            _paragraph(
                "Linked Vocabulary Database view (Word, Context, Meaning, Professional Category, Review Status)."
            ),
        ]
    )
    if vocabulary_database_id:
        blocks.append(_linked_database_block(vocabulary_database_id))
    else:
        blocks.append(_paragraph("Vocabulary records are stored in the Vocabulary Database."))

    blocks.append(_heading("Career Reflection"))
    blocks.append(_table_block(_career_reflection_rows(payload.career_reflection), table_width=2))

    blocks.extend(
        [
            _heading("Next Learning Direction"),
            _table_block(_next_learning_direction_rows(payload.next_learning_direction), table_width=3),
        ]
    )
    return blocks


def weekly_review_page_properties(payload: WeeklyReviewPublishPayload) -> dict[str, Any]:
    quality_score = min(
        100,
        60
        + len(payload.knowledge_insights) * 5
        + len(payload.expression_upgrade) * 5
        + len(payload.next_learning_direction) * 3,
    )
    return {
        "Week": _title_property(payload.week),
        "Source Period": _rich_text_property(payload.week),
        "Status": _select_property("Draft"),
        "Quality Score": _number_property(quality_score),
        "Title": _title_property(payload.week),
    }


def find_existing_weekly_review_page(
    notion: Client,
    weekly_database_id: str,
    week: str,
) -> Optional[str]:
    try:
        if hasattr(notion, "data_sources"):
            response = notion.data_sources.query(
                data_source_id=weekly_database_id,
                filter={"property": "Week", "title": {"equals": week}},
            )
        else:
            response = notion.databases.query(
                database_id=weekly_database_id,
                filter={"property": "Week", "title": {"equals": week}},
            )
    except Exception:
        return None

    results = response.get("results", [])
    if not results:
        return None
    return results[0].get("id")


def publish_weekly_review(
    payload: WeeklyReviewPublishPayload,
    notion: Optional[Client] = None,
    weekly_database_id: Optional[str] = None,
    vocabulary_database_id: Optional[str] = None,
) -> WeeklyReviewPublishResult:
    if notion is None or weekly_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        weekly_database_id = weekly_database_id or config.weekly_database_id
        vocabulary_database_id = vocabulary_database_id or config.vocabulary_database_id

    page_id = find_existing_weekly_review_page(notion, weekly_database_id, payload.week)
    try:
        if page_id:
            response = notion.pages.update(
                page_id=page_id,
                properties=weekly_review_page_properties(payload),
            )
        else:
            response = notion.pages.create(
                parent={"data_source_id": weekly_database_id},
                properties=weekly_review_page_properties(payload),
                children=weekly_review_body_blocks(payload, vocabulary_database_id),
            )
    except APIResponseError as exc:
        raise WeeklyReviewPublisherError(
            f"Notion API failed to publish weekly review: {exc.code} {exc.message}"
        ) from exc
    except Exception as exc:
        raise WeeklyReviewPublisherError(f"Failed to publish weekly review: {exc}") from exc

    return WeeklyReviewPublishResult(page_id=response.get("id", page_id or ""), page_url=response.get("url"))
