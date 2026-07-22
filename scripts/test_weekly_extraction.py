#!/usr/bin/env python3
"""Smoke test for weekly learning extraction.

This script queries recent Podcast Library pages, extracts weekly learning
context, prints a compact summary, and saves the intermediate JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.workflow.weekly_learning_context_pipeline import run_weekly_learning_extraction  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test weekly learning extraction.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/weekly_learning_context.json"),
        help="Where to save WeeklyLearningContext.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    context, report, saved_path = run_weekly_learning_extraction(output_path=args.output)

    print(f"Podcast count: {len(context.get('podcasts', []))}")
    print(f"Expression count: {len(context.get('learning_expressions', []))}")
    print(f"AI highlight count: {len(context.get('ai_highlights', []))}")
    print(f"User vocabulary count: {len(context.get('user_vocabulary', []))}")
    print(f"Saved JSON: {saved_path}")
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
