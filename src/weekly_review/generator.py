"""Weekly review generation pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from src.analyzer.ai_client import SkillAIWorkflowError
from src.config.settings import load_env_file
from src.weekly_review.reflection_analyzer import ReflectionAnalyzer
from src.weekly_review.reflection_analyzer import save_reflection_context
from src.weekly_review.factory import create_weekly_review_generation_provider
from src.weekly_review.prompt import load_weekly_review_generator_prompt
from src.weekly_review.schema import WeeklyReviewSchemaError, load_weekly_review_generator_schema
from src.weekly_review.quality_checker import check_weekly_review_quality


class WeeklyReviewGenerationError(RuntimeError):
    """Raised when weekly review generation cannot complete."""


@dataclass(frozen=True)
class WeeklyReviewGenerationResult:
    input_path: Path
    output_path: Path
    reflection_context_path: Path
    payload: dict[str, Any]
    quality_report: dict[str, Any] | None = None


def load_weekly_learning_context(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise WeeklyReviewGenerationError(f"Weekly learning context does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WeeklyReviewGenerationError(
            f"Weekly learning context is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise WeeklyReviewGenerationError("Weekly learning context must be a JSON object.")
    return payload


def _validate_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    payload = _normalize_legacy_output(payload)
    required_keys = [
        "period",
        "core_idea",
        "mindset_shift",
        "ideas_worth_compounding",
        "expressions_worth_reusing",
        "language_thinking_connection",
        "next_week_application",
        "sources",
    ]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise SkillAIWorkflowError(
            f"Weekly review output is missing required fields: {', '.join(missing)}"
        )
    if not isinstance(payload.get("period"), Mapping):
        raise SkillAIWorkflowError("weekly review output period must be an object.")
    if not isinstance(payload.get("core_idea"), Mapping):
        raise SkillAIWorkflowError("weekly review output core_idea must be an object.")
    mindset_shift = payload.get("mindset_shift")
    if mindset_shift is not None and not isinstance(mindset_shift, Mapping):
        raise SkillAIWorkflowError("weekly review output mindset_shift must be an object or null.")
    if not isinstance(payload.get("ideas_worth_compounding"), list):
        raise SkillAIWorkflowError("weekly review output ideas_worth_compounding must be an array.")
    if not isinstance(payload.get("expressions_worth_reusing"), list):
        raise SkillAIWorkflowError("weekly review output expressions_worth_reusing must be an array.")
    if not isinstance(payload.get("language_thinking_connection"), str):
        raise SkillAIWorkflowError("weekly review output language_thinking_connection must be a string.")
    if not isinstance(payload.get("next_week_application"), Mapping):
        raise SkillAIWorkflowError("weekly review output next_week_application must be an object.")
    if not isinstance(payload.get("sources"), list):
        raise SkillAIWorkflowError("weekly review output sources must be an array.")
    return dict(payload)


def _normalize_legacy_output(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert pre-curation WeeklyReview artifacts at the validation boundary."""
    if "core_idea" in payload:
        return dict(payload)

    executive = payload.get("executive_summary", {})
    if not isinstance(executive, Mapping):
        executive = {}
    insights = [item for item in payload.get("knowledge_insights", []) if isinstance(item, Mapping)]
    language = payload.get("language_growth", {})
    if not isinstance(language, Mapping):
        language = {}
    applications = [item for item in payload.get("career_application", []) if isinstance(item, Mapping)]
    first_insight = insights[0] if insights else {}
    first_application = applications[0] if applications else {}
    theme = executive.get("weekly_theme", "")
    if isinstance(theme, Mapping):
        theme = theme.get("theme", "")
    source_ids = [str(item).strip() for item in payload.get("source_page_ids", []) if str(item).strip()]
    return {
        "period": dict(payload.get("period", {})) if isinstance(payload.get("period"), Mapping) else {},
        "core_idea": {
            "idea": str(first_insight.get("insight") or theme or executive.get("learning_summary", "")).strip(),
            "why_it_matters": str(first_insight.get("why_it_matters", "")).strip(),
            "refined_understanding": str(executive.get("learning_summary", "")).strip(),
        },
        "mindset_shift": None,
        "ideas_worth_compounding": [
            {
                "idea": str(item.get("insight", "")).strip(),
                "why_it_matters": str(item.get("why_it_matters", "")).strip(),
                "application": str(item.get("professional_application", "")).strip(),
                "source_reference": "",
            }
            for item in insights[:4]
        ],
        "expressions_worth_reusing": [
            {
                "expression": str(item.get("expression", "")).strip(),
                "contextual_meaning": str(item.get("learning_value", "")).strip(),
                "reusable_example": str(item.get("professional_usage", "")).strip(),
                "communication_function": str(item.get("learning_value", "")).strip(),
            }
            for item in language.get("new_expressions", [])[:5]
            if isinstance(item, Mapping)
        ],
        "language_thinking_connection": str(first_insight.get("why_it_matters", "")).strip(),
        "next_week_application": {
            "scenario": str(first_application.get("scenario", "")).strip(),
            "behavior": str(first_application.get("action") or first_application.get("application", "")).strip(),
            "phrase_to_use": "",
            "completion_condition": "Complete the behavior once in the named scenario.",
        },
        "sources": [{"page_id": page_id, "title": "", "url": ""} for page_id in source_ids],
        "source_page_ids": source_ids,
        "source_podcast_ids": source_ids,
    }


