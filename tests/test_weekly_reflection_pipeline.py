from __future__ import annotations

import json
from pathlib import Path

from src.workflow.weekly_reflection_pipeline import (
    WeeklyReflectionPipelineError,
    run_weekly_reflection_pipeline,
)


class FakePages:
    def __init__(self):
        self.create_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "reflection_page", "url": "https://notion.so/reflection_page"}


class FakeNotion:
    def __init__(self):
        self.pages = FakePages()


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
                "title": "Negotiation as Relationship Management",
                "date": "2026-07-17",
                "topic": "Negotiation",
                "difficulty": "Intermediate",
                "url": "https://example.com/1",
                "summary": {
                    "english": "This week centered on negotiation and framing.",
                    "chinese": "本周围绕谈判和 framing 展开。",
                },
                "key_takeaways": ["Negotiation is relationship management."],
                "transcript_available": True,
            }
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
                "source_page_id": "page_1",
                "highlight_type": "pink",
            }
        ],
    }


def sample_reflection_context() -> dict:
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
        "cross_content_patterns": ["Listening before influencing appears across the week's learning."],
        "professional_actions": ["Pause before replying in difficult conversations."],
    }


def sample_weekly_review() -> dict:
    return {
        "period": {
            "start_date": "2026-07-13",
            "end_date": "2026-07-20",
            "generated_at": "2026-07-20T12:00:00Z",
            "source": "Podcast Library",
        },
        "executive_summary": {
            "weekly_theme": "Negotiation as relationship management",
            "learning_summary": "This week centered on transferable communication patterns.",
            "key_takeaways": ["Negotiation is relationship management."],
        },
        "knowledge_insights": [
            {
                "insight": "Communication improves when I frame conversations carefully.",
                "why_it_matters": "It helps align expectations.",
                "professional_application": "Use the same framing in stakeholder updates.",
            }
        ],
        "language_growth": {
            "new_expressions": [
                {
                    "expression": "challenge assumptions",
                    "category": "Business Phrase",
                    "learning_value": "Useful for strategic discussions.",
                }
            ],
            "personal_vocabulary": [
                {
                    "word": "leverage",
                    "context": "Companies can leverage AI to redesign workflows.",
                    "professional_relevance": "Useful in business strategy conversations.",
                }
            ],
        },
        "career_application": [
            {
                "scenario": "Stakeholder Communication",
                "application": "Use clearer framing before proposing changes.",
            }
        ],
        "quality_score": 95,
        "source_page_ids": ["page_1"],
    }


def test_run_weekly_reflection_pipeline_success(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")

    reflection_output = tmp_path / "reflection_context.json"
    weekly_review_output = tmp_path / "weekly_review.json"
    notion = FakeNotion()
    published = {}

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_notion_config",
        lambda: type("Config", (), {"token": "secret", "podcast_database_id": "podcast_db"})(),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_weekly_reflection_database_id",
        lambda: "weekly_reflection_db",
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda input_path, output_path: type(
            "ReflectionResult",
            (),
            {
                "output_path": output_path,
                "payload": sample_reflection_context(),
            },
        )(),
    )

    def fake_run_weekly_review_generation(input_path, output_path):
        output_path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False), encoding="utf-8")
        reflection_output.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")
        return type(
            "ReviewResult",
            (),
            {
                "output_path": output_path,
                "payload": sample_weekly_review(),
                "quality_report": {"passed": True, "score": 91, "issues": [], "suggestions": []},
            },
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_weekly_review_generation",
        fake_run_weekly_review_generation,
    )
    def fake_publish_weekly_reflection(
        weekly_review,
        reflection_context,
        notion,
        weekly_reflection_database_id,
        podcast_database_id=None,
        pipeline_run_id="",
        reflection_context_id="",
    ):
        published["payload"] = {
            "weekly_review": weekly_review,
            "reflection_context": reflection_context,
            "weekly_reflection_database_id": weekly_reflection_database_id,
            "podcast_database_id": podcast_database_id,
            "pipeline_run_id": pipeline_run_id,
            "reflection_context_id": reflection_context_id,
            "notion": notion,
        }
        return type(
            "PublishResult",
            (),
            {"page_id": "reflection_page", "page_url": "https://notion.so/reflection_page"},
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.publish_weekly_reflection",
        fake_publish_weekly_reflection,
    )

    result = run_weekly_reflection_pipeline(
        weekly_learning_context_path=input_path,
        weekly_review_output_path=weekly_review_output,
        reflection_context_output_path=reflection_output,
        notion=notion,
        weekly_reflection_database_id="weekly_reflection_db",
        podcast_database_id="podcast_db",
    )

    assert result.publish_result.page_id == "reflection_page"
    assert result.reflection_context_path == reflection_output.resolve()
    assert result.weekly_review_path == weekly_review_output.resolve()
    assert result.quality_report["score"] == 91
    assert published["payload"]["weekly_reflection_database_id"] == "weekly_reflection_db"
    assert published["payload"]["podcast_database_id"] == "podcast_db"
    assert published["payload"]["pipeline_run_id"]
    assert published["payload"]["reflection_context_id"] == "reflection_context"
    assert published["payload"]["reflection_context"]["weekly_theme"]["theme"] == "Negotiation as relationship management"


