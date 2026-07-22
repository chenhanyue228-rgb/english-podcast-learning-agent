"""Manual vocabulary capture helpers.

This module only reacts to an explicit user comment trigger. It does not scan
highlights automatically and it does not infer unknown words from transcript
text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional


VOCAB_TRIGGER = "?vocab"


class VocabularyCaptureError(RuntimeError):
    """Raised when a manual vocabulary capture cannot be built."""


@dataclass(frozen=True)
class VocabularyCaptureRequest:
    word: str
    context: str
    source: str
    page_id: str
    meaning: str = ""
    professional_category: str = ""
    source_page_id: str = ""
    first_seen: str = ""
    review_status: str = "New"
    last_review: str = ""
    usage_example: str = ""
    personal_note: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "type": "vocabulary",
            "word": self.word,
            "original_context": self.context,
            "meaning": self.meaning,
            "professional_category": self.professional_category,
            "source": self.source,
            "source_page_id": self.source_page_id or self.page_id,
            "first_seen": self.first_seen or date.today().isoformat(),
            "review_status": self.review_status,
            "last_review": self.last_review,
            "usage_example": self.usage_example,
            "personal_note": self.personal_note,
        }


def is_vocab_trigger(comment_text: str) -> bool:
    return VOCAB_TRIGGER in comment_text.strip().lower()


def build_vocabulary_record(
    highlighted_text: str,
    comment_text: str,
    context: str,
    source: str,
    page_id: str,
) -> dict[str, str]:
    if not is_vocab_trigger(comment_text):
        raise VocabularyCaptureError("Vocabulary trigger ?vocab not found in comment.")

    word = highlighted_text.strip()
    if not word:
        raise VocabularyCaptureError("Highlighted text is required for vocabulary capture.")

    record = VocabularyCaptureRequest(
        word=word,
        context=context.strip(),
        source=source.strip() or "Podcast Library",
        page_id=page_id.strip(),
    )
    return record.to_dict()


def prepare_vocabulary_memory(
    highlighted_text: str,
    comment_text: str,
    context: str,
    source: str,
    page_id: str,
    meaning: str = "",
    professional_category: str = "",
    usage_example: str = "",
    personal_note: str = "",
    first_seen: Optional[str] = None,
    last_review: str = "",
    review_status: str = "New",
) -> dict[str, str]:
    """Prepare a reusable vocabulary memory record for later review stages."""
    record = VocabularyCaptureRequest(
        word=highlighted_text.strip(),
        context=context.strip(),
        source=source.strip() or "Podcast Library",
        page_id=page_id.strip(),
        meaning=meaning.strip(),
        professional_category=professional_category.strip(),
        source_page_id=page_id.strip(),
        first_seen=(first_seen or date.today().isoformat()).strip(),
        review_status=review_status.strip() or "New",
        last_review=last_review.strip(),
        usage_example=usage_example.strip(),
        personal_note=personal_note.strip(),
    )
    return record.to_dict()


def parse_vocabulary_annotation(annotation: Mapping[str, Any]) -> Optional[dict[str, str]]:
    """Parse a Notion-style annotation payload into a vocabulary record.

    Expected keys:
    - text: highlighted text
    - comment: manual trigger comment
    - context: original context sentence
    - source: source page label
    - page_id: Notion page id
    """
    text = str(annotation.get("text", "")).strip()
    comment = str(annotation.get("comment", "")).strip()
    context = str(annotation.get("context", "")).strip()
    source = str(annotation.get("source", "")).strip()
    page_id = str(annotation.get("page_id", "")).strip()

    if not is_vocab_trigger(comment):
        return None
    return prepare_vocabulary_memory(
        highlighted_text=text,
        comment_text=comment,
        context=context,
        source=source,
        page_id=page_id,
    )
