"""Publish Phase 3 AI learning analysis into existing Notion pages."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Sequence

from notion_client import APIResponseError, Client

from src.analyzer.models import AIAnalysisResult, LearningItem
from src.notion.config import load_notion_config
from src.notion.renderers import expression_body_blocks, podcast_body_blocks
from src.notion.schema import (
    COMMONNESS_LEVELS,
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    category_color,
)
from src.notion.target_binding import ensure_notion_target_binding_for_write
from src.notion.uploader import create_notion_client

logger = logging.getLogger(__name__)


class LearningPublisherError(RuntimeError):
    """Raised when AI learning material cannot be published to Notion."""


@dataclass(frozen=True)
class LearningPublishPayload:
    """Input required to publish Phase 3 learning material to Notion."""

    podcast_page_id: str
    analysis: AIAnalysisResult
    transcript: str


@dataclass(frozen=True)
class CompletePodcastLearningPayload:
    """Input required to create a complete Podcast Library learning page."""

    title: str
    source_url: Optional[str]
    source_type: str
    transcript: str
    analysis: AIAnalysisResult
    processed_date: str = field(default_factory=lambda: date.today().isoformat())


@dataclass(frozen=True)
class LearningPublishResult:
    """Notion page IDs created or updated by the learning publisher."""

    podcast_page_id: str
    expression_page_ids: list[str]
    podcast_page_url: Optional[str] = None


def select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}} if name else {"select": None}


def rich_text_property(text: str) -> dict[str, Any]:
    if not text:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": text}}]}


def title_property(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def relation_property(page_ids: Sequence[str]) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def url_property(url: Optional[str]) -> dict[str, Any]:
    return {"url": url}


def date_property(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def api_error_message(exc: APIResponseError) -> str:
    """Return a readable Notion SDK error message across SDK versions."""
    code = getattr(exc, "code", "unknown")
    detail = getattr(exc, "message", None) or getattr(exc, "detail", None) or str(exc)
    return f"{code} {detail}".strip()


EXPRESSION_PROPERTY_TYPES = {
    "Expression": "title",
    "Category": "select",
    "Commonness": "select",
    "Source Podcast": "relation",
    "Review Status": "select",
}


def notion_database_properties(
    notion: Client,
    database_id: str,
) -> dict[str, Any]:
    """Return the property definitions for a Notion database."""
    try:
        if hasattr(notion, "data_sources"):
            response = notion.data_sources.retrieve(data_source_id=database_id)
        else:
            response = notion.databases.retrieve(database_id=database_id)
    except Exception as exc:
        raise LearningPublisherError(
            "Failed to inspect Expression Database schema."
        ) from exc

    properties = response.get("properties", {})
    if not isinstance(properties, dict):
        raise LearningPublisherError(
            "Expression Database returned an invalid schema."
        )
    return properties


def normalized_notion_id(value: Any) -> str:
    """Normalize UUID formatting for safe Notion data source comparisons."""
    return str(value or "").strip().replace("-", "").casefold()


def validate_expression_database_schema(
    properties: dict[str, Any],
    podcast_database_id: str,
    *,
    require_commonness: bool,
) -> None:
    """Validate the complete Expression schema without mutating Notion."""
    if not podcast_database_id.strip():
        raise LearningPublisherError(
            "Podcast Library data source configuration is required."
        )

    for property_name, expected_type in EXPRESSION_PROPERTY_TYPES.items():
        actual = properties.get(property_name)
        if actual is None:
            if property_name == "Commonness" and not require_commonness:
                continue
            raise LearningPublisherError(
                f"Expression Database schema is missing required property "
                f"'{property_name}'."
            )
        if not isinstance(actual, dict) or actual.get("type") != expected_type:
            raise LearningPublisherError(
                f"Expression Database property '{property_name}' has an "
                "incompatible type."
            )

    source_podcast = properties["Source Podcast"]
    relation = source_podcast.get("relation")
    if not isinstance(relation, dict):
        raise LearningPublisherError(
            "Expression Database relation 'Source Podcast' is incompatible."
        )
    if normalized_notion_id(relation.get("data_source_id")) != normalized_notion_id(
        podcast_database_id
    ):
        raise LearningPublisherError(
            "Expression Database relation 'Source Podcast' targets an "
            "incompatible data source."
        )
    if "single_property" not in relation or "dual_property" in relation:
        raise LearningPublisherError(
            "Expression Database relation 'Source Podcast' must use "
            "single_property mode."
        )


def ensure_expression_database_schema(
    notion: Client,
    expression_database_id: str,
    podcast_database_id: str,
) -> None:
    """Validate Expression schema and repair only a missing Commonness field."""
    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={
            EXPRESSION_DATABASE: expression_database_id,
            PODCAST_LIBRARY: podcast_database_id,
        },
    )
    properties = notion_database_properties(notion, expression_database_id)
    validate_expression_database_schema(
        properties,
        podcast_database_id,
        require_commonness=False,
    )
    if "Commonness" in properties:
        validate_expression_database_schema(
            properties,
            podcast_database_id,
            require_commonness=True,
        )
        return

    commonness_property = {
        "Commonness": {
            "select": {
                "options": [{"name": option} for option in COMMONNESS_LEVELS]
            }
        }
    }

    try:
        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "update"):
            notion.data_sources.update(
                data_source_id=expression_database_id,
                properties=commonness_property,
            )
        elif hasattr(notion, "databases") and hasattr(notion.databases, "update"):
            notion.databases.update(
                database_id=expression_database_id,
                properties=commonness_property,
            )
        else:
            raise LearningPublisherError(
                "Notion client cannot update Expression Database schema."
            )
    except LearningPublisherError:
        raise
    except APIResponseError as exc:
        raise LearningPublisherError(
            "Failed to update Expression Database schema."
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            "Failed to update Expression Database schema."
        ) from exc

    logger.info("Added missing Commonness property to Expression Database.")

    repaired_properties = notion_database_properties(
        notion,
        expression_database_id,
    )
    validate_expression_database_schema(
        repaired_properties,
        podcast_database_id,
        require_commonness=True,
    )


def podcast_update_properties(analysis: AIAnalysisResult) -> dict[str, Any]:
    metadata = analysis.podcast_metadata
    properties = {
        "Topic": select_property(metadata.topic),
        "Difficulty": select_property(metadata.difficulty),
        "Short Summary": rich_text_property(metadata.short_summary),
    }
    if metadata.title:
        properties["Title"] = title_property(metadata.title)
    return properties


def complete_podcast_page_properties(
    payload: CompletePodcastLearningPayload,
) -> dict[str, Any]:
    """Build complete Podcast Library properties for a learning page."""
    properties = {
        "Title": title_property(payload.analysis.podcast_metadata.title or payload.title),
        "URL": url_property(payload.source_url),
        "Source Type": select_property(payload.source_type),
        "Date": date_property(payload.processed_date),
    }
    properties.update(podcast_update_properties(payload.analysis))
    if not payload.analysis.podcast_metadata.title:
        properties["Title"] = title_property(payload.title)
    return properties


def analysis_summary_text(analysis: AIAnalysisResult) -> str:
    parts = [analysis.summary.english]
    if analysis.summary.chinese:
        parts.append(analysis.summary.chinese)
    if analysis.summary.key_points:
        parts.append(
            "\n".join(f"- {key_point}" for key_point in analysis.summary.key_points)
        )
    return "\n\n".join(part for part in parts if part)


def learning_item_payload(item: LearningItem) -> dict[str, str]:
    color = item.highlight_color or category_color(item.category)
    return {
        "expression": item.text,
        "text": item.text,
        "category": item.category,
        "meaning": item.meaning,
        "chinese_meaning": item.chinese_meaning,
        "usage_context": item.usage_context,
        "commonness": item.commonness or "Medium",
        "context": item.context_sentence,
        "context_sentence": item.context_sentence,
        "example": item.example_sentence,
        "example_sentence": item.example_sentence,
        "color": color,
    }


def expression_page_properties(
    item: LearningItem,
    podcast_page_id: str,
    include_commonness: bool = True,
) -> dict[str, Any]:
    properties = {
        "Expression": title_property(item.text),
        "Category": select_property(item.category),
        "Review Status": select_property("New"),
        "Source Podcast": relation_property([podcast_page_id]),
    }
    if include_commonness:
        properties["Commonness"] = select_property(item.commonness or "Medium")
    return properties


def update_podcast_learning_page(
    notion: Client,
    podcast_page_id: str,
    analysis: AIAnalysisResult,
    transcript: str,
) -> None:
    if not podcast_page_id.strip():
        raise LearningPublisherError("Podcast page ID is required.")
    if not transcript.strip():
        raise LearningPublisherError("Transcript text is required.")

    ensure_notion_target_binding_for_write(notion)
    learning_items = analysis.all_learning_items()
    try:
        notion.pages.update(
            page_id=podcast_page_id,
            properties=podcast_update_properties(analysis),
        )
        notion.blocks.children.append(
            block_id=podcast_page_id,
            children=podcast_body_blocks(
                summary=analysis_summary_text(analysis),
                transcript=transcript,
                expressions=[learning_item_payload(item) for item in learning_items],
            ),
        )
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Notion API failed to update podcast page: {api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(f"Failed to update podcast page: {exc}") from exc


def create_expression_page(
    notion: Client,
    expression_database_id: str,
    podcast_page_id: str,
    item: LearningItem,
) -> str:
    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={EXPRESSION_DATABASE: expression_database_id},
    )
    try:
        response = notion.pages.create(
            parent={"data_source_id": expression_database_id},
            properties=expression_page_properties(
                item,
                podcast_page_id,
            ),
            children=expression_body_blocks(
                learning_item_payload(item),
                fallback_context_sentence=item.context_sentence,
            ),
        )
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Notion API failed to create expression '{item.text}': "
            f"{api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            f"Failed to create expression '{item.text}': {exc}"
        ) from exc

    page_id = response.get("id")
    if not page_id:
        raise LearningPublisherError(
            f"Notion did not return a page ID for expression '{item.text}'."
        )
    return page_id


def create_complete_podcast_learning_page(
    notion: Client,
    podcast_database_id: str,
    payload: CompletePodcastLearningPayload,
) -> tuple[str, Optional[str]]:
    """Create a Podcast Library page with complete Phase 3 learning content."""
    if not payload.title.strip():
        raise LearningPublisherError("Podcast title is required.")
    if not payload.source_type.strip():
        raise LearningPublisherError("Podcast source_type is required.")
    if not payload.transcript.strip():
        raise LearningPublisherError("Transcript text is required.")

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={PODCAST_LIBRARY: podcast_database_id},
    )
    try:
        response = notion.pages.create(
            parent={"data_source_id": podcast_database_id},
            properties=complete_podcast_page_properties(payload),
            children=podcast_body_blocks(
                summary=analysis_summary_text(payload.analysis),
                transcript=payload.transcript,
                expressions=[
                    learning_item_payload(item)
                    for item in payload.analysis.all_learning_items()
                ],
            ),
        )
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Notion API failed to create complete podcast page: "
            f"{api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            f"Failed to create complete podcast page: {exc}"
        ) from exc

    page_id = response.get("id")
    if not page_id:
        raise LearningPublisherError("Notion did not return a podcast page ID.")
    return page_id, response.get("url")


def find_existing_complete_podcast_page(
    notion: Client,
    podcast_database_id: str,
    payload: CompletePodcastLearningPayload,
) -> Optional[dict[str, Any]]:
    """Find the Podcast Library page representing the same source identity."""
    if payload.source_url:
        query_filter: dict[str, Any] = {
            "property": "URL",
            "url": {"equals": payload.source_url},
        }
    else:
        title = payload.analysis.podcast_metadata.title or payload.title
        query_filter = {
            "and": [
                {"property": "Title", "title": {"equals": title}},
                {
                    "property": "Source Type",
                    "select": {"equals": payload.source_type},
                },
            ]
        }

    try:
        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
            response = notion.data_sources.query(
                data_source_id=podcast_database_id,
                filter=query_filter,
                page_size=1,
            )
        elif hasattr(notion, "databases") and hasattr(notion.databases, "query"):
            response = notion.databases.query(
                database_id=podcast_database_id,
                filter=query_filter,
                page_size=1,
            )
        else:
            logger.warning(
                "Notion client does not expose a data source query API; "
                "Podcast idempotency check skipped."
            )
            return None
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Notion API failed to check existing podcast page: {api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            f"Failed to check existing podcast page: {exc}"
        ) from exc

    results = response.get("results", [])
    if not isinstance(results, list) or not results:
        return None
    first = results[0]
    return first if isinstance(first, dict) else None


def update_complete_podcast_page_properties(
    notion: Client,
    page_id: str,
    payload: CompletePodcastLearningPayload,
) -> None:
    """Refresh properties for an exact repeat without duplicating page content."""
    ensure_notion_target_binding_for_write(notion)
    try:
        notion.pages.update(
            page_id=page_id,
            properties=complete_podcast_page_properties(payload),
        )
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Notion API failed to update existing podcast page: {api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            f"Failed to update existing podcast page: {exc}"
        ) from exc


def expression_identity_filter(
    item: LearningItem,
    podcast_page_id: str,
) -> dict[str, Any]:
    """Build the stable Notion identity for one Podcast expression."""
    return {
        "and": [
            {
                "property": "Expression",
                "title": {"equals": item.text},
            },
            {
                "property": "Category",
                "select": {"equals": item.category},
            },
            {
                "property": "Source Podcast",
                "relation": {"contains": podcast_page_id},
            },
        ]
    }


def normalized_expression_identity(item: LearningItem) -> tuple[str, str]:
    """Return the stable per-Podcast identity used for artifact deduplication."""
    normalized_text = " ".join(item.text.split()).casefold()
    normalized_category = " ".join(item.category.split()).casefold()
    return normalized_text, normalized_category


def deduplicate_expected_expression_items(
    items: Sequence[LearningItem],
) -> list[LearningItem]:
    """Keep the first item for each normalized identity within one Podcast."""
    unique_items: list[LearningItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        identity = normalized_expression_identity(item)
        if identity in seen:
            continue
        seen.add(identity)
        unique_items.append(item)
    return unique_items


def find_existing_expression_page_ids(
    notion: Client,
    expression_database_id: str,
    podcast_page_id: str,
    item: LearningItem,
) -> list[str]:
    """Return all exact Expression page matches for one stable identity."""
    try:
        if not hasattr(notion, "data_sources") or not hasattr(
            notion.data_sources,
            "query",
        ):
            raise LearningPublisherError(
                "Notion client cannot query existing Expression records."
            )
        response = notion.data_sources.query(
            data_source_id=expression_database_id,
            filter=expression_identity_filter(item, podcast_page_id),
            page_size=2,
        )
    except LearningPublisherError:
        raise
    except Exception as exc:
        raise LearningPublisherError(
            "Failed to inspect existing Expression records."
        ) from exc

    results = response.get("results", [])
    if not isinstance(results, list):
        raise LearningPublisherError(
            "Notion returned an invalid Expression query result."
        )
    page_ids: list[str] = []
    for result in results:
        page_id = (
            str(result.get("id", "")).strip()
            if isinstance(result, dict)
            else ""
        )
        if not page_id:
            raise LearningPublisherError(
                "Existing Expression record did not include a page ID."
            )
        page_ids.append(page_id)
    return page_ids


def reconcile_expression_pages(
    notion: Client,
    expression_database_id: str,
    podcast_page_id: str,
    items: Sequence[LearningItem],
) -> list[str]:
    """Reuse exact Expression matches and create only missing pages."""
    expected: list[tuple[LearningItem, list[str]]] = []
    for item in deduplicate_expected_expression_items(items):
        expected.append(
            (
                item,
                find_existing_expression_page_ids(
                    notion=notion,
                    expression_database_id=expression_database_id,
                    podcast_page_id=podcast_page_id,
                    item=item,
                ),
            )
        )

    if any(len(page_ids) > 1 for _, page_ids in expected):
        raise LearningPublisherError(
            "Duplicate Expression records found for one expected learning item."
        )

    page_ids: list[str] = []
    for item, existing_page_ids in expected:
        page_ids.append(
            (existing_page_ids[0] if existing_page_ids else None)
            or create_expression_page(
                notion=notion,
                expression_database_id=expression_database_id,
                podcast_page_id=podcast_page_id,
                item=item,
            )
        )
    return page_ids


def publish_complete_learning_materials(
    payload: CompletePodcastLearningPayload,
    notion: Optional[Client] = None,
    podcast_database_id: Optional[str] = None,
    expression_database_id: Optional[str] = None,
) -> LearningPublishResult:
    """Create a complete Podcast page and related Expression Database pages."""
    if notion is None or podcast_database_id is None or expression_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id
        expression_database_id = expression_database_id or config.expression_database_id

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={
            PODCAST_LIBRARY: podcast_database_id,
            EXPRESSION_DATABASE: expression_database_id,
        },
    )
    ensure_expression_database_schema(
        notion,
        expression_database_id,
        podcast_database_id,
    )
    expected_items = deduplicate_expected_expression_items(
        payload.analysis.all_learning_items()
    )

    existing_page = find_existing_complete_podcast_page(
        notion=notion,
        podcast_database_id=podcast_database_id,
        payload=payload,
    )
    if existing_page:
        podcast_page_id = str(existing_page.get("id", "")).strip()
        if not podcast_page_id:
            raise LearningPublisherError(
                "Notion existing Podcast Library result did not include a page ID."
            )
        podcast_page_url = existing_page.get("url")
        update_complete_podcast_page_properties(
            notion=notion,
            page_id=podcast_page_id,
            payload=payload,
        )
        logger.info("Updated an existing Podcast Library page.")
    else:
        podcast_page_id, podcast_page_url = create_complete_podcast_learning_page(
            notion=notion,
            podcast_database_id=podcast_database_id,
            payload=payload,
        )

    expression_page_ids = reconcile_expression_pages(
        notion=notion,
        expression_database_id=expression_database_id,
        podcast_page_id=podcast_page_id,
        items=expected_items,
    )

    return LearningPublishResult(
        podcast_page_id=podcast_page_id,
        expression_page_ids=expression_page_ids,
        podcast_page_url=(
            str(podcast_page_url) if podcast_page_url is not None else None
        ),
    )


def publish_learning_materials(
    payload: LearningPublishPayload,
    notion: Optional[Client] = None,
    expression_database_id: Optional[str] = None,
    podcast_database_id: Optional[str] = None,
) -> LearningPublishResult:
    """Publish AI learning analysis to an existing Podcast Library page."""
    if (
        notion is None
        or expression_database_id is None
        or podcast_database_id is None
    ):
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        expression_database_id = expression_database_id or config.expression_database_id
        podcast_database_id = podcast_database_id or config.podcast_database_id

    ensure_notion_target_binding_for_write(
        notion,
        configured_role_ids={
            PODCAST_LIBRARY: podcast_database_id,
            EXPRESSION_DATABASE: expression_database_id,
        },
    )
    ensure_expression_database_schema(
        notion,
        expression_database_id,
        podcast_database_id,
    )
    expected_items = deduplicate_expected_expression_items(
        payload.analysis.all_learning_items()
    )

    update_podcast_learning_page(
        notion=notion,
        podcast_page_id=payload.podcast_page_id,
        analysis=payload.analysis,
        transcript=payload.transcript,
    )

    expression_page_ids = reconcile_expression_pages(
        notion=notion,
        expression_database_id=expression_database_id,
        podcast_page_id=payload.podcast_page_id,
        items=expected_items,
    )

    return LearningPublishResult(
        podcast_page_id=payload.podcast_page_id,
        expression_page_ids=expression_page_ids,
    )
