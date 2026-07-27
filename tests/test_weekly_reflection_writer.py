from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.test_weekly_reflection_writer as weekly_reflection_script
from src.notion.weekly_reflection_writer import (
    WeeklyReflectionWriterError,
    WeeklyReflectionPublishPayload,
    load_reflection_context_json,
    load_weekly_review_json,
    publish_weekly_reflection,
    weekly_reflection_body_blocks,
    weekly_reflection_page_properties,
)


class FakePages:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "reflection_page", "url": "https://notion.so/reflection_page"}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"], "url": "https://notion.so/reflection_page"}


class FakeDataSources:
    def __init__(self, results=None):
        self.results = results or []
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {"results": self.results}


class FakeBlockChildren:
    def __init__(self):
        self.list_calls = []
        self.append_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
        return {"results": [{"id": "old_block_1"}, {"id": "old_block_2"}], "has_more": False}

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        return {"results": []}


class FakeBlocks:
    def __init__(self):
        self.children = FakeBlockChildren()
        self.delete_calls = []

    def delete(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {"id": kwargs["block_id"]}


class FakeNotion:
    def __init__(self, results=None):
        self.data_sources = FakeDataSources(results=results)
        self.pages = FakePages()
        self.blocks = FakeBlocks()


def sample_weekly_review() -> dict:
    return {
        "period": {
            "start_date": "2026-07-13",
            "end_date": "2026-07-20",
            "generated_at": "2026-07-20T12:00:00Z",
            "source": "Podcast Library",
        },
        "core_idea": {
            "idea": "Negotiation is relationship management.",
            "why_it_matters": "It protects trust while solving difficult problems.",
            "refined_understanding": "The relationship is part of the outcome.",
        },
        "mindset_shift": {
            "before": "I treated negotiation as winning.",
            "now": "I now treat it as joint problem solving.",
        },
        "ideas_worth_compounding": [
            {"idea": "Listening reveals hidden interests.", "why_it_matters": "It prevents solving the wrong problem.", "application": "Ask before proposing.", "source_reference": "Podcast A"},
            {"idea": "Framing shapes collaboration.", "why_it_matters": "It reduces defensiveness.", "application": "Name the shared outcome.", "source_reference": "Podcast B"},
        ],
        "expressions_worth_reusing": [
            {"expression": "challenge assumptions", "contextual_meaning": "Test beliefs constructively.", "reusable_example": "Let's challenge our assumptions.", "communication_function": "Constructive challenge"},
            {"expression": "joint problem solving", "contextual_meaning": "Collaborate on a shared problem.", "reusable_example": "Let's use joint problem solving.", "communication_function": "Collaborative framing"},
            {"expression": "building long-term relationships", "contextual_meaning": "Prioritize durable trust.", "reusable_example": "This supports long-term relationships.", "communication_function": "Long-term orientation"},
        ],
        "language_thinking_connection": "Joint problem solving turns disagreement into a shared object of attention and gives the user a more precise collaborative frame.",
        "next_week_application": {"scenario": "Stakeholder challenge", "behavior": "Restate the shared goal.", "phrase_to_use": "Let's treat this as joint problem solving.", "completion_condition": "Use it once and record the response."},
        "sources": [
            {"page_id": "page_1", "title": "Podcast A", "url": "https://example.com/1"},
            {"page_id": "page_2", "title": "Podcast B", "url": "https://example.com/2"},
        ],
        "quality_score": 95,
        "source_page_ids": ["page_1", "page_2"],
    }


def sample_reflection_context() -> dict:
    return {
        "weekly_theme": {
            "category": "Negotiation",
            "theme": "Negotiation as relationship management",
        },
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
        "cross_content_patterns": [
            "Listening before influencing appears across the week's learning."
        ],
        "professional_actions": [
            "Pause before replying in difficult conversations."
        ],
    }


def test_weekly_reflection_writer_properties_use_expected_mapping() -> None:
    weekly_review = sample_weekly_review()
    reflection_context = sample_reflection_context()
    properties = weekly_reflection_page_properties(
        WeeklyReflectionPublishPayload(
            weekly_review=weekly_review,
            reflection_context=reflection_context,
            quality_score=95,
        )
    )

    assert properties["Week"]["title"][0]["text"]["content"].startswith("Week 29 Reflection")
    assert properties["Date"]["date"]["start"] == "2026-07-13"
    assert set(properties) == {"Week", "Date", "Podcasts"}
    assert properties["Podcasts"]["relation"] == [{"id": "page_1"}, {"id": "page_2"}]


def test_weekly_reflection_body_blocks_starts_with_toc_and_sections() -> None:
    payload = WeeklyReflectionPublishPayload(
        weekly_review=sample_weekly_review(),
        reflection_context=sample_reflection_context(),
        quality_score=95,
    )

    blocks = weekly_reflection_body_blocks(payload, podcast_database_id="podcast_db")

    assert blocks[0]["type"] == "table_of_contents"
    assert sum(block["type"] == "table_of_contents" for block in blocks) == 1
    assert blocks[1]["type"] == "heading_2"
    assert blocks[1]["heading_2"]["rich_text"][0]["text"]["content"] == "1. This Week's Core Idea"
    assert not any(block["type"] == "bulleted_list_item" and block["bulleted_list_item"]["rich_text"][0]["text"]["content"].startswith("1. ") for block in blocks)
    assert any(block["type"] == "table" and block["table"]["table_width"] == 4 for block in blocks)
    headings = [block["heading_2"]["rich_text"][0]["text"]["content"] for block in blocks if block["type"] == "heading_2"]
    assert headings == [
        "1. This Week's Core Idea",
        "2. How My Thinking Changed",
        "3. Ideas Worth Compounding",
        "4. Expressions Worth Reusing",
        "5. Language-Thinking Connection",
        "6. One Application for Next Week",
        "7. Sources",
    ]


def test_publish_weekly_reflection_creates_page_with_expected_payload() -> None:
    notion = FakeNotion()
    result = publish_weekly_reflection(
        sample_weekly_review(),
        sample_reflection_context(),
        notion=notion,
        weekly_reflection_database_id="weekly_reflection_db",
        podcast_database_id="podcast_db",
    )

    assert result.page_id == "reflection_page"
    assert notion.pages.create_calls
    call = notion.pages.create_calls[0]
    assert call["parent"] == {"data_source_id": "weekly_reflection_db"}
    assert call["properties"]["Week"]["title"][0]["text"]["content"].startswith("Week 29 Reflection")
    assert call["properties"]["Date"]["date"]["start"] == "2026-07-13"
    assert call["properties"]["Podcasts"]["relation"] == [{"id": "page_1"}, {"id": "page_2"}]
    assert call["children"][0]["type"] == "table_of_contents"
    assert any(
        block["type"] == "heading_2" and block["heading_2"]["rich_text"][0]["text"]["content"] == "1. This Week's Core Idea"
        for block in call["children"]
    )


def test_identity_query_failure_stops_before_page_create() -> None:
    notion = FakeNotion()
    notion.data_sources.query = lambda **_kwargs: (_ for _ in ()).throw(
        RuntimeError("private query failure")
    )

    with pytest.raises(
        WeeklyReflectionWriterError,
        match="Failed to query existing Weekly Reflection identity",
    ):
        publish_weekly_reflection(
            sample_weekly_review(),
            sample_reflection_context(),
            notion=notion,
            weekly_reflection_database_id="weekly_reflection_db",
            podcast_database_id="podcast_db",
        )

    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []


def test_publish_weekly_reflection_updates_existing_page_when_same_period_and_sources() -> None:
    notion = FakeNotion(
        results=[
            {
        "id": "existing_page",
        "properties": {
                    "Date": {"date": {"start": "2026-07-13", "end": "2026-07-20"}},
                    "Week": {"title": [{"text": {"content": "Week 29 Reflection — Negotiation as relationship management"}}]},
                    "Podcasts": {
                        "relation": [{"id": "page_1"}, {"id": "page_2"}],
                    },
                },
            }
        ]
    )

    result = publish_weekly_reflection(
        sample_weekly_review(),
        sample_reflection_context(),
        notion=notion,
        weekly_reflection_database_id="weekly_reflection_db",
        podcast_database_id="podcast_db",
    )

    assert result.page_id == "existing_page"
    assert notion.pages.update_calls
    assert not notion.pages.create_calls
    assert notion.blocks.delete_calls == [
        {"block_id": "old_block_1"},
        {"block_id": "old_block_2"},
    ]
    assert notion.blocks.children.append_calls[0]["block_id"] == "existing_page"
    replacement = notion.blocks.children.append_calls[0]["children"]
    assert sum(block["type"] == "table_of_contents" for block in replacement) == 1


def test_publish_weekly_reflection_rejects_invalid_weekly_review() -> None:
    try:
        publish_weekly_reflection(
            {"period": {}},
            sample_reflection_context(),
            notion=FakeNotion(),
            weekly_reflection_database_id="weekly_reflection_db",
        )
    except WeeklyReflectionWriterError as exc:
        assert "Weekly review period must contain" in str(exc)
    else:
        raise AssertionError("Expected WeeklyReflectionWriterError")


def test_load_weekly_review_json_reads_object(tmp_path: Path) -> None:
    path = tmp_path / "weekly_review.json"
    path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False), encoding="utf-8")

    payload = load_weekly_review_json(path)
    assert payload["period"]["start_date"] == "2026-07-13"


