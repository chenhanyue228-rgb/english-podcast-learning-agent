"""Publish manual vocabulary memory records into Notion.

This module only writes user-triggered vocabulary memory items. It does not
scan highlights automatically and it does not modify Podcast Library pages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, TYPE_CHECKING

from notion_client import APIResponseError

from src.notion.schema import PODCAST_LIBRARY, VOCABULARY_DATABASE
from src.notion.pagination import NotionPaginationError, next_notion_cursor
from src.notion.target_binding import (
    ensure_notion_page_belongs_to_role,
    ensure_notion_target_binding_for_write,
)
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
    chinese_meaning: str = ""
    part_of_speech: str = ""
    common_collocations: tuple[str, ...] = ()
    semantic_category: str = ""


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


def _heading(level: int, value: str) -> dict[str, Any]:
    block_type = f"heading_{level}"
    return {
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": [{"type": "text", "text": {"content": value}}]
        },
    }


def _paragraph(value: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": (
                [{"type": "text", "text": {"content": value}}]
                if value
                else []
            )
        },
    }


def _query_records(
    notion: "Client",
    vocabulary_database_id: str,
    word: str,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    visited: set[str] = set()
    try:
        while True:
            request: dict[str, Any] = {
                "filter": {
                    "property": "Name",
                    "title": {"equals": word},
                },
                "page_size": 100,
            }
            if cursor is not None:
                request["start_cursor"] = cursor
            if hasattr(notion, "data_sources") and hasattr(
                notion.data_sources,
                "query",
            ):
                response = notion.data_sources.query(
                    data_source_id=vocabulary_database_id,
                    **request,
                )
            else:
                response = notion.databases.query(
                    database_id=vocabulary_database_id,
                    **request,
                )
            if not isinstance(response, Mapping):
                raise VocabularyPublisherError(
                    "vocabulary_identity_query_failed"
                )
            page = response.get("results")
            if not isinstance(page, list) or any(
                not isinstance(item, Mapping) for item in page
            ):
                raise VocabularyPublisherError(
                    "vocabulary_identity_query_failed"
                )
            results.extend(dict(item) for item in page)
            cursor = next_notion_cursor(
                response,
                current_cursor=cursor,
                visited_cursors=visited,
            )
            if cursor is None:
                return results
    except VocabularyPublisherError:
        raise
    except NotionPaginationError as exc:
        raise VocabularyPublisherError(
            "vocabulary_identity_query_failed"
        ) from exc
    except Exception as exc:
        raise VocabularyPublisherError(
            "vocabulary_identity_query_failed"
        ) from exc


def find_existing_vocabulary_page(
    notion: "Client",
    vocabulary_database_id: str,
    word: str,
) -> Optional[dict[str, Any]]:
    records = _query_records(notion, vocabulary_database_id, word)
    if len(records) > 1:
        raise VocabularyPublisherError("vocabulary_identity_not_unique")
    return records[0] if records else None


def _page_body(payload: VocabularyPublishPayload) -> list[dict[str, Any]]:
    blocks = [
        _heading(1, payload.word),
        _heading(2, "Context"),
        _paragraph(payload.original_context),
        _heading(2, "Meaning"),
        _paragraph(payload.meaning),
        _heading(2, "Chinese Meaning"),
        _paragraph(payload.chinese_meaning),
        _heading(2, "Part of Speech"),
        _paragraph(payload.part_of_speech),
        _heading(2, "Professional Context"),
        _paragraph(payload.semantic_category or payload.professional_category),
        _heading(2, "Usage Example"),
        _paragraph(payload.usage_example),
        _heading(2, "Common Collocations"),
    ]
    blocks.extend(
        {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [
                    {"type": "text", "text": {"content": value}}
                ]
            },
        }
        for value in payload.common_collocations
    )
    blocks.extend(
        (
            _heading(2, "Personal Note"),
            _paragraph(payload.personal_note),
            _heading(2, "Source"),
            _paragraph(
                "Podcast Library source linked."
                if payload.source_page_id
                else "Podcast Library source not provided."
            ),
            _heading(2, "Review Status"),
            _paragraph(payload.review_status),
        )
    )
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

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={VOCABULARY_DATABASE: vocabulary_database_id},
    )
    if payload.source_page_id:
        ensure_notion_page_belongs_to_role(
            notion,
            payload.source_page_id,
            PODCAST_LIBRARY,
        )
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

    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        VOCABULARY_DATABASE,
    )
    if payload.source_page_id:
        ensure_notion_page_belongs_to_role(
            notion,
            payload.source_page_id,
            PODCAST_LIBRARY,
        )
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

    return VocabularyPublishResult(
        page_id=response.get("id", page_id),
        page_url=response.get("url"),
    )


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

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={VOCABULARY_DATABASE: vocabulary_database_id},
    )
    if payload.source_page_id:
        ensure_notion_page_belongs_to_role(
            notion,
            payload.source_page_id,
            PODCAST_LIBRARY,
        )
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


def _property_mapping(
    page: Mapping[str, Any],
    property_name: str,
) -> Mapping[str, Any]:
    properties = page.get("properties")
    if not isinstance(properties, Mapping):
        return {}
    value = properties.get(property_name)
    return value if isinstance(value, Mapping) else {}


def _relation_ids(page: Mapping[str, Any], property_name: str) -> list[str]:
    relation = _property_mapping(page, property_name).get("relation")
    if not isinstance(relation, list):
        return []
    return [
        str(item["id"])
        for item in relation
        if isinstance(item, Mapping)
        and isinstance(item.get("id"), str)
        and str(item["id"]).strip()
    ]


def _merged_relation_property(
    existing_page: Mapping[str, Any],
    source_page_id: str,
) -> dict[str, Any]:
    relation_ids = _relation_ids(existing_page, "Source")
    if source_page_id and source_page_id not in relation_ids:
        relation_ids.append(source_page_id)
    return {"relation": [{"id": page_id} for page_id in relation_ids]}


def _automatic_update_properties(
    payload: VocabularyPublishPayload,
    existing_page: Mapping[str, Any],
) -> dict[str, Any]:
    """Return only machine-managed properties for an automatic retry/update."""
    return {
        "Original Context": _rich_text_property(payload.original_context),
        "Meaning": _rich_text_property(payload.meaning),
        "Professional Category": _select_property(
            payload.professional_category
        ),
        "Source": _merged_relation_property(
            existing_page,
            payload.source_page_id,
        ),
        "Usage Example": _rich_text_property(payload.usage_example),
    }


def upsert_automatic_vocabulary_occurrence(
    payload: VocabularyPublishPayload,
    *,
    notion: "Client",
    vocabulary_database_id: str,
) -> VocabularyUpsertResult:
    """Fail-closed automatic upsert that preserves user-managed fields/body."""
    if not payload.word.strip() or not payload.source_page_id.strip():
        raise VocabularyPublisherError("automatic_vocabulary_payload_invalid")

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={VOCABULARY_DATABASE: vocabulary_database_id},
    )
    ensure_notion_page_belongs_to_role(
        notion,
        payload.source_page_id,
        PODCAST_LIBRARY,
        force_refresh=True,
    )
    records = _query_records(
        notion,
        vocabulary_database_id,
        payload.word,
    )
    if len(records) > 1:
        raise VocabularyPublisherError("vocabulary_identity_not_unique")

    if not records:
        try:
            response = notion.pages.create(
                parent={"data_source_id": vocabulary_database_id},
                properties=vocabulary_page_properties(payload),
                children=_page_body(payload),
            )
        except Exception as exc:
            raise VocabularyPublisherError(
                "automatic_vocabulary_create_failed"
            ) from exc
        page_id = response.get("id") if isinstance(response, Mapping) else None
        if not isinstance(page_id, str) or not page_id.strip():
            raise VocabularyPublisherError(
                "automatic_vocabulary_create_failed"
            )
        return VocabularyUpsertResult(
            page_id=page_id,
            page_url=(
                response.get("url")
                if isinstance(response.get("url"), str)
                else None
            ),
            action="created",
        )

    existing = records[0]
    page_id = existing.get("id")
    if not isinstance(page_id, str) or not page_id.strip():
        raise VocabularyPublisherError("vocabulary_identity_invalid")
    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        VOCABULARY_DATABASE,
        force_refresh=True,
    )
    try:
        response = notion.pages.update(
            page_id=page_id,
            properties=_automatic_update_properties(payload, existing),
        )
    except Exception as exc:
        raise VocabularyPublisherError(
            "automatic_vocabulary_update_failed"
        ) from exc
    return VocabularyUpsertResult(
        page_id=page_id,
        page_url=(
            response.get("url")
            if isinstance(response, Mapping)
            and isinstance(response.get("url"), str)
            else None
        ),
        action="updated",
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
        chinese_meaning=str(
            vocabulary_json.get("chinese_meaning", "")
        ).strip(),
        part_of_speech=str(
            vocabulary_json.get("part_of_speech", "")
        ).strip(),
        common_collocations=tuple(
            str(value).strip()
            for value in vocabulary_json.get("common_collocations", [])
            if str(value).strip()
        )
        if isinstance(vocabulary_json.get("common_collocations"), list)
        else (),
    )
    return create_vocabulary_page(
        payload,
        notion=notion,
        vocabulary_database_id=vocabulary_database_id,
    )
