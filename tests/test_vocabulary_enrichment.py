from __future__ import annotations

from src.workflow.vocabulary_enrichment import enrich_vocabulary_candidates


def test_enrich_vocabulary_candidates_returns_complete_placeholder_fields(monkeypatch) -> None:
    monkeypatch.setenv("ENRICHMENT_PROVIDER", "placeholder")

    enriched = enrich_vocabulary_candidates(
        [
            {
                "word": "conversation",
                "context": "The conversation also shows how to negotiate with investors.",
                "source_page_id": "11111111111111111111111111111111",
            }
        ]
    )

    assert len(enriched) == 1
    item = enriched[0]
    assert item["word"] == "conversation"
    assert item["original_context"] == "The conversation also shows how to negotiate with investors."
    assert "meaning" in item
    assert "chinese_meaning" in item
    assert "part_of_speech" in item
    assert "professional_category" in item
    assert "usage_example" in item
    assert item["source_page_id"] == "11111111111111111111111111111111"
