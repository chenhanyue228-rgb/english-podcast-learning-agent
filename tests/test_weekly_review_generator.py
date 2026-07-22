from __future__ import annotations

import json
from pathlib import Path

from src.weekly_review.factory import create_weekly_review_generation_provider
from src.weekly_review.generator import WeeklyReviewGenerationError, run_weekly_review_generation
import scripts.test_weekly_review_generator as weekly_review_script


class FakeWeeklyReviewProvider:
    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        return {
            "period": {
                "start_date": "2026-07-13",
                "end_date": "2026-07-20",
                "generated_at": "2026-07-20T12:00:00Z",
                "source": "Podcast Library",
            },
            "core_idea": {
                "idea": "Negotiation is relationship management, not a zero-sum contest.",
                "why_it_matters": "This changes how I prepare for disagreement.",
                "refined_understanding": "The relationship is part of the outcome.",
            },
            "mindset_shift": {"before": "I focused on winning.", "now": "I focus on shared outcomes."},
            "ideas_worth_compounding": [
                {"idea": "Listening reveals hidden interests.", "why_it_matters": "It prevents solving the wrong problem.", "application": "Ask before proposing.", "source_reference": "Podcast A"},
                {"idea": "Framing shapes collaboration.", "why_it_matters": "It reduces defensiveness.", "application": "Name the shared goal.", "source_reference": "Podcast A"},
            ],
            "expressions_worth_reusing": [
                {"expression": "challenge assumptions", "contextual_meaning": "Test beliefs constructively.", "reusable_example": "Let's challenge our assumptions.", "communication_function": "Constructive challenge"},
                {"expression": "joint problem solving", "contextual_meaning": "Collaborate on a shared problem.", "reusable_example": "Let's use joint problem solving.", "communication_function": "Collaborative framing"},
                {"expression": "building long-term relationships", "contextual_meaning": "Prioritize durable trust.", "reusable_example": "This supports building long-term relationships.", "communication_function": "Long-term orientation"},
            ],
            "language_thinking_connection": "The phrase 'joint problem solving' reframes the other person as a collaborator and makes disagreement easier to structure constructively.",
            "next_week_application": {"scenario": "Stakeholder challenge", "behavior": "Restate the shared outcome.", "phrase_to_use": "Let's treat this as joint problem solving.", "completion_condition": "Use it once and record the response."},
            "sources": [{"page_id": "page_1", "title": "AI Leadership in Practice", "url": "https://example.com/1"}],
        }


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
                "title": "AI Leadership in Practice",
                "date": "2026-07-17",
                "topic": "AI Leadership",
                "difficulty": "Intermediate",
                "url": "https://example.com/1",
                "summary": {
                    "english": "The episode explains how leaders adapt to AI-driven change.",
                    "chinese": "本集讲述领导者如何适应 AI 驱动的变化。",
                },
                "key_takeaways": [
                    "Leadership is about framing change clearly.",
                    "Adoption requires operational follow-through.",
                ],
                "transcript_available": True,
            }
        ],
        "learning_expressions": [
            {
                "expression": "take ownership",
                "category": "Business Phrase",
                "meaning": "Accept responsibility",
                "chinese_meaning": "承担责任",
                "usage_context": "Leaders need to take ownership of AI adoption.",
                "example": "We should take ownership of the rollout.",
                "source_page_id": "page_1",
            }
        ],
        "ai_highlights": [],
        "user_vocabulary": [
            {
                "word": "leverage",
                "context": "Companies can leverage AI to redesign workflows.",
                "source_page_id": "page_1",
                "highlight_type": "pink",
            }
        ],
    }


def test_weekly_review_generation_writes_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_weekly_review_generation(
        input_path,
        output_path=output_path,
        provider=FakeWeeklyReviewProvider(),
    )

    assert result.input_path == input_path.resolve()
    assert result.output_path == output_path.resolve()
    assert output_path.exists()

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["period"]["source"] == "Podcast Library"
    assert payload["core_idea"]["idea"]
    assert payload["ideas_worth_compounding"]
    assert payload["expressions_worth_reusing"][0]["expression"] == "challenge assumptions"
    assert payload["language_thinking_connection"]
    assert payload["next_week_application"]["scenario"]


