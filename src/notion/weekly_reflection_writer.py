"""Publish Weekly Reflection pages into Notion.

This module writes the final Weekly Reflection page from a generated
WeeklyReview.json and ReflectionContext.json pair. It reuses the existing
Notion SDK client factory and keeps the publisher logic isolated from the
weekly review generator and reflection analyzer.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from notion_client import APIResponseError, Client

from src.notion.config import load_dotenv
from src.notion.schema import PODCAST_LIBRARY, WEEKLY_REVIEW
from src.notion.target_binding import (
    ensure_notion_page_belongs_to_role,
    ensure_notion_target_binding_for_write,
)
from src.notion.uploader import create_notion_client
from src.weekly_review.generator import _normalize_legacy_output
from src.workflow.notion_client import query_database


DEFAULT_WEEKLY_REVIEW_JSON_PATH = Path("output/weekly_review.json")
DEFAULT_REFLECTION_CONTEXT_JSON_PATH = Path("output/reflection_context.json")
DEFAULT_WEEKLY_REFLECTION_DATABASE_ID_ENV = "NOTION_WEEKLY_REFLECTION_DATABASE_ID"
LEGACY_WEEKLY_REFLECTION_DATABASE_ID_ENV = "NOTION_WEEKLY_REVIEW_DATABASE_ID"


class WeeklyReflectionWriterError(RuntimeError):
    """Raised when a Weekly Reflection page cannot be published."""


@dataclass(frozen=True)
class WeeklyReflectionPublishPayload:
    """Input required to publish a Weekly Reflection page."""

    weekly_review: Mapping[str, Any]
    reflection_context: Mapping[str, Any]
    quality_score: int = 0
    pipeline_run_id: str = ""
    reflection_context_id: str = ""


@dataclass(frozen=True)
class WeeklyReflectionPublishResult:
    """Result returned after creating a Weekly Reflection page."""

    page_id: str
    page_url: Optional[str] = None


def _title_property(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _rich_text_property(value: str) -> dict[str, Any]:
    normalized = _normalize_text(value)
    if not normalized:
        return {"rich_text": []}

    # Notion rich_text property items are limited to 2000 characters each.
    # Split long content into safe chunks instead of failing the publish call.
    chunk_size = 1900
    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > chunk_size:
        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)

    if not chunks:
        chunks = [normalized]
    return {
        "rich_text": [
            {"type": "text", "text": {"content": chunk}}
            for chunk in chunks
        ]
    }


def _select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def _number_property(value: int) -> dict[str, Any]:
    return {"number": value}


def _relation_property(page_ids: Sequence[str]) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids if str(page_id).strip()]}


def _heading(text: str, level: int = 2) -> dict[str, Any]:
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": [{"type": "text", "text": {"content": text}}]},
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


def _table_cell(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text}}]


def _table_row(*cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": list(cells),
        },
    }


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


def _toc_block() -> dict[str, Any]:
    return {
        "object": "block",
        "type": "table_of_contents",
        "table_of_contents": {"color": "default"},
    }


def _source_podcasts_block(database_id: str) -> dict[str, Any]:
    return _paragraph(
        "Source podcasts are linked through the relation property on the Weekly Reflection database. "
        f"Podcast database: {database_id}"
    )


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _truncate_text(value: object, limit: int = 180) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _limit_items(items: Sequence[Any], limit: int) -> list[Any]:
    return list(items)[:limit] if isinstance(items, Sequence) else []


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise WeeklyReflectionWriterError(f"{label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WeeklyReflectionWriterError(f"{label} is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise WeeklyReflectionWriterError(f"{label} must be a JSON object.")
    return payload


def load_weekly_review_json(path: Path = DEFAULT_WEEKLY_REVIEW_JSON_PATH) -> dict[str, Any]:
    return _load_json_object(path, "Weekly review JSON")


def load_reflection_context_json(
    path: Path = DEFAULT_REFLECTION_CONTEXT_JSON_PATH,
) -> dict[str, Any]:
    return _load_json_object(path, "Reflection context JSON")


def _validate_weekly_review_json(payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = _normalize_legacy_output(payload)
    required = [
        "period",
        "core_idea",
        "mindset_shift",
        "ideas_worth_compounding",
        "expressions_worth_reusing",
        "language_thinking_connection",
        "next_week_application",
        "sources",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise WeeklyReflectionWriterError(
            f"Weekly review JSON is missing required fields: {', '.join(missing)}"
        )

    period = payload.get("period")
    if not isinstance(period, Mapping):
        raise WeeklyReflectionWriterError("Weekly review period must be an object.")
    for key in ["start_date", "end_date", "generated_at", "source"]:
        if not isinstance(period.get(key), str):
            raise WeeklyReflectionWriterError(f"Weekly review period must contain {key} as a string.")

    if not isinstance(payload.get("core_idea"), Mapping):
        raise WeeklyReflectionWriterError("Weekly review core_idea must be an object.")
    if payload.get("mindset_shift") is not None and not isinstance(payload.get("mindset_shift"), Mapping):
        raise WeeklyReflectionWriterError("Weekly review mindset_shift must be an object or null.")
    if not isinstance(payload.get("ideas_worth_compounding"), list):
        raise WeeklyReflectionWriterError("Weekly review ideas_worth_compounding must be an array.")
    if not isinstance(payload.get("expressions_worth_reusing"), list):
        raise WeeklyReflectionWriterError("Weekly review expressions_worth_reusing must be an array.")
    if not isinstance(payload.get("language_thinking_connection"), str):
        raise WeeklyReflectionWriterError("Weekly review language_thinking_connection must be a string.")
    if not isinstance(payload.get("next_week_application"), Mapping):
        raise WeeklyReflectionWriterError("Weekly review next_week_application must be an object.")
    if not isinstance(payload.get("sources"), list):
        raise WeeklyReflectionWriterError("Weekly review sources must be an array.")

    return dict(payload)


def _validate_reflection_context_json(payload: Mapping[str, Any]) -> dict[str, Any]:
    required = ["weekly_theme", "mindset_shifts", "professional_actions"]
    missing = [key for key in required if key not in payload]
    if missing:
        raise WeeklyReflectionWriterError(
            f"Reflection context is missing required fields: {', '.join(missing)}"
        )

    weekly_theme = payload.get("weekly_theme")
    if not isinstance(weekly_theme, Mapping):
        raise WeeklyReflectionWriterError("Reflection weekly_theme must be an object.")
    if not isinstance(weekly_theme.get("category"), str):
        raise WeeklyReflectionWriterError("Reflection weekly_theme.category must be a string.")
    if not isinstance(weekly_theme.get("theme"), str):
        raise WeeklyReflectionWriterError("Reflection weekly_theme.theme must be a string.")

    mindset_shifts = payload.get("mindset_shifts")
    if not isinstance(mindset_shifts, list):
        raise WeeklyReflectionWriterError("Reflection mindset_shifts must be an array.")
    for shift in mindset_shifts:
        if not isinstance(shift, Mapping):
            raise WeeklyReflectionWriterError("Each mindset shift must be an object.")
        if not isinstance(shift.get("before"), str) or not isinstance(shift.get("after"), str):
            raise WeeklyReflectionWriterError("Each mindset shift must contain before and after strings.")
        evidence = shift.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise WeeklyReflectionWriterError("Each mindset shift must contain non-empty evidence.")
        for evidence_item in evidence:
            if not isinstance(evidence_item, Mapping):
                raise WeeklyReflectionWriterError("Each mindset shift evidence item must be an object.")
            if not isinstance(evidence_item.get("source"), str) or not isinstance(
                evidence_item.get("supporting_concept"),
                str,
            ):
                raise WeeklyReflectionWriterError(
                    "Each mindset shift evidence item must contain source and supporting_concept strings."
                )
        confidence = shift.get("confidence")
        if not isinstance(confidence, (int, float)):
            raise WeeklyReflectionWriterError("Each mindset shift must include a confidence score.")

    if not isinstance(payload.get("cross_content_patterns", []), list):
        raise WeeklyReflectionWriterError("Reflection cross_content_patterns must be an array.")
    professional_actions = payload.get("professional_actions")
    if not isinstance(professional_actions, list) or not professional_actions:
        raise WeeklyReflectionWriterError("Reflection professional_actions must be a non-empty array.")

    return dict(payload)


def _week_label(period: Mapping[str, Any], weekly_theme: str) -> str:
    start_date = _normalize_text(period.get("start_date", ""))
    if start_date:
        try:
            year, month, day = (int(part) for part in start_date.split("-"))
            week_number = date(year, month, day).isocalendar().week
            return f"Week {week_number} Reflection — {weekly_theme}".strip(" —")
        except Exception:
            pass
    return f"Weekly Reflection — {weekly_theme}".strip(" —")


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _extract_source_page_ids(weekly_review: Mapping[str, Any], reflection_context: Mapping[str, Any]) -> list[str]:
    candidates = []
    for source in (
        weekly_review.get("source_page_ids"),
        weekly_review.get("source_podcast_ids"),
        reflection_context.get("source_page_ids"),
        reflection_context.get("source_podcast_ids"),
    ):
        if isinstance(source, list):
            candidates.extend(str(item).strip() for item in source if str(item).strip())
    seen: set[str] = set()
    unique_ids: list[str] = []
    for page_id in candidates:
        if page_id in seen:
            continue
        seen.add(page_id)
        unique_ids.append(page_id)
    return unique_ids


def _extract_vocabulary_relation_ids(
    weekly_review: Mapping[str, Any],
    reflection_context: Mapping[str, Any],
) -> list[str]:
    candidates = []
    for source in (
        weekly_review.get("vocabulary_page_ids"),
        weekly_review.get("vocabulary_ids"),
        reflection_context.get("vocabulary_page_ids"),
        reflection_context.get("vocabulary_ids"),
    ):
        if isinstance(source, list):
            candidates.extend(str(item).strip() for item in source if str(item).strip())
    seen: set[str] = set()
    unique_ids: list[str] = []
    for page_id in candidates:
        if page_id in seen:
            continue
        seen.add(page_id)
        unique_ids.append(page_id)
    return unique_ids


def _extract_relation_ids(page: Mapping[str, Any], property_name: str) -> list[str]:
    properties = page.get("properties", {})
    if not isinstance(properties, Mapping):
        return []
    prop = properties.get(property_name, {})
    if not isinstance(prop, Mapping):
        return []
    relation = prop.get("relation", [])
    if not isinstance(relation, list):
        return []
    ids: list[str] = []
    for item in relation:
        if not isinstance(item, Mapping):
            continue
        page_id = str(item.get("id", "")).strip()
        if page_id:
            ids.append(page_id)
    return ids


def _extract_date_property(page: Mapping[str, Any], property_name: str) -> tuple[str, str]:
    properties = page.get("properties", {})
    if not isinstance(properties, Mapping):
        return "", ""
    prop = properties.get(property_name, {})
    if not isinstance(prop, Mapping):
        return "", ""
    date_value = prop.get("date", {})
    if not isinstance(date_value, Mapping):
        return "", ""
    return str(date_value.get("start", "") or ""), str(date_value.get("end", "") or "")


def _page_matches_reflection_identity(
    page: Mapping[str, Any],
    period: Mapping[str, Any],
    source_page_ids: Sequence[str],
) -> bool:
    start_date = _normalize_text(period.get("start_date", ""))
    end_date = _normalize_text(period.get("end_date", ""))
    page_start, page_end = _extract_date_property(page, "Date")
    if not page_start and not page_end:
        page_start, page_end = _extract_date_property(page, "Period")
    if start_date and page_start != start_date:
        return False
    if end_date and page_end and page_end != end_date:
        return False

    if source_page_ids:
        page_source_ids = set(_extract_relation_ids(page, "Podcasts"))
        if not page_source_ids:
            page_source_ids = set(_extract_relation_ids(page, "Source Podcasts"))
        if not set(source_page_ids).issubset(page_source_ids):
            return False
    return True


def _render_mindset_shift(shift: Mapping[str, Any]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        _paragraph(f"Before: {str(shift.get('before', '')).strip()}"),
        _paragraph(f"After: {str(shift.get('after', '')).strip()}"),
    ]
    evidence_items = []
    for item in _as_list(shift.get("evidence")):
        if not isinstance(item, Mapping):
            continue
        source = _normalize_text(item.get("source", ""))
        supporting = _normalize_text(item.get("supporting_concept", ""))
        if source or supporting:
            evidence_items.append(f"{source}: {supporting}".strip(": "))
    if evidence_items:
        blocks.append(_bullet("Evidence:"))
        blocks.extend(_bullet(item) for item in evidence_items)
    confidence = shift.get("confidence")
    if isinstance(confidence, (int, float)):
        blocks.append(_paragraph(f"Confidence: {float(confidence):.2f}"))
    return blocks


def _knowledge_insight_lines(knowledge_insights: Sequence[Mapping[str, Any]]) -> list[str]:
    lines: list[str] = []
    for item in knowledge_insights:
        if not isinstance(item, Mapping):
            continue
        insight = _normalize_text(item.get("insight", ""))
        why_it_matters = _normalize_text(item.get("why_it_matters", ""))
        professional_application = _normalize_text(item.get("professional_application", ""))
        parts = [
            f"Insight: {insight}" if insight else "",
            f"Why it matters: {why_it_matters}" if why_it_matters else "",
            f"Professional application: {professional_application}" if professional_application else "",
        ]
        lines.append(" | ".join(part for part in parts if part))
    return lines


def _executive_summary_lines(executive_summary: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    weekly_theme = executive_summary.get("weekly_theme", "")
    if isinstance(weekly_theme, Mapping):
        category = _normalize_text(weekly_theme.get("category", ""))
        theme = _normalize_text(weekly_theme.get("theme", ""))
        if category or theme:
            lines.append(f"Theme: {category} — {theme}".strip(" —"))
    elif isinstance(weekly_theme, str) and weekly_theme.strip():
        lines.append(f"Theme: {weekly_theme.strip()}")

    learning_summary = _normalize_text(executive_summary.get("learning_summary", ""))
    if learning_summary:
        lines.append(f"Learning summary: {learning_summary}")

    key_takeaways = executive_summary.get("key_takeaways", [])
    if isinstance(key_takeaways, list):
        takeaways = [
            _normalize_text(item)
            for item in key_takeaways
            if _normalize_text(item)
        ]
        if takeaways:
            lines.append("Key takeaways:")
            lines.extend(f"- {item}" for item in takeaways)
    return lines


def _language_growth_text(weekly_review: Mapping[str, Any]) -> str:
    sections: list[str] = []
    expressions = _as_list(weekly_review.get("language_growth", {}).get("new_expressions", []))
    if expressions:
        sections.append(
            "\n".join(
                f"Expression: {_normalize_text(item.get('expression', ''))} | Category: {_normalize_text(item.get('category', ''))} | Learning Value: {_normalize_text(item.get('learning_value', ''))} | Professional Usage: {_normalize_text(item.get('professional_usage', ''))}"
                for item in expressions
                if isinstance(item, Mapping)
            )
        )
    vocabulary = _as_list(weekly_review.get("language_growth", {}).get("personal_vocabulary", []))
    if vocabulary:
        sections.append(
            "\n".join(
                f"Word: {_normalize_text(item.get('word', ''))} | Context: {_normalize_text(item.get('context', ''))} | Professional Relevance: {_normalize_text(item.get('professional_relevance') or item.get('meaning') or item.get('my_usage') or '')}"
                for item in vocabulary
                if isinstance(item, Mapping)
            )
        )
    return "\n\n".join(section for section in sections if section)


def _expression_rows(expressions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell("Expression"),
            _table_cell("Category"),
            _table_cell("Learning Value"),
            _table_cell("Professional Usage"),
        )
    ]
    for item in expressions:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            _table_row(
                _table_cell(_normalize_text(item.get("expression", ""))),
                _table_cell(_normalize_text(item.get("category", ""))),
                _table_cell(_normalize_text(item.get("learning_value", ""))),
                _table_cell(_normalize_text(item.get("professional_usage", ""))),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _vocabulary_rows(vocabulary: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell("Word"),
            _table_cell("Context"),
            _table_cell("Professional Relevance"),
        )
    ]
    for item in vocabulary:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            _table_row(
                _table_cell(_normalize_text(item.get("word", ""))),
                _table_cell(_normalize_text(item.get("context", ""))),
                _table_cell(
                    _normalize_text(
                        item.get("professional_relevance")
                        or item.get("meaning")
                        or item.get("my_usage")
                        or item.get("review_status")
                        or ""
                    )
                ),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _career_rows(career_application: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell("Scenario"),
            _table_cell("Insight"),
            _table_cell("Action"),
        )
    ]
    for item in career_application:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            _table_row(
                _table_cell(_normalize_text(item.get("scenario", ""))),
                _table_cell(_normalize_text(item.get("insight", ""))),
                _table_cell(_normalize_text(item.get("action", item.get("application", "")))),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _snapshot_rows(
    weekly_review: Mapping[str, Any],
    reflection_context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    period = weekly_review.get("period", {})
    if not isinstance(period, Mapping):
        period = {}
    executive_summary = weekly_review.get("executive_summary", {})
    if not isinstance(executive_summary, Mapping):
        executive_summary = {}
    knowledge_insights = _as_list(weekly_review.get("knowledge_insights"))
    learning_summary = _truncate_text(executive_summary.get("learning_summary", ""), 160)
    if not learning_summary and knowledge_insights:
        first_insight = knowledge_insights[0]
        if isinstance(first_insight, Mapping):
            learning_summary = _truncate_text(first_insight.get("insight", ""), 160)
    if not learning_summary:
        learning_summary = "Weekly learning reflection."

    podcast_count = str(len(_extract_source_page_ids(weekly_review, reflection_context)))
    expression_count = str(len(_as_list(weekly_review.get("language_growth", {}).get("new_expressions", []))))
    vocabulary_count = str(len(_as_list(weekly_review.get("language_growth", {}).get("personal_vocabulary", []))))

    rows = [
        _table_row(_table_cell("Metric"), _table_cell("Value")),
        _table_row(_table_cell("Podcasts"), _table_cell(podcast_count)),
        _table_row(_table_cell("Expressions"), _table_cell(expression_count)),
        _table_row(_table_cell("Vocabulary"), _table_cell(vocabulary_count)),
        _table_row(_table_cell("Learning Summary"), _table_cell(learning_summary)),
    ]
    return rows


def _mindset_shift_rows(reflection_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    shifts = [
        shift for shift in _as_list(reflection_context.get("mindset_shifts")) if isinstance(shift, Mapping)
    ]
    rows = [
        _table_row(
            _table_cell("Before"),
            _table_cell("After"),
            _table_cell("Evidence"),
        )
    ]
    for shift in shifts[:2]:
        evidence_items = []
        for item in _as_list(shift.get("evidence")):
            if not isinstance(item, Mapping):
                continue
            source = _truncate_text(item.get("source", ""), 36)
            supporting = _truncate_text(item.get("supporting_concept", ""), 90)
            if source or supporting:
                evidence_items.append(" — ".join(part for part in [source, supporting] if part))
        rows.append(
            _table_row(
                _table_cell(_truncate_text(shift.get("before", ""), 150)),
                _table_cell(_truncate_text(shift.get("after", ""), 150)),
                _table_cell("; ".join(evidence_items[:2])),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _expression_learning_rows(expressions: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell("Expression"),
            _table_cell("Category"),
            _table_cell("Why it matters"),
            _table_cell("Example"),
        )
    ]
    for item in _limit_items(expressions, 5):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            _table_row(
                _table_cell(_truncate_text(item.get("expression", ""), 48)),
                _table_cell(_truncate_text(item.get("category", ""), 24)),
                _table_cell(_truncate_text(item.get("learning_value", "") or item.get("meaning", ""), 120)),
                _table_cell(_truncate_text(item.get("professional_usage", "") or item.get("example", ""), 120)),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _vocabulary_learning_rows(vocabulary: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [
        _table_row(
            _table_cell("Word"),
            _table_cell("Context"),
            _table_cell("Professional relevance"),
        )
    ]
    for item in _limit_items(vocabulary, 5):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            _table_row(
                _table_cell(_truncate_text(item.get("word", ""), 36)),
                _table_cell(_truncate_text(item.get("context", ""), 120)),
                _table_cell(
                    _truncate_text(
                        item.get("professional_relevance")
                        or item.get("meaning")
                        or item.get("my_usage")
                        or "",
                        120,
                    )
                ),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _professional_application_rows(
    weekly_review: Mapping[str, Any],
) -> list[dict[str, Any]]:
    knowledge_insights = [
        item for item in _as_list(weekly_review.get("knowledge_insights")) if isinstance(item, Mapping)
    ]
    career_application = [
        item for item in _as_list(weekly_review.get("career_application")) if isinstance(item, Mapping)
    ]
    rows = [
        _table_row(
            _table_cell("Scenario"),
            _table_cell("Insight"),
            _table_cell("Action"),
        )
    ]
    for idx, item in enumerate(career_application[:3]):
        insight = ""
        if idx < len(knowledge_insights):
            insight = _truncate_text(knowledge_insights[idx].get("insight", ""), 120)
        rows.append(
            _table_row(
                _table_cell(_truncate_text(item.get("scenario", ""), 48)),
                _table_cell(insight),
                _table_cell(_truncate_text(item.get("application", "") or item.get("action", ""), 120)),
            )
        )
    if len(rows) == 1:
        rows.append(_table_row(_table_cell(""), _table_cell(""), _table_cell("")))
    return rows


def _next_week_actions_blocks(reflection_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions = [
        _truncate_text(item, 160)
        for item in _as_list(reflection_context.get("professional_actions"))
        if _truncate_text(item, 160)
    ]
    blocks = [_heading("Next Week Actions")]
    if not actions:
        blocks.append(_paragraph("No next-week actions were generated."))
        return blocks
    for action in actions[:3]:
        blocks.append(_bullet(action))
    return blocks


def _source_reference_blocks(weekly_review: Mapping[str, Any]) -> list[dict[str, Any]]:
    source_ids = _extract_source_page_ids(weekly_review, {})
    blocks = [_heading("Sources")]
    if not source_ids:
        blocks.append(_paragraph("Source podcast references are stored in the Podcasts relation property."))
        return blocks
    for page_id in source_ids[:5]:
        blocks.append(_bullet(f"Podcast page ID: {page_id}"))
    return blocks


def weekly_reflection_page_properties(
    payload: WeeklyReflectionPublishPayload,
) -> dict[str, Any]:
    weekly_review = payload.weekly_review
    reflection_context = payload.reflection_context
    period = weekly_review.get("period", {})
    if not isinstance(period, Mapping):
        period = {}
    weekly_theme = reflection_context.get("weekly_theme", {})
    if not isinstance(weekly_theme, Mapping):
        weekly_theme = {}
    week_title = _week_label(period, _normalize_text(weekly_theme.get("theme", "")) or "Learning")
    properties = {
        "Week": _title_property(week_title),
        "Date": {"date": {"start": _normalize_text(period.get("start_date", "")) or None}},
        "Podcasts": _relation_property(_extract_source_page_ids(weekly_review, reflection_context)),
    }
    return properties


def weekly_reflection_body_blocks(
    payload: WeeklyReflectionPublishPayload,
    podcast_database_id: Optional[str] = None,
) -> list[dict[str, Any]]:
    weekly_review = payload.weekly_review
    reflection_context = payload.reflection_context
    blocks: list[dict[str, Any]] = [_toc_block()]

    core = weekly_review.get("core_idea", {})
    if not isinstance(core, Mapping):
        core = {}
    blocks.append(_heading("1. This Week's Core Idea"))
    blocks.append(_paragraph(_normalize_text(core.get("idea", ""))))
    blocks.append(_paragraph(f"Why it matters: {_normalize_text(core.get('why_it_matters', ''))}"))
    blocks.append(_paragraph(f"My refined understanding: {_normalize_text(core.get('refined_understanding', ''))}"))

    shift = weekly_review.get("mindset_shift")
    if isinstance(shift, Mapping) and _normalize_text(shift.get("before")) and _normalize_text(shift.get("now")):
        blocks.append(_heading("2. How My Thinking Changed"))
        blocks.append(_paragraph(f"Before: {_normalize_text(shift.get('before', ''))}"))
        blocks.append(_paragraph(f"Now: {_normalize_text(shift.get('now', ''))}"))

    ideas = [item for item in _as_list(weekly_review.get("ideas_worth_compounding")) if isinstance(item, Mapping)]
    if ideas:
        blocks.append(_heading("3. Ideas Worth Compounding"))
        for item in ideas[:4]:
            blocks.append(_heading(_normalize_text(item.get("idea", "")), level=3))
            blocks.append(_paragraph(f"Why it matters: {_normalize_text(item.get('why_it_matters', ''))}"))
            blocks.append(_paragraph(f"Where to apply it: {_normalize_text(item.get('application', ''))}"))
            source = _normalize_text(item.get("source_reference", ""))
            if source:
                blocks.append(_paragraph(f"Source: {source}"))

    expressions = [item for item in _as_list(weekly_review.get("expressions_worth_reusing")) if isinstance(item, Mapping)]
    if expressions:
        rows = [_table_row(_table_cell("Expression"), _table_cell("Contextual meaning"), _table_cell("Reusable example"), _table_cell("Function"))]
        for item in expressions[:5]:
            rows.append(_table_row(
                _table_cell(_normalize_text(item.get("expression", ""))),
                _table_cell(_normalize_text(item.get("contextual_meaning", ""))),
                _table_cell(_normalize_text(item.get("reusable_example", ""))),
                _table_cell(_normalize_text(item.get("communication_function", ""))),
            ))
        blocks.append(_heading("4. Expressions Worth Reusing"))
        blocks.append(_table_block(rows, table_width=4))

    connection = _normalize_text(weekly_review.get("language_thinking_connection", ""))
    if connection:
        blocks.append(_heading("5. Language-Thinking Connection"))
        blocks.append(_paragraph(connection))

    application = weekly_review.get("next_week_application", {})
    if isinstance(application, Mapping):
        blocks.append(_heading("6. One Application for Next Week"))
        blocks.append(_paragraph(f"Scenario: {_normalize_text(application.get('scenario', ''))}"))
        blocks.append(_paragraph(f"Behavior: {_normalize_text(application.get('behavior', ''))}"))
        blocks.append(_paragraph(f"Phrase to use: {_normalize_text(application.get('phrase_to_use', ''))}"))
        blocks.append({
            "object": "block",
            "type": "to_do",
            "to_do": {
                "rich_text": [{"type": "text", "text": {"content": _normalize_text(application.get("completion_condition", ""))}}],
                "checked": False,
            },
        })

    sources = [item for item in _as_list(weekly_review.get("sources")) if isinstance(item, Mapping)]
    if sources:
        blocks.append(_heading("7. Sources"))
        for source in sources[:5]:
            title = _normalize_text(source.get("title", "")) or "Podcast source"
            url = _normalize_text(source.get("url", ""))
            blocks.append(_bullet(f"{title}: {url}" if url else title))

    return blocks


def _resolve_inputs(
    weekly_review: Mapping[str, Any],
    reflection_context: Mapping[str, Any],
    pipeline_run_id: str = "",
    reflection_context_id: str = "",
) -> WeeklyReflectionPublishPayload:
    validated_weekly_review = _validate_weekly_review_json(weekly_review)
    validated_reflection_context = _validate_reflection_context_json(reflection_context)
    quality_score = int(
        weekly_review.get("quality_score")
        or weekly_review.get("quality_report", {}).get("score", 0)
        or validated_weekly_review.get("quality_score", 0)
        or 0
    )
    return WeeklyReflectionPublishPayload(
        weekly_review=validated_weekly_review,
        reflection_context=validated_reflection_context,
        quality_score=quality_score,
        pipeline_run_id=_normalize_text(pipeline_run_id),
        reflection_context_id=_normalize_text(reflection_context_id),
    )


def find_existing_weekly_reflection_page(
    notion: Client,
    weekly_reflection_database_id: str,
    payload: WeeklyReflectionPublishPayload,
) -> Optional[str]:
    weekly_review = payload.weekly_review
    period = weekly_review.get("period", {})
    if not isinstance(period, Mapping):
        period = {}
    source_page_ids = _extract_source_page_ids(weekly_review, payload.reflection_context)
    start_date = _normalize_text(period.get("start_date", ""))
    if not start_date:
        return None

    try:
        response = query_database(
            notion,
            weekly_reflection_database_id,
            filter={"property": "Date", "date": {"equals": start_date}},
        )
    except Exception as exc:
        raise WeeklyReflectionWriterError(
            "Failed to query existing Weekly Reflection identity."
        ) from exc

    for page in response.get("results", []):
        if isinstance(page, Mapping) and _page_matches_reflection_identity(page, period, source_page_ids):
            page_id = str(page.get("id", "")).strip()
            if page_id:
                return page_id
    return None


def load_weekly_reflection_database_id(
    env: Optional[Mapping[str, str]] = None,
) -> str:
    if env is None:
        load_dotenv(Path(".env"))
        env = os.environ
    database_id = (
        env.get(DEFAULT_WEEKLY_REFLECTION_DATABASE_ID_ENV)
        or env.get(LEGACY_WEEKLY_REFLECTION_DATABASE_ID_ENV)
        or ""
    ).strip()
    if not database_id:
        raise WeeklyReflectionWriterError(
            "Missing required environment variable NOTION_WEEKLY_REFLECTION_DATABASE_ID. "
            "Add it to .env before publishing Weekly Reflection pages."
        )
    return database_id


def _replace_generated_page_body(
    notion: Client,
    page_id: str,
    children: Sequence[Mapping[str, Any]],
) -> None:
    """Replace the generated body while preserving the page identity and relations."""
    blocks_api = getattr(notion, "blocks", None)
    children_api = getattr(blocks_api, "children", None)
    if blocks_api is None or children_api is None:
        return

    cursor: Optional[str] = None
    existing_blocks: list[Mapping[str, Any]] = []
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = children_api.list(**kwargs)
        existing_blocks.extend(
            item for item in response.get("results", []) if isinstance(item, Mapping)
        )
        if not response.get("has_more"):
            break
        cursor = str(response.get("next_cursor", "") or "")
        if not cursor:
            break

    for block in existing_blocks:
        block_id = _normalize_text(block.get("id", ""))
        if block_id:
            blocks_api.delete(block_id=block_id)
    children_api.append(block_id=page_id, children=list(children))


def publish_weekly_reflection(
    weekly_review: Mapping[str, Any],
    reflection_context: Mapping[str, Any],
    notion: Optional[Client] = None,
    weekly_reflection_database_id: Optional[str] = None,
    podcast_database_id: Optional[str] = None,
    pipeline_run_id: str = "",
    reflection_context_id: str = "",
) -> WeeklyReflectionPublishResult:
    payload = _resolve_inputs(
        weekly_review,
        reflection_context,
        pipeline_run_id=pipeline_run_id,
        reflection_context_id=reflection_context_id,
    )

    if notion is None or weekly_reflection_database_id is None:
        notion_token = os.environ.get("NOTION_TOKEN", "").strip()
        if not notion_token:
            raise WeeklyReflectionWriterError(
                "Missing required environment variable NOTION_TOKEN. "
                "Create a Notion integration token and add it to .env."
            )
        notion = notion or create_notion_client(notion_token)
        weekly_reflection_database_id = weekly_reflection_database_id or load_weekly_reflection_database_id()

    configured_role_ids = {WEEKLY_REVIEW: weekly_reflection_database_id}
    if podcast_database_id:
        configured_role_ids[PODCAST_LIBRARY] = podcast_database_id
    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids=configured_role_ids,
    )
    source_page_ids = _extract_source_page_ids(
        payload.weekly_review,
        payload.reflection_context,
    )
    for source_page_id in source_page_ids:
        ensure_notion_page_belongs_to_role(
            notion,
            source_page_id,
            PODCAST_LIBRARY,
        )
    try:
        existing_page_id = find_existing_weekly_reflection_page(
            notion,
            weekly_reflection_database_id,
            payload,
        )
        if existing_page_id:
            ensure_notion_page_belongs_to_role(
                notion,
                existing_page_id,
                WEEKLY_REVIEW,
            )
            response = notion.pages.update(
                page_id=existing_page_id,
                properties=weekly_reflection_page_properties(payload),
            )
            _replace_generated_page_body(
                notion,
                existing_page_id,
                weekly_reflection_body_blocks(payload, podcast_database_id=podcast_database_id),
            )
        else:
            response = notion.pages.create(
                parent={"data_source_id": weekly_reflection_database_id},
                properties=weekly_reflection_page_properties(payload),
                children=weekly_reflection_body_blocks(payload, podcast_database_id=podcast_database_id),
            )
    except APIResponseError as exc:
        code = getattr(exc, "code", "unknown")
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        raise WeeklyReflectionWriterError(
            f"Notion API failed to publish weekly reflection: {code} {detail}"
        ) from exc
    except Exception as exc:
        raise WeeklyReflectionWriterError(f"Failed to publish weekly reflection: {exc}") from exc

    page_id = response.get("id", "")
    if not page_id:
        raise WeeklyReflectionWriterError("Notion did not return a page ID.")
    return WeeklyReflectionPublishResult(page_id=page_id, page_url=response.get("url"))
