"""Sync manual vocabulary captures from Podcast Library comments.

Vocabulary Database is a vocabulary memory store only. This module reacts only
to explicit comment triggers on Podcast Library pages and does not consume
analysis JSON or weekly review outputs.
"""

from __future__ import annotations

import logging
import json
import re
from time import perf_counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import httpx
from notion_client import APIResponseError

from src.memory.vocabulary_capture import prepare_vocabulary_memory
from src.notion.config import load_notion_config
from src.notion.comment_sync_state import load_comment_state, save_comment_state
from src.notion.discussion_reader import normalize_comment_events
from src.notion.uploader import create_notion_client
from src.notion.vocabulary_publisher import (
    VocabularyPublisherError,
    upsert_vocabulary_page,
)


LOGGER = logging.getLogger(__name__)

VOCAB_TRIGGER_TEXT = "3"
TEXT_BLOCK_TYPES = {
    "paragraph",
    "heading_1",
    "heading_2",
    "heading_3",
    "bulleted_list_item",
    "numbered_list_item",
    "quote",
    "callout",
    "to_do",
    "toggle",
    "code",
}
NOTION_COMMENT_TIMEOUT = httpx.Timeout(
    connect=10.0,
    read=30.0,
    write=30.0,
    pool=10.0,
)


class CommentVocabSyncError(RuntimeError):
    """Raised when vocabulary comment sync cannot complete."""


@dataclass(frozen=True)
class VocabCommentRecord:
    page_id: str
    block_id: str
    comment_id: str
    comment_text: str
    highlighted_text: str
    context_text: str
    term: str


@dataclass(frozen=True)
class CommentVocabSyncResult:
    scanned_pages: int
    scanned_comments: int
    matched_comments: int
    created: int
    updated: int
    skipped: int
    previews: Optional[list[dict[str, str]]] = None


