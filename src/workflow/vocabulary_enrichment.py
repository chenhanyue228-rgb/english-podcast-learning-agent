"""Vocabulary enrichment layer backed by a pluggable provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from src.enrichment.factory import create_vocabulary_enrichment_provider
from src.enrichment.provider import VocabularyEnrichmentProvider


@dataclass(frozen=True)
class VocabularyEnrichmentItem:
    word: str
    original_context: str
    meaning: str
    chinese_meaning: str
    part_of_speech: str
    professional_category: str
    usage_example: str
    source_page_id: str
    common_collocations: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "word": self.word,
            "original_context": self.original_context,
            "meaning": self.meaning,
            "chinese_meaning": self.chinese_meaning,
            "part_of_speech": self.part_of_speech,
            "professional_category": self.professional_category,
            "usage_example": self.usage_example,
            "source_page_id": self.source_page_id,
            "common_collocations": self.common_collocations,
        }


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_list_of_strings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [
            str(item).strip()
            for item in value
            if str(item).strip()
        ]
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return [part for part in parts if part]
    return []


def _default_provider() -> VocabularyEnrichmentProvider:
    provider = create_vocabulary_enrichment_provider()
    if not hasattr(provider, "enrich"):
        raise TypeError("Selected enrichment provider does not implement enrich().")
    return provider  # type: ignore[return-value]


def enrich_vocabulary_candidates(
    items: list[Mapping[str, Any]],
    provider: Optional[VocabularyEnrichmentProvider] = None,
) -> list[dict[str, Any]]:
    """Convert approved candidates into enrichment preview records."""
    active_provider = provider or _default_provider()
    batch_enrich = getattr(active_provider, "enrich_many", None)
    batch_outputs = batch_enrich(items) if callable(batch_enrich) else None
    enriched: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        word = _clean_text(item.get("word"))
        context = _clean_text(item.get("context"))
        source_page_id = _clean_text(item.get("source_page_id"))
        enriched_data = (
            batch_outputs[index]
            if batch_outputs is not None
            else active_provider.enrich(word, context)
        )
        enriched.append(
            VocabularyEnrichmentItem(
                word=_clean_text(enriched_data.get("word") or word),
                original_context=_clean_text(enriched_data.get("original_context") or context),
                meaning=_clean_text(enriched_data.get("meaning")),
                chinese_meaning=_clean_text(enriched_data.get("chinese_meaning")),
                part_of_speech=_clean_text(enriched_data.get("part_of_speech")),
                professional_category=_clean_text(enriched_data.get("professional_category")),
                usage_example=_clean_text(enriched_data.get("usage_example")),
                source_page_id=source_page_id,
                common_collocations=_clean_list_of_strings(enriched_data.get("common_collocations")),
            ).to_json()
        )
    print("enrichment completed")
    return enriched
