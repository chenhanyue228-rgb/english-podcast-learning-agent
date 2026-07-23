from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from notion_client import APIResponseError

from src.notion import check_workspace
from src.notion.schema import (
    REQUIRED_DATABASE_PROPERTIES,
    REQUIRED_DATABASE_RELATIONS,
    WORKSPACE_DATABASE_ORDER,
)


DATABASE_IDS = {
    "Podcast Library": "podcast-id",
    "Expression Database": "expression-id",
    "Vocabulary Database": "vocabulary-id",
    "Weekly Review": "weekly-id",
}


def _database(
    name: str,
    *,
    relation_overrides: dict[str, dict] | None = None,
    type_overrides: dict[str, str] | None = None,
) -> dict:
    properties: dict[str, dict] = {}
    for property_name, property_type in REQUIRED_DATABASE_PROPERTIES[name].items():
        actual_type = (type_overrides or {}).get(property_name, property_type)
        property_data = {"type": actual_type, actual_type: {}}
        target_database = (REQUIRED_DATABASE_RELATIONS.get(name) or {}).get(
            property_name
        )
        if actual_type == "relation" and target_database:
            property_data["relation"] = {
                "data_source_id": DATABASE_IDS[target_database],
                "single_property": {},
            }
        properties[property_name] = property_data

    for property_name, relation in (relation_overrides or {}).items():
        properties[property_name] = {
            "type": "relation",
            "relation": relation,
        }

    return {
        "properties": properties,
    }


def test_validate_workspace_uses_fixed_database_order(monkeypatch) -> None:
    config = SimpleNamespace(
        token="test-token",
        podcast_database_id="podcast-id",
        expression_database_id="expression-id",
        vocabulary_database_id="vocabulary-id",
        weekly_database_id="weekly-id",
    )
    databases = {name: _database(name) for name in WORKSPACE_DATABASE_ORDER}
    calls: list[tuple[str, str]] = []

    class FakeClient:
        def __init__(self, auth: str) -> None:
            assert auth == "test-token"

    monkeypatch.setattr(check_workspace, "load_notion_config", lambda: config)
    monkeypatch.setattr("notion_client.Client", FakeClient)

    def fake_fetch(_notion, database_id: str, name: str):
        calls.append((name, database_id))
        return databases[name]

    monkeypatch.setattr(check_workspace, "fetch_database", fake_fetch)

    results = check_workspace.validate_workspace()

    assert [result.name for result in results] == list(WORKSPACE_DATABASE_ORDER)
    assert [name for name, _database_id in calls] == list(
        WORKSPACE_DATABASE_ORDER
    )
    assert all(result.is_valid for result in results)


def test_three_single_property_relations_pass_semantic_validation() -> None:
    for database_name, relations in REQUIRED_DATABASE_RELATIONS.items():
        expected_targets = {
            property_name: DATABASE_IDS[target_database]
            for property_name, target_database in relations.items()
        }
        result = check_workspace.validate_database(
            database_name,
            _database(database_name),
            REQUIRED_DATABASE_PROPERTIES[database_name],
            expected_targets,
        )

        assert result.is_valid
        assert result.relation_mismatches == []


def test_wrong_relation_target_fails_without_exposing_ids() -> None:
    result = check_workspace.validate_database(
        "Expression Database",
        _database(
            "Expression Database",
            relation_overrides={
                "Source Podcast": {
                    "data_source_id": "unexpected-target",
                    "single_property": {},
                }
            },
        ),
        REQUIRED_DATABASE_PROPERTIES["Expression Database"],
        {"Source Podcast": DATABASE_IDS["Podcast Library"]},
    )

    assert not result.is_valid
    assert result.relation_mismatches == [
        "Expression Database.Source Podcast: relation target mismatch"
    ]
    report = check_workspace.format_validation_report([result])
    assert "relation target mismatch" in report
    assert "unexpected-target" not in report
    assert DATABASE_IDS["Podcast Library"] not in report


def test_dual_property_relation_fails_mode_validation() -> None:
    result = check_workspace.validate_database(
        "Vocabulary Database",
        _database(
            "Vocabulary Database",
            relation_overrides={
                "Source": {
                    "data_source_id": DATABASE_IDS["Podcast Library"],
                    "dual_property": {"synced_property_name": "Vocabulary"},
                }
            },
        ),
        REQUIRED_DATABASE_PROPERTIES["Vocabulary Database"],
        {"Source": DATABASE_IDS["Podcast Library"]},
    )

    assert not result.is_valid
    assert result.relation_mismatches == [
        "Vocabulary Database.Source: relation mode mismatch"
    ]


def test_relation_without_single_property_fails_mode_validation() -> None:
    result = check_workspace.validate_database(
        "Weekly Review",
        _database(
            "Weekly Review",
            relation_overrides={
                "Podcasts": {
                    "data_source_id": DATABASE_IDS["Podcast Library"],
                }
            },
        ),
        REQUIRED_DATABASE_PROPERTIES["Weekly Review"],
        {"Podcasts": DATABASE_IDS["Podcast Library"]},
    )

    assert not result.is_valid
    assert result.relation_mismatches == [
        "Weekly Review.Podcasts: relation mode mismatch"
    ]


def test_relation_property_type_mismatch_fails_validation() -> None:
    result = check_workspace.validate_database(
        "Expression Database",
        _database(
            "Expression Database",
            type_overrides={"Source Podcast": "rich_text"},
        ),
        REQUIRED_DATABASE_PROPERTIES["Expression Database"],
        {"Source Podcast": DATABASE_IDS["Podcast Library"]},
    )

    assert not result.is_valid
    assert result.type_mismatches == [
        "Expression Database.Source Podcast: expected relation, got rich_text"
    ]
    assert result.relation_mismatches == []


def test_validation_report_preserves_fixed_result_order() -> None:
    results = [
        check_workspace.DatabaseValidationResult(name=name, exists=True)
        for name in WORKSPACE_DATABASE_ORDER
    ]

    report = check_workspace.format_validation_report(results)
    positions = [report.index(name) for name in WORKSPACE_DATABASE_ORDER]

    assert positions == sorted(positions)


def test_fetch_database_uses_non_sensitive_api_error_summary() -> None:
    error = APIResponseError(
        code="validation_error",
        status=400,
        message="safe validation failure",
        headers=httpx.Headers(),
        raw_body_text="",
    )

    class FailingDataSources:
        def retrieve(self, **_kwargs):
            raise error

    notion = SimpleNamespace(data_sources=FailingDataSources())

    with pytest.raises(RuntimeError, match="could not be retrieved from Notion") as exc:
        check_workspace.fetch_database(notion, "data-source-id", "Podcast Library")

    assert "safe validation failure" not in str(exc.value)
    assert "data-source-id" not in str(exc.value)
