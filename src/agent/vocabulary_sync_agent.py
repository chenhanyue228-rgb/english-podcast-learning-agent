"""Automated vocabulary sync agent for newly pink-highlighted words."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional

from src.agent.highlight_state import load_highlight_state, save_highlight_state
from src.agent.notion_page_scanner import scan_changed_podcast_pages
from src.enrichment.factory import create_vocabulary_enrichment_provider
from src.notion.config import load_notion_config
from src.notion.highlight_reader import read_pink_highlights
from src.notion.uploader import create_notion_client
from src.notion.vocabulary_publisher import (
    VocabularyPublishPayload,
    VocabularyUpsertResult,
    upsert_vocabulary_page,
)
from src.workflow.vocabulary_candidate_filter import filter_vocabulary_candidates
from src.workflow.vocabulary_enrichment import enrich_vocabulary_candidates


LOGGER = logging.getLogger(__name__)


class VocabularySyncAgentError(RuntimeError):
    """Raised when the automated vocabulary sync agent cannot complete."""


@dataclass(frozen=True)
class VocabularySyncAgentResult:
    scanned_pages: int
    changed_pages: int
    new_highlights: int
    created: int
    updated: int
    skipped: int
    last_scan_time: str
    upsert_results: list[VocabularyUpsertResult]


def _normalise_highlight_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_highlight_key(value: Any) -> str:
    text = _normalise_highlight_text(value)
    if not text:
        return ""
    text = re.sub(r"[\u2018\u2019\u201c\u201d\"'.,;:!?()\[\]{}<>/\\-]+", " ", text.lower())
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    parts = []
    for token in text.split(" "):
        cleaned = token.strip()
        if not cleaned:
            continue
        if cleaned.endswith("ies") and len(cleaned) > 4:
            cleaned = cleaned[:-3] + "y"
        elif cleaned.endswith("s") and len(cleaned) > 3 and not cleaned.endswith(("ss", "us", "is")):
            cleaned = cleaned[:-1]
        parts.append(cleaned)
    return " ".join(parts).strip()


def _parse_timestamp(value: str) -> Optional[datetime]:
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _page_state(state: Mapping[str, Any], page_id: str) -> set[str]:
    processed = state.get("processed_highlights_by_page", {})
    if not isinstance(processed, Mapping):
        return set()
    items = processed.get(page_id, [])
    if not isinstance(items, list):
        return set()
    return {_normalize_highlight_key(item) for item in items if _normalize_highlight_key(item)}


def _merge_processed_highlights(
    state: Mapping[str, Any],
    page_id: str,
    highlights: list[str],
) -> dict[str, Any]:
    merged_state = {
        "last_scan_time": str(state.get("last_scan_time", "")).strip(),
        "processed_highlights_by_page": {},
    }
    processed = state.get("processed_highlights_by_page", {})
    if isinstance(processed, Mapping):
        for existing_page_id, items in processed.items():
            if not isinstance(items, list):
                continue
            merged_state["processed_highlights_by_page"][str(existing_page_id)] = list(
                dict.fromkeys(_normalize_highlight_key(item) for item in items if _normalize_highlight_key(item))
            )
    existing = merged_state["processed_highlights_by_page"].get(page_id, [])
    combined = list(
        dict.fromkeys(
            [
                *existing,
                *[
                    _normalize_highlight_key(item)
                    for item in highlights
                    if _normalize_highlight_key(item)
                ],
            ]
        )
    )
    if combined:
        merged_state["processed_highlights_by_page"][page_id] = combined
    return merged_state


def _build_payload_from_item(item: Mapping[str, Any]) -> VocabularyPublishPayload:
    return VocabularyPublishPayload(
        word=str(item.get("word", "")).strip(),
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


def _approved_items_from_highlights(
    page_id: str,
    highlights: list[dict[str, str]],
    processed_words: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    new_candidates: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for highlight in highlights:
        word = _normalise_highlight_text(highlight.get("text"))
        if not word:
            continue
        normalized_key = _normalize_highlight_key(word)
        if not normalized_key:
            continue
        if normalized_key in processed_words or normalized_key in seen:
            continue
        seen.add(normalized_key)
        new_candidates.append(
            {
                "word": word,
                "context": str(highlight.get("context", "")).strip(),
                "source_page_id": page_id,
            }
        )
    filtered = filter_vocabulary_candidates(new_candidates)
    skipped.extend(filtered.rejected)
    return filtered.approved, skipped


def sync_vocabulary_from_highlight_changes(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    vocabulary_database_id: Optional[str] = None,
    state_path: Optional[Path] = None,
) -> VocabularySyncAgentResult:
    """Sync newly added pink highlights from changed Podcast pages into Notion."""
    if notion is None or podcast_database_id is None or vocabulary_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id
        vocabulary_database_id = vocabulary_database_id or config.vocabulary_database_id

    assert notion is not None
    assert podcast_database_id is not None
    assert vocabulary_database_id is not None

    state = load_highlight_state(state_path) if state_path is not None else load_highlight_state()
    last_scan_time = str(state.get("last_scan_time", "")).strip()

    changed_pages = scan_changed_podcast_pages(
        notion=notion,
        podcast_database_id=podcast_database_id,
        last_scan_time=last_scan_time,
    )

    created = 0
    updated = 0
    skipped = 0
    new_highlights_total = 0
    upsert_results: list[VocabularyUpsertResult] = []
    next_state = {
        "last_scan_time": last_scan_time,
        "processed_highlights_by_page": dict(
            state.get("processed_highlights_by_page", {})
            if isinstance(state.get("processed_highlights_by_page", {}), Mapping)
            else {}
        ),
    }
    newest_seen: Optional[datetime] = _parse_timestamp(last_scan_time or "")

    try:
        for changed_page in changed_pages:
            page_id = changed_page.page_id
            page_timestamp = _parse_timestamp(changed_page.last_edited_time)
            if page_timestamp is not None and (newest_seen is None or page_timestamp > newest_seen):
                newest_seen = page_timestamp

            highlights = read_pink_highlights(page_id=page_id, notion=notion)
            processed_words = _page_state(state, page_id)
            approved_candidates, rejected_candidates = _approved_items_from_highlights(
                page_id=page_id,
                highlights=highlights,
                processed_words=processed_words,
            )
            skipped += len(rejected_candidates)
            new_highlights_total += len(approved_candidates)

            if not approved_candidates:
                next_state = _merge_processed_highlights(
                    next_state,
                    page_id,
                    [
                        _normalize_highlight_key(highlight.get("text"))
                        for highlight in highlights
                        if _normalize_highlight_key(highlight.get("text"))
                    ],
                )
                continue

            enriched_items = enrich_vocabulary_candidates(approved_candidates, provider=create_vocabulary_enrichment_provider())
            for item in enriched_items:
                payload = _build_payload_from_item(item)
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

            next_state = _merge_processed_highlights(
                next_state,
                page_id,
                [
                    _normalize_highlight_key(highlight.get("text"))
                    for highlight in highlights
                    if _normalize_highlight_key(highlight.get("text"))
                ],
            )

        if newest_seen is not None:
            next_state["last_scan_time"] = newest_seen.isoformat()
        elif last_scan_time:
            next_state["last_scan_time"] = last_scan_time
        save_highlight_state(next_state, path=state_path) if state_path is not None else save_highlight_state(next_state)
    except Exception as exc:
        raise VocabularySyncAgentError(str(exc)) from exc

    LOGGER.info(
        "Vocabulary sync agent completed: pages=%s changed=%s new_highlights=%s created=%s updated=%s",
        len(changed_pages),
        len(changed_pages),
        new_highlights_total,
        created,
        updated,
    )
    return VocabularySyncAgentResult(
        scanned_pages=len(changed_pages),
        changed_pages=len(changed_pages),
        new_highlights=new_highlights_total,
        created=created,
        updated=updated,
        skipped=skipped,
        last_scan_time=str(next_state.get("last_scan_time", "")).strip(),
        upsert_results=upsert_results,
    )
