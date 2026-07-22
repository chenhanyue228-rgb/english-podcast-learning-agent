from __future__ import annotations

import os

from src.notion.setup_vocabulary_database import create_vocabulary_database
from src.notion.setup_vocabulary_database import sync_vocabulary_database_schema


class FakePages:
    def __init__(self):
        self.create_calls = []


class FakeDatabases:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {
            "id": "vocabulary_db",
            "data_sources": [{"id": "vocabulary_db"}],
        }

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs.get("database_id")}


class FakeNotion:
    def __init__(self):
        self.databases = FakeDatabases()
        self.pages = FakePages()


def test_create_vocabulary_database_returns_database_id(monkeypatch, tmp_path) -> None:
    notion = FakeNotion()
    env_path = tmp_path / ".env"
    env_path.write_text(
        "NOTION_TOKEN=secret\n"
        "NOTION_PARENT_PAGE_ID=parent\n"
        "NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast_db\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NOTION_TOKEN", "secret")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    monkeypatch.setenv("NOTION_PODCAST_LIBRARY_DATABASE_ID", "podcast_db")

    database_id = create_vocabulary_database("parent", notion=notion)

    assert database_id == "vocabulary_db"
    assert notion.databases.create_calls
    assert notion.databases.create_calls[0]["parent"] == {
        "type": "page_id",
        "page_id": "parent",
    }
    assert "Name" in notion.databases.create_calls[0]["properties"]
    assert "Word" not in notion.databases.create_calls[0]["properties"]


def test_sync_vocabulary_database_schema_updates_existing_database(monkeypatch) -> None:
    notion = FakeNotion()
    monkeypatch.setenv("NOTION_TOKEN", "secret")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent")
    monkeypatch.setenv("NOTION_PODCAST_LIBRARY_DATABASE_ID", "podcast_db")
    monkeypatch.setenv("NOTION_VOCABULARY_DATABASE_ID", "vocabulary_db")
    monkeypatch.setenv("NOTION_WEEKLY_REFLECTION_DATABASE_ID", "weekly_db")

    database_id = sync_vocabulary_database_schema(notion=notion)

    assert database_id == "vocabulary_db"
    assert notion.databases.update_calls[0]["database_id"] == "vocabulary_db"
    assert notion.databases.update_calls[1]["database_id"] == "weekly_db"
    assert notion.databases.update_calls[1]["properties"]["Vocabulary"] == {
        "relation": {
            "data_source_id": "vocabulary_db",
            "single_property": {"synced_property_name": "Vocabulary"},
            "dual_property": {"synced_property_name": "Vocabulary"},
        }
    }
    assert "Name" in notion.databases.update_calls[0]["properties"]
    assert "Word" not in notion.databases.update_calls[0]["properties"]
