from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.notion import setup_workspace


DATABASE_IDS = {
    "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast_db",
    "NOTION_EXPRESSION_DATABASE_ID": "expression_db",
    "NOTION_VOCABULARY_DATABASE_ID": "vocabulary_db",
    "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly_db",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _actual_property(
    name: str,
    definition: dict,
    *,
    property_id: str | None = None,
) -> dict:
    property_type = next(iter(definition))
    return {
        "id": property_id or f"{name.lower().replace(' ', '_')}_id",
        "name": name,
        "type": property_type,
        property_type: deepcopy(definition[property_type]),
    }


class FakeDataSources:
    def __init__(self, schemas: dict[str, dict] | None = None) -> None:
        self.schemas = schemas or {}
        self.update_calls: list[dict] = []
        self.retrieve_calls: list[str] = []

    def retrieve(self, **kwargs):
        data_source_id = kwargs["data_source_id"]
        self.retrieve_calls.append(data_source_id)
        return deepcopy(self.schemas[data_source_id])

    def update(self, **kwargs):
        self.update_calls.append(deepcopy(kwargs))
        data_source_id = kwargs["data_source_id"]
        schema = self.schemas[data_source_id]
        properties = schema["properties"]

        for property_key, definition in kwargs["properties"].items():
            if set(definition) == {"name"}:
                current_name = next(
                    name
                    for name, property_data in properties.items()
                    if name == property_key
                    or property_data.get("id") == property_key
                )
                property_data = properties.pop(current_name)
                property_data["name"] = definition["name"]
                properties[definition["name"]] = property_data
                continue

            properties[property_key] = _actual_property(
                property_key,
                definition,
            )

        return deepcopy(schema)


class FakeDatabases:
    def __init__(self, data_sources: FakeDataSources) -> None:
        self.data_sources = data_sources
        self.create_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(deepcopy(kwargs))
        title = kwargs["title"][0]["text"]["content"]
        data_source_id = f"{title.lower().replace(' ', '_')}_id"
        definitions = kwargs["initial_data_source"]["properties"]
        self.data_sources.schemas[data_source_id] = {
            "id": data_source_id,
            "properties": {
                name: _actual_property(name, definition)
                for name, definition in definitions.items()
            },
        }
        return {
            "id": f"{data_source_id}_container",
            "data_sources": [{"id": data_source_id}],
        }


class FakeNotion:
    def __init__(self, schemas: dict[str, dict] | None = None) -> None:
        self.data_sources = FakeDataSources(schemas)
        self.databases = FakeDatabases(self.data_sources)


def _default_title_schema(data_source_id: str) -> dict:
    return {
        "id": data_source_id,
        "properties": {
            "Name": _actual_property(
                "Name",
                setup_workspace.title_property(),
                property_id=f"{data_source_id}_title",
            )
        },
    }


def test_create_database_uses_current_initial_data_source_payload() -> None:
    notion = FakeNotion()

    data_source_id = setup_workspace.create_database(
        notion,
        "parent_page",
        "Podcast Library",
        setup_workspace.podcast_library_properties(),
    )

    assert data_source_id == "podcast_library_id"
    request = notion.databases.create_calls[0]
    assert request["parent"] == {"type": "page_id", "page_id": "parent_page"}
    assert request["initial_data_source"]["properties"] == (
        setup_workspace.podcast_library_properties()
    )
    assert "properties" not in request
    assert notion.data_sources.retrieve_calls == ["podcast_library_id"]


def test_notion_client_is_pinned_to_validated_data_source_version() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "notion-client==3.1.0" in requirements.splitlines()
    assert "notion-client>=" not in requirements


def test_relation_property_is_single_property_data_source_relation() -> None:
    relation = setup_workspace.relation_property("podcast_db")

    assert relation == {
        "relation": {
            "data_source_id": "podcast_db",
            "single_property": {},
        }
    }
    assert "database_id" not in relation["relation"]
    assert "dual_property" not in relation["relation"]


def test_create_base_databases_uses_fixed_product_order(monkeypatch) -> None:
    created_names: list[str] = []

    def fake_create_database(
        *,
        notion,
        parent_page_id,
        name,
        properties,
        on_data_source_created=None,
    ):
        del notion, parent_page_id, properties
        created_names.append(name)
        data_source_id = f"{name.lower().replace(' ', '_')}_id"
        if on_data_source_created is not None:
            on_data_source_created(data_source_id)
        return data_source_id

    monkeypatch.setattr(setup_workspace, "create_database", fake_create_database)

    database_ids = setup_workspace.create_base_databases(object(), "parent_page")

    assert created_names == [
        "Podcast Library",
        "Expression Database",
        "Vocabulary Database",
        "Weekly Review",
    ]
    assert list(database_ids) == [
        "NOTION_PODCAST_LIBRARY_DATABASE_ID",
        "NOTION_EXPRESSION_DATABASE_ID",
        "NOTION_VOCABULARY_DATABASE_ID",
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
    ]


def test_create_base_databases_reuses_all_existing_ids_without_create() -> None:
    notion = FakeNotion()

    database_ids = setup_workspace.create_base_databases(
        notion,
        "parent_page",
        existing_ids=DATABASE_IDS,
    )

    assert database_ids == DATABASE_IDS
    assert notion.databases.create_calls == []


def test_create_base_databases_reports_each_success_before_later_failure(
    monkeypatch,
) -> None:
    persisted: list[tuple[str, str]] = []

    def fake_create_database(
        *,
        notion,
        parent_page_id,
        name,
        properties,
        on_data_source_created=None,
    ):
        del notion, parent_page_id, properties
        if name == "Expression Database":
            raise RuntimeError("simulated failure")
        data_source_id = f"{name.lower().replace(' ', '_')}_id"
        if on_data_source_created is not None:
            on_data_source_created(data_source_id)
        return data_source_id

    monkeypatch.setattr(setup_workspace, "create_database", fake_create_database)

    with pytest.raises(RuntimeError, match="simulated failure"):
        setup_workspace.create_base_databases(
            object(),
            "parent_page",
            on_database_created=lambda key, value: persisted.append((key, value)),
        )

    assert persisted == [
        ("NOTION_PODCAST_LIBRARY_DATABASE_ID", "podcast_library_id")
    ]


def test_reconcile_repairs_default_titles_and_all_non_relation_fields() -> None:
    notion = FakeNotion(
        {
            data_source_id: _default_title_schema(data_source_id)
            for data_source_id in DATABASE_IDS.values()
        }
    )

    setup_workspace.reconcile_workspace_schema(notion, DATABASE_IDS)

    expected_titles = {
        "podcast_db": "Title",
        "expression_db": "Expression",
        "vocabulary_db": "Name",
        "weekly_db": "Week",
    }
    for data_source_id, expected_title in expected_titles.items():
        properties = notion.data_sources.schemas[data_source_id]["properties"]
        assert expected_title in properties
        assert sum(
            value["type"] == "title" for value in properties.values()
        ) == 1

    for data_source_id, database_name, expected in (
        (
            "podcast_db",
            "Podcast Library",
            setup_workspace.podcast_library_properties(),
        ),
        (
            "expression_db",
            "Expression Database",
            setup_workspace.expression_database_properties("podcast_db"),
        ),
        (
            "vocabulary_db",
            "Vocabulary Database",
            setup_workspace.vocabulary_database_properties("podcast_db"),
        ),
        (
            "weekly_db",
            "Weekly Review",
            setup_workspace.weekly_review_properties("podcast_db"),
        ),
    ):
        del database_name
        properties = notion.data_sources.schemas[data_source_id]["properties"]
        for name, definition in expected.items():
            if "relation" not in definition:
                assert name in properties


def test_reconcile_keeps_unknown_properties_and_is_idempotent() -> None:
    schemas = {
        data_source_id: _default_title_schema(data_source_id)
        for data_source_id in DATABASE_IDS.values()
    }
    schemas["podcast_db"]["properties"]["Custom Field"] = _actual_property(
        "Custom Field",
        {"rich_text": {}},
    )
    notion = FakeNotion(schemas)

    setup_workspace.reconcile_workspace_schema(notion, DATABASE_IDS)
    first_update_count = len(notion.data_sources.update_calls)
    setup_workspace.reconcile_workspace_schema(notion, DATABASE_IDS)

    assert "Custom Field" in notion.data_sources.schemas["podcast_db"]["properties"]
    assert len(notion.data_sources.update_calls) == first_update_count


def test_reconcile_stops_before_update_on_type_conflict() -> None:
    schemas = {
        data_source_id: _default_title_schema(data_source_id)
        for data_source_id in DATABASE_IDS.values()
    }
    schemas["podcast_db"]["properties"]["URL"] = _actual_property(
        "URL",
        {"rich_text": {}},
    )
    notion = FakeNotion(schemas)

    with pytest.raises(
        setup_workspace.WorkspaceSetupError,
        match="expected 'url'",
    ):
        setup_workspace.reconcile_workspace_schema(notion, DATABASE_IDS)

    assert notion.data_sources.update_calls == []
    assert "Name" in notion.data_sources.schemas["podcast_db"]["properties"]


def test_wire_database_relations_uses_three_single_property_relations() -> None:
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    )
                },
            },
            "vocabulary_db": _default_title_schema("vocabulary_db"),
            "weekly_db": {
                "id": "weekly_db",
                "properties": {
                    "Week": _actual_property(
                        "Week",
                        setup_workspace.title_property(),
                    )
                },
            },
        }
    )

    setup_workspace.wire_database_relations(notion, DATABASE_IDS)

    relation_updates = {
        next(
            name
            for name, definition in call["properties"].items()
            if "relation" in definition
        ): next(
            definition["relation"]
            for definition in call["properties"].values()
            if "relation" in definition
        )
        for call in notion.data_sources.update_calls
    }
    assert set(relation_updates) == {"Source Podcast", "Source", "Podcasts"}
    for relation in relation_updates.values():
        assert relation == {
            "data_source_id": "podcast_db",
            "single_property": {},
        }
        assert "database_id" not in relation
        assert "dual_property" not in relation


