"""Publish manual vocabulary memory records into Notion.

This module only writes user-triggered vocabulary memory items. It does not
scan highlights automatically and it does not modify Podcast Library pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, TYPE_CHECKING

from notion_client import APIResponseError

from src.notion.uploader import create_notion_client

if TYPE_CHECKING:
    from notion_client import Client


class VocabularyPublisherError(RuntimeError):
    """Raised when a vocabulary memory item cannot be published to Notion."""


@dataclass(frozen=True)
class VocabularyPublishPayload:
    """Input required to create a Vocabulary Database record."""

    word: str
    original_context: str = ""
    meaning: str = ""
    professional_category: str = ""
    source: str = "Podcast Library"
    source_page_id: str = ""
    first_seen: str = ""
    review_status: str = "New"
    last_review: str = ""
    usage_example: str = ""
    personal_note: str = ""


@dataclass(frozen=True)
class VocabularyPublishResult:
    """Result returned after creating a vocabulary page."""

    page_id: str
    page_url: Optional[str] = None


@dataclass(frozen=True)
class VocabularyUpsertResult:
    """Result returned after upserting a vocabulary page."""

    page_id: str
    page_url: Optional[str] = None
    action: str = "created"


@dataclass(frozen=True)
class VocabularyPublishPlan:
    """Preview of a vocabulary publishing run."""

    total: int
    create: int
    update: int
    previews: list[dict[str, Any]]


def _title_property(value: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": value}}]}


def _rich_text_property(value: str) -> dict[str, Any]:
    if not value:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": value}}]}


def _select_property(value: str) -> dict[str, Any]:
    return {"select": {"name": value}} if value else {"select": None}


def _relation_property(page_id: str) -> dict[str, Any]:
    return {"relation": [{"id": page_id}]} if page_id else {"relation": []}


def _date_property(value: str) -> dict[str, Any]:
    return {"date": {"start": value}} if value else {"date": None}


def _query_records(notion: "Client", vocabulary_database_id: str, word: str) -> list[dict[str, Any]]:
    try:
        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
            response = notion.data_sources.query(
                data_source_id=vocabulary_database_id,
                filter={"property": "Name", "title": {"equals": word}},
            )
        else:
            response = notion.databases.query(
                database_id=vocabulary_database_id,
                filter={"property": "Name", "title": {"equals": word}},
            )
    except Exception:
        return []
    results = response.get("results", [])
    return results if isinstance(results, list) else []


def find_existing_vocabulary_page(
    notion: "Client",
    vocabulary_database_id: str,
    word: str,
) -> Optional[dict[str, Any]]:
    records = _query_records(notion, vocabulary_database_id, word)
    return records[0] if records else None


def _page_body(payload: VocabularyPublishPayload) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "object": "block",
            "type": "heading_1",
            "heading_1": {"rich_text": [{"type": "text", "text": {"content": payload.word}}]},
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Context"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": payload.original_context}}]
                if payload.original_context
                else []
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Meaning"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": payload.meaning}}]
                if payload.meaning
                else []
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Professional Context"}}]
            },
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": payload.professional_category}}
                ]
                if payload.professional_category
                else []
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Usage Example"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": payload.usage_example}}]
                if payload.usage_example
                else []
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Personal Note"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": payload.personal_note}}]
                if payload.personal_note
                else []
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Source"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": f"Podcast Library page ID: {payload.source_page_id}"}}
                ]
                if payload.source_page_id
                else [{"type": "text", "text": {"content": "Podcast Library source not provided."}}]
            },
        },
        {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": "Review Status"}}]},
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": payload.review_status}}]
                if payload.review_status
                else []
            },
        },
    ]
    return blocks


def vocabulary_page_properties(payload: VocabularyPublishPayload) -> dict[str, Any]:
    """Build Vocabulary Database properties for a manual memory record."""
    return {
        "Name": _title_property(payload.word),
        "Original Context": _rich_text_property(payload.original_context),
        "Meaning": _rich_text_property(payload.meaning),
        "Professional Category": _select_property(payload.professional_category),
        "Source": _relation_property(payload.source_page_id),
        "Source Page ID": _rich_text_property(payload.source_page_id),
        "First Seen": _date_property(payload.first_seen),
        "Review Status": _select_property(payload.review_status or "New"),
        "Last Review": _date_property(payload.last_review),
        "Usage Example": _rich_text_property(payload.usage_example),
        "Personal Note": _rich_text_property(payload.personal_note),
    }


def create_vocabulary_page(
    payload: VocabularyPublishPayload,
    notion: Optional["Client"] = None,
    vocabulary_database_id: Optional[str] = None,
) -> VocabularyPublishResult:
    """Create a Vocabulary Database page from a manual vocabulary memory item."""
    if not payload.word.strip():
        raise VocabularyPublisherError("Vocabulary word is required.")

    if notion is None or vocabulary_database_id is None:
        notion = notion or create_notion_client()
        if vocabulary_database_id is None:
            from src.notion.config import load_notion_config

            vocabulary_database_id = load_notion_config().vocabulary_database_id

    try:
        response = notion.pages.create(
            parent={"data_source_id": vocabulary_database_id},
            properties=vocabulary_page_properties(payload),
            children=_page_body(payload),
        )
    except APIResponseError as exc:
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        raise VocabularyPublisherError(
            f"Notion API failed to create vocabulary page: {exc.code} {detail}"
        ) from exc
    except Exception as exc:
        raise VocabularyPublisherError(f"Failed to create vocabulary page: {exc}") from exc

    page_id = response.get("id")
    if not page_id:
        raise VocabularyPublisherError("Notion did not return a vocabulary page ID.")

    return VocabularyPublishResult(page_id=page_id, page_url=response.get("url"))


def update_vocabulary_page(
    page_id: str,
    payload: VocabularyPublishPayload,
    notion: Optional["Client"] = None,
) -> VocabularyPublishResult:
    if notion is None:
        notion = create_notion_client()

    try:
        response = notion.pages.update(
            page_id=page_id,
            properties=vocabulary_page_properties(payload),
        )
    except APIResponseError as exc:
        detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
        raise VocabularyPublisherError(
            f"Notion API failed to update vocabulary page: {exc.code} {detail}"
        ) from exc
    except Exception as exc:
        raise VocabularyPublisherError(f"Failed to update vocabulary page: {exc}") from exc

    return VocabularyPublishResult(page_id=response.get("id", page_id), page_url=response.get("url"))


def upsert_vocabulary_page(
    payload: VocabularyPublishPayload,
    notion: Optional["Client"] = None,
    vocabulary_database_id: Optional[str] = None,
) -> VocabularyUpsertResult:
    if notion is None or vocabulary_database_id is None:
        notion = notion or create_notion_client()
        if vocabulary_database_id is None:
            from src.notion.config import load_notion_config

            vocabulary_database_id = load_notion_config().vocabulary_database_id

    existing = find_existing_vocabulary_page(notion, vocabulary_database_id, payload.word)
    if existing:
        updated = update_vocabulary_page(existing.get("id", ""), payload, notion=notion)
        return VocabularyUpsertResult(
            page_id=updated.page_id,
            page_url=updated.page_url,
            action="updated",
        )

    created = create_vocabulary_page(
        payload,
        notion=notion,
        vocabulary_database_id=vocabulary_database_id,
    )
    return VocabularyUpsertResult(
        page_id=created.page_id,
        page_url=created.page_url,
        action="created",
    )


def build_vocabulary_publish_plan(
    expressions: list[dict[str, Any]],
) -> VocabularyPublishPlan:
    previews: list[dict[str, Any]] = []
    create_count = 0

    for expression in expressions:
        word = str(expression.get("expression", "")).strip()
        if not word:
            continue
        payload = VocabularyPublishPayload(
            word=word,
            original_context=str(
                expression.get("original_context")
                or expression.get("context")
                or expression.get("original_sentence")
                or ""
            ).strip(),
            meaning=str(expression.get("meaning", "")).strip(),
            professional_category=str(
                expression.get("category")
                or expression.get("professional_category")
                or ""
            ).strip(),
            source="Podcast Library",
            source_page_id=str(expression.get("source_page_id", "")).strip(),
            first_seen="",
            review_status="New",
            last_review="",
            usage_example=str(
                expression.get("original_context")
                or expression.get("context")
                or expression.get("example_sentence")
                or expression.get("example")
                or ""
            ).strip(),
            personal_note=str(
                expression.get("learning_note")
                or expression.get("my_note")
                or ""
            ).strip(),
        )

        create_count += 1
        previews.append(
            {
                "Name": payload.word,
                "Meaning": payload.meaning,
                "Category": payload.professional_category,
            }
        )

    return VocabularyPublishPlan(
        total=len(previews),
        create=create_count,
        update=0,
        previews=previews[:3],
    )


def publish_vocabulary_memory(
    vocabulary_json: Mapping[str, Any],
    notion: Optional["Client"] = None,
    vocabulary_database_id: Optional[str] = None,
) -> VocabularyPublishResult:
    """Publish a validated vocabulary memory JSON record into Notion."""
    payload = VocabularyPublishPayload(
        word=str(vocabulary_json.get("word", "")).strip(),
        original_context=str(
            vocabulary_json.get("original_context")
            or vocabulary_json.get("context")
            or ""
        ).strip(),
        meaning=str(vocabulary_json.get("meaning", "")).strip(),
        professional_category=str(
            vocabulary_json.get("professional_category")
            or vocabulary_json.get("category")
            or ""
        ).strip(),
        source=str(vocabulary_json.get("source", "Podcast Library")).strip() or "Podcast Library",
        source_page_id=str(vocabulary_json.get("source_page_id", "")).strip(),
        first_seen=str(vocabulary_json.get("first_seen", "")).strip(),
        review_status=str(vocabulary_json.get("review_status", "New")).strip() or "New",
        last_review=str(vocabulary_json.get("last_review", "")).strip(),
        usage_example=str(
            vocabulary_json.get("usage_example")
            or vocabulary_json.get("my_usage")
            or ""
        ).strip(),
        personal_note=str(
            vocabulary_json.get("personal_note")
            or vocabulary_json.get("my_note")
            or ""
        ).strip(),
    )
    return create_vocabulary_page(
        payload,
        notion=notion,
        vocabulary_database_id=vocabulary_database_id,
    )
