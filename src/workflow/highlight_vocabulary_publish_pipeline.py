"""Publish approved pink-highlight vocabulary into Notion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client
from src.notion.vocabulary_publisher import (
    VocabularyPublishPayload,
    VocabularyUpsertResult,
    upsert_vocabulary_page,
)
from src.workflow.vocabulary_learning_pipeline import build_vocabulary_learning_preview


@dataclass(frozen=True)
class HighlightVocabularyPublishResult:
    page_id: str
    created: int
    updated: int
    skipped: int
    preview_count: int
    upsert_results: list[VocabularyUpsertResult]


def _publish_payload_from_item(item: Mapping[str, Any]) -> VocabularyPublishPayload:
    word = str(item.get("word", "")).strip()
    return VocabularyPublishPayload(
        word=word,
        original_context=str(item.get("original_context", "")).strip(),
        meaning=str(item.get("meaning", "")).strip(),
        professional_category=str(item.get("professional_category", "")).strip(),
        source="Podcast Library",
        source_page_id=str(item.get("source_page_id", "")).strip(),
        first_seen=date.today().isoformat(),
        review_status="New",
        last_review="",
        usage_example=str(
            item.get("usage_example")
            or item.get("original_context")
            or item.get("context")
            or ""
        ).strip(),
        personal_note="",
    )


def publish_highlight_vocabulary(
    page_id: str,
    notion: Any = None,
    vocabulary_database_id: Optional[str] = None,
) -> HighlightVocabularyPublishResult:
    """Publish approved pink-highlight vocabulary into the Vocabulary Database."""
    preview = build_vocabulary_learning_preview(page_id=page_id, notion=notion)
    approved_items = [
        item
        for item in preview.get("approved_vocabulary", [])
        if isinstance(item, Mapping) and str(item.get("word", "")).strip()
    ]

    if notion is None or vocabulary_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        vocabulary_database_id = vocabulary_database_id or config.vocabulary_database_id

    assert notion is not None
    assert vocabulary_database_id is not None

    created = 0
    updated = 0
    skipped = len(preview.get("rejected_candidates", []))
    upsert_results: list[VocabularyUpsertResult] = []

    for item in approved_items:
        payload = _publish_payload_from_item(item)
        result = upsert_vocabulary_page(
            payload,
            notion=notion,
            vocabulary_database_id=vocabulary_database_id,
        )
        upsert_results.append(result)
        if result.action == "updated":
            updated += 1
        else:
            created += 1

    return HighlightVocabularyPublishResult(
        page_id=page_id,
        created=created,
        updated=updated,
        skipped=skipped,
        preview_count=len(approved_items),
        upsert_results=upsert_results,
    )
