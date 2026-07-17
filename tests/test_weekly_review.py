from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.workflow.weekly_review_pipeline import (
    fetch_weekly_learning_data,
    run_weekly_review_workflow,
)


class FakeQueryResult:
    def __init__(self, results):
        self._results = results

    def get(self, key, default=None):
        if key == "results":
            return self._results
        return default


class FakeDataSources:
    def __init__(self, podcast_results=None, expression_results=None, weekly_results=None):
        self.podcast_results = podcast_results or []
        self.expression_results = expression_results or []
        self.weekly_results = weekly_results or []
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        data_source_id = kwargs.get("data_source_id")
        if data_source_id == "podcast_db":
            return FakeQueryResult(self.podcast_results)
        if data_source_id == "weekly_db":
            return FakeQueryResult(self.weekly_results)
        return FakeQueryResult(self.expression_results)


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


class FakeBlocks:
    def __init__(self):
        self.children = type("Children", (), {"append": lambda self, **kwargs: {}})()


class FakeNotion:
    def __init__(self, podcast_results=None, expression_results=None, weekly_results=None):
        self.data_sources = FakeDataSources(podcast_results, expression_results, weekly_results)
        self.pages = FakePages()
        self.blocks = FakeBlocks()


def podcast_page(page_id: str, title: str, topic: str = "AI", difficulty: str = "Intermediate", short_summary: str = "Short summary"):
    return {
        "id": page_id,
        "properties": {
            "Title": {"title": [{"plain_text": title, "text": {"content": title}}]},
            "Topic": {"select": {"name": topic}},
            "Difficulty": {"select": {"name": difficulty}},
            "Short Summary": {"rich_text": [{"plain_text": short_summary, "text": {"content": short_summary}}]},
        },
    }


def expression_page(page_id: str, title: str, podcast_id: str, category: str = "Business Phrase", meaning: str = "Meaning", usage_context: str = "Context"):
    return {
        "id": page_id,
        "properties": {
            "Expression": {"title": [{"plain_text": title, "text": {"content": title}}]},
            "Category": {"select": {"name": category}},
            "Meaning": {"rich_text": [{"plain_text": meaning, "text": {"content": meaning}}]},
            "Usage Context": {"rich_text": [{"plain_text": usage_context, "text": {"content": usage_context}}]},
            "Review Status": {"select": {"name": "New"}},
            "Source Podcast": {"relation": [{"id": podcast_id}]},
        },
    }


def test_empty_week_fetches_no_data(tmp_path: Path) -> None:
    notion = FakeNotion()

    data = fetch_weekly_learning_data(
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
        today=None,
    )

    assert data.podcasts == []
    assert data.expressions == []


def test_weekly_review_workflow_collects_podcasts_and_expressions(tmp_path: Path) -> None:
    notion = FakeNotion(
        podcast_results=[podcast_page("podcast_1", "Episode 1")],
        expression_results=[expression_page("expr_1", "take ownership", "podcast_1")],
        weekly_results=[],
    )
    analysis_path = tmp_path / "weekly_review.json"
    analysis_path.write_text(
        '{"week":"2026-W29","date":"2026-07-17","statistics":{"podcast_count":1,"expression_count":1,"category_distribution":{"Business Phrase":1}},"summary":{"english":"Summary","chinese":"总结"},"key_learning_points":["Point"],"recommended_review":[{"expression":"take ownership","reason":"Useful"}]}',
        encoding="utf-8",
    )

    result = run_weekly_review_workflow(
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
        weekly_database_id="weekly_db",
        data_dir=tmp_path,
        generated_analysis_path=analysis_path,
    )

    assert result.publish_result.page_id == "weekly_page"
    assert notion.pages.create_calls
    assert notion.pages.create_calls[0]["properties"]["Expression Count"] == {"number": 1}
    assert notion.pages.create_calls[0]["properties"]["Podcasts"] == {"relation": [{"id": "podcast_1"}]}


def test_multiple_podcasts_keep_all_relations(tmp_path: Path) -> None:
    notion = FakeNotion(
        podcast_results=[
            podcast_page("podcast_1", "Episode 1"),
            podcast_page("podcast_2", "Episode 2"),
        ],
        expression_results=[
            expression_page("expr_1", "take ownership", "podcast_1"),
            expression_page("expr_2", "move the needle", "podcast_2"),
        ],
        weekly_results=[],
    )
    analysis_path = tmp_path / "weekly_review.json"
    analysis_path.write_text(
        '{"week":"2026-W29","date":"2026-07-17","statistics":{"podcast_count":2,"expression_count":2,"category_distribution":{"Business Phrase":2}},"summary":{"english":"Summary","chinese":"总结"},"key_learning_points":["Point"],"recommended_review":[{"expression":"take ownership","reason":"Useful"}]}',
        encoding="utf-8",
    )

    result = run_weekly_review_workflow(
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
        weekly_database_id="weekly_db",
        data_dir=tmp_path,
        generated_analysis_path=analysis_path,
    )

    assert result.publish_result.page_id == "weekly_page"
    assert notion.pages.create_calls[0]["properties"]["Podcasts"] == {
        "relation": [{"id": "podcast_1"}, {"id": "podcast_2"}]
    }
