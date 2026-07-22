#!/usr/bin/env python3
"""Smoke test for weekly review generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.weekly_review.reflection_analyzer import (  # noqa: E402
    ReflectionAnalyzer,
    ReflectionGenerationError,
    load_weekly_learning_context,
)
from src.weekly_review.generator import run_weekly_review_generation  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Test weekly review generation.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("output/weekly_learning_context.json"),
        help="Path to WeeklyLearningContext.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/weekly_review.json"),
        help="Where to save WeeklyReview.json.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    print("============================")
    print("Weekly Review Generation Report")
    print("============================")
    print()

    try:
        weekly_learning_context = load_weekly_learning_context(args.input)
        reflection_context = ReflectionAnalyzer().generate(weekly_learning_context)
    except ReflectionGenerationError as exc:  # pragma: no cover - exercised in tests
        print("ReflectionContext validation failed.")
        print()
        print("Reason:")
        print(str(exc))
        return 1

    weekly_theme = reflection_context.get("weekly_theme", {})
    if not isinstance(weekly_theme, dict):
        weekly_theme = {}

    print("ReflectionContext loaded successfully.")
    print("ReflectionContext saved:")
    print("YES")
    print()
    print("Path:")
    print("output/reflection_context.json")
    print()
    print("Reflection Context Report")
    print()
    print("Weekly Theme:")
    print(str(weekly_theme.get("category", "")))
    print(str(weekly_theme.get("theme", "")))
    print()
    print("Mindset Shifts:")
    print(len(reflection_context.get("mindset_shifts", [])))
    print()
    print("Cross Content Patterns:")
    print(len(reflection_context.get("cross_content_patterns", [])))
    print()
    print("Professional Actions:")
    print(len(reflection_context.get("professional_actions", [])))
    print()
    print("Supporting Language Assets:")
    print()
    print("Expressions:")
    print(len(weekly_learning_context.get("learning_expressions", [])))
    print()
    print("Vocabulary:")
    print(len(weekly_learning_context.get("user_vocabulary", [])))
    print()

    try:
        result = run_weekly_review_generation(args.input, output_path=args.output)
    except Exception as exc:  # pragma: no cover - exercised in tests
        print("Generation Status:")
        print("Status: FAILED")
        print()
        print("Quality Gate:")
        print("Passed: false")
        print("Score: 0/100")
        print()
        print("Issues:")
        print("- generation failed before quality checks")
        print()
        print("Suggestions:")
        print("- inspect the generation error and rerun")
        print()
        print("Generation failed")
        print()
        print("Reason:")
        print(str(exc))
        return 1

    quality = result.quality_report or {"passed": False, "score": 0, "issues": [], "suggestions": []}
    payload = result.payload

    print("Generation Status:")
    print("Status: SUCCESS")
    print()
    print("Quality Gate:")
    print(f"Passed: {str(quality.get('passed', False)).lower()}")
    print(f"Score: {int(quality.get('score', 0))}/100")
    print()
    print("Issues:")
    issues = quality.get("issues", [])
    if issues:
        for issue in issues:
            print(f"- {issue}")
    else:
        print("- none")
    print()
    print("Suggestions:")
    suggestions = quality.get("suggestions", [])
    if suggestions:
        for suggestion in suggestions:
            print(f"- {suggestion}")
    else:
        print("- none")
    print()
    print("Output:")
    print(f"Saved: {result.output_path}")
    print()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
