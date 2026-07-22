"""Read pink highlights from Notion page blocks.

This module is read-only. It reuses the existing Notion client/config helpers
and only inspects page blocks and their rich text annotations.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Optional

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


TEXT_BLOCK_TYPES = {"paragraph", "heading_1", "heading_2", "heading_3", "quote", "table_cell"}
PINK_COLORS = {"pink", "pink_background"}


def _is_text_block(block: Mapping[str, Any]) -> bool:
    block_type = str(block.get("type", "")).strip().lower()
    return block_type in TEXT_BLOCK_TYPES


def _block_rich_text(block: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    block_type = str(block.get("type", "")).strip().lower()
    payload = block.get(block_type)
    if isinstance(payload, Mapping):
        rich_text = payload.get("rich_text")
        if isinstance(rich_text, list):
            return [item for item in rich_text if isinstance(item, Mapping)]
    return []


def _table_row_cells(block: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    block_type = str(block.get("type", "")).strip().lower()
    payload = block.get(block_type)
    if isinstance(payload, Mapping):
        cells = payload.get("cells")
        if isinstance(cells, list):
            normalized_cells: list[list[Mapping[str, Any]]] = []
            for cell in cells:
                if isinstance(cell, list):
                    normalized_cells.append([item for item in cell if isinstance(item, Mapping)])
            return normalized_cells
    return []


def _plain_text_from_rich_text_item(item: Mapping[str, Any]) -> str:
    plain_text = item.get("plain_text")
    if isinstance(plain_text, str) and plain_text.strip():
        return plain_text.strip()

    text_value = item.get("text")
    if isinstance(text_value, Mapping):
        content = text_value.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

    return ""


def _block_context(block: Mapping[str, Any]) -> str:
    texts: list[str] = []
    block_type = str(block.get("type", "")).strip().lower()
    if block_type == "table_row":
        for cell in _table_row_cells(block):
            cell_texts = []
            for item in cell:
                text = _plain_text_from_rich_text_item(item)
                if text:
                    cell_texts.append(text)
            if cell_texts:
                texts.append(" ".join(cell_texts))
    else:
        for item in _block_rich_text(block):
            text = _plain_text_from_rich_text_item(item)
            if text:
                texts.append(text)
    return " ".join(texts).strip()


def _split_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _sentence_for_highlight(block_context: str, highlighted_text: str) -> str:
    if not block_context:
        return ""
    if not highlighted_text:
        return block_context

    highlight_lower = highlighted_text.strip().lower()
    for sentence in _split_sentences(block_context):
        if highlight_lower in sentence.lower():
            return sentence
    return block_context


def _is_pink_highlight(item: Mapping[str, Any]) -> bool:
    annotations = item.get("annotations")
    if not isinstance(annotations, Mapping):
        return False
    color = annotations.get("color")
    return isinstance(color, str) and color.strip().lower() in PINK_COLORS


def _iter_child_blocks(notion: Any, block_id: str) -> Iterable[Mapping[str, Any]]:
    response = notion.blocks.children.list(block_id=block_id, page_size=100)
    results = response.get("results", [])
    if not isinstance(results, list):
        return []
    for block in results:
        if isinstance(block, Mapping):
            yield block
            child_id = str(block.get("id", "")).strip()
            if child_id and block.get("has_children"):
                yield from _iter_child_blocks(notion, child_id)


def _iter_page_blocks(notion: Any, page_id: str) -> Iterable[Mapping[str, Any]]:
    return _iter_child_blocks(notion, page_id)


def read_pink_highlights(
    page_id: str,
    notion: Optional[Any] = None,
) -> list[dict[str, str]]:
    """Return pink-highlighted text snippets from a Notion page."""
    if notion is None:
        config = load_notion_config()
        notion = create_notion_client(config.token)

    highlights: list[dict[str, str]] = []
    for block in _iter_page_blocks(notion, page_id):
        block_type = str(block.get("type", "")).strip().lower()
        if not _is_text_block(block) and block_type != "table_row":
            continue
        block_id = str(block.get("id", "")).strip()
        block_context = _block_context(block)
        if block_type == "table_row":
            for cell in _table_row_cells(block):
                for item in cell:
                    if not _is_pink_highlight(item):
                        continue
                    text = _plain_text_from_rich_text_item(item)
                    if not text:
                        continue
                    context = _sentence_for_highlight(block_context, text)
                    annotations = item.get("annotations")
                    color = ""
                    if isinstance(annotations, Mapping):
                        color_value = annotations.get("color")
                        if isinstance(color_value, str):
                            color = color_value.strip()
                    highlights.append(
                        {
                            "text": text,
                            "color": color,
                            "block_id": block_id,
                            "context": context,
                        }
                    )
            continue
        for item in _block_rich_text(block):
            if not _is_pink_highlight(item):
                continue
            text = _plain_text_from_rich_text_item(item)
            if not text:
                continue
            context = _sentence_for_highlight(block_context, text)
            annotations = item.get("annotations")
            color = ""
            if isinstance(annotations, Mapping):
                color_value = annotations.get("color")
                if isinstance(color_value, str):
                    color = color_value.strip()
            highlights.append(
                {
                    "text": text,
                    "color": color,
                    "block_id": block_id,
                    "context": context,
                }
            )
    return highlights


def debug_print_pink_highlights(page_id: str, notion: Optional[Any] = None) -> list[dict[str, str]]:
    """Read a page and print detected pink highlights for manual verification."""
    highlights = read_pink_highlights(page_id=page_id, notion=notion)
    for highlight in highlights:
        print(
            f"pink highlight found: block_id={highlight['block_id']} "
            f"color={highlight['color']} text={highlight['text']}"
        )
    if not highlights:
        print("NO_PINK_HIGHLIGHT_FOUND")
    return highlights
