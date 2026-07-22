"""Extract weekly learning data from Podcast Library pages."""

from __future__ import annotations

import re
from typing import Any, Mapping, Optional, Sequence

from src.notion.highlight_reader import read_pink_highlights
from src.workflow.block_parser import (
    ParsedBlock,
    contains_cjk,
    flatten_parsed_blocks,
    is_text_block,
    parse_block_tree,
)


class PodcastExtractionError(RuntimeError):
    """Raised when Podcast Library page extraction fails."""


COLOR_TO_CATEGORY = {
    "green_background": "Native Expression",
    "blue_background": "Business Phrase",
    "yellow_background": "Industry Term",
    "purple_background": "Collocation",
    "orange_background": "Sentence Pattern",
}

EXPRESSION_HEADER_ALIASES = {
    "expression": "expression",
    "text": "expression",
    "category": "category",
    "meaning": "meaning",
    "chinese meaning": "chinese_meaning",
    "usage context": "usage_context",
    "usage": "usage_context",
    "example": "example",
    "commonness": "commonness",
}


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _extract_title_property(page: Mapping[str, Any], property_name: str = "Title") -> str:
    properties = page.get("properties", {})
    prop = properties.get(property_name)
    if not isinstance(prop, Mapping):
        return ""
    title = prop.get("title")
    if not isinstance(title, list):
        return ""
    for item in title:
        if isinstance(item, Mapping):
            text = _as_text(item.get("plain_text") or item.get("text", {}).get("content", ""))
            if text:
                return text
    return ""


def _extract_select_property(page: Mapping[str, Any], name: str) -> str:
    prop = page.get("properties", {}).get(name)
    if not isinstance(prop, Mapping):
        return ""
    select_value = prop.get("select")
    if not isinstance(select_value, Mapping):
        return ""
    return _as_text(select_value.get("name"))


def _extract_url_property(page: Mapping[str, Any], name: str = "URL") -> str:
    prop = page.get("properties", {}).get(name)
    if not isinstance(prop, Mapping):
        return ""
    return _as_text(prop.get("url"))


def _extract_date_property(page: Mapping[str, Any], name: str = "Date") -> str:
    prop = page.get("properties", {}).get(name)
    if not isinstance(prop, Mapping):
        return ""
    date_value = prop.get("date")
    if isinstance(date_value, Mapping):
        return _as_text(date_value.get("start"))
    return ""


def _extract_rich_text_property(page: Mapping[str, Any], name: str) -> str:
    prop = page.get("properties", {}).get(name)
    if not isinstance(prop, Mapping):
        return ""
    value = prop.get("rich_text")
    if not isinstance(value, list):
        return ""
    texts: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        text = _as_text(item.get("plain_text") or item.get("text", {}).get("content", ""))
        if text:
            texts.append(text)
    return " ".join(texts).strip()


def _is_heading(block: ParsedBlock, heading_text: str) -> bool:
    return block.type.startswith("heading_") and block.text.casefold() == heading_text.casefold()


def _section_range(
    blocks: Sequence[ParsedBlock],
    start_title: str,
    stop_titles: Sequence[str] = (),
) -> list[ParsedBlock]:
    start_index = None
    start_level = 2
    for index, block in enumerate(blocks):
        if _is_heading(block, start_title):
            start_index = index
            start_level = block.heading_level or 2
            break

    if start_index is None:
        return []

    stop_set = {title.casefold() for title in stop_titles}
    collected: list[ParsedBlock] = []
    for block in blocks[start_index + 1 :]:
        if block.type.startswith("heading_") and block.heading_level <= start_level:
            if not stop_set or block.text.casefold() in stop_set:
                break
            if block.heading_level <= start_level:
                break
        collected.append(block)
    return collected


def _looks_english(text: str) -> bool:
    return bool(text) and not contains_cjk(text)


def _first_nonempty(texts: Sequence[str], predicate) -> str:
    for text in texts:
        if text and predicate(text):
            return text
    return ""


def _first_bullet_like(blocks: Sequence[ParsedBlock]) -> list[str]:
    bullets = []
    for block in blocks:
        if block.type in {"bulleted_list_item", "numbered_list_item"} and block.text:
            bullets.append(block.text)
    return bullets


def _build_summary(blocks: Sequence[ParsedBlock]) -> dict[str, Any]:
    texts = [block.text for block in blocks if block.text and block.type in {"paragraph", "quote", "bulleted_list_item", "numbered_list_item"}]
    english = _first_nonempty(texts, _looks_english)
    chinese = _first_nonempty(texts, contains_cjk)
    bullets = _first_bullet_like(blocks)
    takeaways = bullets or [text for text in texts if text not in {english, chinese}]
    return {
        "english": english,
        "chinese": chinese,
        "key_takeaways": takeaways[:10],
    }


