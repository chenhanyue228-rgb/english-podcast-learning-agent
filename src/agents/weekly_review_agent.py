"""Weekly Review agent orchestration.

This layer translates analysis JSON into Weekly Review Notion payloads,
supports dry-run previews, and publishes using the existing Notion client.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.analyzer.ai_client import read_generated_analysis_file
from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client
from src.notion.weekly_review_publisher import (
    WeeklyReviewPublishPayload,
    WeeklyReviewPublishResult,
    publish_weekly_review,
)


LOGGER = logging.getLogger(__name__)


class WeeklyReviewAgentError(RuntimeError):
    """Raised when Weekly Review analysis or publishing fails."""


@dataclass(frozen=True)
class WeeklyReviewDryRunPlan:
    week: str
    total_expression_items: int
    total_vocabulary_items: int
    category_distribution: dict[str, int]
    top_expressions: list[dict[str, Any]]
    preview_payload: dict[str, Any]


@dataclass(frozen=True)
class WeeklyReviewAgentResult:
    kind: str
    value: str
    publish_result: Optional[WeeklyReviewPublishResult] = None


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _top_expression_items(analysis: Mapping[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    expression_items = []
    for item in _as_list(analysis.get("expression_review")):
        if not isinstance(item, Mapping):
            continue
        expression = str(item.get("expression", "")).strip()
        if not expression:
            continue
        expression_items.append(
            {
                "expression": expression,
                "category": str(item.get("category", "")).strip(),
                "meaning": str(item.get("meaning", "")).strip(),
                "original_context": str(item.get("original_context", "")).strip(),
                "learning_note": str(item.get("learning_note", "")).strip(),
                "review_priority": int(item.get("review_priority", 0) or 0),
            }
        )
    expression_items.sort(key=lambda item: item["review_priority"], reverse=True)
    return expression_items[:limit]


def _category_distribution(analysis: Mapping[str, Any]) -> dict[str, int]:
    distribution = _as_mapping(analysis.get("category_distribution"))
    result: dict[str, int] = {}
    for key, value in distribution.items():
        try:
            result[str(key)] = int(value)
        except Exception:
            result[str(key)] = 0
    return result


def _build_payload_from_analysis(analysis: Mapping[str, Any]) -> WeeklyReviewPublishPayload:
    week = str(analysis.get("week", "")).strip()
    podcast_summary = _as_mapping(analysis.get("podcast_summary"))
    key_topics = [str(item).strip() for item in _as_list(analysis.get("key_topics")) if str(item).strip()]
    learning_insights = [
        item for item in _as_list(analysis.get("learning_insights")) if isinstance(item, Mapping)
    ]
    expression_review = _top_expression_items(analysis)
    vocabulary_memory = [
        item for item in _as_list(analysis.get("vocabulary_memory")) if isinstance(item, Mapping)
    ]
    next_week_plan = [str(item).strip() for item in _as_list(analysis.get("next_week_plan")) if str(item).strip()]

    executive_summary = {
        "overview": str(podcast_summary.get("english", "")).strip()
        or str(podcast_summary.get("chinese", "")).strip(),
        "takeaway": str(
            analysis.get("podcast_summary", {}).get("chinese", "")
            if isinstance(analysis.get("podcast_summary"), Mapping)
            else ""
        ).strip()
        or (key_topics[0] if key_topics else ""),
        "highlights": key_topics,
    }

    knowledge_insights = []
    for item in learning_insights:
        insight = str(item.get("insight", "")).strip()
        evidence = str(item.get("evidence", "")).strip()
        why_it_matters = str(item.get("why_it_matters", "")).strip()
        knowledge_insights.append(
            {
                "what_happened": insight,
                "why_it_matters": why_it_matters or evidence,
                "my_interpretation": evidence or insight,
                "application": why_it_matters or (next_week_plan[0] if next_week_plan else ""),
            }
        )

    expression_upgrade = [
        {
            "expression": item["expression"],
            "meaning": item["meaning"],
            "context": item["original_context"],
            "example": item["learning_note"] or item["original_context"],
        }
        for item in expression_review
    ]

    career_reflection = {
        "questions": [
            "What changed my thinking this week?",
            "Which phrases are worth using in real work situations?",
        ],
        "possible_applications": next_week_plan[:2] or ["Use the strongest learning points in the next speaking session."],
    }

    return WeeklyReviewPublishPayload(
        week=week,
        executive_summary=executive_summary,
        knowledge_insights=knowledge_insights,
        expression_upgrade=expression_upgrade,
        vocabulary_memory=vocabulary_memory,
        career_reflection=career_reflection,
        next_learning_direction=next_week_plan,
    )


def build_weekly_review_dry_run_plan(analysis: Mapping[str, Any]) -> WeeklyReviewDryRunPlan:
    top_expressions = _top_expression_items(analysis)
    payload = _build_payload_from_analysis(analysis)
    vocabulary_memory = _as_list(analysis.get("vocabulary_memory"))
    return WeeklyReviewDryRunPlan(
        week=str(analysis.get("week", "")).strip(),
        total_expression_items=len(top_expressions),
        total_vocabulary_items=len([item for item in vocabulary_memory if isinstance(item, Mapping)]),
        category_distribution=_category_distribution(analysis),
        top_expressions=top_expressions[:3],
        preview_payload={
            "week": payload.week,
            "executive_summary": payload.executive_summary,
            "knowledge_insights": payload.knowledge_insights[:2],
            "expression_upgrade": payload.expression_upgrade[:3],
            "vocabulary_memory": payload.vocabulary_memory[:3],
            "career_reflection": payload.career_reflection,
            "next_learning_direction": payload.next_learning_direction[:3],
        },
    )


def _print_dry_run_plan(plan: WeeklyReviewDryRunPlan) -> None:
    print("Weekly Review dry run")
    print()
    print("Week:")
    print(plan.week)
    print()
    print("Total expressions:")
    print(plan.total_expression_items)
    print()
    print("Vocabulary items:")
    print(plan.total_vocabulary_items)
    print()
    print("Category distribution:")
    print(json.dumps(plan.category_distribution, ensure_ascii=False, indent=2))
    print()
    print("Preview:")
    print(json.dumps(plan.preview_payload, ensure_ascii=False, indent=2))


def run_weekly_review_agent(
    analysis_path: Path,
    dry_run: bool = False,
    notion: Optional[Any] = None,
    weekly_database_id: Optional[str] = None,
    vocabulary_database_id: Optional[str] = None,
) -> WeeklyReviewAgentResult:
    try:
        analysis_payload = read_generated_analysis_file(analysis_path)
        if not isinstance(analysis_payload, Mapping):
            raise WeeklyReviewAgentError("Weekly Review analysis JSON must be an object.")
        analysis = analysis_payload
    except Exception as exc:
        raise WeeklyReviewAgentError(str(exc)) from exc

    if dry_run:
        plan = build_weekly_review_dry_run_plan(analysis)
        _print_dry_run_plan(plan)
        return WeeklyReviewAgentResult(kind="weekly_review_dry_run", value=str(analysis_path))

    config = load_notion_config()
    notion = notion or create_notion_client(config.token)
    weekly_database_id = weekly_database_id or config.weekly_database_id
    vocabulary_database_id = vocabulary_database_id or getattr(
        config,
        "vocabulary_database_id",
        None,
    )

    payload = _build_payload_from_analysis(analysis)
    try:
        result = publish_weekly_review(
            payload,
            notion=notion,
            weekly_database_id=weekly_database_id,
            vocabulary_database_id=vocabulary_database_id,
        )
    except Exception as exc:
        raise WeeklyReviewAgentError(str(exc)) from exc

    LOGGER.info("Weekly review page created: %s", result.page_id)
    return WeeklyReviewAgentResult(
        kind="weekly_review_page",
        value=result.page_url or result.page_id,
        publish_result=result,
    )
