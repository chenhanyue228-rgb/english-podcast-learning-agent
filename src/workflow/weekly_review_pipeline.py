"""Weekly review workflow for Notion-backed learning summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.analyzer.weekly_review_analyzer import (
    WeeklyExpressionItem,
    WeeklyLearningData,
    WeeklyPodcastItem,
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


def _extract_title_property(page: Mapping[str, Any]) -> str:
    properties = page.get("properties", {})
    title_prop = properties.get("Title", {})
    title = title_prop.get("title", [])
    if title and isinstance(title, list):
        first = title[0].get("plain_text") or title[0].get("text", {}).get("content", "")
        return str(first)
    return ""


def _extract_rich_text_property(page: Mapping[str, Any], name: str) -> str:
    properties = page.get("properties", {})
    value = properties.get(name, {}).get("rich_text", [])
    if value and isinstance(value, list):
        return " ".join(
            str(item.get("plain_text") or item.get("text", {}).get("content", "")).strip()
            for item in value
            if isinstance(item, Mapping)
        ).strip()
    return ""


def _extract_select_property(page: Mapping[str, Any], name: str) -> str:
    return str(page.get("properties", {}).get(name, {}).get("select", {}).get("name", ""))


def _extract_relation_ids(page: Mapping[str, Any], name: str) -> list[str]:
    relations = page.get("properties", {}).get(name, {}).get("relation", [])
    if not isinstance(relations, list):
        return []
    return [str(item.get("id", "")) for item in relations if isinstance(item, Mapping) and item.get("id")]


def fetch_weekly_learning_data(
    notion: Any,
    podcast_database_id: str,
    expression_database_id: str,
    today: Optional[date] = None,
) -> WeeklyLearningData:
    start_date, end_date = _week_bounds(today)
    week = _week_label(today)
    current_date = (today or date.today()).isoformat()

    podcast_results: list[Mapping[str, Any]] = []
    try:
        if hasattr(notion, "data_sources"):
            podcast_results = notion.data_sources.query(
                data_source_id=podcast_database_id,
                filter={
                    "and": [
                        {"property": "Date", "date": {"on_or_after": start_date}},
                        {"property": "Date", "date": {"on_or_before": end_date}},
                    ]
                },
            ).get("results", [])
        else:
            podcast_results = notion.databases.query(
                database_id=podcast_database_id,
                filter={
                    "and": [
                        {"property": "Date", "date": {"on_or_after": start_date}},
                        {"property": "Date", "date": {"on_or_before": end_date}},
                    ]
                },
            ).get("results", [])
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
            if hasattr(notion, "data_sources"):
                expression_results = notion.data_sources.query(
                    data_source_id=expression_database_id,
                    filter={
                        "or": [
                            {
                                "property": "Source Podcast",
                                "relation": {"contains": podcast_id},
                            }
                            for podcast_id in podcast_ids
                        ]
                    },
                ).get("results", [])
            else:
                expression_results = notion.databases.query(
                    database_id=expression_database_id,
                    filter={
                        "or": [
                            {
                                "property": "Source Podcast",
                                "relation": {"contains": podcast_id},
                            }
                            for podcast_id in podcast_ids
                        ]
                    },
                ).get("results", [])
        except Exception as exc:
            raise WeeklyReviewPipelineError(f"Failed to fetch expression data: {exc}") from exc

        for page in expression_results:
            relations = _extract_relation_ids(page, "Source Podcast")
            if not any(page_id in podcast_ids for page_id in relations):
                continue
            expression_items.append(
                WeeklyExpressionItem(
                    expression=_extract_title_property(page),
                    category=_extract_select_property(page, "Category"),
                    meaning=_extract_rich_text_property(page, "Meaning"),
                    usage_context=_extract_rich_text_property(page, "Usage Context"),
                    review_status=_extract_select_property(page, "Review Status"),
                    podcast_page_id=relations[0] if relations else "",
                )
            )

    weekly_data = WeeklyLearningData(
        week=week,
        date=current_date,
        podcasts=podcast_items,
        expressions=expression_items,
    )

    return weekly_data


def build_weekly_review_artifacts(
    notion: Any,
    podcast_database_id: str,
    expression_database_id: str,
    data_dir: Path,
    today: Optional[date] = None,
) -> tuple[Path, Path, WeeklyLearningData]:
    weekly_data = fetch_weekly_learning_data(
        notion,
        podcast_database_id,
        expression_database_id,
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
    today: Optional[date] = None,
) -> WeeklyReviewPipelineResult:
    weekly_data = fetch_weekly_learning_data(
        notion,
        podcast_database_id,
        expression_database_id,
        today=today,
    )
    request_path = data_dir / "weekly_review_requests" / f"{weekly_data.week}.json"
    request_path = save_weekly_review_request(weekly_data, request_path)
    analysis = validate_weekly_review_output(
        json.loads(generated_analysis_path.read_text(encoding="utf-8"))
    )
    publish_result = publish_weekly_review(
        WeeklyReviewPublishPayload(
            week=str(analysis.get("week", weekly_data.week)),
            date=str(analysis.get("date", weekly_data.date)),
            statistics=analysis.get("statistics", {}),
            summary=analysis.get("summary", {}),
            key_learning_points=list(analysis.get("key_learning_points", [])),
            recommended_review=list(analysis.get("recommended_review", [])),
            podcast_page_ids=[podcast.page_id for podcast in weekly_data.podcasts if podcast.page_id],
        ),
        notion=notion,
        weekly_database_id=weekly_database_id,
    )
    return WeeklyReviewPipelineResult(
        request_path=request_path,
        analysis_path=generated_analysis_path,
        publish_result=publish_result,
    )