def test_load_reflection_context_json_reads_object(tmp_path: Path) -> None:
    path = tmp_path / "reflection_context.json"
    path.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False), encoding="utf-8")

    payload = load_reflection_context_json(path)
    assert payload["weekly_theme"]["theme"] == "Negotiation as relationship management"


def test_weekly_reflection_writer_script_smoke(tmp_path: Path, capsys, monkeypatch) -> None:
    weekly_review_path = tmp_path / "weekly_review.json"
    reflection_path = tmp_path / "reflection_context.json"
    weekly_review_path.write_text(json.dumps(sample_weekly_review(), ensure_ascii=False, indent=2), encoding="utf-8")
    reflection_path.write_text(json.dumps(sample_reflection_context(), ensure_ascii=False, indent=2), encoding="utf-8")

    original_publish = weekly_reflection_script.publish_weekly_reflection

    def fake_publish(weekly_review, reflection_context, notion=None, weekly_reflection_database_id=None, podcast_database_id=None):
        assert weekly_review["period"]["start_date"] == "2026-07-13"
        assert reflection_context["weekly_theme"]["theme"] == "Negotiation as relationship management"
        return type("Result", (), {"page_id": "reflection_page", "page_url": "https://notion.so/reflection_page"})()

    monkeypatch.setattr(weekly_reflection_script, "publish_weekly_reflection", fake_publish)

    try:
        exit_code = weekly_reflection_script.main(
            [
                "--weekly-review-json",
                str(weekly_review_path),
                "--reflection-json",
                str(reflection_path),
                "--podcast-database-id",
                "podcast_db",
            ]
        )
    finally:
        monkeypatch.setattr(weekly_reflection_script, "publish_weekly_reflection", original_publish)

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Weekly Reflection Writer Report" in captured.out
    assert "ReflectionContext loaded: YES" in captured.out
    assert "WeeklyReview loaded: YES" in captured.out
    assert "Page created: YES" in captured.out
    assert "Page ID:" in captured.out
