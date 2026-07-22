from __future__ import annotations

from src.enrichment.placeholder_provider import PlaceholderVocabularyEnrichmentProvider
from src.workflow.vocabulary_enrichment import enrich_vocabulary_candidates


def test_placeholder_provider_returns_empty_enrichment_fields() -> None:
    provider = PlaceholderVocabularyEnrichmentProvider()

    enriched = provider.enrich("conversation", "The conversation also shows how to negotiate with investors.")

    assert enriched["word"] == "conversation"
    assert enriched["original_context"] == "The conversation also shows how to negotiate with investors."
    assert enriched["meaning"] == ""
    assert enriched["chinese_meaning"] == ""
    assert enriched["part_of_speech"] == ""
    assert enriched["professional_category"] == ""
    assert enriched["usage_example"] == ""
    assert "common_collocations" not in enriched


def test_enrich_vocabulary_candidates_uses_provider() -> None:
    class CustomProvider:
        def enrich(self, word: str, context: str) -> dict[str, object]:
            return {
                "word": "provider replacement",
                "original_context": "Provider-generated context must be ignored.",
                "source_page_id": "provider_page",
                "meaning": "meaning",
                "chinese_meaning": "中文",
                "part_of_speech": "noun",
                "professional_category": "Business Phrase",
                "usage_example": "Use it in meetings.",
                "common_collocations": ["have a conversation", "difficult conversation", "conversation with stakeholders"],
            }

    enriched = enrich_vocabulary_candidates(
        [
            {
                "word": "conversation",
                "context": "The conversation also shows how to negotiate with investors.",
                "source_page_id": "page_1",
            }
        ],
        provider=CustomProvider(),
    )

    assert enriched[0]["word"] == "conversation"
    assert enriched[0]["original_context"] == (
        "The conversation also shows how to negotiate with investors."
    )
    assert enriched[0]["meaning"] == "meaning"
    assert enriched[0]["chinese_meaning"] == "中文"
    assert enriched[0]["part_of_speech"] == "noun"
    assert enriched[0]["professional_category"] == "Business Phrase"
    assert enriched[0]["usage_example"] == "Use it in meetings."
    assert enriched[0]["source_page_id"] == "page_1"
    assert enriched[0]["common_collocations"] == [
        "have a conversation",
        "difficult conversation",
        "conversation with stakeholders",
    ]


def test_enrich_vocabulary_candidates_keeps_empty_collocations_field() -> None:
    class CustomProvider:
        def enrich(self, word: str, context: str) -> dict[str, str]:
            return {
                "word": word,
                "original_context": context,
                "meaning": "meaning",
                "chinese_meaning": "中文",
                "part_of_speech": "noun",
                "professional_category": "Business Communication",
                "usage_example": "Use it in meetings.",
            }

    enriched = enrich_vocabulary_candidates(
        [
            {
                "word": "conversation",
                "context": "The conversation also shows how to negotiate with investors.",
                "source_page_id": "page_1",
            }
        ],
        provider=CustomProvider(),
    )

    assert enriched[0]["common_collocations"] == []


def test_enrich_vocabulary_candidates_parses_string_collocations() -> None:
    class CustomProvider:
        def enrich(self, word: str, context: str) -> dict[str, str]:
            return {
                "word": word,
                "original_context": context,
                "meaning": "meaning",
                "chinese_meaning": "中文",
                "part_of_speech": "noun",
                "professional_category": "Business Communication",
                "usage_example": "Use it in meetings.",
                "common_collocations": "collocation one, collocation two, collocation three",
            }

    enriched = enrich_vocabulary_candidates(
        [
            {
                "word": "conversation",
                "context": "The conversation also shows how to negotiate with investors.",
                "source_page_id": "page_1",
            }
        ],
        provider=CustomProvider(),
    )

    assert enriched[0]["common_collocations"] == [
        "collocation one",
        "collocation two",
        "collocation three",
    ]
