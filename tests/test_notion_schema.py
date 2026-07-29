from __future__ import annotations

from src.notion.schema import REQUIRED_DATABASE_PROPERTIES, VOCABULARY_DATABASE, WEEKLY_REVIEW


def test_vocabulary_database_schema_keeps_only_tracking_properties() -> None:
    properties = REQUIRED_DATABASE_PROPERTIES[VOCABULARY_DATABASE]

    assert properties == {
        "Name": "title",
        "Source": "relation",
        "First Seen": "date",
        "Review Status": "select",
        "Last Review": "date",
    }


def test_weekly_review_schema_includes_vocabulary_relation() -> None:
    properties = REQUIRED_DATABASE_PROPERTIES[WEEKLY_REVIEW]

    assert properties == {"Week": "title", "Date": "date", "Podcasts": "relation"}
