from __future__ import annotations

from copy import deepcopy

import pytest

from src.notion import setup_vocabulary_database
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
)
from src.notion.setup_vocabulary_database import (
    LEGACY_VOCABULARY_DATABASE_CREATION_DISABLED,
    VOCABULARY_SCHEMA_SYNC_FAILED,
    VocabularyDatabaseSetupError,
    _update_database,
    create_vocabulary_database,
    sync_vocabulary_database_schema,
)
from src.notion.target_binding import (
    CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP,
    TARGET_DATABASE_ROLE_MISMATCH,
    TARGET_PARENT_MISMATCH,
    TARGET_PARENT_NOT_CONFIGURED,
    TARGET_RELATION_MODE_INVALID,
    TARGET_RELATION_OUTSIDE_GROUP,
    NotionTargetBindingError,
)
from tests.acceptance.fakes import FakeNotion


def _configure_environment(
    monkeypatch: pytest.MonkeyPatch,
    notion: FakeNotion,
    *,
    target_parent: str | None = None,
) -> None:
    config = notion.config
    monkeypatch.setenv("NOTION_TOKEN", "safe-fake-token")
    monkeypatch.setenv(
        "NOTION_PODCAST_LIBRARY_DATABASE_ID",
        config.podcast_data_source_id,
    )
    monkeypatch.setenv(
        "NOTION_EXPRESSION_DATABASE_ID",
        config.expression_data_source_id,
    )
    monkeypatch.setenv(
        "NOTION_VOCABULARY_DATABASE_ID",
        config.vocabulary_data_source_id,
    )
    monkeypatch.setenv(
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID",
        config.weekly_data_source_id,
    )
    monkeypatch.setenv(
        "NOTION_TARGET_PARENT_PAGE_ID",
        config.target_parent_page_id if target_parent is None else target_parent,
    )


def _assert_no_writes(notion: FakeNotion) -> None:
    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []
    assert notion.pages.delete_calls == []
    assert notion.blocks.children.append_calls == []
    assert notion.blocks.delete_calls == []
    assert notion.data_sources.update_calls == []
    assert notion.databases.create_calls == []
    assert notion.databases.update_calls == []


def test_legacy_create_vocabulary_database_is_disabled() -> None:
    notion = FakeNotion(seed_unrelated_records=False)

    with pytest.raises(VocabularyDatabaseSetupError) as exc:
        create_vocabulary_database("untrusted-parent", notion=notion)

    assert exc.value.code == LEGACY_VOCABULARY_DATABASE_CREATION_DISABLED
    _assert_no_writes(notion)


def test_sync_updates_only_bound_vocabulary_schema_with_single_relation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)

    database_id = sync_vocabulary_database_schema(notion=notion)

    assert database_id == notion.config.vocabulary_data_source_id
    assert len(notion.data_sources.update_calls) == 1
    update = notion.data_sources.update_calls[0]
    assert update["data_source_id"] == notion.config.vocabulary_data_source_id
    relation = update["properties"]["Source"]["relation"]
    assert relation == {
        "data_source_id": notion.config.podcast_data_source_id,
        "single_property": {},
    }
    assert "dual_property" not in relation
    assert set(update["properties"]) == {
        "Name",
        "First Seen",
        "Last Review",
        "Review Status",
        "Source",
    }
    assert notion.databases.create_calls == []
    assert notion.databases.update_calls == []


def test_direct_update_rejects_unconfigured_database_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)

    with pytest.raises(NotionTargetBindingError) as exc:
        _update_database(
            notion,
            "outside-vocabulary-data-source",
            notion.config.podcast_data_source_id,
        )

    assert exc.value.code == TARGET_DATABASE_ROLE_MISMATCH
    _assert_no_writes(notion)


def test_sync_rejects_missing_target_parent_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion, target_parent="")

    with pytest.raises(NotionTargetBindingError) as exc:
        sync_vocabulary_database_schema(notion=notion)

    assert exc.value.code == TARGET_PARENT_NOT_CONFIGURED
    _assert_no_writes(notion)


def test_sync_rejects_explicit_parent_mismatch_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)

    with pytest.raises(NotionTargetBindingError) as exc:
        sync_vocabulary_database_schema(
            notion=notion,
            parent_page_id="outside-parent",
        )

    assert exc.value.code == TARGET_PARENT_MISMATCH
    _assert_no_writes(notion)


def test_sync_rejects_mixed_parent_group_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)
    original_retrieve = notion.databases.retrieve
    podcast_database_id = notion.database_id_by_data_source_id[
        notion.config.podcast_data_source_id
    ]

    def retrieve(**kwargs):
        result = original_retrieve(**kwargs)
        if kwargs.get("database_id") == podcast_database_id:
            result = deepcopy(result)
            result["parent"]["page_id"] = "outside-parent"
        return result

    monkeypatch.setattr(notion.databases, "retrieve", retrieve)

    with pytest.raises(NotionTargetBindingError) as exc:
        sync_vocabulary_database_schema(notion=notion)

    assert exc.value.code == CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP
    _assert_no_writes(notion)


def test_sync_rejects_cross_group_relation_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)
    relation = notion.schemas[notion.config.expression_data_source_id][
        "Source Podcast"
    ]["relation"]
    relation["data_source_id"] = "outside-podcast-data-source"

    with pytest.raises(NotionTargetBindingError) as exc:
        sync_vocabulary_database_schema(notion=notion)

    assert exc.value.code == TARGET_RELATION_OUTSIDE_GROUP
    _assert_no_writes(notion)


def test_sync_rejects_dual_relation_before_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notion = FakeNotion(seed_unrelated_records=False)
    _configure_environment(monkeypatch, notion)
    relation = notion.schemas[notion.config.expression_data_source_id][
        "Source Podcast"
    ]["relation"]
    relation.pop("single_property")
    relation["dual_property"] = {"synced_property_name": "Expressions"}

    with pytest.raises(NotionTargetBindingError) as exc:
        sync_vocabulary_database_schema(notion=notion)

    assert exc.value.code == TARGET_RELATION_MODE_INVALID
    _assert_no_writes(notion)


def test_main_redacts_unexpected_failure(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        setup_vocabulary_database,
        "sync_vocabulary_database_schema",
        lambda: (_ for _ in ()).throw(
            RuntimeError("secret-token full-notion-id")
        ),
    )

    assert setup_vocabulary_database.main() == 1
    captured = capsys.readouterr()
    assert VOCABULARY_SCHEMA_SYNC_FAILED in captured.err
    assert "secret-token" not in captured.err
    assert "full-notion-id" not in captured.err
