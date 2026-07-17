"""Validation and normalization for Phase 3 AI analysis output."""

from __future__ import annotations

from typing import Any, Mapping

from src.analyzer.models import (
    AIAnalysisResult,
    LearningItem,
    LearningNote,
    PodcastMetadata,
    SentencePattern,
    Summary,
    ensure_mapping,
)
from src.notion.schema import CATEGORY_COLORS, EXPRESSION_CATEGORIES


class AnalysisValidationError(ValueError):
    """Raised when AI analysis JSON does not match the expected schema."""


CATEGORY_ALIASES = {
    "Business Expression": "Business Phrase",
    "Business Expressions": "Business Phrase",
    "Industry Term": "Industry Term",
    "Industry Terminology": "Industry Term",
    "Native Expression": "Native Expression",
    "Native Expressions": "Native Expression",
    "Collocation": "Collocation",
    "Sentence Pattern": "Sentence Pattern",
    "Sentence Patterns": "Sentence Pattern",
}

DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}
COMMONNESS_LEVELS = {"High", "Medium", "Low"}
COMMONNESS_ALIASES = {
    "Common": "High",
    "Frequent": "High",
    "Often": "High",
    "Moderate": "Medium",
    "Sometimes": "Medium",
    "Rare": "Low",
    "Uncommon": "Low",
}


def as_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def as_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def normalize_category(category: str) -> str:
    normalized = CATEGORY_ALIASES.get(as_text(category), as_text(category))
    if normalized not in EXPRESSION_CATEGORIES:
        raise AnalysisValidationError(f"Unsupported learning item category: {category}")
    return normalized


def color_for_category(category: str, fallback: str = "") -> str:
    return as_text(fallback).lower() or CATEGORY_COLORS.get(category, "").lower()


def normalize_commonness(commonness: str) -> str:
    normalized = COMMONNESS_ALIASES.get(as_text(commonness), as_text(commonness))
    if normalized not in COMMONNESS_LEVELS:
        raise AnalysisValidationError(
            "learning item commonness must be High, Medium, or Low."
        )
    return normalized


def quality_score_for_item(commonness: str, confidence: float) -> int:
    base_scores = {"High": 60, "Medium": 45, "Low": 30}
    scoring_confidence = confidence if confidence > 0 else 0.85
    score = base_scores[commonness] + int(round(scoring_confidence * 40))
    return min(100, max(0, score))


def validate_summary(payload: Mapping[str, Any]) -> Summary:
    summary = ensure_mapping(payload.get("summary", {}), "summary")
    english = as_text(summary.get("english"))
    chinese = as_text(summary.get("chinese"))
    if not english:
        raise AnalysisValidationError("summary.english is required.")
    key_points = summary.get("key_points", [])
    if not isinstance(key_points, list):
        raise AnalysisValidationError("summary.key_points must be a list.")
    return Summary(
        english=english,
        chinese=chinese,
        key_points=[as_text(point) for point in key_points if as_text(point)],
    )


def validate_podcast_metadata(payload: Mapping[str, Any]) -> PodcastMetadata:
    metadata = payload.get("podcast_metadata", {})
    if metadata is None:
        metadata = {}
    metadata = ensure_mapping(metadata, "podcast_metadata")
    difficulty = as_text(metadata.get("difficulty"))
    if difficulty and difficulty not in DIFFICULTIES:
        raise AnalysisValidationError(
            "podcast_metadata.difficulty must be Beginner, Intermediate, or Advanced."
        )
    return PodcastMetadata(
        title=as_text(metadata.get("title")),
        topic=as_text(metadata.get("topic")),
        difficulty=difficulty,
        short_summary=as_text(metadata.get("short_summary")),
    )


def validate_learning_item(payload: Mapping[str, Any]) -> LearningItem:
    text = as_text(payload.get("text"))
    category = normalize_category(as_text(payload.get("category")))
    meaning = as_text(payload.get("meaning"))
    commonness = normalize_commonness(as_text(payload.get("commonness", "Medium")))
    if not text:
        raise AnalysisValidationError("learning item text is required.")
    if not meaning:
        raise AnalysisValidationError(f"meaning is required for learning item: {text}")
    confidence = as_float(payload.get("confidence"))
    quality_score = quality_score_for_item(commonness, confidence)
    if quality_score < 70:
        raise AnalysisValidationError(
            f"learning item '{text}' is too weak (quality score {quality_score})."
        )
    return LearningItem(
        text=text,
        category=category,
        meaning=meaning,
        chinese_meaning=as_text(payload.get("chinese_meaning")),
        usage_context=as_text(payload.get("usage_context")),
        context_sentence=as_text(payload.get("context_sentence")),
        example_sentence=as_text(payload.get("example_sentence")),
        highlight_color=color_for_category(category, as_text(payload.get("highlight_color"))),
        commonness=commonness,
        confidence=confidence,
        quality_score=quality_score,
    )


def validate_sentence_pattern(payload: Mapping[str, Any]) -> SentencePattern:
    item = validate_learning_item({**dict(payload), "category": "Sentence Pattern"})
    return SentencePattern(
        text=item.text,
        meaning=item.meaning,
        chinese_meaning=item.chinese_meaning,
        usage_context=item.usage_context,
        context_sentence=item.context_sentence,
        example_sentence=item.example_sentence,
        highlight_color=item.highlight_color or "orange",
        commonness=item.commonness,
        confidence=item.confidence,
    )


def validate_learning_note(payload: Mapping[str, Any]) -> LearningNote:
    title = as_text(payload.get("title"))
    note = as_text(payload.get("note"))
    if not title or not note:
        raise AnalysisValidationError("learning note title and note are required.")
    return LearningNote(
        title=title,
        note=note,
        chinese_note=as_text(payload.get("chinese_note")),
    )


def deduplicate_learning_items(items: list[LearningItem]) -> list[LearningItem]:
    seen: set[tuple[str, str]] = set()
    deduped: list[LearningItem] = []
    for item in items:
        key = (item.text.casefold(), item.category)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def validate_ai_analysis(payload: Mapping[str, Any]) -> AIAnalysisResult:
    root = ensure_mapping(payload, "AI analysis")
    learning_items = root.get("learning_items", [])
    sentence_patterns = root.get("sentence_patterns", [])
    learning_notes = root.get("learning_notes", [])

    if not isinstance(learning_items, list):
        raise AnalysisValidationError("learning_items must be a list.")
    if not isinstance(sentence_patterns, list):
        raise AnalysisValidationError("sentence_patterns must be a list.")
    if not isinstance(learning_notes, list):
        raise AnalysisValidationError("learning_notes must be a list.")

    validated_items = [
        validate_learning_item(ensure_mapping(item, "learning item"))
        for item in learning_items
    ]
    validated_patterns = [
        validate_sentence_pattern(ensure_mapping(pattern, "sentence pattern"))
        for pattern in sentence_patterns
    ]
    return AIAnalysisResult(
        summary=validate_summary(root),
        podcast_metadata=validate_podcast_metadata(root),
        learning_items=deduplicate_learning_items(validated_items),
        sentence_patterns=validated_patterns,
        learning_notes=[
            validate_learning_note(ensure_mapping(note, "learning note"))
            for note in learning_notes
        ],
    )