def test_run_weekly_reflection_pipeline_reflection_failure(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("reflection failed")),
    )

    try:
        run_weekly_reflection_pipeline(
            weekly_learning_context_path=input_path,
            notion=FakeNotion(),
            weekly_reflection_database_id="weekly_reflection_db",
            podcast_database_id="podcast_db",
        )
    except WeeklyReflectionPipelineError as exc:
        assert "Failed step: Reflection Analysis" in str(exc)
    else:
        raise AssertionError("Expected WeeklyReflectionPipelineError")


def test_run_weekly_reflection_pipeline_quality_gate_failure(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_notion_config",
        lambda: type("Config", (), {"token": "secret", "podcast_database_id": "podcast_db"})(),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_weekly_reflection_database_id",
        lambda: "weekly_reflection_db",
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda input_path, output_path: (
            output_path.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")
            or type("ReflectionResult", (), {"output_path": output_path, "payload": sample_reflection_context()})()
        ),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_weekly_review_generation",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("quality gate failed")),
    )

    try:
        run_weekly_reflection_pipeline(
            weekly_learning_context_path=input_path,
            notion=FakeNotion(),
            weekly_reflection_database_id="weekly_reflection_db",
            podcast_database_id="podcast_db",
        )
    except WeeklyReflectionPipelineError as exc:
        assert "Failed step: Weekly Review / Quality Gate" in str(exc)
    else:
        raise AssertionError("Expected WeeklyReflectionPipelineError")


def test_run_weekly_reflection_pipeline_notion_writer_failure(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_notion_config",
        lambda: type("Config", (), {"token": "secret", "podcast_database_id": "podcast_db"})(),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_weekly_reflection_database_id",
        lambda: "weekly_reflection_db",
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda input_path, output_path: (
            output_path.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")
            or type("ReflectionResult", (), {"output_path": output_path, "payload": sample_reflection_context()})()
        ),
    )

    def fake_run_weekly_review_generation(input_path, output_path):
        output_path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False), encoding="utf-8")
        return type(
            "ReviewResult",
            (),
            {
                "output_path": output_path,
                "payload": sample_weekly_review(),
                "quality_report": {"passed": True, "score": 92, "issues": [], "suggestions": []},
            },
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_weekly_review_generation",
        fake_run_weekly_review_generation,
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.publish_weekly_reflection",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("writer failed")),
    )

    try:
        run_weekly_reflection_pipeline(
            weekly_learning_context_path=input_path,
            notion=FakeNotion(),
            weekly_reflection_database_id="weekly_reflection_db",
            podcast_database_id="podcast_db",
        )
    except WeeklyReflectionPipelineError as exc:
        assert "Failed step: Notion Publish" in str(exc)
    else:
        raise AssertionError("Expected WeeklyReflectionPipelineError")


def test_run_weekly_reflection_pipeline_writes_run_metadata_and_logs(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")
    reflection_output = tmp_path / "reflection_context.json"
    weekly_review_output = tmp_path / "weekly_review.json"
    pipeline_run_output = tmp_path / "pipeline_run.json"
    logs_dir = tmp_path / "logs"

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_notion_config",
        lambda: type("Config", (), {"token": "secret", "podcast_database_id": "podcast_db"})(),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_weekly_reflection_database_id",
        lambda: "weekly_reflection_db",
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda input_path, output_path: type("ReflectionResult", (), {"output_path": output_path, "payload": sample_reflection_context()})(),
    )

    def fake_run_weekly_review_generation(input_path, output_path):
        output_path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False), encoding="utf-8")
        reflection_output.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")
        return type(
            "ReviewResult",
            (),
            {
                "output_path": output_path,
                "payload": sample_weekly_review(),
                "quality_report": {"passed": True, "score": 91, "issues": [], "suggestions": []},
            },
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_weekly_review_generation",
        fake_run_weekly_review_generation,
    )
    def fake_publish_weekly_reflection(
        weekly_review,
        reflection_context,
        notion,
        weekly_reflection_database_id,
        podcast_database_id=None,
        pipeline_run_id="",
        reflection_context_id="",
    ):
        return type(
            "PublishResult",
            (),
            {"page_id": "reflection_page", "page_url": "https://notion.so/reflection_page"},
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.publish_weekly_reflection",
        fake_publish_weekly_reflection,
    )

    result = run_weekly_reflection_pipeline(
        weekly_learning_context_path=input_path,
        weekly_review_output_path=weekly_review_output,
        reflection_context_output_path=reflection_output,
        notion=FakeNotion(),
        weekly_reflection_database_id="weekly_reflection_db",
        podcast_database_id="podcast_db",
        pipeline_run_output_path=pipeline_run_output,
        logs_dir=logs_dir,
    )

    assert result.publish_result is not None
    assert pipeline_run_output.exists()
    run_payload = json.loads(pipeline_run_output.read_text(encoding="utf-8"))
    assert run_payload["status"] == "success"
    assert run_payload["run_id"]
    assert run_payload["period"] == "2026-07-13..2026-07-20"
    assert run_payload["steps"]["extraction"] == "success"
    assert run_payload["steps"]["reflection"] == "success"
    assert run_payload["steps"]["generation"] == "success"
    assert run_payload["steps"]["quality_gate"] == "passed"
    assert run_payload["steps"]["notion"] == "success"
    log_files = list(logs_dir.glob("weekly_reflection_*.log"))
    assert log_files
    log_text = log_files[0].read_text(encoding="utf-8")
    assert '"step": "extraction"' in log_text
    assert '"status": "success"' in log_text


