"""Weekly review analysis handoff for Codex Skill generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.analyzer.ai_client import SkillAIWorkflowError, load_analysis_schema
from src.analyzer.prompt_loader import load_prompt
from src.analyzer.validators import ensure_mapping


DEFAULT_WEEKLY_REVIEW_PROMPT_PATH = Path("skill/prompts/weekly_review_prompt.md")
DEFAULT_WEEKLY_REVIEW_SCHEMA_PATH = Path("skill/schemas/weekly_review_schema.json")


class WeeklyReviewAnalyzerError(RuntimeError):
    """Raised when weekly review analysis cannot be prepared or validated."""


@dataclass(frozen=True)
class WeeklyPodcastItem:
    title: str
    topic: str = ""
    difficulty: str = ""
    short_summary: str = ""
    page_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "short_summary": self.short_summary,
            "page_id": self.page_id,
        }


@dataclass(frozen=True)
class WeeklyExpressionItem:
    expression: str
    category: str
    meaning: str = ""
    usage_context: str = ""
    review_status: str = ""
    podcast_page_id: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "expression": self.expression,
            "category": self.category,
            "meaning": self.meaning,
            "usage_context": self.usage_context,
            "review_status": self.review_status,
            "podcast_page_id": self.podcast_page_id,
        }


@dataclass(frozen=True)
class WeeklyLearningData:
    week: str
    date: str
    podcasts: Sequence[WeeklyPodcastItem]
    expressions: Sequence[WeeklyExpressionItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week": self.week,
            "date": self.date,
            "podcasts": [podcast.to_dict() for podcast in self.podcasts],
            "expressions": [expression.to_dict() for expression in self.expressions],
        }


@dataclass(frozen=True)
class WeeklyReviewRequest:
    week: str
    date: str
    prompt: str
    schema: Mapping[str, Any]
    weekly_learning_data: WeeklyLearningData

    def to_dict(self) -> dict[str, Any]:
        return {
            "week": self.week,
            "date": self.date,
            "prompt": self.prompt,
            "schema": dict(self.schema),
            "weekly_learning_data": self.weekly_learning_data.to_dict(),
        }


def load_weekly_review_prompt(
    prompt_path: Path = DEFAULT_WEEKLY_REVIEW_PROMPT_PATH,
) -> str:
    return load_prompt(prompt_path.name, prompt_path.parent)


def load_weekly_review_schema(
    schema_path: Path = DEFAULT_WEEKLY_REVIEW_SCHEMA_PATH,
) -> Mapping[str, Any]:
    return load_analysis_schema(schema_path)


def build_weekly_review_request(
    weekly_learning_data: WeeklyLearningData,
    prompt_path: Path = DEFAULT_WEEKLY_REVIEW_PROMPT_PATH,
    schema_path: Path = DEFAULT_WEEKLY_REVIEW_SCHEMA_PATH,
) -> WeeklyReviewRequest:
    if not weekly_learning_data.week.strip():
        raise WeeklyReviewAnalyzerError("Week label is required.")
    if not weekly_learning_data.date.strip():
        raise WeeklyReviewAnalyzerError("Review date is required.")

    prompt = load_weekly_review_prompt(prompt_path)
    schema = load_weekly_review_schema(schema_path)
    return WeeklyReviewRequest(
        week=weekly_learning_data.week,
        date=weekly_learning_data.date,
        prompt=prompt,
        schema=schema,
        weekly_learning_data=weekly_learning_data,
    )


def validate_weekly_review_output(generated_output: Mapping[str, Any]) -> dict[str, Any]:
    payload = ensure_mapping(generated_output, "weekly_review")
    required_keys = [
        "week",
        "date",
        "statistics",
        "summary",
        "key_learning_points",
        "recommended_review",
    ]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise SkillAIWorkflowError(
            f"Weekly review output is missing required fields: {', '.join(missing)}"
        )
    return dict(payload)


def save_weekly_review_request(
    weekly_learning_data: WeeklyLearningData,
    output_path: Path,
    prompt_path: Path = DEFAULT_WEEKLY_REVIEW_PROMPT_PATH,
    schema_path: Path = DEFAULT_WEEKLY_REVIEW_SCHEMA_PATH,
) -> Path:
    request = build_weekly_review_request(
        weekly_learning_data,
        prompt_path=prompt_path,
        schema_path=schema_path,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()