def test_wire_repairs_relation_missing_data_source_target() -> None:
    relation_without_target = _actual_property(
        "Source Podcast",
        {"relation": {"single_property": {}}},
    )
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    ),
                    "Source Podcast": relation_without_target,
                },
            },
            "vocabulary_db": {
                "id": "vocabulary_db",
                "properties": {
                    "Name": _actual_property(
                        "Name",
                        setup_workspace.title_property(),
                    ),
                    "Source": _actual_property(
                        "Source",
                        setup_workspace.relation_property("podcast_db"),
                    ),
                },
            },
            "weekly_db": {
                "id": "weekly_db",
                "properties": {
                    "Week": _actual_property(
                        "Week",
                        setup_workspace.title_property(),
                    ),
                    "Podcasts": _actual_property(
                        "Podcasts",
                        setup_workspace.relation_property("podcast_db"),
                    ),
                },
            },
        }
    )

    setup_workspace.wire_database_relations(notion, DATABASE_IDS)

    assert notion.data_sources.update_calls == [
        {
            "data_source_id": "expression_db",
            "properties": {
                "Source Podcast": setup_workspace.relation_property("podcast_db")
            },
        }
    ]


def test_print_onboarding_describes_single_four_database_flow(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setenv("NOTION_TOKEN", "top-secret-token")
    setup_workspace.print_onboarding()

    output = capsys.readouterr().out
    assert "Notion onboarding modes" not in output
    assert output.index("Podcast Library") < output.index("Expression Database")
    assert output.index("Expression Database") < output.index("Vocabulary Database")
    assert output.index("Vocabulary Database") < output.index("Weekly Review")
    assert "Weekly Reflection learning note" in output
    assert "top-secret-token" not in output
