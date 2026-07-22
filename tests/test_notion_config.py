from __future__ import annotations

from src.notion.config import load_notion_config


def test_load_notion_config_includes_vocabulary_database_id() -> None:
    config = load_notion_config(
        env={
            "NOTION_TOKEN": "secret",
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast_db",
            "NOTION_EXPRESSION_DATABASE_ID": "expression_db",
            "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly_db",
            "NOTION_VOCABULARY_DATABASE_ID": "vocabulary_db",
        }
    )

    assert config.token == "secret"
    assert config.podcast_database_id == "podcast_db"
    assert config.expression_database_id == "expression_db"
    assert config.weekly_database_id == "weekly_db"
    assert config.vocabulary_database_id == "vocabulary_db"
    assert config.database_mapping["vocabulary_database_id"] == "vocabulary_db"


def test_load_notion_config_accepts_legacy_weekly_review_database_id() -> None:
    config = load_notion_config(
        env={
            "NOTION_TOKEN": "secret",
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast_db",
            "NOTION_EXPRESSION_DATABASE_ID": "expression_db",
            "NOTION_WEEKLY_REVIEW_DATABASE_ID": "weekly_db",
            "NOTION_VOCABULARY_DATABASE_ID": "vocabulary_db",
        }
    )

    assert config.weekly_database_id == "weekly_db"
