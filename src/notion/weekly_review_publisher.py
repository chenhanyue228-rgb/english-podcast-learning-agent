"""Publish weekly review analysis into Notion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional, Sequence

from notion_client import APIResponseError, Client

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


class WeeklyReviewPublisherError(RuntimeError):
    """Raised when a weekly review cannot be published."""


@dataclass(frozen=True)
class WeeklyReviewPublishPayload:
    week: str
    date: str
    statistics: Mapping[str, Any]
    summary: Mapping[str, str]
    key_learning_points: Sequence[str]
    recommended_review: Sequence[Mapping[str, str]]
    podcast_page_ids: Sequence[str]


@dataclass(frozen=True)
class WeeklyReviewPublishResult:
    page_id: str
    page_url: Optional[str] = None


def _select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}} if name else {"select": None}


def _date_property(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def _title_property(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _number_property(value: int) -> dict[str, Any]:
    return {"number": value}


def _rich_text_property(value: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": value}}]} if value else {"rich_text": []}


def _relation_property(page_ids: Sequence[str]) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def _heading(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]},
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


def expressions_table_block(
    recommended_review: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    rows = [
        {
            "type": "table_row",
            "table_row": {
                "cells": [
                    _table_cell({"type": "text", "text": {"content": "Expression"}}),
                    _table_cell({"type": "text", "text": {"content": "Category"}}),
                    _table_cell({"type": "text", "text": {"content": "Reason"}}),
                ]
            },
        }
    ]
    for item in recommended_review:
        rows.append(
            {
                "type": "table_row",
                "table_row": {
                    "cells": [
                        _table_cell({"type": "text", "text": {"content": item.get("expression", "")}}),
                        _table_cell({"type": "text", "text": {"content": item.get("category", "")}}),
                        _table_cell({"type": "text", "text": {"content": item.get("reason", "")}}),
                    ]
                },
            }
        )

    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": 3,
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def weekly_review_body_blocks(
    summary: Mapping[str, str],
    key_learning_points: Sequence[str],
    recommended_review: Sequence[Mapping[str, str]],
    podcast_page_ids: Sequence[str],
) -> list[dict[str, Any]]:
    return [
        _heading("Weekly Summary"),
        _paragraph(summary.get("english", "")),
        _paragraph(summary.get("chinese", "")),
        _heading("Key Learning Points"),
        *[_bullet(point) for point in key_learning_points],
        _heading("Expressions To Review"),
        expressions_table_block(recommended_review),
        _heading("Related Podcasts"),
        _paragraph(
            ", ".join(podcast_page_ids) if podcast_page_ids else "No related podcasts this week."
        ),
    ]


def weekly_review_page_properties(payload: WeeklyReviewPublishPayload) -> dict[str, Any]:
    expression_count = int(payload.statistics.get("expression_count", 0))
    return {
        "Week": _title_property(payload.week),
        "Date": _date_property(payload.date),
        "Expression Count": _number_property(expression_count),
        "Vocabulary Count": _number_property(expression_count),
        "Podcasts": _relation_property(payload.podcast_page_ids),
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
) -> WeeklyReviewPublishResult:
    if notion is None or weekly_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        weekly_database_id = weekly_database_id or config.weekly_database_id

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
                children=weekly_review_body_blocks(
                    payload.summary,
                    payload.key_learning_points,
                    payload.recommended_review,
                    payload.podcast_page_ids,
                ),
            )
    except APIResponseError as exc:
        raise WeeklyReviewPublisherError(
            f"Notion API failed to publish weekly review: {exc.code} {exc.message}"
        ) from exc
    except Exception as exc:
        raise WeeklyReviewPublisherError(f"Failed to publish weekly review: {exc}") from exc

    return WeeklyReviewPublishResult(page_id=response.get("id", page_id or ""), page_url=response.get("url"))
