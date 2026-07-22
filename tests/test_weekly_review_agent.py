from __future__ import annotations

import json
from pathlib import Path

from src.agents.weekly_review_agent import (
    WeeklyReviewAgentError,
    build_weekly_review_dry_run_plan,
    run_weekly_review_agent,
)


class FakePages:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "weekly_page", "url": "https://notion.so/weekly_page"}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"], "url": "https://notion.so/weekly_page"}


class FakeNotion:
    def __init__(self):
        self.pages = FakePages()
        self.data_sources = type("DataSources", (), {})()


def sample_analysis() -> dict:
    return {
        "week": "2026-W29",
        "podcast_summary": {
            "english": "This week centered on AI leadership and negotiation.",
            "chinese": "本周围绕 AI 领导力和谈判展开。",
        },
        "key_topics": ["AI Leadership", "Negotiation"],
        "expression_review": [
            {
                "expression": "move the needle",
                "category": "Native Expression",
                "meaning": "Create meaningful impact",
                "original_context": "You need actions that move the needle.",
                "learning_note": "Revisit this expression.",
                "review_priority": 100,
            },
            {
                "expression": "take ownership",
                "category": "Business Phrase",
                "meaning": "Accept responsibility",
                "original_context": "Companies need to take ownership of AI adoption.",
                "learning_note": "Useful business phrase.",
                "review_priority": 60,
            },
        ],
        "category_distribution": {
            "Native Expression": 1,
            "Business Phrase": 1,
        },
        "learning_insights": [
            {
                "insight": "The week strengthened transferable language.",
                "evidence": "Expressions pointed to leadership language.",
                "why_it_matters": "Reusable language matters.",
            }
        ],
        "next_week_plan": ["Practice the strongest expressions.", "Revisit the summary."],
        "vocabulary_memory": [
            {
                "word": "leverage",
                "context": "Companies can leverage AI to redesign workflows.",
                "meaning": "利用资源创造优势",
                "professional_category": "Business Strategy",
                "my_usage": "We need to leverage technology.",
                "review_status": "New",
            }
        ],
    }


def test_build_weekly_review_dry_run_plan_formats_preview() -> None:
    plan = build_weekly_review_dry_run_plan(sample_analysis())

    assert plan.week == "2026-W29"
    assert plan.total_expression_items == 2
    assert plan.total_vocabulary_items == 1
    assert plan.top_expressions[0]["expression"] == "move the needle"
    assert plan.preview_payload["week"] == "2026-W29"


def test_run_weekly_review_agent_dry_run_does_not_publish(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    analysis_path = tmp_path / "2026-W29.json"
    analysis_path.write_text(json.dumps(sample_analysis(), ensure_ascii=False), encoding="utf-8")

    notion_calls = {"created": 0}

    monkeypatch.setattr("src.agents.weekly_review_agent.load_notion_config", lambda: type("Config", (), {
        "token": "secret",
        "weekly_database_id": "weekly_db",
        "vocabulary_database_id": "vocab_db",
    })())

    def fake_create_notion_client(token):
        notion_calls["created"] += 1
        raise AssertionError("Notion client should not be created in dry-run mode")

    monkeypatch.setattr("src.agents.weekly_review_agent.create_notion_client", fake_create_notion_client)

    result = run_weekly_review_agent(analysis_path, dry_run=True)

    captured = capsys.readouterr()
    assert result.kind == "weekly_review_dry_run"
    assert "Weekly Review dry run" in captured.out
    assert "Total expressions:" in captured.out
    assert notion_calls["created"] == 0


def test_run_weekly_review_agent_publishes_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    analysis_path = tmp_path / "2026-W29.json"
    analysis_path.write_text(json.dumps(sample_analysis(), ensure_ascii=False), encoding="utf-8")

    fake_notion = FakeNotion()
    published = {}

    monkeypatch.setattr("src.agents.weekly_review_agent.load_notion_config", lambda: type("Config", (), {
        "token": "secret",
        "weekly_database_id": "weekly_db",
        "vocabulary_database_id": "vocab_db",
    })())
    monkeypatch.setattr("src.agents.weekly_review_agent.create_notion_client", lambda token: fake_notion)

    def fake_publish_weekly_review(payload, notion, weekly_database_id, vocabulary_database_id=None):
        published["payload"] = payload
        published["weekly_database_id"] = weekly_database_id
        published["vocabulary_database_id"] = vocabulary_database_id
        return type("Result", (), {"page_id": "weekly_page", "page_url": "https://notion.so/weekly_page"})()

    monkeypatch.setattr("src.agents.weekly_review_agent.publish_weekly_review", fake_publish_weekly_review)

    result = run_weekly_review_agent(analysis_path, dry_run=False)

    assert result.kind == "weekly_review_page"
    assert published["weekly_database_id"] == "weekly_db"
    assert published["vocabulary_database_id"] == "vocab_db"
    assert published["payload"].week == "2026-W29"
    assert published["payload"].expression_upgrade[0]["expression"] == "move the needle"


def test_run_weekly_review_agent_rejects_non_object(tmp_path: Path) -> None:
    analysis_path = tmp_path / "bad.json"
    analysis_path.write_text("[]", encoding="utf-8")

    try:
        run_weekly_review_agent(analysis_path, dry_run=True)
    except WeeklyReviewAgentError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("Expected WeeklyReviewAgentError")
