"""Read-only orchestrator for the vocabulary preview pipeline."""

from __future__ import annotations

from typing import Any

from src.workflow.highlight_vocabulary_pipeline import build_highlight_vocabulary_preview
from src.workflow.vocabulary_candidate_filter import filter_vocabulary_candidates
from src.workflow.vocabulary_enrichment import enrich_vocabulary_candidates


def build_vocabulary_preview(page_id: str, notion: Any = None) -> dict[str, Any]:
    """Build the full vocabulary preview payload without writing to Notion."""
    highlight_preview = build_highlight_vocabulary_preview(page_id=page_id, notion=notion)
    candidates = [
        {
            "word": item.word,
            "context": item.context,
            "source_page_id": item.source_page_id,
        }
        for item in highlight_preview.items
    ]
    filtered = filter_vocabulary_candidates(candidates)
    vocabulary_preview = enrich_vocabulary_candidates(filtered.approved)

    return {
        "page_id": page_id,
        "total_highlights": highlight_preview.count,
        "rejected": [
            {
                "word": item.get("word", ""),
                "reason": item.get("reason", ""),
            }
            for item in filtered.rejected
        ],
        "vocabulary_preview": vocabulary_preview,
    }


def preview_vocabulary(page_id: str, notion: Any = None) -> dict[str, Any]:
    """Return the full JSON payload for the vocabulary preview pipeline."""
    return build_vocabulary_preview(page_id=page_id, notion=notion)
