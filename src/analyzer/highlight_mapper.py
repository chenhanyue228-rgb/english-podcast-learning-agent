"""Map extracted English expressions back into transcript rich text.

The mapper preserves the original transcript and returns Notion API compatible
rich text items. It uses phrase boundary checks to avoid accidental substring
matches such as highlighting "own" inside "ownership".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence, TypedDict


DEFAULT_COLOR_BY_TYPE = {
    "Native Expression": "green",
    "Business Phrase": "blue",
    "Business Expression": "blue",
    "Industry Term": "yellow",
    "Collocation": "green",
    "Sentence Pattern": "green",
}

NOTION_RICH_TEXT_CONTENT_LIMIT = 2000


class ExtractedExpression(TypedDict, total=False):
    """Expression data produced by the learning analyzer."""

    text: str
    type: str
    color: str


@dataclass(frozen=True)
class HighlightSpan:
    """A selected highlight location in the transcript."""

    start: int
    end: int
    color: str
    expression: str


def normalize_notion_color(color: str) -> str:
    """Convert a simple color name to a Notion background color."""
    normalized = color.strip().lower()
    if normalized.endswith("_background"):
        return normalized
    return f"{normalized}_background"


def resolve_expression_color(expression: Mapping[str, str]) -> str:
    """Return the Notion annotation color for an extracted expression."""
    if expression.get("color"):
        return normalize_notion_color(expression["color"])

    expression_type = expression.get("type", "")
    return normalize_notion_color(DEFAULT_COLOR_BY_TYPE.get(expression_type, "default"))


def is_word_character(character: str) -> bool:
    return character.isalnum() or character == "_"


def has_phrase_boundaries(transcript: str, start: int, end: int) -> bool:
    """Check that a match is not embedded inside a larger word."""
    before = transcript[start - 1] if start > 0 else ""
    after = transcript[end] if end < len(transcript) else ""

    starts_inside_word = bool(before and is_word_character(before))
    ends_inside_word = bool(after and is_word_character(after))

    return not starts_inside_word and not ends_inside_word


def find_phrase_spans(
    transcript: str,
    expression: Mapping[str, str],
) -> list[HighlightSpan]:
    """Find all boundary-safe occurrences of one expression in a transcript."""
    phrase = expression.get("text", "").strip()
    if not phrase:
        return []

    transcript_lower = transcript.lower()
    phrase_lower = phrase.lower()
    color = resolve_expression_color(expression)
    spans: list[HighlightSpan] = []

    search_from = 0
    while search_from < len(transcript):
        start = transcript_lower.find(phrase_lower, search_from)
        if start == -1:
            break

        end = start + len(phrase)
        if has_phrase_boundaries(transcript, start, end):
            spans.append(
                HighlightSpan(
                    start=start,
                    end=end,
                    color=color,
                    expression=transcript[start:end],
                )
            )

        search_from = start + 1

    return spans


def select_non_overlapping_spans(spans: Sequence[HighlightSpan]) -> list[HighlightSpan]:
    """Choose deterministic, non-overlapping spans.

    Longer phrases win over shorter phrases when candidates overlap. Earlier
    phrases win when length is the same.
    """
    sorted_spans = sorted(spans, key=lambda span: (-(span.end - span.start), span.start))
    selected: list[HighlightSpan] = []

    for candidate in sorted_spans:
        overlaps_existing = any(
            candidate.start < existing.end and existing.start < candidate.end
            for existing in selected
        )
        if not overlaps_existing:
            selected.append(candidate)

    return sorted(selected, key=lambda span: span.start)


def plain_rich_text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": {"content": text}}


def highlighted_rich_text(text: str, color: str) -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": text},
        "annotations": {"color": color, "bold": True},
    }


def map_highlights_to_rich_text(
    transcript: str,
    expressions: Sequence[Mapping[str, str]],
) -> list[dict[str, Any]]:
    """Return Notion-compatible rich text items with highlighted expressions."""
    if not transcript:
        return []

    candidate_spans = [
        span
        for expression in expressions
        for span in find_phrase_spans(transcript, expression)
    ]
    selected_spans = select_non_overlapping_spans(candidate_spans)

    if not selected_spans:
        return [plain_rich_text(transcript)]

    rich_text: list[dict[str, Any]] = []
    cursor = 0

    for span in selected_spans:
        if cursor < span.start:
            rich_text.append(plain_rich_text(transcript[cursor : span.start]))

        rich_text.append(
            highlighted_rich_text(transcript[span.start : span.end], span.color)
        )
        cursor = span.end

    if cursor < len(transcript):
        rich_text.append(plain_rich_text(transcript[cursor:]))

    return rich_text


def map_highlights_for_paragraph(
    transcript: str,
    expressions: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    """Return a complete Notion paragraph block for highlighted transcript text."""
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": map_highlights_to_rich_text(transcript, expressions)},
    }


def split_rich_text_item(
    item: Mapping[str, Any],
    max_content_length: int = NOTION_RICH_TEXT_CONTENT_LIMIT,
) -> list[dict[str, Any]]:
    """Split one Notion rich text item while preserving annotations."""
    content = item.get("text", {}).get("content", "")
    if len(content) <= max_content_length:
        return [dict(item)]

    split_items: list[dict[str, Any]] = []
    for start in range(0, len(content), max_content_length):
        cloned_item = dict(item)
        cloned_text = dict(item.get("text", {}))
        cloned_text["content"] = content[start : start + max_content_length]
        cloned_item["text"] = cloned_text
        split_items.append(cloned_item)
    return split_items


def map_highlights_to_paragraph_blocks(
    transcript: str,
    expressions: Sequence[Mapping[str, str]],
    max_content_length: int = NOTION_RICH_TEXT_CONTENT_LIMIT,
) -> list[dict[str, Any]]:
    """Return one or more Notion paragraph blocks for long highlighted text."""
    rich_text_items = [
        split_item
        for item in map_highlights_to_rich_text(transcript, expressions)
        for split_item in split_rich_text_item(item, max_content_length)
    ]
    if not rich_text_items:
        return []

    paragraphs: list[dict[str, Any]] = []
    current_items: list[dict[str, Any]] = []
    current_length = 0

    for item in rich_text_items:
        content_length = len(item.get("text", {}).get("content", ""))
        if current_items and current_length + content_length > max_content_length:
            paragraphs.append(
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {"rich_text": current_items},
                }
            )
            current_items = []
            current_length = 0

        current_items.append(item)
        current_length += content_length

    if current_items:
        paragraphs.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": current_items},
            }
        )

    return paragraphs