def _comment_parent_type(comment: Mapping[str, Any]) -> str:
    parent = comment.get("parent")
    if isinstance(parent, Mapping):
        value = parent.get("type")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _comment_parent_id(comment: Mapping[str, Any]) -> str:
    parent = comment.get("parent")
    if isinstance(parent, Mapping):
        for key in ("block_id", "page_id", "data_source_id"):
            value = parent.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    for key in ("block_id", "page_id", "parent_block_id"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _comment_discussion_id(comment: Mapping[str, Any]) -> str:
    discussion = comment.get("discussion")
    if isinstance(discussion, Mapping):
        for key in ("id", "discussion_id", "discussionId", "url"):
            value = discussion.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("discussion_id", "discussionId", "discussion_url", "discussionUrl"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _comment_created_time(comment: Mapping[str, Any]) -> str:
    value = comment.get("created_time")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _comment_discussion_range_text(comment: Mapping[str, Any]) -> str:
    discussion = comment.get("discussion")
    if isinstance(discussion, Mapping):
        value = discussion.get("rangeText")
        if isinstance(value, str) and value.strip():
            return value.strip()
    value = comment.get("rangeText")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _comment_source_structure(comment: Mapping[str, Any]) -> str:
    if isinstance(comment.get("discussion"), Mapping):
        return "discussion"
    if isinstance(comment.get("rich_text"), Sequence) and not isinstance(comment.get("rich_text"), (str, bytes)):
        return "rich_text"
    if isinstance(comment.get("text"), Mapping):
        return "text"
    return "unknown"


def _comment_rich_text_preview(comment: Mapping[str, Any]) -> str:
    rich_text = comment.get("rich_text")
    if isinstance(rich_text, Sequence) and not isinstance(rich_text, (str, bytes)):
        parts: list[str] = []
        for item in rich_text:
            if not isinstance(item, Mapping):
                continue
            plain_text = item.get("plain_text")
            if isinstance(plain_text, str) and plain_text.strip():
                parts.append(plain_text.strip())
                continue
            text_value = item.get("text")
            if isinstance(text_value, Mapping):
                content = text_value.get("content")
                if isinstance(content, str) and content.strip():
                    parts.append(content.strip())
        return " ".join(parts).strip()
    text_value = comment.get("text")
    if isinstance(text_value, Mapping):
        content = text_value.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _is_trigger_comment(comment_text: str) -> bool:
    return comment_text.strip() == VOCAB_TRIGGER_TEXT


def _normalize_comment_text(comment: Mapping[str, Any]) -> str:
    text = comment.get("rich_text")
    if isinstance(text, Sequence) and not isinstance(text, (str, bytes)):
        parts = []
        for item in text:
            if isinstance(item, Mapping):
                parts.append(
                    str(item.get("plain_text") or item.get("text", {}).get("content", "")).strip()
                )
        joined = " ".join(part for part in parts if part).strip()
        if joined:
            return joined

    if isinstance(comment.get("text"), Mapping):
        text_value = comment["text"].get("content")
        if text_value:
            return str(text_value).strip()

    return str(comment.get("content", "")).strip()


def _extract_text_from_mapping(mapping: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, Mapping):
            text_value = value.get("content") or value.get("plain_text")
            if isinstance(text_value, str) and text_value.strip():
                return text_value.strip()
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
            parts: list[str] = []
            for item in value:
                if isinstance(item, Mapping):
                    plain_text = item.get("plain_text")
                    if isinstance(plain_text, str) and plain_text.strip():
                        parts.append(plain_text.strip())
                        continue
                    text_value = item.get("text")
                    if isinstance(text_value, Mapping):
                        content = text_value.get("content")
                        if isinstance(content, str) and content.strip():
                            parts.append(content.strip())
            joined = " ".join(parts).strip()
            if joined:
                return joined
    return ""


def _extract_context_from_comment(comment: Mapping[str, Any]) -> str:
    context = _extract_text_from_mapping(
        comment,
        (
            "context",
            "original_context",
            "source_text",
            "quoted_text",
            "reference_text",
            "referenced_text",
        ),
    )
    if context:
        return context

    rich_text = comment.get("rich_text")
    if isinstance(rich_text, Sequence) and not isinstance(rich_text, (str, bytes)):
        parts = []
        for item in rich_text:
            if isinstance(item, Mapping):
                text_value = item.get("plain_text") or item.get("text", {}).get("content", "")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
        joined = " ".join(parts).strip()
        if joined:
            return joined
    return ""


def _extract_highlighted_text_from_comment(comment: Mapping[str, Any]) -> str:
    highlighted = _extract_text_from_mapping(
        comment,
        (
            "highlighted_text",
            "selected_text",
            "selection",
            "target_text",
            "anchor_text",
            "anchor",
            "quote",
            "quoted_text",
            "referenced_text",
            "reference_text",
        ),
    )
    if highlighted:
        return highlighted

    rich_text = comment.get("rich_text")
    if isinstance(rich_text, Sequence) and not isinstance(rich_text, (str, bytes)):
        parts: list[str] = []
        for item in rich_text:
            if not isinstance(item, Mapping):
                continue
            annotations = item.get("annotations")
            if not isinstance(annotations, Mapping):
                continue
            is_highlighted = any(
                bool(annotations.get(flag))
                for flag in ("bold", "italic", "underline", "strikethrough", "code")
            ) or (
                isinstance(annotations.get("color"), str)
                and str(annotations.get("color")).strip().lower() not in {"", "default"}
            )
            if is_highlighted:
                text_value = str(
                    item.get("plain_text")
                    or item.get("text", {}).get("content", "")
                ).strip()
                if text_value:
                    parts.append(text_value)
        joined = " ".join(parts).strip()
        if joined:
            return joined
    return ""


def _normalize_vocab_candidate(text: str) -> str:
    cleaned = re.sub(r"[\u2018\u2019\u201c\u201d\"'.,;:!?()\[\]{}<>]", "", text).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        return ""

    parts = cleaned.split(" ")
    if not parts:
        return ""

    last = parts[-1]
    lower = last.lower()
    normalized_last = last
    if lower.endswith("ies") and len(lower) > 4:
        normalized_last = last[:-3] + "y"
    elif lower.endswith("s") and len(lower) > 3 and not lower.endswith(("ss", "us", "is")):
        normalized_last = last[:-1]
    parts[-1] = normalized_last
    return " ".join(parts).strip().lower()


def fetch_podcast_library_pages(notion: Any, podcast_database_id: str) -> list[Mapping[str, Any]]:
    request_started_at = perf_counter()
    try:
        if hasattr(notion, "data_sources") and hasattr(notion.data_sources, "query"):
            response = notion.data_sources.query(
                data_source_id=podcast_database_id,
                page_size=100,
            )
        else:
            response = notion.databases.query(
                database_id=podcast_database_id,
                page_size=100,
            )
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
        elapsed = perf_counter() - request_started_at
        _log_notion_request_failed("pages.query", exc, elapsed)
        raise CommentVocabSyncError(f"Failed to fetch Podcast Library pages: {exc}") from exc
    except Exception as exc:
        elapsed = perf_counter() - request_started_at
        if isinstance(exc, (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout)):
            _log_notion_request_failed("pages.query", exc, elapsed)
        raise CommentVocabSyncError(f"Failed to fetch Podcast Library pages: {exc}") from exc
    duration = perf_counter() - request_started_at
    print(f"GET /pages query_duration: {duration:.3f} seconds")
    if duration > 3:
        print(f"SLOW REQUEST\nendpoint: pages.query\nduration: {duration:.3f} seconds")

    results = response.get("results", [])
    pages = [page for page in results if isinstance(page, Mapping)]
    pages.sort(
        key=lambda page: (
            str(page.get("last_edited_time") or page.get("created_time") or ""),
            str(page.get("id") or ""),
        ),
        reverse=True,
    )
    return pages


def _collect_direct_block_entries(notion: Any, page_id: str) -> list[Mapping[str, Any]]:
    try:
        response = notion.blocks.children.list(block_id=page_id, page_size=100)
    except Exception:
        return []
    results = response.get("results", [])
    if not isinstance(results, list):
        return []
    entries: list[Mapping[str, Any]] = []
    for child in results:
        if isinstance(child, Mapping):
            entries.append(child)
    return entries


def _is_text_block(block: Mapping[str, Any]) -> bool:
    block_type = str(block.get("type", "")).strip().lower()
    return block_type in TEXT_BLOCK_TYPES


def _iter_page_block_ids(
    notion: Any,
    page_id: str,
    block_limit: int = 20,
    include_root_block: bool = False,
) -> list[str]:
    block_ids: list[str] = []
    for block in _collect_direct_block_entries(notion, page_id):
        if not _is_text_block(block):
            continue
        block_id = str(block.get("id", "")).strip()
        if block_id:
            block_ids.append(block_id)
    if include_root_block:
        block_ids = [page_id] + block_ids
    return block_ids[: max(block_limit, 0)]


def _limit_pages_for_debug(pages: list[Mapping[str, Any]], page_limit: int = 3) -> list[Mapping[str, Any]]:
    if page_limit <= 0:
        return []
    return pages[:page_limit]


def _log_vocab_comment_skip(
    comment_id: str,
    comment_text: str,
    block_id: str,
    highlighted_text: str,
    skip_reason: str,
) -> None:
    message = (
        "SKIPPED VOCAB COMMENT\n"
        "- comment_id: %s\n"
        "- block_id: %s\n"
        "- comment_text: %s\n"
        "- extracted_highlighted_text: %s\n"
        "- reason: %s"
    )
    values = (comment_id, block_id, comment_text, highlighted_text or "", skip_reason)
    LOGGER.info(message, *values)
    print(
        "SKIPPED VOCAB COMMENT\n"
        f"- comment_id: {comment_id}\n"
        f"- block_id: {block_id}\n"
        f"- comment_text: {comment_text}\n"
        f"- extracted_highlighted_text: {highlighted_text or ''}\n"
        f"- reason: {skip_reason}"
    )


def _log_notion_request_failed(endpoint: str, error: Exception, elapsed: float) -> None:
    print(
        "NOTION REQUEST FAILED\n"
        f"endpoint: {endpoint}\n"
        f"error: {error}\n"
        f"elapsed: {elapsed:.3f}"
    )


def fetch_page_comments_raw(block_id: str, page_id: str = "", debug: bool = False) -> list[Mapping[str, Any]]:
    config = load_notion_config()
    url = "https://api.notion.com/v1/comments"
    headers = {
        "Authorization": f"Bearer {config.token}",
        "Notion-Version": "2022-06-28",
        "Accept": "application/json",
    }
    try:
        request_started_at = perf_counter()
        with httpx.Client(timeout=NOTION_COMMENT_TIMEOUT) as client:
            response = client.get(
                url,
                headers=headers,
                params={"block_id": block_id},
            )
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
        elapsed = perf_counter() - request_started_at
        print(
            "NOTION COMMENT REQUEST FAILED\n"
            f"block_id: {block_id}\n"
            f"endpoint: comments?block_id={block_id}\n"
            f"error: {exc}\n"
            f"elapsed: {elapsed:.3f}"
        )
        raise CommentVocabSyncError(f"Failed to fetch comments for block {block_id}: {exc}") from exc
    except Exception as exc:
        raise CommentVocabSyncError(f"Failed to fetch comments for block {block_id}: {exc}") from exc
    duration = perf_counter() - request_started_at
    print(f"GET /comments block_id={block_id} duration: {duration:.3f} seconds")
    if duration > 3:
        print(f"SLOW REQUEST\nendpoint: comments\nblock_id: {block_id}\nduration: {duration:.3f} seconds")

    if response.status_code >= 400:
        raise CommentVocabSyncError(
            f"Failed to fetch comments for block {block_id}: HTTP {response.status_code} {response.text[:200]}"
        )

    payload = response.json()
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    normalized_comments: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, Mapping):
            continue
        discussion = item.get("discussion")
        if isinstance(discussion, Mapping):
            range_text = discussion.get("rangeText")
            comments = discussion.get("comments")
            if isinstance(comments, Sequence) and not isinstance(comments, (str, bytes)):
                for discussion_comment in comments:
                    if not isinstance(discussion_comment, Mapping):
                        continue
                    normalized_comment = dict(discussion_comment)
                    text_value = normalized_comment.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        normalized_comment["text"] = {"content": text_value.strip()}
                        normalized_comment.setdefault(
                            "rich_text",
                            [
                                {
                                    "plain_text": text_value.strip(),
                                    "text": {"content": text_value.strip()},
                                }
                            ],
                        )
                    if isinstance(range_text, str) and range_text.strip():
                        normalized_comment.setdefault("highlighted_text", range_text.strip())
                        normalized_comment.setdefault("anchor_text", range_text.strip())
                    normalized_comment.setdefault("discussion", discussion)
                    normalized_comments.append(normalized_comment)
                continue
        normalized_comments.append(dict(item))
    if debug and normalized_comments:
        for comment in normalized_comments:
            comment_id = str(comment.get("id", "")).strip()
            comment_text = _normalize_comment_text(comment)
            discussion_id = _comment_discussion_id(comment)
            range_text = _comment_discussion_range_text(comment)
            print("DEBUG COMMENT SUMMARY")
            print(f"page_id: {page_id}")
            print(f"block_id: {block_id}")
            print(f"comment_id: {comment_id}")
            print(f"comment_text: {comment_text}")
            print(f"discussion_id: {discussion_id}")
            print(f"rangeText: {range_text}")
            print(f"source_structure: {_comment_source_structure(comment)}")
            print(f"comment_keys: {sorted(comment.keys())}")
            print(f"comment_rich_text: {_comment_rich_text_preview(comment)}")
            discussion = comment.get("discussion")
            if isinstance(discussion, Mapping):
                print(f"discussion_info: {json.dumps(discussion, ensure_ascii=False)}")
            else:
                print("discussion_info: {}")
            if comment_text == VOCAB_TRIGGER_TEXT:
                print("DEBUG TRIGGER COMMENT FOUND")
                print(f"comment_id: {comment_id}")
                print(f"block_id: {block_id}")
                print("original comment data source: fetch_page_comments_raw")
    if normalized_comments:
        print("DEBUG FIRST COMMENT JSON:")
        print(json.dumps(normalized_comments[0], indent=2, ensure_ascii=False))
    return normalized_comments


def debug_comment_sync(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    page_limit: int = 3,
    block_limit: int = 20,
) -> int:
    if notion is None or podcast_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id

    assert notion is not None
    assert podcast_database_id is not None

    pages = _limit_pages_for_debug(fetch_podcast_library_pages(notion, podcast_database_id), page_limit=page_limit)
    if not pages:
        return 0
    debug_count = 0
    for page_index, page in enumerate(pages, start=1):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        print(f"Scanning pages: {page_index}/{len(pages)}")
        block_ids = _iter_page_block_ids(notion, page_id, block_limit=block_limit)
        for block_index, block_id in enumerate(block_ids, start=1):
            print(f"Scanning blocks: {block_index}/{block_limit}")
            comments = fetch_page_comments_raw(block_id)
            for comment in comments:
                comment_id = str(comment.get("id", "")).strip()
                comment_text = _normalize_comment_text(comment)
                parent_type = _comment_parent_type(comment)
                parent_id = _comment_parent_id(comment)
                highlighted_text = _extract_highlighted_text_from_comment(comment)
                print(f"Page: {page_id}")
                print(f"Block: {block_id}")
                print(f"Comment ID: {comment_id}")
                print(f"Comment text: {comment_text}")
                print(f"Parent type: {parent_type}")
                print(f"Parent ID: {parent_id}")
                print(f"Highlighted text: {highlighted_text}")
                debug_count += 1
        break
    return debug_count


def debug_page_comments(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    page_limit: int = 3,
    block_limit: int = 20,
) -> int:
    if notion is None or podcast_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id

    assert notion is not None
    assert podcast_database_id is not None

    pages = _limit_pages_for_debug(fetch_podcast_library_pages(notion, podcast_database_id), page_limit=page_limit)
    if not pages:
        return 0
    debug_count = 0
    for page_index, page in enumerate(pages, start=1):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        print(f"Scanning pages: {page_index}/{len(pages)}")
        block_ids = _iter_page_block_ids(notion, page_id, block_limit=block_limit)
        for block_index, block_id in enumerate(block_ids, start=1):
            print(f"Scanning blocks: {block_index}/{block_limit}")
            comments = fetch_page_comments_raw(block_id)
            for comment in comments:
                if not isinstance(comment, Mapping):
                    continue
                comment_id = str(comment.get("id", "")).strip()
                parent = comment.get("parent")
                parent_value = ""
                if isinstance(parent, Mapping):
                    parent_value = str(parent.get("type", "")).strip()
                rich_text = comment.get("rich_text", [])
                created_time = str(comment.get("created_time", "")).strip()
                print(f"page_id={page_id}")
                print(f"block_id={block_id}")
                print(f"comment_id={comment_id}")
                print(f"parent={parent_value}")
                print(f"rich_text={rich_text}")
                print(f"created_time={created_time}")
                debug_count += 1
        break
    return debug_count


def debug_comment_sources(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    page_limit: int = 3,
    block_limit: int = 20,
) -> int:
    if notion is None or podcast_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id

    assert notion is not None
    assert podcast_database_id is not None

    pages = _limit_pages_for_debug(fetch_podcast_library_pages(notion, podcast_database_id), page_limit=page_limit)
    if not pages:
        return 0
    debug_count = 0
    for page_index, page in enumerate(pages, start=1):
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        print(f"Scanning pages: {page_index}/{len(pages)}")
        block_ids = _iter_page_block_ids(notion, page_id, block_limit=block_limit)
        for block_index, block_id in enumerate(block_ids, start=1):
            print(f"Scanning blocks: {block_index}/{block_limit}")
            comments = fetch_page_comments_raw(block_id, page_id=page_id, debug=True)
            for comment in comments:
                if not isinstance(comment, Mapping):
                    continue
                comment_id = str(comment.get("id", "")).strip()
                comment_text = _normalize_comment_text(comment)
                discussion_id = _comment_discussion_id(comment)
                range_text = _comment_discussion_range_text(comment)
                source_structure = _comment_source_structure(comment)
                print(f"page_id: {page_id}")
                print(f"block_id: {block_id}")
                print(f"comment_id: {comment_id}")
                print(f"comment_text: {comment_text}")
                print(f"discussion_id: {discussion_id}")
                print(f"rangeText: {range_text}")
                print(f"source_structure: {source_structure}")
                debug_count += 1
        break
    return debug_count


def _iter_vocab_comment_records(
    page_id: str,
    block_id: str,
    comments: Iterable[Mapping[str, Any]],
) -> list[VocabCommentRecord]:
    records: list[VocabCommentRecord] = []
    for comment in comments:
        comment_id = str(comment.get("id", "")).strip()
        comment_text = _normalize_comment_text(comment)
        discussion_id = _comment_discussion_id(comment)
        highlighted_text = _extract_highlighted_text_from_comment(comment)
        anchor_text = _extract_text_from_mapping(
            comment,
            (
                "anchor_text",
                "anchor",
                "selected_text",
                "selection",
                "target_text",
                "quote",
                "quoted_text",
                "referenced_text",
                "reference_text",
            ),
        )
        source_structure = _comment_source_structure(comment)
        print(
            "DEBUG COMMENT PARSER ENTRY\n"
            f"comment_id: {comment_id}\n"
            f"comment_text: {comment_text}\n"
            f"discussion_id: {discussion_id}\n"
            f"highlighted_text: {highlighted_text}\n"
            f"anchor_text: {anchor_text}\n"
            f"source_structure: {source_structure}"
        )
        if not comment_text:
            discussion = comment.get("discussion")
            if isinstance(discussion, Mapping):
                discussion_comments = discussion.get("comments")
                if isinstance(discussion_comments, Sequence) and not isinstance(
                    discussion_comments, (str, bytes)
                ):
                    for discussion_comment in discussion_comments:
                        if not isinstance(discussion_comment, Mapping):
                            continue
                        nested_text = _normalize_comment_text(discussion_comment)
                        if not nested_text:
                            text_value = discussion_comment.get("text")
                            if isinstance(text_value, str) and text_value.strip():
                                nested_text = text_value.strip()
                        if nested_text:
                            comment_text = nested_text
                            break
        print(f"DEBUG BEFORE TRIGGER: {comment_text}")
        trigger_matched = _is_trigger_comment(comment_text)
        print(f"DEBUG TRIGGER MATCHED: {trigger_matched}")
        if not trigger_matched:
            continue
        if not highlighted_text:
            discussion = comment.get("discussion")
            if isinstance(discussion, Mapping):
                range_text = discussion.get("rangeText")
                if isinstance(range_text, str) and range_text.strip():
                    highlighted_text = range_text.strip()
        parent_id = _comment_parent_id(comment)
        candidate_block_id = parent_id or block_id
        if not candidate_block_id:
            candidate_block_id = block_id
        print(
            f"page_id={page_id} block_id={candidate_block_id} comment_id={comment_id} comment_text={comment_text} highlighted_text={highlighted_text or ''}"
        )
        if not highlighted_text:
            LOGGER.warning("vocab comment found but highlight unavailable")
            _log_vocab_comment_skip(
                comment_id=comment_id,
                comment_text=comment_text,
                block_id=candidate_block_id,
                highlighted_text="",
                skip_reason="highlight unavailable",
            )
            continue
        context_text = _extract_context_from_comment(comment)
        term = _normalize_vocab_candidate(highlighted_text)
        if not term:
            LOGGER.warning(
                "vocab comment found but highlighted text could not be normalized: page_id=%s comment_id=%s",
                page_id,
                comment_id,
            )
            _log_vocab_comment_skip(
                comment_id=comment_id,
                comment_text=comment_text,
                block_id=candidate_block_id,
                highlighted_text=highlighted_text,
                skip_reason="empty extracted word",
            )
            continue
        records.append(
            VocabCommentRecord(
                page_id=page_id,
                block_id=candidate_block_id,
                comment_id=comment_id,
                comment_text=comment_text,
                highlighted_text=highlighted_text,
                context_text=context_text or highlighted_text,
                term=term,
            )
        )
    return records


def _build_vocabulary_payload(
    record: VocabCommentRecord,
    page: Mapping[str, Any],
) -> dict[str, str]:
    return prepare_vocabulary_memory(
        highlighted_text=record.term,
        comment_text=record.comment_text,
        context=record.context_text,
        source="Podcast Library",
        page_id=record.page_id,
        meaning="",
        professional_category="",
        usage_example="",
        personal_note="",
    )


def sync_vocab_comments(
    notion: Any = None,
    podcast_database_id: Optional[str] = None,
    vocabulary_database_id: Optional[str] = None,
    dry_run: bool = False,
) -> CommentVocabSyncResult:
    sync_started_at = perf_counter()
    print("[SYNCH START]")
    print("=== SYNC DEBUG ===")
    if notion is None or podcast_database_id is None or vocabulary_database_id is None:
        config = load_notion_config()
        notion = notion or create_notion_client(config.token)
        podcast_database_id = podcast_database_id or config.podcast_database_id
        vocabulary_database_id = vocabulary_database_id or config.vocabulary_database_id

    assert notion is not None
    assert podcast_database_id is not None
    assert vocabulary_database_id is not None

    comment_state = load_comment_state()
    processed_comment_ids = set(str(item).strip() for item in comment_state.get("processed_comment_ids", []))
    processed_discussion_ids = set(
        str(item).strip() for item in comment_state.get("processed_discussion_ids", [])
    )
    last_scan_time = str(comment_state.get("last_scan_time", "")).strip()
    next_comment_ids = set(processed_comment_ids)
    next_discussion_ids = set(processed_discussion_ids)

    query_started_at = perf_counter()
    pages = fetch_podcast_library_pages(notion, podcast_database_id)
    query_elapsed = perf_counter() - query_started_at
    print(f"1. query podcast pages:\n{query_elapsed:.3f} seconds")
    print("Stage 1:")
    print("Query pages:")
    print(f"{query_elapsed:.3f} seconds")
    print()
    print(f"Pages count:\n{len(pages)}")
    pages_scanned = 0
    blocks_scanned = 0
    scanned_comments = 0
    matched_comments = 0
    created = 0
    updated = 0
    skipped = 0
    previews: list[dict[str, str]] = []
    fetch_comments_elapsed = 0.0
    matched_trigger_comments = 0
    upsert_elapsed = 0.0
    block_upsert_index = 0
    any_failure = False
    latest_scan_time = last_scan_time

    for page in pages:
        page_id = str(page.get("id", "")).strip()
        if not page_id:
            continue
        pages_scanned += 1
        comments_started_at = perf_counter()
        direct_block_ids = _iter_page_block_ids(notion, page_id, block_limit=20)
        comments: list[Mapping[str, Any]] = []
        print("Stage 2:")
        print(f"Scan blocks:\n{pages_scanned}/{len(pages)}")
        for block_index, block_id in enumerate(direct_block_ids, start=1):
            print(f"Scanning block:\npage_id: {page_id}\nblock_id: {block_id}")
            block_request_started_at = perf_counter()
            comments.extend(fetch_page_comments_raw(block_id))
            block_request_elapsed = perf_counter() - block_request_started_at
            print(f"comment fetch time:\n{block_request_elapsed:.3f} seconds")
        blocks_scanned += len(direct_block_ids)
        fetch_comments_elapsed += perf_counter() - comments_started_at
        scanned_comments += len(comments)
        LOGGER.info("Comments found: %s", len(comments))
        normalized_events = normalize_comment_events(comments, page_id=page_id, block_id="")
        filtered_events: list[Mapping[str, Any]] = []
        for event in normalized_events:
            comment = event.to_mapping()
            comment_id = str(comment.get("id", "")).strip()
            discussion_id = _comment_discussion_id(comment)
            created_time = _comment_created_time(comment)
            if comment_id and comment_id in processed_comment_ids:
                skipped += 1
                continue
            if discussion_id and discussion_id in processed_discussion_ids:
                skipped += 1
                continue
            if last_scan_time and created_time and created_time <= last_scan_time:
                skipped += 1
                continue
            filtered_events.append(comment)
        vocab_records = _iter_vocab_comment_records(
            page_id,
            "",
            filtered_events,
        )
        matched_trigger_comments += len(vocab_records)
        matched_comments += len(vocab_records)
        print("Stage 3:")
        print(f"Matched comments:\n{len(vocab_records)}")

        for record_index, record in enumerate(vocab_records, start=1):
            payload = _build_vocabulary_payload(record, page)
            previews.append(
                {
                    "Name": payload["word"],
                    "Meaning": payload.get("meaning", ""),
                    "Category": payload.get("professional_category", ""),
                    "Source Page ID": payload.get("source_page_id", ""),
                }
            )
            if dry_run:
                created += 1
                continue
            try:
                block_upsert_index += 1
                print("Stage 4:")
                print(f"Vocabulary upsert:\n{block_upsert_index}/{max(len(vocab_records), 1)}")
                upsert_started_at = perf_counter()
                result = upsert_vocabulary_page(
                    payload,
                    notion=notion,
                    vocabulary_database_id=vocabulary_database_id,
                )
                upsert_elapsed += perf_counter() - upsert_started_at
            except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
                elapsed = perf_counter() - upsert_started_at
                _log_notion_request_failed("vocabulary.upsert", exc, elapsed)
                skipped += 1
                any_failure = True
                continue
            except (VocabularyPublisherError, APIResponseError, Exception) as exc:
                LOGGER.warning(
                    "Failed to sync vocab comment page_id=%s comment_id=%s: %s",
                    record.page_id,
                    record.comment_id,
                    exc,
                )
                skipped += 1
                any_failure = True
                continue

            if result.action == "updated":
                updated += 1
                _log_vocab_comment_skip(
                    comment_id=record.comment_id,
                    comment_text=record.comment_text,
                    block_id=record.block_id,
                    highlighted_text=record.highlighted_text,
                    skip_reason="existing vocabulary entry",
                )
                LOGGER.info("Vocabulary updated: %s", updated)
            else:
                created += 1
                LOGGER.info("Vocabulary created: %s", created)

            if record.comment_id:
                next_comment_ids.add(record.comment_id)
            discussion_id = _comment_discussion_id(
                next(
                    (
                        item
                        for item in filtered_events
                        if str(item.get("id", "")).strip() == record.comment_id
                    ),
                    {},
                )
            )
            if discussion_id:
                next_discussion_ids.add(discussion_id)
            created_time = _comment_created_time(
                next(
                    (
                        item
                        for item in filtered_events
                        if str(item.get("id", "")).strip() == record.comment_id
                    ),
                    {},
                )
            )
            if created_time and created_time > latest_scan_time:
                latest_scan_time = created_time

    print("Stage 5:")
    print(f"TOTAL TIME:\n{perf_counter() - sync_started_at:.3f} seconds")
    print(f"Pages scanned:\n{pages_scanned}")
    print(f"Blocks scanned:\n{blocks_scanned}")
    print(f"Comments fetched:\n{scanned_comments}")
    print(f"3. matched trigger comments:\n{matched_trigger_comments}")
    print(f"Trigger comments found:\n{matched_trigger_comments}")
    print(f"Highlighted words extracted:\n{matched_comments}")
    print(f"2. fetch comments:\n{fetch_comments_elapsed:.3f} seconds")
    print(f"4. vocabulary upsert:\n{upsert_elapsed:.3f} seconds")
    print(f"Vocabulary created:\n{created}")
    print(f"Vocabulary updated:\n{updated}")
    total_elapsed = perf_counter() - sync_started_at
    print(f"TOTAL TIME: {total_elapsed:.3f} seconds")

    if not any_failure:
        save_comment_state(
            {
                "processed_comment_ids": sorted(next_comment_ids),
                "processed_discussion_ids": sorted(next_discussion_ids),
                "last_scan_time": latest_scan_time,
            }
        )

    return CommentVocabSyncResult(
        scanned_pages=pages_scanned,
        scanned_comments=scanned_comments,
        matched_comments=matched_comments,
        created=created,
        updated=updated,
        skipped=skipped,
        previews=previews[:3],
    )


def sync_vocab_comments_from_workspace() -> CommentVocabSyncResult:
    return sync_vocab_comments()
