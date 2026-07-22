"""Factory for selecting a vocabulary enrichment provider."""

from __future__ import annotations

import os
import warnings

from src.enrichment.codex_provider import CodexVocabularyEnrichmentProvider
from src.enrichment.llm_provider import OpenAIVocabularyEnrichmentProvider
from src.enrichment.placeholder_provider import PlaceholderVocabularyEnrichmentProvider


def create_vocabulary_enrichment_provider() -> object:
    """Return the configured enrichment provider.

    Production defaults to Codex artifacts. Placeholder is deterministic test
    support; OpenAI remains an explicitly selected deprecated compatibility path.
    """
    provider_name = os.environ.get("ENRICHMENT_PROVIDER", "codex").strip().lower()
    if provider_name == "openai":
        warnings.warn(
            "ENRICHMENT_PROVIDER=openai is deprecated; use the Codex artifact runtime.",
            DeprecationWarning,
            stacklevel=2,
        )
        return OpenAIVocabularyEnrichmentProvider()
    if provider_name == "placeholder":
        return PlaceholderVocabularyEnrichmentProvider()
    if provider_name == "codex":
        return CodexVocabularyEnrichmentProvider()
    raise ValueError(f"Unsupported ENRICHMENT_PROVIDER: {provider_name}")
