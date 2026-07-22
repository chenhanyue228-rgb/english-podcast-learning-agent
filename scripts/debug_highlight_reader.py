#!/usr/bin/env python3
"""Read-only debug helper for verifying Notion pink highlights."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.notion.highlight_reader import read_pink_highlights  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python scripts/debug_highlight_reader.py <page_id>")
        return 1

    page_id = args[0].strip()
    highlights = read_pink_highlights(page_id)
    payload = {
        "page_id": page_id,
        "count": len(highlights),
        "highlights": [
            {
                "text": highlight.get("text", ""),
                "color": highlight.get("color", ""),
                "context": highlight.get("context", ""),
            }
            for highlight in highlights
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
