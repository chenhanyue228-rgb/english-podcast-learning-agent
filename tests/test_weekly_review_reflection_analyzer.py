from __future__ import annotations

import json
from pathlib import Path

from src.weekly_review.reflection_analyzer import (
    ReflectionGenerationError,
    load_weekly_learning_context,
    run_reflection_analysis,
)


def sample_weekly_learning_context() -> dict:
    return {
        "metadata": {
            "period_start": "2026-07-13",
            "period_end": "2026-07-20",
            "generated_at": "2026-07-20T12:00:00Z",
            "source": "Podcast Library",
        },
        "podcasts": [
            {
                "page_id": "page_1",
                "title": "Ask & You Shall Receive: Questions For Better Negotiations",
                "date": "2026-07-17",
                "topic": "Negotiation",
                "difficulty": "Intermediate",
                "url": "https://example.com/1",
                "summary": {
                    "english": "This episode discusses negotiation techniques.",
                    "chinese": "这一集讲述谈判技巧。",
                },
                "key_takeaways": [
                    "Negotiation is relationship management.",
                    "Good framing matters.",
                ],
                "transcript_available": True,
            },
            {
                "page_id": "page_2",
                "title": "Leadership Under Pressure",
                "date": "2026-07-18",
                "topic": "Leadership",
                "difficulty": "Intermediate",
                "url": "https://example.com/2",
                "summary": {
                    "english": "This episode talks about leadership and communication.",
                    "chinese": "这一集讨论领导力与沟通。",
                },
                "key_takeaways": [
                    "Regulate emotion before responding.",
                    "Frame difficult conversations carefully.",
                ],
                "transcript_available": True,
            },
        ],
        "learning_expressions": [
            {
                "expression": "challenge assumptions",
                "category": "Business Phrase",
                "meaning": "Question ideas carefully",
                "chinese_meaning": "质疑假设",
                "usage_context": "You need to challenge assumptions in meetings.",
                "example": "Let's challenge assumptions before we decide.",
                "source_page_id": "page_1",
            }
        ],
        "ai_highlights": [],
        "user_vocabulary": [
            {
                "word": "vulnerability",
                "context": "Showing vulnerability can build trust.",
                "source_page_id": "page_2",
                "highlight_type": "pink",
            }
        ],
    }


def test_reflection_context_is_structured_and_not_summary_like(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "reflection_context.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_reflection_analysis(input_path, output_path=output_path)

    assert result.input_path == input_path.resolve()
    assert result.output_path == output_path.resolve()
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["weekly_theme"]["theme"] == "Negotiation"
    assert payload["weekly_theme"]["category"] == "Negotiation"
    assert payload["mindset_shifts"]
    assert payload["cross_content_patterns"]
    assert payload["professional_actions"]
    assert payload["mindset_shifts"][0]["confidence"] >= 0.8
    assert isinstance(payload["mindset_shifts"][0]["evidence"], list)
    assert payload["mindset_shifts"][0]["evidence"][0]["source"]
    assert payload["mindset_shifts"][0]["evidence"][0]["supporting_concept"]
    assert "This episode discusses" not in json.dumps(payload["mindset_shifts"][0]["after"])
    assert "This podcast explains" not in json.dumps(payload["mindset_shifts"][0]["after"])


def test_load_weekly_learning_context_requires_object(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("[]", encoding="utf-8")

    try:
        load_weekly_learning_context(path)
    except ReflectionGenerationError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("Expected ReflectionGenerationError")


def test_strong_multi_podcast_reflection_has_high_confidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "reflection_context.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload = json.loads(run_reflection_analysis(input_path, output_path=output_path).output_path.read_text(encoding="utf-8"))

    assert payload["weekly_theme"]["theme"] == "Negotiation"
    assert payload["mindset_shifts"][0]["confidence"] >= 0.85
    assert len(payload["mindset_shifts"][0]["evidence"]) >= 1
    assert len(payload["professional_actions"]) >= 1


def test_weak_single_source_reflection_has_lower_confidence(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    single_source = sample_weekly_learning_context()
    single_source["podcasts"] = single_source["podcasts"][:1]
    input_path = tmp_path / "single.json"
    output_path = tmp_path / "reflection_context.json"
    input_path.write_text(
        json.dumps(single_source, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    payload = json.loads(run_reflection_analysis(input_path, output_path=output_path).output_path.read_text(encoding="utf-8"))

    assert payload["mindset_shifts"][0]["confidence"] < 0.85
    assert payload["mindset_shifts"][0]["evidence"]


def test_missing_evidence_handling_uses_metadata_fallback(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    no_evidence = sample_weekly_learning_context()
    no_evidence["podcasts"][0]["summary"] = {"english": "", "chinese": ""}
    no_evidence["podcasts"][0]["key_takeaways"] = []
    no_evidence["podcasts"] = no_evidence["podcasts"][:1]
    input_path = tmp_path / "missing_evidence.json"
    output_path = tmp_path / "reflection_context.json"
    input_path.write_text(
        json.dumps(no_evidence, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_reflection_analysis(input_path, output_path=output_path)

    assert result.output_path == output_path.resolve()
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["mindset_shifts"][0]["evidence"]
    assert payload["mindset_shifts"][0]["evidence"][0]["source"] == "Podcast metadata"
