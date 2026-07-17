"""Low-level Notion uploader for transcript-only Podcast Library pages.

The complete learning publisher lives in ``src.notion.learning_publisher``.
This module is kept for shared helpers and transcript-only publishing tests. It
does not write Expression Database entries, transcript highlights, or Weekly
Review records.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple, Union

from notion_client import APIResponseError, Client

from src.notion.config import load_dotenv


LOGGER = logging.getLogger(__name__)

NOTION_TOKEN_ENV = "NOTION_TOKEN"
PODCAST_DATABASE_ID_ENV = "PODCAST_DATABASE_ID"
LEGACY_PODCAST_DATABASE_ID_ENV = "NOTION_PODCAST_LIBRARY_DATABASE_ID"
MAX_RICH_TEXT_LENGTH = 1900


class NotionUploadError(RuntimeError):
    """Raised when a Podcast Library page cannot be created."""


@dataclass(frozen=True)
class PodcastUploadPayload:
    """Input required to create a transcript-only Podcast Library page."""

    title: str
    source_url: Optional[str]
    source_type: str
    transcript: Union[str, Mapping[str, Any]]
    processed_date: str = field(default_factory=lambda: date.today().isoformat())


@dataclass(frozen=True)
class PodcastUploadResult:
    """Result returned after creating a Notion podcast page."""

    page_id: str
    url: Optional[str] = None


def require_value(value: Optional[str], name: str, help_text: str) -> str:
    if value and value.strip():
        return value.strip()
    raise NotionUploadError(f"Missing required environment variable {name}. {help_text}")


def load_notion_upload_config(env: Optional[Mapping[str, str]] = None) -> Tuple[str, str]:
    """Load NOTION_TOKEN and Podcast Library database ID for this uploader."""
    if env is None:
        load_dotenv(Path(".env"))
        env = os.environ

    token = require_value(
        env.get(NOTION_TOKEN_ENV),
        NOTION_TOKEN_ENV,
        "Create a Notion integration token and add it to .env.",
    )
    podcast_database_id = (
        env.get(PODCAST_DATABASE_ID_ENV)
        or env.get(LEGACY_PODCAST_DATABASE_ID_ENV)
    )
    database_id = require_value(
        podcast_database_id,
        PODCAST_DATABASE_ID_ENV,
        "Set PODCAST_DATABASE_ID or NOTION_PODCAST_LIBRARY_DATABASE_ID in .env.",
    )
    return token, database_id


def create_notion_client(token: Optional[str] = None) -> Client:
    """Create the official Notion API SDK client."""
    notion_token = token or load_notion_upload_config()[0]
    return Client(auth=notion_token)


def title_property(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def url_property(url: Optional[str]) -> dict[str, Any]:
    return {"url": url}


def select_property(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def date_property(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def rich_text(content: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": content}}


def heading_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": [rich_text(text)]},
    }


def paragraph_block(text: str) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [rich_text(text)] if text else []},
    }


def chunk_text(text: str, chunk_size: int = MAX_RICH_TEXT_LENGTH) -> list[str]:
    """Split long transcript text into Notion-safe paragraph chunks."""
    normalized = text.strip()
    if not normalized:
        return [""]

    chunks: list[str] = []
    remaining = normalized
    while len(remaining) > chunk_size:
        split_at = remaining.rfind("\n", 0, chunk_size)
        if split_at <= 0:
            split_at = remaining.rfind(" ", 0, chunk_size)
        if split_at <= 0:
            split_at = chunk_size
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


def transcript_to_text(transcript: Union[str, Mapping[str, Any]]) -> str:
    """Normalize transcript string or transcript.json payload to plain text."""
    if isinstance(transcript, str):
        return transcript

    text = transcript.get("text")
    if isinstance(text, str):
        return text

    segments = transcript.get("segments")
    if isinstance(segments, list):
        return " ".join(
            str(segment.get("text", "")).strip()
            for segment in segments
            if isinstance(segment, Mapping)
        ).strip()

    raise NotionUploadError(
        "Transcript must be a string or a mapping with 'text' or 'segments'."
    )


def podcast_page_properties(payload: PodcastUploadPayload) -> dict[str, Any]:
    """Build transcript-only Podcast Library page properties."""
    return {
        "Title": title_property(payload.title),
        "URL": url_property(payload.source_url),
        "Source Type": select_property(payload.source_type),
        "Date": date_property(payload.processed_date),
    }


def podcast_page_children(transcript: Union[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Build Podcast Library page body containing only Transcript."""
    transcript_text = transcript_to_text(transcript)
    return [
        heading_block("Transcript"),
        *[paragraph_block(chunk) for chunk in chunk_text(transcript_text)],
    ]


def create_podcast_page(
    payload: PodcastUploadPayload,
    notion: Optional[Client] = None,
    podcast_database_id: Optional[str] = None,
) -> PodcastUploadResult:
    """Create one Podcast Library page and return its Notion page ID."""
    if not payload.title.strip():
        raise NotionUploadError("Podcast title is required.")
    if not payload.source_type.strip():
        raise NotionUploadError("Podcast source_type is required.")

    if notion is None or podcast_database_id is None:
        token, configured_database_id = load_notion_upload_config()
        notion = notion or create_notion_client(token)
        podcast_database_id = podcast_database_id or configured_database_id

    LOGGER.info("Creating Notion Podcast Library page: %s", payload.title)
    try:
        response = notion.pages.create(
            parent={"data_source_id": podcast_database_id},
            properties=podcast_page_properties(payload),
            children=podcast_page_children(payload.transcript),
        )
    except APIResponseError as exc:
        raise NotionUploadError(
            f"Notion API failed to create podcast page: {exc.code} {exc.message}"
        ) from exc
    except Exception as exc:
        raise NotionUploadError(f"Failed to create podcast page: {exc}") from exc

    page_id = response.get("id")
    if not page_id:
        raise NotionUploadError("Notion did not return a page ID.")

    return PodcastUploadResult(page_id=page_id, url=response.get("url"))
