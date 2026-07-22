#!/usr/bin/env python3
"""Read-only CLI for vocabulary review preview."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.workflow.vocabulary_learning_pipeline import build_vocabulary_learning_preview  # noqa: E402
from src.workflow.vocabulary_review import approve_vocabulary_items  # noqa: E402


def _pending_items(preview_payload: dict[str, object]) -> list[dict[str, object]]:
    items = preview_payload.get("pending_vocabulary", [])
    return [item for item in items if isinstance(item, dict)]


def _rejected_items(preview_payload: dict[str, object]) -> list[dict[str, object]]:
    rejected: list[dict[str, object]] = []
    for item in preview_payload.get("rejected_candidates", []):
        if isinstance(item, dict):
            rejected.append(item)
    return rejected


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python scripts/debug_vocabulary_review.py <page_id>")
        return 1

    page_id = args[0].strip()
    preview_payload = build_vocabulary_learning_preview(page_id)
    pending_items = _pending_items(preview_payload)
    approved_payload = approve_vocabulary_items(pending_items)

    output = {
        "pending_vocabulary": pending_items,
        "approved_vocabulary": approved_payload.get("approved", []),
        "rejected_vocabulary": _rejected_items(preview_payload),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
