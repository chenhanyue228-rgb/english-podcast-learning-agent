"""Default placeholder enrichment provider."""

from __future__ import annotations

from dataclasses import dataclass

from src.enrichment.provider import VocabularyEnrichmentProvider


@dataclass(frozen=True)
class PlaceholderVocabularyEnrichmentProvider(VocabularyEnrichmentProvider):
    """Return empty enrichment fields for preview-only flows."""

    def enrich(self, word: str, context: str) -> dict[str, str]:
        return {
            "word": word.strip(),
            "original_context": context.strip(),
            "meaning": "",
            "chinese_meaning": "",
            "part_of_speech": "",
            "professional_category": "",
            "usage_example": "",
        }
