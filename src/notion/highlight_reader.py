"""Read pink highlights from Notion page blocks.

This module is read-only. It reuses the existing Notion client/config helpers
and only inspects page blocks and their rich text annotations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client


TEXT_BLOCK_TYPES = {"paragraph", "heading_1", "heading_2", "heading_3", "quote", "table_cell"}
PINK_COLORS = {"pink", "pink_background"}


@dataclass(frozen=True)
class PinkHighlightOccurrence:
    """One exact pink rich-text occurrence and its deterministic position."""

    page_id: str
    block_id: str
    block_type: str
    block_path: tuple[int, ...]
    rich_text_index: int
    start_offset: int
    end_offset: int
    row_index: Optional[int]
    cell_index: Optional[int]
    text: str
    color: str
    context: str

    @property
    def position_descriptor(self) -> str:
        path = ".".join(str(part) for part in self.block_path)
        row = "" if self.row_index is None else str(self.row_index)
        cell = "" if self.cell_index is None else str(self.cell_index)
        return (
            f"path={path};row={row};cell={cell};rich_text={self.rich_text_index};"
            f"span={self.start_offset}:{self.end_offset}"
        )


@dataclass(frozen=True)
class _TraversedBlock:
    block: Mapping[str, Any]
    path: tuple[int, ...]
    row_index: Optional[int]


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


def _exact_text_from_rich_text_item(item: Mapping[str, Any]) -> str:
    plain_text = item.get("plain_text")
    if isinstance(plain_text, str):
        return plain_text

    text_value = item.get("text")
    if isinstance(text_value, Mapping):
        content = text_value.get("content")
        if isinstance(content, str):
            return content

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


def _list_child_blocks(notion: Any, block_id: str) -> Iterable[Mapping[str, Any]]:
    cursor: Optional[str] = None
    while True:
        kwargs: dict[str, Any] = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = notion.blocks.children.list(**kwargs)
        results = response.get("results", [])
        if isinstance(results, list):
            for block in results:
                if isinstance(block, Mapping):
                    yield block
        if not response.get("has_more"):
            break
        next_cursor = response.get("next_cursor")
        if not isinstance(next_cursor, str) or not next_cursor.strip():
            break
        cursor = next_cursor


def _iter_traversed_child_blocks(
    notion: Any,
    block_id: str,
    *,
    parent_path: tuple[int, ...] = (),
    parent_type: str = "",
) -> Iterable[_TraversedBlock]:
    for child_index, block in enumerate(_list_child_blocks(notion, block_id)):
        path = (*parent_path, child_index)
        block_type = str(block.get("type", "")).strip().lower()
        row_index = child_index if parent_type == "table" and block_type == "table_row" else None
        yield _TraversedBlock(block=block, path=path, row_index=row_index)
        child_id = str(block.get("id", "")).strip()
        if child_id and block.get("has_children"):
            yield from _iter_traversed_child_blocks(
                notion,
                child_id,
                parent_path=path,
                parent_type=block_type,
            )


def _iter_child_blocks(notion: Any, block_id: str) -> Iterable[Mapping[str, Any]]:
    for traversed in _iter_traversed_child_blocks(notion, block_id):
        yield traversed.block


def _iter_page_blocks(notion: Any, page_id: str) -> Iterable[Mapping[str, Any]]:
    return _iter_child_blocks(notion, page_id)


def _highlight_color(item: Mapping[str, Any]) -> str:
    annotations = item.get("annotations")
    if not isinstance(annotations, Mapping):
        return ""
    color = annotations.get("color")
    return color.strip() if isinstance(color, str) else ""


def _occurrence_from_item(
    *,
    page_id: str,
    traversed: _TraversedBlock,
    item: Mapping[str, Any],
    rich_text_index: int,
    start_offset: int,
    context: str,
    cell_index: Optional[int] = None,
) -> Optional[PinkHighlightOccurrence]:
    if not _is_pink_highlight(item):
        return None
    text = _exact_text_from_rich_text_item(item)
    if not text.strip():
        return None
    block = traversed.block
    block_type = str(block.get("type", "")).strip().lower()
    block_id = str(block.get("id", "")).strip()
    return PinkHighlightOccurrence(
        page_id=page_id,
        block_id=block_id,
        block_type=block_type,
        block_path=traversed.path,
        rich_text_index=rich_text_index,
        start_offset=start_offset,
        end_offset=start_offset + len(text),
        row_index=traversed.row_index,
        cell_index=cell_index,
        text=text,
        color=_highlight_color(item),
        context=_sentence_for_highlight(context, text),
    )


def read_pink_highlight_occurrences(
    page_id: str,
    notion: Optional[Any] = None,
) -> list[PinkHighlightOccurrence]:
    """Return every exact pink rich-text occurrence, including its position."""
    if notion is None:
        config = load_notion_config()
        notion = create_notion_client(config.token)

    occurrences: list[PinkHighlightOccurrence] = []
    for traversed in _iter_traversed_child_blocks(notion, page_id):
        block = traversed.block
        block_type = str(block.get("type", "")).strip().lower()
        if not _is_text_block(block) and block_type != "table_row":
            continue
        block_context = _block_context(block)
        if block_type == "table_row":
            for cell_index, cell in enumerate(_table_row_cells(block)):
                cell_offset = 0
                for rich_text_index, item in enumerate(cell):
                    occurrence = _occurrence_from_item(
                        page_id=page_id,
                        traversed=traversed,
                        item=item,
                        rich_text_index=rich_text_index,
                        start_offset=cell_offset,
                        context=block_context,
                        cell_index=cell_index,
                    )
                    if occurrence is not None:
                        occurrences.append(occurrence)
                    cell_offset += len(_exact_text_from_rich_text_item(item))
            continue

        block_offset = 0
        for rich_text_index, item in enumerate(_block_rich_text(block)):
            occurrence = _occurrence_from_item(
                page_id=page_id,
                traversed=traversed,
                item=item,
                rich_text_index=rich_text_index,
                start_offset=block_offset,
                context=block_context,
            )
            if occurrence is not None:
                occurrences.append(occurrence)
            block_offset += len(_exact_text_from_rich_text_item(item))
    return occurrences


def read_pink_highlights(
    page_id: str,
    notion: Optional[Any] = None,
) -> list[dict[str, str]]:
    """Return pink-highlighted text snippets from a Notion page."""
    if notion is None:
        config = load_notion_config()
        notion = create_notion_client(config.token)

    return [
        {
            "text": occurrence.text,
            "color": occurrence.color,
            "block_id": occurrence.block_id,
            "context": occurrence.context,
        }
        for occurrence in read_pink_highlight_occurrences(page_id=page_id, notion=notion)
    ]


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
