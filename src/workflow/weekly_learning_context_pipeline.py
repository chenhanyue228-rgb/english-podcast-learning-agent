"""Orchestrate Podcast Library extraction into WeeklyLearningContext.json."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from src.config.settings import load_settings
from src.notion.uploader import create_notion_client
from src.workflow.podcast_extractor import extract_weekly_learning_context_for_page
from src.workflow.podcast_query import query_podcast_pages
from src.workflow.schema_validator import validate_weekly_learning_context


class WeeklyLearningContextPipelineError(RuntimeError):
    """Raised when weekly learning context extraction fails."""


@dataclass(frozen=True)
class WeeklyLearningExtractionReport:
    podcast_pages_scanned: int
    successfully_extracted: int
    expressions_found: int
    ai_highlights_found: int
    pink_highlights_found: int
    failures: int

    def to_dict(self) -> dict[str, int]:
        return {
            "podcast_pages_scanned": self.podcast_pages_scanned,
            "successfully_extracted": self.successfully_extracted,
            "expressions_found": self.expressions_found,
            "ai_highlights_found": self.ai_highlights_found,
            "pink_highlights_found": self.pink_highlights_found,
            "failures": self.failures,
        }


def _date_range(today: Optional[date] = None) -> tuple[str, str]:
    current = today or date.today()
    start = current - timedelta(days=7)
    return start.isoformat(), current.isoformat()


def _generated_at() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_weekly_learning_context(
    notion: Any,
    podcast_database_id: str,
    today: Optional[date] = None,
) -> tuple[dict[str, Any], WeeklyLearningExtractionReport]:
    start_date, end_date = _date_range(today)
    pages = query_podcast_pages(
        notion=notion,
        database_id=podcast_database_id,
        start_date=start_date,
        end_date=end_date,
    )

    podcasts: list[dict[str, Any]] = []
    learning_expressions: list[dict[str, Any]] = []
    ai_highlights: list[dict[str, Any]] = []
    user_vocabulary: list[dict[str, Any]] = []
    failures = 0

    for page in pages:
        try:
            extraction = extract_weekly_learning_context_for_page(page, notion=notion)
        except Exception:
            failures += 1
            continue

        if not extraction:
            failures += 1
            continue

        podcasts.extend(extraction.get("podcasts", []))
        learning_expressions.extend(extraction.get("learning_expressions", []))
        ai_highlights.extend(extraction.get("ai_highlights", []))
        user_vocabulary.extend(extraction.get("user_vocabulary", []))

    context = {
        "metadata": {
            "period_start": start_date,
            "period_end": end_date,
            "generated_at": _generated_at(),
            "source": "Podcast Library",
        },
        "podcasts": podcasts,
        "learning_expressions": learning_expressions,
        "ai_highlights": ai_highlights,
        "user_vocabulary": user_vocabulary,
    }
    validate_weekly_learning_context(context)
    report = WeeklyLearningExtractionReport(
        podcast_pages_scanned=len(pages),
        successfully_extracted=len(podcasts),
        expressions_found=len(learning_expressions),
        ai_highlights_found=len(ai_highlights),
        pink_highlights_found=len(user_vocabulary),
        failures=failures,
    )
    return context, report


def save_weekly_learning_context(
    context: Mapping[str, Any],
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(context), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()


def run_weekly_learning_extraction(
    notion: Any = None,
    output_path: Path = Path("output/weekly_learning_context.json"),
    today: Optional[date] = None,
) -> tuple[dict[str, Any], WeeklyLearningExtractionReport, Path]:
    settings = load_settings()
    if not settings.notion_token:
        raise WeeklyLearningContextPipelineError(
            "Missing NOTION_TOKEN. Set it in .env before running extraction."
        )
    if not settings.notion_podcast_database_id:
        raise WeeklyLearningContextPipelineError(
            "Missing NOTION_PODCAST_LIBRARY_DATABASE_ID. Set it in .env before running extraction."
        )

    active_notion = notion or create_notion_client(settings.notion_token)
    context, report = build_weekly_learning_context(
        notion=active_notion,
        podcast_database_id=settings.notion_podcast_database_id,
        today=today,
    )
    saved_path = save_weekly_learning_context(context, output_path)
    return context, report, saved_path