def test_weekly_review_provider_factory_defaults_to_codex(monkeypatch) -> None:
    monkeypatch.delenv("WEEKLY_REVIEW_PROVIDER", raising=False)

    provider = create_weekly_review_generation_provider()

    assert provider.__class__.__name__ == "CodexWeeklyReviewGenerationProvider"


def test_weekly_review_provider_factory_supports_placeholder(monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REVIEW_PROVIDER", "placeholder")

    provider = create_weekly_review_generation_provider()

    assert provider.__class__.__name__ == "PlaceholderWeeklyReviewGenerationProvider"


def test_weekly_review_provider_factory_uses_openai(monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REVIEW_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = create_weekly_review_generation_provider()

    assert provider.__class__.__name__ == "OpenAIWeeklyReviewGenerationProvider"


def test_weekly_review_generator_script_smoke(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    original_runner = weekly_review_script.run_weekly_review_generation
    original_analyzer = weekly_review_script.ReflectionAnalyzer

    def fake_runner(*_args, **_kwargs):
        output_path.write_text(
            json.dumps(FakeWeeklyReviewProvider().generate("", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return type(
            "Result",
            (),
            {
                "payload": FakeWeeklyReviewProvider().generate("", {}),
                "output_path": output_path,
                "quality_report": {
                    "passed": True,
                    "score": 92,
                    "issues": [],
                    "suggestions": [],
                },
            },
        )()

    class FakeReflectionAnalyzer:
        def generate(self, weekly_learning_context):
            return {
                "weekly_theme": {"category": "Negotiation", "theme": "Negotiation as relationship management"},
                "mindset_shifts": [
                    {
                        "before": "I used to treat negotiation as winning.",
                        "after": "I now see negotiation as relationship management.",
                        "evidence": [
                            {"source": "Podcast summary", "supporting_concept": "relationship management"}
                        ],
                        "confidence": 0.95,
                    }
                ],
                "cross_content_patterns": ["Negotiation shows up across the week's learning."],
                "professional_actions": ["Pause before responding in difficult conversations."],
            }

    weekly_review_script.run_weekly_review_generation = fake_runner
    weekly_review_script.ReflectionAnalyzer = lambda: FakeReflectionAnalyzer()
    try:
        exit_code = weekly_review_script.main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        )
    finally:
        weekly_review_script.run_weekly_review_generation = original_runner
        weekly_review_script.ReflectionAnalyzer = original_analyzer

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "ReflectionContext loaded successfully." in captured.out
    assert "ReflectionContext saved:" in captured.out
    assert "YES" in captured.out
    assert "Path:" in captured.out
    assert "output/reflection_context.json" in captured.out
    assert "Reflection Context Report" in captured.out
    assert "Weekly Theme:" in captured.out
    assert "Mindset Shifts:" in captured.out
    assert "Cross Content Patterns:" in captured.out
    assert "Professional Actions:" in captured.out
    assert "Supporting Language Assets:" in captured.out
    assert "Expressions:" in captured.out
    assert "Vocabulary:" in captured.out
    assert "Quality Gate:" in captured.out
    assert "Score: 92/100" in captured.out
    assert "Status: SUCCESS" in captured.out
    assert "Saved:" in captured.out
    assert output_path.exists()


def test_weekly_review_generator_script_failure_visible(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    original_runner = weekly_review_script.run_weekly_review_generation
    original_analyzer = weekly_review_script.ReflectionAnalyzer

    class FakeReflectionAnalyzer:
        def generate(self, weekly_learning_context):
            return {
                "weekly_theme": {"category": "Negotiation", "theme": "Negotiation as relationship management"},
                "mindset_shifts": [
                    {
                        "before": "I used to treat negotiation as winning.",
                        "after": "I now see negotiation as relationship management.",
                        "evidence": [{"source": "Podcast summary", "supporting_concept": "relationship management"}],
                        "confidence": 0.95,
                    }
                ],
                "cross_content_patterns": ["Negotiation shows up across the week's learning."],
                "professional_actions": ["Pause before responding in difficult conversations."],
            }

    def failing_runner(*_args, **_kwargs):
        raise WeeklyReviewGenerationError("weekly review quality gate failed: demo")

    weekly_review_script.ReflectionAnalyzer = lambda: FakeReflectionAnalyzer()
    weekly_review_script.run_weekly_review_generation = failing_runner
    try:
        exit_code = weekly_review_script.main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        )
    finally:
        weekly_review_script.run_weekly_review_generation = original_runner
        weekly_review_script.ReflectionAnalyzer = original_analyzer

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ReflectionContext loaded successfully." in captured.out
    assert "Generation failed" in captured.out
    assert "Reason:" in captured.out
    assert "weekly review quality gate failed" in captured.out


def test_weekly_review_generator_script_reflection_validation_failure_visible(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    original_analyzer = weekly_review_script.ReflectionAnalyzer

    class FailingReflectionAnalyzer:
        def generate(self, weekly_learning_context):
            raise weekly_review_script.ReflectionGenerationError("reflection context missing weekly_theme")

    weekly_review_script.ReflectionAnalyzer = lambda: FailingReflectionAnalyzer()
    try:
        exit_code = weekly_review_script.main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        )
    finally:
        weekly_review_script.ReflectionAnalyzer = original_analyzer

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ReflectionContext validation failed." in captured.out
    assert "Reason:" in captured.out
    assert "reflection context missing weekly_theme" in captured.out


def test_weekly_review_generation_persists_reflection_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("WEEKLY_REFLECTION_PROVIDER", "placeholder")
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    reflection_output = Path("output/reflection_context.json")
    if reflection_output.exists():
        reflection_output.unlink()
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = run_weekly_review_generation(
        input_path,
        output_path=output_path,
        provider=FakeWeeklyReviewProvider(),
    )

    assert result.reflection_context_path == Path("output/reflection_context.json").resolve()
    assert result.reflection_context_path.exists()


def test_weekly_review_generator_script_reports_quality_score(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    output_path = tmp_path / "weekly_review.json"
    input_path.write_text(
        json.dumps(sample_weekly_learning_context(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    original_runner = weekly_review_script.run_weekly_review_generation
    original_analyzer = weekly_review_script.ReflectionAnalyzer

    class FakeReflectionAnalyzer:
        def generate(self, weekly_learning_context):
            return {
                "weekly_theme": {"category": "Negotiation", "theme": "Negotiation as relationship management"},
                "mindset_shifts": [
                    {
                        "before": "I used to treat negotiation as winning.",
                        "after": "I now see negotiation as relationship management.",
                        "evidence": [{"source": "Podcast summary", "supporting_concept": "relationship management"}],
                        "confidence": 0.95,
                    }
                ],
                "cross_content_patterns": ["Negotiation shows up across the week's learning."],
                "professional_actions": ["Pause before responding in difficult conversations."],
            }

    def fake_runner(*_args, **_kwargs):
        output_path.write_text(
            json.dumps(FakeWeeklyReviewProvider().generate("", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return type(
            "Result",
            (),
            {
                "payload": FakeWeeklyReviewProvider().generate("", {}),
                "output_path": output_path,
                "quality_report": {
                    "passed": True,
                    "score": 92,
                    "issues": [],
                    "suggestions": [],
                },
            },
        )()

    weekly_review_script.ReflectionAnalyzer = lambda: FakeReflectionAnalyzer()
    weekly_review_script.run_weekly_review_generation = fake_runner
    try:
        exit_code = weekly_review_script.main(
            [
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
        )
    finally:
        weekly_review_script.run_weekly_review_generation = original_runner
        weekly_review_script.ReflectionAnalyzer = original_analyzer

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Score: 92/100" in captured.out
    assert "Passed: true" in captured.out
