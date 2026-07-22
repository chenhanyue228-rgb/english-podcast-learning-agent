from __future__ import annotations

from src.enrichment.factory import create_vocabulary_enrichment_provider
from src.enrichment.llm_provider import OpenAIVocabularyEnrichmentProvider
from src.enrichment.codex_provider import CodexVocabularyEnrichmentProvider


def test_create_vocabulary_enrichment_provider_defaults_to_codex(monkeypatch) -> None:
    monkeypatch.delenv("ENRICHMENT_PROVIDER", raising=False)

    provider = create_vocabulary_enrichment_provider()

    assert isinstance(provider, CodexVocabularyEnrichmentProvider)


def test_create_vocabulary_enrichment_provider_returns_openai(monkeypatch) -> None:
    monkeypatch.setenv("ENRICHMENT_PROVIDER", "openai")

    provider = create_vocabulary_enrichment_provider()

    assert isinstance(provider, OpenAIVocabularyEnrichmentProvider)