def test_run_weekly_reflection_pipeline_dry_run_skips_notion(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")
    reflection_output = tmp_path / "reflection_context.json"
    weekly_review_output = tmp_path / "weekly_review.json"
    pipeline_run_output = tmp_path / "pipeline_run.json"
    logs_dir = tmp_path / "logs"

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_notion_config",
        lambda: type("Config", (), {"token": "secret", "podcast_database_id": "podcast_db"})(),
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.load_weekly_reflection_database_id",
        lambda: "weekly_reflection_db",
    )
    def fake_run_reflection_analysis(input_path, output_path):
        output_path.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")
        return type("ReflectionResult", (), {"output_path": output_path, "payload": sample_reflection_context()})()

    def fake_run_weekly_review_generation(input_path, output_path):
        output_path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False), encoding="utf-8")
        return type(
            "ReviewResult",
            (),
            {
                "output_path": output_path,
                "payload": sample_weekly_review(),
                "quality_report": {"passed": True, "score": 91, "issues": [], "suggestions": []},
            },
        )()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        fake_run_reflection_analysis,
    )
    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_weekly_review_generation",
        fake_run_weekly_review_generation,
    )
    notion_calls = {}

    def fake_publish_weekly_reflection(*args, **kwargs):
        notion_calls["called"] = True
        return type("PublishResult", (), {"page_id": "reflection_page", "page_url": "https://notion.so/reflection_page"})()

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.publish_weekly_reflection",
        fake_publish_weekly_reflection,
    )

    result = run_weekly_reflection_pipeline(
        weekly_learning_context_path=input_path,
        weekly_review_output_path=weekly_review_output,
        reflection_context_output_path=reflection_output,
        notion=FakeNotion(),
        weekly_reflection_database_id="weekly_reflection_db",
        podcast_database_id="podcast_db",
        dry_run=True,
        pipeline_run_output_path=pipeline_run_output,
        logs_dir=logs_dir,
    )

    assert result.dry_run is True
    assert result.publish_result is None
    assert notion_calls == {}
    run_payload = json.loads(pipeline_run_output.read_text(encoding="utf-8"))
    assert run_payload["status"] == "success"
    assert run_payload["steps"]["notion"] == "skipped"


def test_run_weekly_reflection_pipeline_records_failure_state(tmp_path: Path, monkeypatch) -> None:
    input_path = tmp_path / "weekly_learning_context.json"
    input_path.write_text(json.dumps(sample_weekly_learning_context(), ensure_ascii=False), encoding="utf-8")
    pipeline_run_output = tmp_path / "pipeline_run.json"
    logs_dir = tmp_path / "logs"

    monkeypatch.setattr(
        "src.workflow.weekly_reflection_pipeline.run_reflection_analysis",
        lambda *args, **kwargs: (_ for _ in ()).throw(Exception("reflection failed")),
    )

    try:
        run_weekly_reflection_pipeline(
            weekly_learning_context_path=input_path,
            notion=FakeNotion(),
            weekly_reflection_database_id="weekly_reflection_db",
            podcast_database_id="podcast_db",
            pipeline_run_output_path=pipeline_run_output,
            logs_dir=logs_dir,
        )
    except WeeklyReflectionPipelineError:
        pass
    else:
        raise AssertionError("Expected WeeklyReflectionPipelineError")

    run_payload = json.loads(pipeline_run_output.read_text(encoding="utf-8"))
    assert run_payload["status"] == "failed"
    assert run_payload["steps"]["reflection"] == "failed"
