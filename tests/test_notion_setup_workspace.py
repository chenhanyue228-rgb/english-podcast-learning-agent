from __future__ import annotations

from src.notion.setup_workspace import wire_database_relations


class FakeDataSources:
    def __init__(self) -> None:
        self.update_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs.get("data_source_id")}


class FakeNotion:
    def __init__(self) -> None:
        self.data_sources = FakeDataSources()


def test_wire_database_relations_wires_vocabulary_to_podcast_and_weekly_review() -> None:
    notion = FakeNotion()
    wire_database_relations(
        notion,
        {
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast_db",
            "NOTION_EXPRESSION_DATABASE_ID": "expression_db",
            "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly_db",
            "NOTION_VOCABULARY_DATABASE_ID": "vocabulary_db",
        },
    )

    assert len(notion.data_sources.update_calls) == 3
    assert notion.data_sources.update_calls[0]["data_source_id"] == "expression_db"
    assert notion.data_sources.update_calls[1]["data_source_id"] == "weekly_db"
    assert notion.data_sources.update_calls[2]["data_source_id"] == "vocabulary_db"
    assert notion.data_sources.update_calls[1]["properties"] == {
        "Podcasts": {"relation": {"data_source_id": "podcast_db"}}
    }