def save_weekly_review(output: Mapping[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(dict(output), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()


class WeeklyReviewGenerator:
    """Prepare prompt, invoke provider, validate output, and persist JSON."""

    def __init__(
        self,
        provider: Optional[object] = None,
        prompt_path: Path = Path("skill/prompts/weekly_review_generator_prompt.md"),
        schema_path: Path = Path("skill/schemas/weekly_review_generator_schema.json"),
    ) -> None:
        self.provider = provider or create_weekly_review_generation_provider()
        self.prompt_path = prompt_path
        self.schema_path = schema_path
        self.prompt = load_weekly_review_generator_prompt(prompt_path)
        try:
            self.schema = load_weekly_review_generator_schema(schema_path)
        except WeeklyReviewSchemaError as exc:
            raise WeeklyReviewGenerationError(str(exc)) from exc

    def generate(self, weekly_learning_context: Mapping[str, Any]) -> dict[str, Any]:
        reflection_context = ReflectionAnalyzer().generate(weekly_learning_context)
        save_reflection_context(reflection_context, Path("output/reflection_context.json"))
        source_page_ids = [
            str(item.get("page_id", "")).strip()
            for item in weekly_learning_context.get("podcasts", [])
            if isinstance(item, Mapping) and str(item.get("page_id", "")).strip()
        ]
        context = {
            "reflection_context": reflection_context,
            "weekly_learning_context": weekly_learning_context,
            "schema": self.schema,
        }
        generated = self.provider.generate(self.prompt, context)
        validated = _validate_output(generated)
        if source_page_ids:
            validated.setdefault("source_page_ids", source_page_ids)
            validated.setdefault("source_podcast_ids", source_page_ids)
        return validated


def run_weekly_review_generation(
    input_path: Path,
    output_path: Path = Path("output/weekly_review.json"),
    provider: Optional[object] = None,
) -> WeeklyReviewGenerationResult:
    load_env_file()

    weekly_learning_context = load_weekly_learning_context(input_path)
    generator = WeeklyReviewGenerator(provider=provider)
    payload = generator.generate(weekly_learning_context)
    quality_report = check_weekly_review_quality(payload)
    if not quality_report.passed:
        raise WeeklyReviewGenerationError(
            "Weekly review quality gate failed: "
            + "; ".join(quality_report.issues)
        )
    saved_path = save_weekly_review(payload, output_path)
    return WeeklyReviewGenerationResult(
        input_path=input_path.resolve(),
        output_path=saved_path,
        reflection_context_path=Path("output/reflection_context.json").resolve(),
        payload=payload,
        quality_report=quality_report.to_dict(),
    )
