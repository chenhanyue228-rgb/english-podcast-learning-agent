"""Preview pipeline for turning pink highlights into vocabulary candidates.

This module is read-only. It does not call Notion publishing APIs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from src.notion.highlight_reader import read_pink_highlights
from src.workflow.vocabulary_candidate_filter import filter_vocabulary_candidates


@dataclass(frozen=True)
class HighlightVocabularyPreviewItem:
    word: str
    context: str
    source_page_id: str


@dataclass(frozen=True)
class HighlightVocabularyPreview:
    count: int
    items: list[HighlightVocabularyPreviewItem]

    def to_json(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "items": [
                {
                    "word": item.word,
                    "context": item.context,
                    "source_page_id": item.source_page_id,
                }
                for item in self.items
            ],
        }


def build_highlight_vocabulary_preview(page_id: str, notion: Any = None) -> HighlightVocabularyPreview:
    """Build a non-persisted vocabulary preview from pink highlights."""
    highlights = read_pink_highlights(page_id=page_id, notion=notion)
    items = [
        HighlightVocabularyPreviewItem(
            word=str(highlight.get("text", "")).strip(),
            context=str(highlight.get("context", "")).strip(),
            source_page_id=page_id,
        )
        for highlight in highlights
        if str(highlight.get("text", "")).strip()
    ]
    return HighlightVocabularyPreview(count=len(items), items=items)


def preview_highlight_vocabulary(page_id: str, notion: Any = None) -> dict[str, Any]:
    """Return a filtered JSON-serializable preview for pink highlight candidates."""
    preview = build_highlight_vocabulary_preview(page_id=page_id, notion=notion)
    filtered = filter_vocabulary_candidates(
        [
            {
                "word": item.word,
                "context": item.context,
                "source_page_id": item.source_page_id,
            }
            for item in preview.items
        ]
    )
    return {
        "page_id": page_id,
        "total_highlights": preview.count,
        "approved_count": len(filtered.approved),
        "rejected_count": len(filtered.rejected),
        "approved": [
            {
                "word": item.get("word", ""),
                "context": item.get("context", ""),
                "source_page_id": item.get("source_page_id", ""),
            }
            for item in filtered.approved
        ],
        "rejected": [
            {
                "word": item.get("word", ""),
                "reason": item.get("reason", ""),
            }
            for item in filtered.rejected
        ],
    }
