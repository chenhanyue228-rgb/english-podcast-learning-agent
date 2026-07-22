"""Weekly review workflow for Notion-backed learning summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import logging

from src.analyzer.weekly_review_analyzer import (
    WeeklyExpressionItem,
    WeeklyLearningData,
    WeeklyPodcastItem,
    WeeklyVocabularyMemoryItem,
    build_weekly_review_request,
    save_weekly_review_request,
    validate_weekly_review_output,
)
from src.notion.config import load_notion_config
from src.notion.weekly_review_publisher import (
    WeeklyReviewPublishPayload,
    WeeklyReviewPublishResult,
    publish_weekly_review,
)
from src.notion.uploader import create_notion_client


LOGGER = logging.getLogger(__name__)


class WeeklyReviewPipelineError(RuntimeError):
    """Raised when the weekly review workflow cannot complete."""


@dataclass(frozen=True)
class WeeklyReviewPipelineResult:
    request_path: Path
    analysis_path: Path
    publish_result: WeeklyReviewPublishResult


def _week_bounds(today: Optional[date] = None) -> tuple[str, str]:
    current = today or date.today()
    start = current - timedelta(days=current.weekday())
    return start.isoformat(), current.isoformat()


def _week_label(today: Optional[date] = None) -> str:
    current = today or date.today()
    return f"{current.isocalendar()[0]}-W{current.isocalendar()[1]:02d}"


def _extract_title_property(page: Mapping[str, Any], property_name: str = "Title") -> str:
    properties = page.get("properties", {})
    title_prop = properties.get(property_name)
    if not isinstance(title_prop, Mapping):
        _debug_empty_property(page, property_name, "title")
        return ""
    title = title_prop.get("title")
    if not isinstance(title, list):
        _debug_empty_property(page, property_name, "title")
        return ""
    first = _extract_first_text_value(title)
    if first:
        return first
    _debug_empty_property(page, property_name, "title")
    return ""


def _extract_rich_text_property(page: Mapping[str, Any], name: str) -> str:
    properties = page.get("properties", {})
    prop = properties.get(name)
    if not isinstance(prop, Mapping):
        _debug_empty_property(page, name, "rich_text")
        return ""
    value = prop.get("rich_text")
    if not isinstance(value, list):
        _debug_empty_property(page, name, "rich_text")
        return ""
    text = " ".join(
        str(item.get("plain_text") or item.get("text", {}).get("content", "")).strip()
        for item in value
        if isinstance(item, Mapping)
    ).strip()
    if text:
        return text
    _debug_empty_property(page, name, "rich_text")
    return ""


def _extract_select_property(page: Mapping[str, Any], name: str) -> str:
    properties = page.get("properties", {})
    prop = properties.get(name)
    if not isinstance(prop, Mapping):
        _debug_empty_property(page, name, "select")
        return ""
    value = prop.get("select")
    if not isinstance(value, Mapping):
        _debug_empty_property(page, name, "select")
        return ""
    result = value.get("name")
    if result:
        return str(result)
    _debug_empty_property(page, name, "select")
    return ""


def _extract_multi_select_property(page: Mapping[str, Any], name: str) -> str:
    properties = page.get("properties", {})
    prop = properties.get(name)
    if not isinstance(prop, Mapping):
        _debug_empty_property(page, name, "multi_select")
        return ""
    value = prop.get("multi_select")
    if not isinstance(value, list):
        _debug_empty_property(page, name, "multi_select")
        return ""
    names = [
        str(item.get("name", "")).strip()
        for item in value
        if isinstance(item, Mapping) and item.get("name")
    ]
    if names:
        return ", ".join(names)
    _debug_empty_property(page, name, "multi_select")
    return ""


def _extract_relation_ids(page: Mapping[str, Any], name: str) -> list[str]:
    relations = page.get("properties", {}).get(name, {}).get("relation", [])
    if not isinstance(relations, list):
        return []
    return [str(item.get("id", "")) for item in relations if isinstance(item, Mapping) and item.get("id")]


def _extract_first_text_value(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return ""
    first = items[0]
    if not isinstance(first, Mapping):
        return ""
    return str(first.get("plain_text") or first.get("text", {}).get("content", "")).strip()


def _debug_empty_property(page: Mapping[str, Any], property_name: str, property_type: str) -> None:
    page_id = str(page.get("id", ""))
    LOGGER.debug(
        "Empty Notion property: page_id=%s property_name=%s property_type=%s",
        page_id,
        property_name,
        property_type,
    )


def _build_statistics(
    weekly_data: WeeklyLearningData,
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    podcast_count = len(weekly_data.podcasts)
    expression_count = len(weekly_data.expressions)
    category_distribution: dict[str, int] = {}
    for expression in weekly_data.expressions:
        category = str(expression.category).strip() or "Unknown"
        category_distribution[category] = category_distribution.get(category, 0) + 1
    return {
        "podcast_count": podcast_count,
        "expression_count": expression_count,
        "category_distribution": category_distribution,
    }


def _query_data_source(
    notion: Any,
    data_source_id: str,
    query_filter: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
        response = notion.data_sources.query(
            data_source_id=data_source_id,
            filter=query_filter,
        )
        return response.get("results", [])

    raise WeeklyReviewPipelineError(
        "This Notion client does not support data_sources.query(). "
        "The installed notion-client version or runtime wrapper is incompatible."
    )


def fetch_weekly_learning_data(
    notion: Any,
    podcast_database_id: str,
    expression_database_id: str,
    vocabulary_memory: Optional[Sequence[Mapping[str, Any]]] = None,
    today: Optional[date] = None,
) -> WeeklyLearningData:
    start_date, end_date = _week_bounds(today)
    week = _week_label(today)
    current_date = (today or date.today()).isoformat()
    try:
        podcast_results = _query_data_source(
            notion,
            podcast_database_id,
            {
                "and": [
                    {"property": "Date", "date": {"on_or_after": start_date}},
                    {"property": "Date", "date": {"on_or_before": end_date}},
                ]
            },
        )
    except Exception as exc:
        raise WeeklyReviewPipelineError(f"Failed to fetch podcast data: {exc}") from exc

    podcast_items: list[WeeklyPodcastItem] = []
    podcast_ids: list[str] = []
    for page in podcast_results:
        page_id = str(page.get("id", ""))
        podcast_ids.append(page_id)
        podcast_items.append(
            WeeklyPodcastItem(
                title=_extract_title_property(page),
                topic=_extract_select_property(page, "Topic"),
                difficulty=_extract_select_property(page, "Difficulty"),
                short_summary=_extract_rich_text_property(page, "Short Summary"),
                page_id=page_id,
            )
        )

    expression_items: list[WeeklyExpressionItem] = []
    if podcast_ids:
        try:
            expression_results = _query_data_source(
                notion,
                expression_database_id,
                {
                    "or": [
                        {
                            "property": "Source Podcast",
                            "relation": {"contains": podcast_id},
                        }
                        for podcast_id in podcast_ids
                    ]
                },
            )
        except Exception as exc:
            raise WeeklyReviewPipelineError(f"Failed to fetch expression data: {exc}") from exc

        for page in expression_results:
            relations = _extract_relation_ids(page, "Source Podcast")
            if not any(page_id in podcast_ids for page_id in relations):
                continue
            expression_items.append(
                WeeklyExpressionItem(
                    expression=_extract_title_property(page, "Expression"),
                    category=_extract_select_property(page, "Category"),
                    meaning=_extract_rich_text_property(page, "Meaning"),
                    usage_context=_extract_rich_text_property(page, "Usage Context"),
                    review_status=_extract_select_property(page, "Review Status")
                    or _extract_multi_select_property(page, "Review Status"),
                    podcast_page_id=relations[0] if relations else "",
                )
            )

    weekly_data = WeeklyLearningData(
        week=week,
        date=current_date,
        podcasts=podcast_items,
        expressions=expression_items,
        vocabulary_memory=[
            WeeklyVocabularyMemoryItem(
                word=str(item.get("word", "")).strip(),
                context=str(item.get("context", "")).strip(),
                meaning=str(item.get("meaning", "")).strip(),
                professional_category=str(item.get("professional_category", "")).strip(),
                my_usage=str(item.get("my_usage", "")).strip(),
                review_status=str(item.get("review_status", "")).strip(),
            )
            for item in (vocabulary_memory or [])
            if isinstance(item, Mapping) and str(item.get("word", "")).strip()
        ],
    )

    return weekly_data


def build_weekly_review_artifacts(
    notion: Any,
    podcast_database_id: str,
    expression_database_id: str,
    data_dir: Path,
    vocabulary_memory: Optional[Sequence[Mapping[str, Any]]] = None,
    today: Optional[date] = None,
) -> tuple[Path, Path, WeeklyLearningData]:
    weekly_data = fetch_weekly_learning_data(
        notion,
        podcast_database_id,
        expression_database_id,
        vocabulary_memory=vocabulary_memory,
        today=today,
    )
    request_path = data_dir / "weekly_review_requests" / f"{weekly_data.week}.json"
    request_path = save_weekly_review_request(weekly_data, request_path)
    return request_path, request_path.with_name(f"{weekly_data.week}.analysis.json"), weekly_data


def run_weekly_review_workflow(
    notion: Any,
    podcast_database_id: str,
    expression_database_id: str,
    weekly_database_id: str,
    data_dir: Path,
    generated_analysis_path: Path,
    vocabulary_memory: Optional[Sequence[Mapping[str, Any]]] = None,
    today: Optional[date] = None,
) -> WeeklyReviewPipelineResult:
    weekly_data = fetch_weekly_learning_data(
        notion,
        podcast_database_id,
        expression_database_id,
        vocabulary_memory=vocabulary_memory,
        today=today,
    )
    request_path = data_dir / "weekly_review_requests" / f"{weekly_data.week}.json"
    request_path = save_weekly_review_request(weekly_data, request_path)
    analysis = validate_weekly_review_output(
        json.loads(generated_analysis_path.read_text(encoding="utf-8"))
    )
    statistics = _build_statistics(weekly_data, analysis)
    executive_summary = analysis.get("executive_summary", {})
    if not isinstance(executive_summary, Mapping):
        executive_summary = {}
    knowledge_insights = analysis.get("knowledge_insights", [])
    if not isinstance(knowledge_insights, list):
        knowledge_insights = []
    expression_upgrade = analysis.get("expression_upgrade", [])
    if not isinstance(expression_upgrade, list):
        expression_upgrade = []
    vocabulary_memory = analysis.get("vocabulary_memory", [])
    if not isinstance(vocabulary_memory, list):
        vocabulary_memory = []
    career_reflection = analysis.get("career_reflection", {})
    if not isinstance(career_reflection, Mapping):
        career_reflection = {}
    next_learning_direction = analysis.get("next_learning_direction", [])
    if not isinstance(next_learning_direction, list):
        next_learning_direction = []
    publish_result = publish_weekly_review(
        WeeklyReviewPublishPayload(
            week=str(analysis.get("week", weekly_data.week)),
            executive_summary=executive_summary,
            knowledge_insights=knowledge_insights,
            expression_upgrade=expression_upgrade,
            vocabulary_memory=vocabulary_memory,
            career_reflection=career_reflection,
            next_learning_direction=next_learning_direction,
        ),
        notion=notion,
        weekly_database_id=weekly_database_id,
    )
    return WeeklyReviewPipelineResult(
        request_path=request_path,
        analysis_path=generated_analysis_path,
        publish_result=publish_result,
    )
