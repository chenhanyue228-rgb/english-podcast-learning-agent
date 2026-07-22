from __future__ import annotations

from src.notion import setup_workspace
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


def test_create_base_databases_uses_four_product_database_names(monkeypatch) -> None:
    created_names = []

    def fake_create_database(*, notion, parent_page_id, name, properties):
        created_names.append(name)
        return f"{name.lower().replace(' ', '_')}_id"

    monkeypatch.setattr(setup_workspace, "create_database", fake_create_database)

    database_ids = setup_workspace.create_base_databases(object(), "parent_page")

    assert created_names == [
        "Podcast Library",
        "Expression Database",
        "Weekly Review",
        "Vocabulary Database",
    ]
    assert set(database_ids) == {
        "NOTION_PODCAST_LIBRARY_DATABASE_ID",
        "NOTION_EXPRESSION_DATABASE_ID",
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
        "NOTION_VOCABULARY_DATABASE_ID",
    }


def test_print_onboarding_describes_single_four_database_flow(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "top-secret-token")
    setup_workspace.print_onboarding()

    output = capsys.readouterr().out
    assert "Notion onboarding modes" not in output
    assert "Podcast Library" in output
    assert "Expression Database" in output
    assert "Weekly Review" in output
    assert "Weekly Reflection learning note" in output
    assert "Vocabulary Database" in output
    assert "top-secret-token" not in output
