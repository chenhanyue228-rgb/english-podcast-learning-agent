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
DEFAULT_WEEKLY_REVIEW_SCHEMA_PATH = Path("skill/schemas/weekly_review_v2_analysis_schema.json")


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
class WeeklyVocabularyMemoryItem:
    word: str
    context: str = ""
    meaning: str = ""
    professional_category: str = ""
    my_usage: str = ""
    review_status: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "word": self.word,
            "context": self.context,
            "meaning": self.meaning,
            "professional_category": self.professional_category,
            "my_usage": self.my_usage,
            "review_status": self.review_status,
        }


@dataclass(frozen=True)
class WeeklyLearningData:
    week: str
    date: str
    podcasts: Sequence[WeeklyPodcastItem]
    expressions: Sequence[WeeklyExpressionItem]
    vocabulary_memory: Sequence[WeeklyVocabularyMemoryItem] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "week": self.week,
            "date": self.date,
            "podcasts": [podcast.to_dict() for podcast in self.podcasts],
            "expressions": [expression.to_dict() for expression in self.expressions],
            "vocabulary_memory": [memory.to_dict() for memory in self.vocabulary_memory],
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


@dataclass(frozen=True)
class WeeklyReviewAnalysis:
    week: str
    executive_summary: Mapping[str, Any]
    knowledge_insights: Sequence[Mapping[str, Any]]
    expression_upgrade: Sequence[Mapping[str, Any]]
    vocabulary_memory: Sequence[Mapping[str, Any]]
    career_reflection: Mapping[str, Any]
    next_learning_direction: Sequence[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "week": self.week,
            "executive_summary": dict(self.executive_summary),
            "knowledge_insights": [dict(item) for item in self.knowledge_insights],
            "expression_upgrade": [dict(item) for item in self.expression_upgrade],
            "vocabulary_memory": [dict(item) for item in self.vocabulary_memory],
            "career_reflection": dict(self.career_reflection),
            "next_learning_direction": list(self.next_learning_direction),
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
        "executive_summary",
        "knowledge_insights",
        "expression_upgrade",
        "vocabulary_memory",
        "career_reflection",
        "next_learning_direction",
    ]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise SkillAIWorkflowError(
            f"Weekly review output is missing required fields: {', '.join(missing)}"
        )
    if not isinstance(payload.get("executive_summary"), Mapping):
        raise SkillAIWorkflowError("Weekly review output executive_summary must be an object.")
    if not isinstance(payload.get("knowledge_insights"), list):
        raise SkillAIWorkflowError("Weekly review output knowledge_insights must be an array.")
    if not isinstance(payload.get("expression_upgrade"), list):
        raise SkillAIWorkflowError("Weekly review output expression_upgrade must be an array.")
    if not isinstance(payload.get("vocabulary_memory"), list):
        raise SkillAIWorkflowError("Weekly review output vocabulary_memory must be an array.")
    if not isinstance(payload.get("career_reflection"), Mapping):
        raise SkillAIWorkflowError("Weekly review output career_reflection must be an object.")
    if not isinstance(payload.get("next_learning_direction"), list):
        raise SkillAIWorkflowError(
            "Weekly review output next_learning_direction must be an array."
        )
    return dict(payload)


