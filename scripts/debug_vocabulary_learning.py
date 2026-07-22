#!/usr/bin/env python3
"""Read-only CLI for vocabulary learning preview."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.enrichment.factory import create_vocabulary_enrichment_provider  # noqa: E402
from src.notion.config import load_dotenv  # noqa: E402
from src.workflow.vocabulary_learning_pipeline import preview_vocabulary_learning  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python scripts/debug_vocabulary_learning.py <page_id>")
        return 1

    load_dotenv()
    provider = create_vocabulary_enrichment_provider()
    print(f"provider.class.name={provider.__class__.__name__}")
    page_id = args[0].strip()
    payload = preview_vocabulary_learning(page_id)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
