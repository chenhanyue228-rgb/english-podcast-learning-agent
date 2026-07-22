from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.analyzer.ai_client import SkillAIWorkflowError
from src.analyzer.weekly_review_analyzer import (
    build_weekly_review_analysis,
    load_weekly_review_request,
    save_weekly_review_analysis,
    validate_weekly_review_output,
)


def sample_request() -> dict:
    return {
        "week": "2026-W29",
        "date": "2026-07-17",
        "weekly_learning_data": {
            "week": "2026-W29",
            "date": "2026-07-17",
            "podcasts": [
                {
                    "title": "AI Leadership in Practice",
                    "topic": "AI Leadership",
                    "difficulty": "Intermediate",
                    "short_summary": "How leaders adapt when AI changes execution.",
                    "page_id": "podcast_1",
                },
                {
                    "title": "Negotiation and Communication",
                    "topic": "Negotiation",
                    "difficulty": "Intermediate",
                    "short_summary": "Language for framing ideas and managing pushback.",
                    "page_id": "podcast_2",
                },
            ],
            "expressions": [
                {
                    "expression": "take ownership",
                    "category": "Business Phrase",
                    "meaning": "Accept responsibility",
                    "usage_context": "Companies need to take ownership of AI adoption.",
                    "review_status": "New",
                    "podcast_page_id": "podcast_1",
                },
                {
                    "expression": "move the needle",
                    "category": "Native Expression",
                    "meaning": "Create meaningful impact",
                    "usage_context": "You need actions that move the needle.",
                    "review_status": "Learning",
                    "podcast_page_id": "podcast_1",
                },
                {
                    "expression": "operational leverage",
                    "category": "Industry Term",
                    "meaning": "Improve business efficiency",
                    "usage_context": "AI should create operational leverage.",
                    "review_status": "New",
                    "podcast_page_id": "podcast_2",
                },
                {
                    "expression": "on the same page",
                    "category": "Collocation",
                    "meaning": "In agreement",
                    "usage_context": "Make sure everyone is on the same page.",
                    "review_status": "Learning",
                    "podcast_page_id": "podcast_2",
                },
                {
                    "expression": "what it takes",
                    "category": "Sentence Pattern",
                    "meaning": "The necessary requirements",
                    "usage_context": "It takes what it takes to execute well.",
                    "review_status": "New",
                    "podcast_page_id": "podcast_2",
                },
            ],
            "vocabulary_memory": [
                {
                    "word": "leverage",
                    "context": "Companies can leverage AI to move faster.",
                    "meaning": "Use resources effectively",
                    "professional_category": "Word",
                    "my_usage": "We can leverage AI tools to save time.",
                    "review_status": "New",
                }
            ],
        },
    }


def test_build_weekly_review_analysis_uses_request_data() -> None:
    request = sample_request()

    analysis = build_weekly_review_analysis(request)

    payload = analysis.to_dict()
    assert payload["week"] == "2026-W29"
    assert "executive_summary" in payload
    assert "knowledge_insights" in payload
    assert "expression_upgrade" in payload
    assert "vocabulary_memory" in payload
    assert "career_reflection" in payload
    assert "next_learning_direction" in payload


def test_validate_weekly_review_output_requires_new_fields() -> None:
    with pytest.raises(SkillAIWorkflowError, match="executive_summary"):
        validate_weekly_review_output({"week": "2026-W29"})


def test_save_weekly_review_analysis_round_trips(tmp_path: Path) -> None:
    request = sample_request()
    analysis = build_weekly_review_analysis(request)
    out = save_weekly_review_analysis(analysis, tmp_path / "weekly_review.json")

    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["week"] == "2026-W29"
    assert loaded["executive_summary"]
    assert isinstance(loaded["knowledge_insights"], list)
    assert loaded["vocabulary_memory"]


def test_expression_review_non_empty() -> None:
    request = sample_request()

    analysis = build_weekly_review_analysis(request)
    payload = analysis.to_dict()

    assert len(payload["expression_upgrade"]) >= 5
    for item in payload["expression_upgrade"]:
        assert item["expression"]
        assert item["meaning"] is not None
        assert item["context"] is not None
        assert item["example"]


def test_insight_quality_check() -> None:
    request = sample_request()

    analysis = build_weekly_review_analysis(request)
    payload = analysis.to_dict()

    assert payload["knowledge_insights"]
    for item in payload["knowledge_insights"]:
        assert item["what_happened"]
        assert item["why_it_matters"]
        assert item["my_interpretation"]
        assert item["application"]
        assert len(item["what_happened"]) > 20


def test_vocabulary_memory_records_appear_in_analysis() -> None:
    request = sample_request()

    analysis = build_weekly_review_analysis(request)
    payload = analysis.to_dict()

    assert payload["vocabulary_memory"] == [
        {
            "word": "leverage",
            "context": "Companies can leverage AI to move faster.",
            "meaning": "Use resources effectively",
            "professional_category": "Word",
            "my_usage": "We can leverage AI tools to save time.",
            "review_status": "New",
        }
    ]
