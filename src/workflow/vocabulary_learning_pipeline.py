"""Read-only orchestrator for the vocabulary learning preview pipeline."""

from __future__ import annotations

from typing import Any

from src.enrichment.factory import create_vocabulary_enrichment_provider
from src.workflow.highlight_vocabulary_pipeline import build_highlight_vocabulary_preview
from src.workflow.vocabulary_candidate_filter import filter_vocabulary_candidates
from src.workflow.vocabulary_enrichment import enrich_vocabulary_candidates


def build_vocabulary_learning_preview(page_id: str, notion: Any = None) -> dict[str, Any]:
    """Build the full vocabulary learning preview payload without writing to Notion."""
    print("highlight preview started")
    highlight_preview = build_highlight_vocabulary_preview(page_id=page_id, notion=notion)
    print(f"highlight preview completed: {highlight_preview.count}")
    candidates = [
        {
            "word": item.word,
            "context": item.context,
            "source_page_id": item.source_page_id,
        }
        for item in highlight_preview.items
    ]
    filtered = filter_vocabulary_candidates(candidates)
    print(
        "candidate filter completed: "
        f"accepted={len(filtered.approved)} rejected={len(filtered.rejected)}"
    )
    provider = create_vocabulary_enrichment_provider()
    print(f"enrichment started: provider={provider.__class__.__name__}")
    enriched = enrich_vocabulary_candidates(filtered.approved, provider=provider)
    print(f"enrichment completed: enriched={len(enriched)}")
    approved_words = {
        str(item.get("word", "")).strip()
        for item in enriched
        if isinstance(item, dict) and str(item.get("word", "")).strip()
    }

    return {
        "page_id": page_id,
        "total_highlights": highlight_preview.count,
        "rejected_candidates": [
            {
                "word": item.get("word", ""),
                "reason": item.get("reason", ""),
            }
            for item in filtered.rejected
        ],
        "pending_vocabulary": [],
        "approved_vocabulary": [
            {**item, "review_status": "New"}
            for item in enriched
            if str(item.get("word", "")).strip() in approved_words
        ],
    }


def preview_vocabulary_learning(page_id: str, notion: Any = None) -> dict[str, Any]:
    """Return the final JSON payload for the vocabulary learning preview pipeline."""
    return build_vocabulary_learning_preview(page_id=page_id, notion=notion)
