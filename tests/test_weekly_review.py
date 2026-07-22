from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import logging

from src.workflow.weekly_review_pipeline import (
    _extract_multi_select_property,
    _extract_rich_text_property,
    _extract_select_property,
    _extract_title_property,
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


class FakeDatabases:
    def __init__(self, podcast_results=None, expression_results=None, weekly_results=None):
        self.podcast_results = podcast_results or []
        self.expression_results = expression_results or []
        self.weekly_results = weekly_results or []
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        database_id = kwargs.get("database_id")
        if database_id == "podcast_db":
            return FakeQueryResult(self.podcast_results)
        if database_id == "weekly_db":
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
        self.databases = FakeDatabases(podcast_results, expression_results, weekly_results)
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


def test_extractors_return_empty_string_for_null_notion_fields(caplog) -> None:
    page = {
        "id": "page_1",
        "properties": {
            "Title": {"title": None},
            "Topic": {"select": None},
            "Difficulty": {"multi_select": None},
            "Short Summary": {"rich_text": None},
        },
    }

    caplog.set_level(logging.DEBUG)

    assert _extract_title_property(page) == ""
    assert _extract_select_property(page, "Topic") == ""
    assert _extract_multi_select_property(page, "Difficulty") == ""
    assert _extract_rich_text_property(page, "Short Summary") == ""

    debug_lines = "\n".join(record.message for record in caplog.records)
    assert "page_id=page_1" in debug_lines
    assert "property_name=Title" in debug_lines
    assert "property_name=Topic" in debug_lines
    assert "property_name=Difficulty" in debug_lines
    assert "property_name=Short Summary" in debug_lines


def test_extractors_return_empty_string_when_property_missing(caplog) -> None:
    page = {"id": "page_2", "properties": {}}

    caplog.set_level(logging.DEBUG)

    assert _extract_title_property(page) == ""
    assert _extract_select_property(page, "Topic") == ""
    assert _extract_multi_select_property(page, "Tags") == ""
    assert _extract_rich_text_property(page, "Short Summary") == ""

    debug_lines = "\n".join(record.message for record in caplog.records)
    assert "page_id=page_2" in debug_lines


def test_weekly_review_workflow_collects_podcasts_and_expressions(tmp_path: Path) -> None:
    notion = FakeNotion(
        podcast_results=[podcast_page("podcast_1", "Episode 1")],
        expression_results=[expression_page("expr_1", "take ownership", "podcast_1")],
        weekly_results=[],
    )
    analysis_path = tmp_path / "weekly_review.json"
    analysis_path.write_text(
        '{"week":"2026-W29","executive_summary":{"overview":"Summary","takeaway":"总结","highlights":["Topic"]},"knowledge_insights":[{"what_happened":"Something happened","why_it_matters":"It matters","my_interpretation":"Interpretation","application":"Apply it"}],"expression_upgrade":[{"expression":"take ownership","meaning":"Accept responsibility","context":"Useful","example":"We need to take ownership."}],"vocabulary_memory":[],"career_reflection":{"questions":["What changed?"],"possible_applications":["Use it at work."]},"next_learning_direction":["Plan"]}',
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
    assert notion.pages.create_calls[0]["properties"]["Week"]["title"][0]["text"]["content"] == "2026-W29"
    assert notion.pages.create_calls[0]["properties"]["Status"] == {"select": {"name": "Draft"}}
    assert notion.data_sources.query_calls[0]["data_source_id"] == "podcast_db"
    assert notion.data_sources.query_calls[1]["data_source_id"] == "expression_db"


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
        '{"week":"2026-W29","executive_summary":{"overview":"Summary","takeaway":"总结","highlights":["Topic"]},"knowledge_insights":[{"what_happened":"Something happened","why_it_matters":"It matters","my_interpretation":"Interpretation","application":"Apply it"}],"expression_upgrade":[{"expression":"take ownership","meaning":"Accept responsibility","context":"Useful","example":"We need to take ownership."}],"vocabulary_memory":[],"career_reflection":{"questions":["What changed?"],"possible_applications":["Use it at work."]},"next_learning_direction":["Plan"]}',
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
    assert notion.pages.create_calls[0]["properties"]["Week"]["title"][0]["text"]["content"] == "2026-W29"
    assert notion.data_sources.query_calls[0]["data_source_id"] == "podcast_db"


def test_weekly_review_workflow_preserves_vocabulary_memory(tmp_path: Path) -> None:
    notion = FakeNotion(
        podcast_results=[podcast_page("podcast_1", "Episode 1")],
        expression_results=[expression_page("expr_1", "take ownership", "podcast_1")],
        weekly_results=[],
    )
    analysis_path = tmp_path / "weekly_review.json"
    analysis_path.write_text(
        '{"week":"2026-W29","executive_summary":{"overview":"Summary","takeaway":"总结","highlights":["Topic"]},"knowledge_insights":[{"what_happened":"Something happened","why_it_matters":"It matters","my_interpretation":"Interpretation","application":"Apply it"}],"expression_upgrade":[{"expression":"take ownership","meaning":"Accept responsibility","context":"Useful","example":"We need to take ownership."}],"vocabulary_memory":[{"word":"leverage","context":"Companies can leverage AI.","meaning":"Use resources effectively","professional_category":"Word","my_usage":"We can leverage AI tools to save time.","review_status":"New"}],"career_reflection":{"questions":["What changed?"],"possible_applications":["Use it at work."]},"next_learning_direction":["Plan"]}',
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
    assert notion.pages.create_calls[0]["properties"]["Week"]["title"][0]["text"]["content"] == "2026-W29"
