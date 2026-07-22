#!/usr/bin/env python3
"""Smoke test for Weekly Reflection Notion writing."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.notion.weekly_reflection_writer import (  # noqa: E402
    WeeklyReflectionWriterError,
    load_reflection_context_json,
    load_weekly_review_json,
    publish_weekly_reflection,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test Weekly Reflection Notion writing.")
    parser.add_argument(
        "--weekly-review-json",
        type=Path,
        default=Path("output/weekly_review.json"),
        help="Path to WeeklyReview.json.",
    )
    parser.add_argument(
        "--reflection-json",
        type=Path,
        default=Path("output/reflection_context.json"),
        help="Path to ReflectionContext.json.",
    )
    parser.add_argument(
        "--podcast-database-id",
        default=None,
        help="Optional Podcast Library database ID for source link blocks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    print("============================")
    print("Weekly Reflection Writer Report")
    print("============================")
    print()

    try:
        weekly_review = load_weekly_review_json(args.weekly_review_json)
        reflection_context = load_reflection_context_json(args.reflection_json)
    except WeeklyReflectionWriterError as exc:
        print("Input validation failed.")
        print()
        print("Reason:")
        print(str(exc))
        return 1

    print(f"ReflectionContext loaded: {'YES' if reflection_context else 'NO'}")
    print(f"WeeklyReview loaded: {'YES' if weekly_review else 'NO'}")
    print()

    try:
        result = publish_weekly_reflection(
            weekly_review,
            reflection_context,
            podcast_database_id=args.podcast_database_id,
        )
    except WeeklyReflectionWriterError as exc:
        print("Notion:")
        print("Page created: NO")
        print()
        print("Reason:")
        print(str(exc))
        return 1

    print("Notion:")
    print("Page created: YES")
    print()
    print("Page ID:")
    print(result.page_id)
    if result.page_url:
        print()
        print("Page URL:")
        print(result.page_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
