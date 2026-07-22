"""Normalize Notion comment payloads into a single comment event shape."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class NormalizedCommentEvent:
    page_id: str
    block_id: str
    comment_id: str
    discussion_id: str
    comment_text: str
    highlighted_text: str
    source_structure: str
    created_time: str
    raw_comment: Mapping[str, Any]
    raw_discussion: Mapping[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        payload = dict(self.raw_comment)
        if self.raw_discussion:
            payload["discussion"] = dict(self.raw_discussion)

        if self.comment_id:
            payload.setdefault("id", self.comment_id)
        if self.created_time:
            payload.setdefault("created_time", self.created_time)
        if self.discussion_id and "discussion_id" not in payload:
            payload["discussion_id"] = self.discussion_id
        if self.highlighted_text:
            payload.setdefault("highlighted_text", self.highlighted_text)
            payload.setdefault("anchor_text", self.highlighted_text)
        if self.comment_text:
            payload.setdefault(
                "text",
                {"content": self.comment_text},
            )
            payload.setdefault(
                "rich_text",
                [
                    {
                        "plain_text": self.comment_text,
                        "text": {"content": self.comment_text},
                    }
                ],
            )
        payload.setdefault("page_id", self.page_id)
        payload.setdefault("block_id", self.block_id)
        payload.setdefault("source_structure", self.source_structure)
        return payload


def _extract_text(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, Mapping):
        for key in ("content", "plain_text", "text"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
        text_value = value.get("text")
        if isinstance(text_value, Mapping):
            return _extract_text(text_value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        parts: list[str] = []
        for item in value:
            if isinstance(item, Mapping):
                text_value = item.get("plain_text")
                if isinstance(text_value, str) and text_value.strip():
                    parts.append(text_value.strip())
                    continue
                nested_text = item.get("text")
                if isinstance(nested_text, Mapping):
                    content = nested_text.get("content")
                    if isinstance(content, str) and content.strip():
                        parts.append(content.strip())
        joined = " ".join(parts).strip()
        if joined:
            return joined
    return ""


def _extract_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _extract_comment_text(comment: Mapping[str, Any]) -> str:
    text = _extract_text(comment.get("rich_text"))
    if text:
        return text
    text = _extract_text(comment.get("text"))
    if text:
        return text
    text = _extract_text(comment.get("content"))
    if text:
        return text
    discussion = comment.get("discussion")
    if isinstance(discussion, Mapping):
        comments = discussion.get("comments")
        if isinstance(comments, Sequence) and not isinstance(comments, (str, bytes)):
            for discussion_comment in comments:
                if not isinstance(discussion_comment, Mapping):
                    continue
                nested_text = _extract_text(discussion_comment.get("rich_text"))
                if nested_text:
                    return nested_text
                nested_text = _extract_text(discussion_comment.get("text"))
                if nested_text:
                    return nested_text
    return ""


def _extract_discussion_id(comment: Mapping[str, Any]) -> str:
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


def _extract_highlighted_text(comment: Mapping[str, Any]) -> str:
    discussion = comment.get("discussion")
    if isinstance(discussion, Mapping):
        value = discussion.get("rangeText")
        if isinstance(value, str) and value.strip():
            return value.strip()
    for key in ("highlighted_text", "selected_text", "selection", "target_text", "anchor_text", "anchor"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_created_time(comment: Mapping[str, Any]) -> str:
    value = comment.get("created_time")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _source_structure(comment: Mapping[str, Any]) -> str:
    if isinstance(comment.get("discussion"), Mapping):
        return "discussion"
    if isinstance(comment.get("rich_text"), Sequence) and not isinstance(comment.get("rich_text"), (str, bytes)):
        return "rich_text"
    if isinstance(comment.get("text"), Mapping):
        return "text"
    return "unknown"


def normalize_comment_event(
    comment: Mapping[str, Any],
    page_id: str,
    block_id: str,
) -> list[NormalizedCommentEvent]:
    raw_comment = _extract_mapping(comment)
    if not raw_comment:
        return []

    discussion = _extract_mapping(raw_comment.get("discussion"))
    discussion_id = _extract_discussion_id(raw_comment)
    highlighted_text = _extract_highlighted_text(raw_comment)
    created_time = _extract_created_time(raw_comment)
    source_structure = _source_structure(raw_comment)
    has_direct_comment_text = bool(
        _extract_text(raw_comment.get("rich_text"))
        or _extract_text(raw_comment.get("text"))
        or _extract_text(raw_comment.get("content"))
    )

    comment_id = str(raw_comment.get("id", "")).strip()
    comment_text = _extract_comment_text(raw_comment)

    if discussion and not has_direct_comment_text:
        nested_comments = discussion.get("comments")
        if isinstance(nested_comments, Sequence) and not isinstance(nested_comments, (str, bytes)):
            events: list[NormalizedCommentEvent] = []
            for nested_comment in nested_comments:
                if not isinstance(nested_comment, Mapping):
                    continue
                nested_raw = _extract_mapping(nested_comment)
                nested_comment_id = str(nested_raw.get("id", "")).strip()
                nested_comment_text = _extract_comment_text(nested_raw)
                if not nested_comment_text:
                    continue
                nested_event = NormalizedCommentEvent(
                    page_id=page_id,
                    block_id=block_id,
                    comment_id=nested_comment_id or comment_id,
                    discussion_id=discussion_id,
                    comment_text=nested_comment_text,
                    highlighted_text=highlighted_text,
                    source_structure="discussion",
                    created_time=_extract_created_time(nested_raw) or created_time,
                    raw_comment=nested_raw,
                    raw_discussion=discussion,
                )
                events.append(nested_event)
            if events:
                return events

    if not comment_text and discussion and isinstance(discussion.get("comments"), Sequence):
        for nested_comment in discussion.get("comments", []):
            if not isinstance(nested_comment, Mapping):
                continue
            nested_text = _extract_comment_text(nested_comment)
            if nested_text:
                comment_text = nested_text
                break

    if not comment_text:
        return []

    return [
        NormalizedCommentEvent(
            page_id=page_id,
            block_id=block_id,
            comment_id=comment_id,
            discussion_id=discussion_id,
            comment_text=comment_text,
            highlighted_text=highlighted_text,
            source_structure=source_structure,
            created_time=created_time,
            raw_comment=raw_comment,
            raw_discussion=discussion,
        )
    ]


def normalize_comment_events(
    comments: Sequence[Mapping[str, Any]],
    page_id: str,
    block_id: str,
) -> list[NormalizedCommentEvent]:
    events: list[NormalizedCommentEvent] = []
    for comment in comments:
        if not isinstance(comment, Mapping):
            continue
        events.extend(normalize_comment_event(comment, page_id=page_id, block_id=block_id))
    return events