def _normalize_header(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold()


def _cell_text(cell: Sequence[Mapping[str, Any]]) -> str:
    texts: list[str] = []
    for item in cell:
        if not isinstance(item, Mapping):
            continue
        text = _as_text(item.get("plain_text") or item.get("text", {}).get("content", ""))
        if text:
            texts.append(text)
    return " ".join(texts).strip()


def _table_rows(table_block: ParsedBlock) -> list[list[str]]:
    rows: list[list[str]] = []
    for child in table_block.children:
        if child.type != "table_row":
            continue
        row = [_cell_text(cell) for cell in child.cells]
        if any(row):
            rows.append(row)
    return rows


def _parse_expression_table(
    table_block: ParsedBlock,
    page_id: str,
    current_category: str,
) -> list[dict[str, Any]]:
    rows = _table_rows(table_block)
    if not rows:
        return []

    header_row = [_normalize_header(cell) for cell in rows[0]]
    column_map = {
        index: EXPRESSION_HEADER_ALIASES.get(header, header)
        for index, header in enumerate(header_row)
    }

    parsed: list[dict[str, Any]] = []
    for row in rows[1:]:
        row_map: dict[str, str] = {}
        for index, cell in enumerate(row):
            key = column_map.get(index, "")
            if key:
                row_map[key] = cell.strip()

        expression = row_map.get("expression", "")
        if not expression:
            continue
        category = row_map.get("category") or current_category
        if not category:
            continue
        parsed.append(
            {
                "expression": expression,
                "category": category,
                "meaning": row_map.get("meaning", ""),
                "chinese_meaning": row_map.get("chinese_meaning", ""),
                "usage_context": row_map.get("usage_context", ""),
                "example": row_map.get("example", ""),
                "commonness": row_map.get("commonness", ""),
                "source_page_id": page_id,
            }
        )
    return parsed


def _extract_learning_expressions(blocks: Sequence[ParsedBlock], page_id: str) -> list[dict[str, Any]]:
    section_blocks = _section_range(
        blocks,
        "Expressions",
        stop_titles=("Highlight Transcript", "Highlighted Transcript", "User Pink Highlight"),
    )
    if not section_blocks:
        return []

    expressions: list[dict[str, Any]] = []
    current_category = ""
    for block in section_blocks:
        if block.type.startswith("heading_") and block.heading_level >= 3 and block.text:
            current_category = block.text
            continue
        if block.type == "table":
            expressions.extend(_parse_expression_table(block, page_id, current_category))
    return expressions


def _iter_rich_text_items(block: ParsedBlock) -> list[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    if block.type == "table_row":
        for cell in block.cells:
            for item in cell:
                if isinstance(item, Mapping):
                    items.append(item)
        return items
    return [item for item in block.rich_text if isinstance(item, Mapping)]


def _item_text(item: Mapping[str, Any]) -> str:
    return _as_text(item.get("plain_text") or item.get("text", {}).get("content", ""))


def _sentence_for_context(block_text: str, highlighted_text: str) -> str:
    normalized = re.sub(r"\s+", " ", block_text).strip()
    if not normalized:
        return ""
    if not highlighted_text:
        return normalized
    highlighted_lower = highlighted_text.casefold()
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    for sentence in sentences:
        if highlighted_lower in sentence.casefold():
            return sentence.strip()
    return normalized


def _extract_ai_highlights(blocks: Sequence[ParsedBlock], page_id: str) -> list[dict[str, Any]]:
    section_blocks = _section_range(
        blocks,
        "Highlight Transcript",
        stop_titles=("User Pink Highlight",),
    )
    if not section_blocks:
        return []

    ai_highlights: list[dict[str, Any]] = []
    for block in section_blocks:
        if not is_text_block(block):
            continue
        block_text = block.text
        for item in _iter_rich_text_items(block):
            annotations = item.get("annotations")
            if not isinstance(annotations, Mapping):
                continue
            color = _as_text(annotations.get("color")).lower()
            category = COLOR_TO_CATEGORY.get(color)
            if not category:
                continue
            text = _item_text(item)
            if not text:
                continue
            ai_highlights.append(
                {
                    "text": text,
                    "category": category,
                    "color": color,
                    "context": _sentence_for_context(block_text, text),
                    "source_page_id": page_id,
                }
            )
    return ai_highlights


def _extract_user_vocabulary(page_id: str, notion: Any) -> list[dict[str, Any]]:
    highlights = read_pink_highlights(page_id=page_id, notion=notion)
    return [
        {
            "word": _as_text(item.get("text")),
            "context": _as_text(item.get("context")),
            "source_page_id": page_id,
            "highlight_type": "pink",
        }
        for item in highlights
        if _as_text(item.get("text"))
    ]


def extract_weekly_learning_context_for_page(
    page: Mapping[str, Any],
    notion: Any,
) -> Optional[dict[str, Any]]:
    page_id = _as_text(page.get("page_id") or page.get("id"))
    properties = page.get("properties", {})
    if not page_id or not isinstance(properties, Mapping):
        return None

    title = _extract_title_property(page, "Title")
    date_value = _extract_date_property(page, "Date")
    if not title or not date_value:
        return None

    page_record = {
        "page_id": page_id,
        "title": title,
        "date": date_value,
        "topic": _extract_select_property(page, "Topic"),
        "difficulty": _extract_select_property(page, "Difficulty"),
        "url": _extract_url_property(page, "URL"),
        "summary": {
            "english": "",
            "chinese": "",
        },
        "key_takeaways": [],
        "transcript_available": False,
    }

    try:
        blocks = parse_block_tree(notion, page_id)
    except Exception as exc:
        raise PodcastExtractionError(f"Failed to read page blocks for {page_id}: {exc}") from exc

    flat_blocks = flatten_parsed_blocks(blocks)
    summary_blocks = _section_range(flat_blocks, "Summary", stop_titles=("Transcript", "Expressions"))
    summary = _build_summary(summary_blocks)
    page_record["summary"]["english"] = summary["english"]
    page_record["summary"]["chinese"] = summary["chinese"]
    page_record["key_takeaways"] = summary["key_takeaways"]
    page_record["transcript_available"] = any(
        block.type == "heading_2" and block.text.casefold() == "transcript"
        for block in flat_blocks
    )

    learning_expressions = _extract_learning_expressions(blocks, page_id)
    ai_highlights = _extract_ai_highlights(flat_blocks, page_id)
    user_vocabulary = _extract_user_vocabulary(page_id, notion)

    return {
        "podcasts": [page_record],
        "learning_expressions": learning_expressions,
        "ai_highlights": ai_highlights,
        "user_vocabulary": user_vocabulary,
    }
