"""Rule-based filtering for vocabulary preview candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class VocabularyCandidateFilterResult:
    approved: list[dict[str, Any]]
    rejected: list[dict[str, Any]]

    def to_json(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "rejected": self.rejected,
        }


_ENGLISH_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z\s\-']*$")
_PERSON_NAME_HINTS = {
    "stan",
    "christensen",
    "matt",
    "lee",
    "duffy",
    "musk",
    "sinek",
    "chris",
    "john",
    "jane",
}


def _word_text(item: dict[str, Any]) -> str:
    return str(item.get("word", "")).strip()


def _is_mostly_english(text: str) -> bool:
    if not text:
        return False
    english_chars = sum(1 for ch in text if ch.isascii() and (ch.isalpha() or ch.isspace() or ch in "-'"))
    return english_chars / max(len(text), 1) >= 0.7


def _looks_like_person_name(text: str) -> bool:
    normalized = text.strip().lower()
    parts = [part for part in re.split(r"[\s\-']+", normalized) if part]
    if len(parts) == 1 and parts[0] in _PERSON_NAME_HINTS:
        return True
    if len(parts) == 2 and all(part in _PERSON_NAME_HINTS for part in parts):
        return True
    if len(parts) == 2 and all(part[:1].isupper() or part in _PERSON_NAME_HINTS for part in text.split()):
        return True
    return False


def _should_reject(item: dict[str, Any]) -> str:
    text = _word_text(item)
    if len(text) < 2:
        return "too short"
    if not _is_mostly_english(text):
        return "non-english"
    if not _ENGLISH_WORD_RE.match(text):
        return "unsupported format"
    if _looks_like_person_name(text):
        return "person name"
    return ""


def filter_vocabulary_candidates(items: list[dict[str, Any]]) -> VocabularyCandidateFilterResult:
    approved: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for item in items:
        reason = _should_reject(item)
        if reason:
            rejected.append({**item, "reason": reason})
        else:
            approved.append(item)

    return VocabularyCandidateFilterResult(approved=approved, rejected=rejected)
