from __future__ import annotations

from src.notion.schema import REQUIRED_DATABASE_PROPERTIES, VOCABULARY_DATABASE, WEEKLY_REVIEW


def test_vocabulary_database_schema_uses_contextual_memory_fields() -> None:
    properties = REQUIRED_DATABASE_PROPERTIES[VOCABULARY_DATABASE]

    assert properties == {
        "Name": "title",
        "Original Context": "rich_text",
        "Meaning": "rich_text",
        "Professional Category": "select",
        "Source": "relation",
        "Source Page ID": "rich_text",
        "First Seen": "date",
        "Review Status": "select",
        "Last Review": "date",
        "Usage Example": "rich_text",
        "Personal Note": "rich_text",
    }


def test_weekly_review_schema_includes_vocabulary_relation() -> None:
    properties = REQUIRED_DATABASE_PROPERTIES[WEEKLY_REVIEW]

    assert properties == {"Week": "title", "Date": "date", "Podcasts": "relation"}
