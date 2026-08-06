from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

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


class FakePages:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(deepcopy(kwargs))

    def update(self, **kwargs):
        self.update_calls.append(deepcopy(kwargs))

    def delete(self, **kwargs):
        self.delete_calls.append(deepcopy(kwargs))


class FakeNotion:
    def __init__(self, schemas: dict[str, dict] | None = None) -> None:
        self.data_sources = FakeDataSources(schemas)
        self.databases = FakeDatabases(self.data_sources)
        self.pages = FakePages()


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


def _contains_none(value) -> bool:
    if value is None:
        return True
    if isinstance(value, dict):
        return any(_contains_none(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_none(item) for item in value)
    return False


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


def test_expression_database_select_options_have_semantic_colors() -> None:
    properties = setup_workspace.expression_database_properties("podcast_db")

    assert properties["Category"]["select"]["options"] == [
        {"name": "Native Expression", "color": "green"},
        {"name": "Business Phrase", "color": "blue"},
        {"name": "Industry Term", "color": "yellow"},
        {"name": "Collocation", "color": "purple"},
        {"name": "Sentence Pattern", "color": "orange"},
    ]
    assert properties["Commonness"]["select"]["options"] == [
        {"name": "High", "color": "red"},
        {"name": "Medium", "color": "yellow"},
        {"name": "Low", "color": "gray"},
    ]
    assert properties["Review Status"]["select"]["options"] == [
        {"name": "New", "color": "blue"},
        {"name": "Reviewing", "color": "yellow"},
        {"name": "Mastered", "color": "green"},
    ]


def test_vocabulary_database_has_lean_schema_and_semantic_status_colors() -> None:
    properties = setup_workspace.vocabulary_database_properties("podcast_db")

    assert set(properties) == {
        "Name",
        "First Seen",
        "Last Review",
        "Review Status",
        "Source",
    }
    assert properties["Review Status"]["select"]["options"] == [
        {"name": "New", "color": "blue"},
        {"name": "Reviewing", "color": "yellow"},
        {"name": "Mastered", "color": "green"},
    ]


def test_reconcile_does_not_rewrite_existing_select_option_colors() -> None:
    expected_schemas = {
        "podcast_db": setup_workspace.podcast_library_properties(),
        "expression_db": setup_workspace.expression_database_properties(
            "podcast_db"
        ),
        "vocabulary_db": setup_workspace.vocabulary_database_properties(
            "podcast_db"
        ),
        "weekly_db": setup_workspace.weekly_review_properties("podcast_db"),
    }
    schemas = {
        data_source_id: {
            "id": data_source_id,
            "properties": {
                name: _actual_property(name, definition)
                for name, definition in properties.items()
            },
        }
        for data_source_id, properties in expected_schemas.items()
    }
    for property_name in ("Category", "Commonness", "Review Status"):
        options = schemas["expression_db"]["properties"][property_name][
            "select"
        ]["options"]
        for option in options:
            option["color"] = "default"
    for option in schemas["vocabulary_db"]["properties"]["Review Status"][
        "select"
    ]["options"]:
        option["color"] = "default"

    notion = FakeNotion(schemas)
    setup_workspace.reconcile_workspace_schema(notion, DATABASE_IDS)

    assert notion.data_sources.update_calls == []


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


def test_setup_workspace_creates_guide_then_links_entries(monkeypatch) -> None:
    from src.notion import parent_page_guide

    calls: list[str] = []
    database_ids = dict(DATABASE_IDS)
    monkeypatch.delenv(setup_workspace.SETUP_STATE_ENV, raising=False)
    monkeypatch.setattr(
        parent_page_guide,
        "ensure_parent_page_guide_for_setup",
        lambda _notion, _parent: calls.append("guide") or True,
    )
    monkeypatch.setattr(
        parent_page_guide,
        "ensure_parent_page_database_links",
        lambda _notion, _parent, _ids: calls.append("links") or 4,
    )
    monkeypatch.setattr(
        setup_workspace,
        "update_env_file",
        lambda _values: calls.append("env"),
    )
    monkeypatch.setattr(
        setup_workspace,
        "create_base_databases",
        lambda _notion, _parent: calls.append("databases")
        or database_ids,
    )
    monkeypatch.setattr(
        setup_workspace,
        "reconcile_workspace_schema",
        lambda _notion, _ids: calls.append("schema"),
    )
    monkeypatch.setattr(
        setup_workspace,
        "wire_database_relations",
        lambda _notion, _ids: calls.append("relations"),
    )

    result = setup_workspace.setup_workspace(
        "0" * 32,
        notion=object(),
    )

    assert result == database_ids
    assert calls == [
        "env",
        "guide",
        "databases",
        "schema",
        "relations",
        "links",
        "env",
    ]


def test_completed_setup_requires_protected_parent_guide_cli(
    monkeypatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setenv(
        setup_workspace.SETUP_STATE_ENV,
        setup_workspace.SETUP_STATE_COMPLETE,
    )
    monkeypatch.setattr(
        setup_workspace,
        "update_env_file",
        lambda _values: calls.append("env"),
    )
    monkeypatch.setattr(
        setup_workspace,
        "create_base_databases",
        lambda *_args, **_kwargs: calls.append("databases"),
    )

    with pytest.raises(
        setup_workspace.WorkspaceSetupError,
        match="protected Parent Page Guide",
    ):
        setup_workspace.setup_workspace("0" * 32, notion=object())

    assert calls == []


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
    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []
    assert notion.pages.delete_calls == []
    for call in notion.data_sources.update_calls:
        assert "Custom Field" not in call["properties"]
        assert not _contains_none(call["properties"])


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


def test_correct_single_property_relation_is_not_updated() -> None:
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    ),
                    "Source Podcast": _actual_property(
                        "Source Podcast",
                        setup_workspace.relation_property("podcast_db"),
                    ),
                },
            }
        }
    )

    setup_workspace.ensure_data_source_schema(
        notion,
        "expression_db",
        "Expression Database",
        {
            "Expression": setup_workspace.title_property(),
            "Source Podcast": setup_workspace.relation_property("podcast_db"),
        },
    )

    assert notion.data_sources.update_calls == []


