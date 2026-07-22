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
from src.notion.schema import COMMONNESS_LEVELS, category_color
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


def notion_database_properties(notion: Client, database_id: str) -> set[str]:
    """Return the available property names for a Notion database."""
    try:
        if hasattr(notion, "data_sources"):
            response = notion.data_sources.retrieve(data_source_id=database_id)
        else:
            response = notion.databases.retrieve(database_id=database_id)
    except APIResponseError as exc:
        logger.warning(
            "Could not inspect Notion database %s: %s",
            database_id,
            api_error_message(exc),
        )
        return set()
    except Exception as exc:
        logger.warning("Could not inspect Notion database %s: %s", database_id, exc)
        return set()

    return set(response.get("properties", {}).keys())


def ensure_expression_database_schema(notion: Client, expression_database_id: str) -> None:
    """Add the Commonness property to older Expression databases when missing."""
    if "Commonness" in notion_database_properties(notion, expression_database_id):
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
            logger.warning(
                "Notion client does not expose a database update API; "
                "skipping Commonness schema migration for %s",
                expression_database_id,
            )
            return
    except APIResponseError as exc:
        raise LearningPublisherError(
            f"Failed to update Expression Database schema: {api_error_message(exc)}"
        ) from exc
    except Exception as exc:
        raise LearningPublisherError(
            f"Failed to update Expression Database schema: {exc}"
        ) from exc

    logger.info(
        "Added missing Commonness property to Expression Database %s",
        expression_database_id,
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
        logger.info("Updated existing Podcast Library page: %s", podcast_page_id)
        return LearningPublishResult(
            podcast_page_id=podcast_page_id,
            expression_page_ids=[],
            podcast_page_url=(
                str(podcast_page_url) if podcast_page_url is not None else None
            ),
        )

    podcast_page_id, podcast_page_url = create_complete_podcast_learning_page(
        notion=notion,
        podcast_database_id=podcast_database_id,
        payload=payload,
    )

    ensure_expression_database_schema(notion, expression_database_id)

    expression_page_ids = [
        create_expression_page(
            notion=notion,
            expression_database_id=expression_database_id,
            podcast_page_id=podcast_page_id,
            item=item,
        )
        for item in payload.analysis.all_learning_items()
    ]

    return LearningPublishResult(
        podcast_page_id=podcast_page_id,
        expression_page_ids=expression_page_ids,
        podcast_page_url=podcast_page_url,
    )


def publish_learning_materials(
    payload: LearningPublishPayload,
    notion: Optional[Client] = None,
    expression_database_id: Optional[str] = None,
) -> LearningPublishResult:
    """Publish AI learning analysis to an existing Podcast Library page."""
    if notion is None or expression_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        expression_database_id = expression_database_id or config.expression_database_id

    update_podcast_learning_page(
        notion=notion,
        podcast_page_id=payload.podcast_page_id,
        analysis=payload.analysis,
        transcript=payload.transcript,
    )

    ensure_expression_database_schema(notion, expression_database_id)

    expression_page_ids = [
        create_expression_page(
            notion=notion,
            expression_database_id=expression_database_id,
            podcast_page_id=payload.podcast_page_id,
            item=item,
        )
        for item in payload.analysis.all_learning_items()
    ]

    return LearningPublishResult(
        podcast_page_id=payload.podcast_page_id,
        expression_page_ids=expression_page_ids,
    )
