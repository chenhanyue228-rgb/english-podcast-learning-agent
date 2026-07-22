"""Provider interface for vocabulary enrichment."""

from __future__ import annotations

from typing import Protocol


class VocabularyEnrichmentProvider(Protocol):
    def enrich(self, word: str, context: str) -> dict[str, str]:
        """Enrich a vocabulary candidate into structured preview fields."""
        raise NotImplementedError
