"""Data models for Phase 3 AI learning analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class Summary:
    english: str
    chinese: str
    key_points: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "english": self.english,
            "chinese": self.chinese,
            "key_points": list(self.key_points),
        }


@dataclass(frozen=True)
class PodcastMetadata:
    title: str = ""
    topic: str = ""
    difficulty: str = ""
    short_summary: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "topic": self.topic,
            "difficulty": self.difficulty,
            "short_summary": self.short_summary,
        }


@dataclass(frozen=True)
class LearningItem:
    text: str
    category: str
    meaning: str
    chinese_meaning: str = ""
    usage_context: str = ""
    context_sentence: str = ""
    example_sentence: str = ""
    highlight_color: str = ""
    commonness: str = "Medium"
    confidence: float = 0.0
    quality_score: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "category": self.category,
            "meaning": self.meaning,
            "chinese_meaning": self.chinese_meaning,
            "usage_context": self.usage_context,
            "context_sentence": self.context_sentence,
            "example_sentence": self.example_sentence,
            "highlight_color": self.highlight_color,
            "commonness": self.commonness,
            "confidence": self.confidence,
            "quality_score": self.quality_score,
        }


@dataclass(frozen=True)
class SentencePattern:
    text: str
    category: str = "Sentence Pattern"
    meaning: str = ""
    chinese_meaning: str = ""
    usage_context: str = ""
    context_sentence: str = ""
    example_sentence: str = ""
    highlight_color: str = "orange"
    commonness: str = "Medium"
    confidence: float = 0.0

    def to_learning_item(self) -> LearningItem:
        return LearningItem(
            text=self.text,
            category=self.category,
            meaning=self.meaning,
            chinese_meaning=self.chinese_meaning,
            usage_context=self.usage_context,
            context_sentence=self.context_sentence,
            example_sentence=self.example_sentence,
            highlight_color=self.highlight_color,
            commonness=self.commonness,
            confidence=self.confidence,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.to_learning_item().to_dict()


@dataclass(frozen=True)
class LearningNote:
    title: str
    note: str
    chinese_note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "note": self.note,
            "chinese_note": self.chinese_note,
        }


@dataclass(frozen=True)
class AIAnalysisResult:
    summary: Summary
    podcast_metadata: PodcastMetadata = field(default_factory=PodcastMetadata)
    learning_items: list[LearningItem] = field(default_factory=list)
    sentence_patterns: list[SentencePattern] = field(default_factory=list)
    learning_notes: list[LearningNote] = field(default_factory=list)

    def all_learning_items(self) -> list[LearningItem]:
        return [
            *self.learning_items,
            *[pattern.to_learning_item() for pattern in self.sentence_patterns],
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary.to_dict(),
            "podcast_metadata": self.podcast_metadata.to_dict(),
            "learning_items": [item.to_dict() for item in self.learning_items],
            "sentence_patterns": [pattern.to_dict() for pattern in self.sentence_patterns],
            "learning_notes": [note.to_dict() for note in self.learning_notes],
        }


def ensure_mapping(payload: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError(f"{name} must be a JSON object.")
    return payload
