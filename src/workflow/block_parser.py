"""Recursive Notion block parser for weekly learning extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from src.workflow.notion_client import list_block_children


TEXT_BLOCK_TYPES = {
    "paragraph",
    "quote",
    "bulleted_list_item",
    "numbered_list_item",
    "heading_1",
    "heading_2",
    "heading_3",
    "table_row",
    "table_cell",
}


@dataclass(frozen=True)
class ParsedBlock:
    """A normalized Notion block with recursively parsed children."""

    id: str
    type: str
    text: str = ""
    rich_text: list[Mapping[str, Any]] = field(default_factory=list)
    cells: list[list[Mapping[str, Any]]] = field(default_factory=list)
    has_children: bool = False
    children: list["ParsedBlock"] = field(default_factory=list)
    raw: Mapping[str, Any] = field(default_factory=dict)

    @property
    def heading_level(self) -> int:
        if self.type.startswith("heading_"):
            suffix = self.type.split("_", 1)[1]
            if suffix.isdigit():
                return int(suffix)
        return 0


def _plain_text_from_item(item: Mapping[str, Any]) -> str:
    plain_text = item.get("plain_text")
    if isinstance(plain_text, str) and plain_text.strip():
        return plain_text.strip()

    text = item.get("text")
    if isinstance(text, Mapping):
        content = text.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    return ""


def _rich_text_items(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rich_text = payload.get("rich_text")
    if not isinstance(rich_text, list):
        return []
    return [item for item in rich_text if isinstance(item, Mapping)]


def _table_cells(payload: Mapping[str, Any]) -> list[list[Mapping[str, Any]]]:
    cells = payload.get("cells")
    if not isinstance(cells, list):
        return []
    normalized: list[list[Mapping[str, Any]]] = []
    for cell in cells:
        if isinstance(cell, list):
            normalized.append([item for item in cell if isinstance(item, Mapping)])
    return normalized


def _block_payload(block: Mapping[str, Any]) -> Mapping[str, Any]:
    block_type = str(block.get("type", "")).strip()
    payload = block.get(block_type)
    if isinstance(payload, Mapping):
        return payload
    return {}


def normalize_block(block: Mapping[str, Any], children: Optional[list[ParsedBlock]] = None) -> ParsedBlock:
    block_type = str(block.get("type", "")).strip().lower()
    payload = _block_payload(block)
    rich_text = _rich_text_items(payload)
    cells = _table_cells(payload) if block_type == "table_row" else []
    text_items: list[str] = []

    if block_type == "table_row":
        for cell in cells:
            cell_text = " ".join(
                part for part in (_plain_text_from_item(item) for item in cell) if part
            ).strip()
            if cell_text:
                text_items.append(cell_text)
    elif block_type == "table_cell":
        text_items = [
            text for text in (_plain_text_from_item(item) for item in rich_text) if text
        ]
    else:
        text_items = [text for text in (_plain_text_from_item(item) for item in rich_text) if text]

    return ParsedBlock(
        id=str(block.get("id", "")).strip(),
        type=block_type,
        text=" ".join(text_items).strip(),
        rich_text=rich_text,
        cells=cells,
        has_children=bool(block.get("has_children")),
        children=children or [],
        raw=block,
    )


def parse_block_tree(notion: Any, block_id: str) -> list[ParsedBlock]:
    """Recursively parse direct and nested child blocks."""
    response = list_block_children(notion, block_id=block_id, page_size=100)
    results = response.get("results", [])
    parsed: list[ParsedBlock] = []

    if not isinstance(results, list):
        return parsed

    for raw_block in results:
        if not isinstance(raw_block, Mapping):
            continue
        child_nodes: list[ParsedBlock] = []
        child_id = str(raw_block.get("id", "")).strip()
        if raw_block.get("has_children") and child_id:
            child_nodes = parse_block_tree(notion, child_id)
        parsed.append(normalize_block(raw_block, child_nodes))
    return parsed


def flatten_parsed_blocks(blocks: list[ParsedBlock]) -> list[ParsedBlock]:
    """Return blocks in document order, preserving recursive children."""
    flattened: list[ParsedBlock] = []
    for block in blocks:
        flattened.append(block)
        if block.children:
            flattened.extend(flatten_parsed_blocks(block.children))
    return flattened


def is_text_block(block: ParsedBlock) -> bool:
    return block.type in TEXT_BLOCK_TYPES


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))