def load_weekly_review_request(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise WeeklyReviewAnalyzerError(f"Weekly review request does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WeeklyReviewAnalyzerError(
            f"Weekly review request is invalid JSON: {exc.msg}"
        ) from exc
    return ensure_mapping(payload, "weekly_review_request")


def build_weekly_review_analysis(request: Mapping[str, Any]) -> WeeklyReviewAnalysis:
    weekly_learning_data = ensure_mapping(request.get("weekly_learning_data"), "weekly_learning_data")
    week = str(request.get("week", "")).strip()
    podcasts = list(weekly_learning_data.get("podcasts", []))
    expressions = list(weekly_learning_data.get("expressions", []))
    vocabulary_memory = _normalize_vocabulary_memory(weekly_learning_data.get("vocabulary_memory", []))

    titles = [str(item.get("title", "")).strip() for item in podcasts if isinstance(item, Mapping)]
    topics = sorted(
        {
            str(item.get("topic", "")).strip()
            for item in podcasts
            if isinstance(item, Mapping) and item.get("topic")
        }
    )

    executive_summary = _build_executive_summary(topics, expressions)
    knowledge_insights = _build_knowledge_insights(topics, titles, expressions)
    expression_upgrade = _build_expression_upgrade(expressions)
    career_reflection = _build_career_reflection(topics, expressions)
    next_learning_direction = _build_next_learning_direction(topics, expressions)

    return WeeklyReviewAnalysis(
        week=week,
        executive_summary=executive_summary,
        knowledge_insights=knowledge_insights,
        expression_upgrade=expression_upgrade,
        vocabulary_memory=vocabulary_memory,
        career_reflection=career_reflection,
        next_learning_direction=next_learning_direction,
    )


def save_weekly_review_analysis(analysis: WeeklyReviewAnalysis, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(analysis.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()


def _build_executive_summary(
    topics: Sequence[str],
    expressions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    topic_text = ", ".join(topics[:3]) if topics else "learning and communication"
    strongest_expression = next(
        (
            str(item.get("expression", "")).strip()
            for item in expressions
            if isinstance(item, Mapping) and str(item.get("expression", "")).strip()
        ),
        "",
    )
    return {
        "overview": (
            f"This week centered on {topic_text}. "
            "The strongest learning signals pointed toward how to frame ideas, manage relationships, "
            "and communicate with clarity."
        ),
        "takeaway": (
            "The week showed how professional language becomes more useful when it is tied to context"
            + (f", especially around '{strongest_expression}'." if strongest_expression else ".")
        ),
        "highlights": list(topics[:3]) if topics else ["Weekly learning review"],
    }


def _build_knowledge_insights(
    topics: Sequence[str],
    titles: Sequence[str],
    expressions: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    topic_text = ", ".join(topics[:2]) if topics else "the week's learning"
    strongest_expression = next(
        (
            str(item.get("expression", "")).strip()
            for item in expressions
            if isinstance(item, Mapping) and str(item.get("expression", "")).strip()
        ),
        "",
    )
    insights: list[dict[str, str]] = [
        {
            "what_happened": f"The week focused on {topic_text} across the published episodes.",
            "why_it_matters": "It shows which communication patterns were repeated enough to matter for review.",
            "my_interpretation": "The content is building a practical vocabulary base rather than isolated facts.",
            "application": "Use the same framing language in work updates, explanations, and follow-up conversations.",
        }
    ]
    if strongest_expression:
        insights.append(
            {
                "what_happened": f"An expression such as '{strongest_expression}' appeared as a reusable learning target.",
                "why_it_matters": "High-value expressions are the bridge between listening and real speaking practice.",
                "my_interpretation": "The expression is useful because it can travel across multiple professional contexts.",
                "application": "Reuse it in status updates, planning discussions, and written communication.",
            }
        )
    if titles:
        insights.append(
            {
                "what_happened": "Multiple episodes reinforced a similar communication theme in different contexts.",
                "why_it_matters": "Repeated themes reveal what the learner is most likely to remember and apply.",
                "my_interpretation": "The week is less about topic coverage and more about pattern recognition.",
                "application": "Review the recurring theme before the next listening session and practice it aloud.",
            }
        )
    return insights[:3]


def _build_expression_upgrade(expressions: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    ranked: list[dict[str, Any]] = []
    for item in expressions:
        if not isinstance(item, Mapping):
            continue
        expression = str(item.get("expression", "")).strip()
        category = str(item.get("category", "")).strip() or "Unknown"
        meaning = str(item.get("meaning", "")).strip()
        usage_context = str(item.get("usage_context", "")).strip()
        review_status = str(item.get("review_status", "")).strip().lower()
        if not expression:
            continue
        score = 0
        if category == "Native Expression":
            score += 40
        if review_status in {"new", "learning"}:
            score += 20
        if usage_context:
            score += 15
        if meaning:
            score += 10
        if len(expression.split()) >= 2:
            score += 10
        if sum(ch.isalpha() for ch in expression) >= 8:
            score += 5
        ranked.append(
            {
                "expression": expression,
                "meaning": meaning,
                "context": usage_context,
                "example": _build_expression_example(expression, usage_context),
                "review_priority": score,
            }
        )
    ranked.sort(
        key=lambda item: (
            int(item.get("review_priority", 0)),
            bool(item.get("meaning")),
            len(str(item.get("expression", ""))),
        ),
        reverse=True,
    )
    reviewed: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in ranked:
        expression = str(item.get("expression", "")).strip()
        if not expression or expression in seen:
            continue
        seen.add(expression)
        reviewed.append(
            {
                "expression": expression,
                "meaning": str(item.get("meaning", "")).strip(),
                "context": str(item.get("context", "")).strip(),
                "example": str(item.get("example", "")).strip(),
            }
        )
        if len(reviewed) >= 5:
            break
    return reviewed


def _build_expression_example(expression: str, original_context: str) -> str:
    if original_context:
        return original_context.rstrip(".")
    return f"I can use '{expression}' in a fresh professional example."


def _build_career_reflection(
    topics: Sequence[str],
    expressions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    strongest_expression = next(
        (
            str(item.get("expression", "")).strip()
            for item in expressions
            if isinstance(item, Mapping) and str(item.get("expression", "")).strip()
        ),
        "",
    )
    questions = [
        "What changed my thinking this week?",
        "What can I apply immediately at work?",
    ]
    if strongest_expression:
        questions.append(f"How can I reuse '{strongest_expression}' in future professional conversations?")
    possible_applications = [
        "Use the upgraded language in status updates, planning meetings, and follow-up notes.",
        "Turn one high-value expression into a short speaking drill before the next review.",
    ]
    if topics:
        possible_applications.append(
            f"Apply the week's main themes ({', '.join(topics[:2])}) when explaining decisions or priorities."
        )
    return {
        "questions": questions,
        "possible_applications": possible_applications,
    }


def _build_next_learning_direction(
    topics: Sequence[str],
    expressions: Sequence[Mapping[str, Any]],
) -> list[str]:
    plan: list[str] = []
    if expressions:
        plan.append("Revisit the highest-value expressions and practice them in short speaking drills.")
    if topics:
        plan.append(
            f"Return to the strongest themes around {', '.join(topics[:2])} and notice how the language changes in context."
        )
    plan.append("Review the weekly reflection before the next listening session.")
    return plan[:3]


def _normalize_vocabulary_memory(
    vocabulary_memory: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for item in vocabulary_memory:
        if not isinstance(item, Mapping):
            continue
        word = str(item.get("word", "")).strip()
        if not word:
            continue
        normalized.append(
            {
                "word": word,
                "context": str(
                    item.get("context")
                    or item.get("original_context")
                    or item.get("source_page_context")
                    or ""
                ).strip(),
                "meaning": str(item.get("meaning", "")).strip(),
                "professional_category": str(
                    item.get("professional_category")
                    or item.get("category")
                    or ""
                ).strip(),
                "my_usage": str(
                    item.get("my_usage")
                    or item.get("usage_example")
                    or item.get("personal_note")
                    or ""
                ).strip(),
                "review_status": str(item.get("review_status", "")).strip(),
            }
        )
    return normalized


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