def test_relation_missing_mode_is_repaired_to_single_property() -> None:
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    ),
                    "Source Podcast": _actual_property(
                        "Source Podcast",
                        {"relation": {"data_source_id": "podcast_db"}},
                    ),
                },
            }
        }
    )

    setup_workspace.ensure_data_source_schema(
        notion,
        "expression_db",
        "Expression Database",
        {
            "Expression": setup_workspace.title_property(),
            "Source Podcast": setup_workspace.relation_property("podcast_db"),
        },
    )

    assert notion.data_sources.update_calls == [
        {
            "data_source_id": "expression_db",
            "properties": {
                "Source Podcast": setup_workspace.relation_property("podcast_db")
            },
        }
    ]


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


def test_relation_with_wrong_target_stops_without_update() -> None:
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    ),
                    "Source Podcast": _actual_property(
                        "Source Podcast",
                        setup_workspace.relation_property("unexpected_target"),
                    ),
                },
            }
        }
    )

    with pytest.raises(
        setup_workspace.WorkspaceSetupError,
        match="points to a different data source",
    ) as error:
        setup_workspace.ensure_data_source_schema(
            notion,
            "expression_db",
            "Expression Database",
            {
                "Expression": setup_workspace.title_property(),
                "Source Podcast": setup_workspace.relation_property("podcast_db"),
            },
        )

    assert "unexpected_target" not in str(error.value)
    assert "podcast_db" not in str(error.value)
    assert notion.data_sources.update_calls == []


