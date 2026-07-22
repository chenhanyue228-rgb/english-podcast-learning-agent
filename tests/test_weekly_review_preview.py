from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.publisher.weekly_review_preview import (
    WeeklyReviewPreviewError,
    build_weekly_review_preview,
    load_weekly_review_analysis,
    validate_weekly_review_preview,
    save_weekly_review_preview,
)


def sample_analysis() -> dict:
    return {
        "week": "2026-W29",
        "executive_summary": {
            "overview": "This week focused on AI leadership and communication.",
            "takeaway": "The learner moved from listening to reusable professional language.",
            "highlights": ["AI Leadership", "Communication"],
        },
        "knowledge_insights": [
            {
                "what_happened": "The episodes repeatedly discussed AI leadership.",
                "why_it_matters": "It exposes a transferable communication theme.",
                "my_interpretation": "The learner is building a practical framing pattern.",
                "application": "Reuse the framing language in work updates.",
            }
        ],
        "expression_upgrade": [
            {
                "expression": "take ownership",
                "meaning": "Accept responsibility",
                "context": "Useful for showing accountability.",
                "example": "We need to take ownership of the rollout.",
            }
        ],
        "vocabulary_memory": [],
        "career_reflection": {
            "questions": ["What changed my thinking this week?"],
            "possible_applications": ["Use the upgraded expressions in meetings."],
        },
        "next_learning_direction": [
            "Review the strongest expressions in short speaking drills."
        ],
    }


def test_build_weekly_review_preview_formats_sections() -> None:
    markdown = build_weekly_review_preview(sample_analysis())

    assert "# Executive Summary" in markdown
    assert "# Knowledge Insights" in markdown
    assert "# Expression Upgrade" in markdown
    assert "# Vocabulary Memory" in markdown
    assert "# Career Reflection" in markdown
    assert "# Next Learning Direction" in markdown
    assert "take ownership" in markdown
    assert "Highlighted Transcript" not in markdown


def test_save_weekly_review_preview_writes_markdown(tmp_path: Path) -> None:
    analysis_path = tmp_path / "2026-W29.json"
    analysis_path.write_text(json.dumps(sample_analysis(), ensure_ascii=False), encoding="utf-8")

    output_path = save_weekly_review_preview(analysis_path, tmp_path / "preview.md")

    assert output_path.name == "preview.md"
    assert output_path.read_text(encoding="utf-8").startswith("# Executive Summary")


def test_load_weekly_review_analysis_requires_json_object(tmp_path: Path) -> None:
    analysis_path = tmp_path / "broken.json"
    analysis_path.write_text("[]", encoding="utf-8")

    with pytest.raises(WeeklyReviewPreviewError, match="must be a JSON object"):
        load_weekly_review_analysis(analysis_path)


def test_validate_weekly_review_preview_warns_on_basic_words() -> None:
    analysis = sample_analysis()
    analysis["expression_upgrade"] = [
        {
            "expression": "good",
            "meaning": "good",
            "context": "basic",
            "example": "good",
        }
    ]

    result = validate_weekly_review_preview(analysis)

    assert result.has_warnings
    assert any("basic words" in issue.message for issue in result.issues)


def test_validate_weekly_review_preview_errors_on_empty_knowledge_insights() -> None:
    analysis = sample_analysis()
    analysis["knowledge_insights"] = []

    result = validate_weekly_review_preview(analysis)

    assert result.has_errors
    assert any("Knowledge Insights are empty" in issue.message for issue in result.issues)


def test_validate_weekly_review_preview_errors_on_missing_career_reflection() -> None:
    analysis = sample_analysis()
    analysis["career_reflection"] = {}

    result = validate_weekly_review_preview(analysis)

    assert result.has_errors
    assert any("Career Reflection is missing" in issue.message for issue in result.issues)


def test_validate_weekly_review_preview_errors_on_summary_only_content() -> None:
    analysis = sample_analysis()
    analysis["knowledge_insights"] = [
        {
            "what_happened": "The episode discussed leadership.",
            "why_it_matters": "It matters.",
            "my_interpretation": "",
            "application": "",
        }
    ]

    result = validate_weekly_review_preview(analysis)

    assert result.has_errors
    assert any("personal interpretation" in issue.message for issue in result.issues)
