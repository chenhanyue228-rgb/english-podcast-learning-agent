from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from notion_client import APIResponseError

from src.notion import check_workspace
from src.notion.schema import (
    REQUIRED_DATABASE_PROPERTIES,
    WORKSPACE_DATABASE_ORDER,
)


def _database(properties: dict[str, str]) -> dict:
    return {
        "properties": {
            name: {"type": property_type}
            for name, property_type in properties.items()
        }
    }


def test_validate_workspace_uses_fixed_database_order(monkeypatch) -> None:
    config = SimpleNamespace(
        token="test-token",
        podcast_database_id="podcast-id",
        expression_database_id="expression-id",
        vocabulary_database_id="vocabulary-id",
        weekly_database_id="weekly-id",
    )
    databases = {
        name: _database(REQUIRED_DATABASE_PROPERTIES[name])
        for name in WORKSPACE_DATABASE_ORDER
    }
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


def test_validation_report_preserves_fixed_result_order() -> None:
    results = [
        check_workspace.DatabaseValidationResult(name=name, exists=True)
        for name in WORKSPACE_DATABASE_ORDER
    ]

    report = check_workspace.format_validation_report(results)
    positions = [report.index(name) for name in WORKSPACE_DATABASE_ORDER]

    assert positions == sorted(positions)


def test_fetch_database_uses_current_api_error_string() -> None:
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

    with pytest.raises(RuntimeError, match="safe validation failure"):
        check_workspace.fetch_database(notion, "data-source-id", "Podcast Library")
