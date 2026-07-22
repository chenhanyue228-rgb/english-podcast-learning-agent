#!/usr/bin/env python3
"""Read-only debug helper for inspecting Notion page blocks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config.settings import load_env_file  # noqa: E402
from src.notion.uploader import create_notion_client  # noqa: E402
from src.workflow.block_parser import parse_block_tree  # noqa: E402


def _serialize_block(block) -> dict:
    return {
        "id": block.id,
        "type": block.type,
        "text": block.text,
        "has_children": block.has_children,
        "children": [_serialize_block(child) for child in block.children],
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python scripts/debug_notion_blocks.py <podcast_page_id>")
        return 1

    load_env_file()
    page_id = args[0].strip()
    notion = create_notion_client()
    blocks = parse_block_tree(notion, page_id)
    payload = {
        "page_id": page_id,
        "count": len(blocks),
        "blocks": [_serialize_block(block) for block in blocks],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
