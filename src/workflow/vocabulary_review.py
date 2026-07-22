"""Vocabulary review state management layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class VocabularyReviewItem:
    word: str
    review_status: str

    def to_json(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "review_status": self.review_status,
        }


@dataclass(frozen=True)
class VocabularyReviewResult:
    pending_vocabulary: list[dict[str, Any]]
    approved: list[dict[str, Any]]
    rejected: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "pending_vocabulary": self.pending_vocabulary,
            "approved": self.approved,
            "rejected": self.rejected,
        }


def _word_text(item: Mapping[str, Any]) -> str:
    return str(item.get("word", "")).strip()


def review_vocabulary_items(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Move enriched items into pending review state."""
    pending_vocabulary: list[dict[str, Any]] = []
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for item in items:
        word = _word_text(item)
        if not word:
            rejected.append({"word": "", "review_status": "rejected"})
            continue
        pending_vocabulary.append(VocabularyReviewItem(word=word, review_status="pending").to_json())

    return VocabularyReviewResult(
        pending_vocabulary=pending_vocabulary,
        approved=approved,
        rejected=rejected,
    ).to_json()


def approve_vocabulary_items(items: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Promote reviewed items to approved state."""
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for item in items:
        word = _word_text(item)
        if not word:
            rejected.append({"word": "", "review_status": "rejected"})
            continue
        approved.append(VocabularyReviewItem(word=word, review_status="approved").to_json())

    return VocabularyReviewResult(
        pending_vocabulary=[],
        approved=approved,
        rejected=rejected,
    ).to_json()