def test_dual_property_relation_stops_without_update() -> None:
    dual_relation = {
        "relation": {
            "data_source_id": "podcast_db",
            "dual_property": {"synced_property_name": "Expressions"},
        }
    }
    notion = FakeNotion(
        {
            "expression_db": {
                "id": "expression_db",
                "properties": {
                    "Expression": _actual_property(
                        "Expression",
                        setup_workspace.title_property(),
                    ),
                    "Source Podcast": _actual_property(
                        "Source Podcast",
                        dual_relation,
                    ),
                },
            }
        }
    )

    with pytest.raises(
        setup_workspace.WorkspaceSetupError,
        match="dual-property relation mode",
    ) as error:
        setup_workspace.ensure_data_source_schema(
            notion,
            "expression_db",
            "Expression Database",
            {
                "Expression": setup_workspace.title_property(),
                "Source Podcast": setup_workspace.relation_property("podcast_db"),
            },
        )

    assert "podcast_db" not in str(error.value)
    assert notion.data_sources.update_calls == []


def test_schema_recovery_only_renames_title_and_adds_missing_fields() -> None:
    schema = _default_title_schema("podcast_db")
    schema["properties"]["Custom Field"] = _actual_property(
        "Custom Field",
        {"rich_text": {}},
    )
    notion = FakeNotion({"podcast_db": schema})

    setup_workspace.ensure_data_source_schema(
        notion,
        "podcast_db",
        "Podcast Library",
        setup_workspace.podcast_library_properties(),
    )

    assert len(notion.data_sources.update_calls) == 1
    properties = notion.data_sources.update_calls[0]["properties"]
    assert set(properties) == {
        "podcast_db_title",
        "URL",
        "Source Type",
        "Date",
        "Topic",
        "Difficulty",
        "Short Summary",
    }
    assert properties["podcast_db_title"] == {"name": "Title"}
    assert "Custom Field" not in properties
    assert not _contains_none(properties)
    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []
    assert notion.pages.delete_calls == []


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


def test_developer_cli_success_does_not_print_configuration_values(
    monkeypatch,
    capsys,
) -> None:
    test_page_url = (
        "https://www.notion.so/Test-0123456789abcdef0123456789abcdef"
    )
    test_page_id = "01234567-89ab-cdef-0123-456789abcdef"
    test_token = "secret_test_token"
    test_database_ids = {
        "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast-sensitive-id",
        "NOTION_EXPRESSION_DATABASE_ID": "expression-sensitive-id",
        "NOTION_VOCABULARY_DATABASE_ID": "vocabulary-sensitive-id",
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly-sensitive-id",
    }

    monkeypatch.setattr(setup_workspace, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        setup_workspace,
        "parse_args",
        lambda: SimpleNamespace(
            print_onboarding=False,
            parent_page_id=test_page_url,
        ),
    )
    monkeypatch.setattr(
        setup_workspace,
        "setup_workspace",
        lambda parent_page_id: test_database_ids,
    )
    monkeypatch.setenv("NOTION_TOKEN", test_token)

    assert setup_workspace.main() == 0

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    for sensitive_value in (
        test_page_url,
        test_page_id,
        test_token,
        *test_database_ids.values(),
    ):
        assert sensitive_value not in combined
    for database_name in setup_workspace.WORKSPACE_DATABASE_ORDER:
        assert f"- {database_name}: complete" in captured.out


def test_developer_cli_failure_uses_non_sensitive_summary(
    monkeypatch,
    capsys,
) -> None:
    test_page_url = (
        "https://www.notion.so/Test-fedcba9876543210fedcba9876543210"
    )
    test_page_id = "fedcba98-7654-3210-fedc-ba9876543210"
    test_token = "secret_test_token"
    test_data_source_id = "sensitive-data-source-id"

    monkeypatch.setattr(setup_workspace, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        setup_workspace,
        "parse_args",
        lambda: SimpleNamespace(
            print_onboarding=False,
            parent_page_id=test_page_url,
        ),
    )
    monkeypatch.setattr(
        setup_workspace,
        "setup_workspace",
        lambda parent_page_id: (_ for _ in ()).throw(
            setup_workspace.WorkspaceSetupError(
                f"failed {parent_page_id} {test_page_id} "
                f"{test_token} {test_data_source_id}"
            )
        ),
    )

    assert setup_workspace.main() == 1

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "No configuration values were displayed" in captured.err
    for sensitive_value in (
        test_page_url,
        test_page_id,
        test_token,
        test_data_source_id,
    ):
        assert sensitive_value not in combined
