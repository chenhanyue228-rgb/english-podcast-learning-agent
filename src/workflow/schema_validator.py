"""Validation helpers for WeeklyLearningContext.json."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


class WeeklyLearningContextValidationError(ValueError):
    """Raised when the weekly learning context schema is invalid."""


def _require_mapping(payload: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise WeeklyLearningContextValidationError(f"{name} must be an object.")
    return payload


def _require_list(payload: Any, name: str) -> Sequence[Any]:
    if not isinstance(payload, list):
        raise WeeklyLearningContextValidationError(f"{name} must be an array.")
    return payload


def _require_text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise WeeklyLearningContextValidationError(f"{name} is required.")
    return text


def validate_weekly_learning_context(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the output schema for weekly learning extraction."""
    root = _require_mapping(payload, "WeeklyLearningContext")
    metadata = _require_mapping(root.get("metadata"), "metadata")
    podcasts = _require_list(root.get("podcasts"), "podcasts")
    learning_expressions = _require_list(root.get("learning_expressions"), "learning_expressions")
    ai_highlights = _require_list(root.get("ai_highlights"), "ai_highlights")
    user_vocabulary = _require_list(root.get("user_vocabulary"), "user_vocabulary")

    _require_text(metadata.get("period_start"), "metadata.period_start")
    _require_text(metadata.get("period_end"), "metadata.period_end")
    _require_text(metadata.get("generated_at"), "metadata.generated_at")
    _require_text(metadata.get("source"), "metadata.source")

    for index, podcast in enumerate(podcasts):
        podcast_map = _require_mapping(podcast, f"podcasts[{index}]")
        _require_text(podcast_map.get("page_id"), f"podcasts[{index}].page_id")
        _require_text(podcast_map.get("title"), f"podcasts[{index}].title")
        _require_text(podcast_map.get("date"), f"podcasts[{index}].date")

    for index, item in enumerate(learning_expressions):
        item_map = _require_mapping(item, f"learning_expressions[{index}]")
        _require_text(item_map.get("expression"), f"learning_expressions[{index}].expression")
        _require_text(item_map.get("category"), f"learning_expressions[{index}].category")

    for index, item in enumerate(ai_highlights):
        item_map = _require_mapping(item, f"ai_highlights[{index}]")
        _require_text(item_map.get("text"), f"ai_highlights[{index}].text")
        _require_text(item_map.get("category"), f"ai_highlights[{index}].category")
        _require_text(item_map.get("color"), f"ai_highlights[{index}].color")
        _require_text(item_map.get("context"), f"ai_highlights[{index}].context")
        _require_text(item_map.get("source_page_id"), f"ai_highlights[{index}].source_page_id")

    for index, item in enumerate(user_vocabulary):
        item_map = _require_mapping(item, f"user_vocabulary[{index}]")
        _require_text(item_map.get("word"), f"user_vocabulary[{index}].word")
        _require_text(item_map.get("context"), f"user_vocabulary[{index}].context")
        _require_text(item_map.get("source_page_id"), f"user_vocabulary[{index}].source_page_id")

    return dict(root)
