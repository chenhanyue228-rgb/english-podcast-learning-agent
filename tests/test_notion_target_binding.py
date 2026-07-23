from __future__ import annotations

import re
import inspect
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from src.notion.config import NotionConfig
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    REQUIRED_DATABASE_PROPERTIES,
    REQUIRED_DATABASE_RELATIONS,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
    WORKSPACE_DATABASE_ORDER,
)
from src.notion.target_binding import (
    CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP,
    TARGET_BINDING_RETRIEVE_FAILED,
    TARGET_PARENT_MISMATCH,
    TARGET_PARENT_NOT_CONFIGURED,
    TARGET_RELATION_MODE_INVALID,
    TARGET_RELATION_OUTSIDE_GROUP,
    NotionTargetBindingError,
    normalize_notion_id,
    validate_notion_target_binding,
)
from src.notion import target_binding, uploader
from src.notion import (
    create_example_data,
    learning_publisher,
    vocabulary_publisher,
    weekly_reflection_writer,
    weekly_review_publisher,
)
from src.workflow import podcast_pipeline
from src.notion.uploader import PodcastUploadPayload


ROLE_SLUGS = {
    PODCAST_LIBRARY: "podcast",
    EXPRESSION_DATABASE: "expression",
    VOCABULARY_DATABASE: "vocabulary",
    WEEKLY_REVIEW: "weekly",
}


def _rich_text(value: str) -> list[dict[str, str]]:
    return [{"plain_text": value}]


def _schema(role: str, role_ids: Mapping[str, str]) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for name, property_type in REQUIRED_DATABASE_PROPERTIES[role].items():
        prop: dict[str, Any] = {"type": property_type}
        target_role = (REQUIRED_DATABASE_RELATIONS.get(role) or {}).get(name)
        if target_role:
            prop["relation"] = {
                "data_source_id": role_ids[target_role],
                "single_property": {},
            }
        properties[name] = prop
    return properties


class _ReadApi:
    def __init__(
        self,
        records: Mapping[str, Mapping[str, Any]],
        calls: list[tuple[str, str]],
        endpoint: str,
    ) -> None:
        self.records = records
        self.calls = calls
        self.endpoint = endpoint

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        key_name = {
            "data_sources": "data_source_id",
            "databases": "database_id",
            "pages": "page_id",
        }[self.endpoint]
        raw_id = str(kwargs[key_name])
        self.calls.append((f"{self.endpoint}.retrieve", normalize_notion_id(raw_id)))
        record = self.records.get(normalize_notion_id(raw_id))
        if record is None:
            raise RuntimeError("private fake retrieve detail")
        return deepcopy(dict(record))


class BindingFakeNotion:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.parents = {
            "old": "11111111111111111111111111111111",
            "new": "22222222222222222222222222222222",
        }
        self.role_ids = {
            group: {
                role: f"{index}{group == 'new' and '2' or '1'}" * 16
                for index, role in enumerate(WORKSPACE_DATABASE_ORDER, start=3)
            }
            for group in ("old", "new")
        }
        self.database_ids = {
            group: {
                role: f"{index}{group == 'new' and 'b' or 'a'}" * 16
                for index, role in enumerate(WORKSPACE_DATABASE_ORDER, start=7)
            }
            for group in ("old", "new")
        }
        data_sources: dict[str, dict[str, Any]] = {}
        databases: dict[str, dict[str, Any]] = {}
        pages: dict[str, dict[str, Any]] = {}
        for group in ("old", "new"):
            pages[self.parents[group]] = {"id": self.parents[group], "object": "page"}
            for role in WORKSPACE_DATABASE_ORDER:
                data_source_id = self.role_ids[group][role]
                database_id = self.database_ids[group][role]
                data_sources[data_source_id] = {
                    "id": data_source_id,
                    "name": role,
                    "parent": {"type": "database_id", "database_id": database_id},
                    "properties": _schema(role, self.role_ids[group]),
                }
                databases[database_id] = {
                    "id": database_id,
                    "title": _rich_text(role),
                    "parent": {
                        "type": "page_id",
                        "page_id": self.parents[group],
                    },
                    "data_sources": [{"id": data_source_id, "name": role}],
                }
        self.data_source_records = {
            normalize_notion_id(key): value for key, value in data_sources.items()
        }
        self.database_records = {
            normalize_notion_id(key): value for key, value in databases.items()
        }
        self.page_records = {
            normalize_notion_id(key): value for key, value in pages.items()
        }
        self.data_sources = _ReadApi(
            self.data_source_records, self.calls, "data_sources"
        )
        self.databases = _ReadApi(
            self.database_records, self.calls, "databases"
        )
        self.pages = _ReadApi(self.page_records, self.calls, "pages")
        self.blocks = SimpleNamespace()

    def config(
        self,
        *,
        group: str = "new",
        expected_parent_group: str = "new",
    ) -> NotionConfig:
        ids = self.role_ids[group]
        return NotionConfig(
            token="obviously-fake-token",
            podcast_database_id=ids[PODCAST_LIBRARY],
            expression_database_id=ids[EXPRESSION_DATABASE],
            vocabulary_database_id=ids[VOCABULARY_DATABASE],
            weekly_database_id=ids[WEEKLY_REVIEW],
            target_parent_page_id=self.parents[expected_parent_group],
        )

    def relation(
        self,
        group: str,
        role: str,
        property_name: str,
    ) -> dict[str, Any]:
        return self.data_source_records[
            normalize_notion_id(self.role_ids[group][role])
        ]["properties"][property_name]["relation"]


def test_correct_group_returns_redacted_immutable_proof() -> None:
    notion = BindingFakeNotion()

    result = validate_notion_target_binding(notion, notion.config())

    assert result.valid is True
    assert result.verified_roles == WORKSPACE_DATABASE_ORDER
    assert result.configured_parent_matches_expected is True
    assert result.all_data_sources_same_group is True
    assert result.internal_relations_verified is True
    assert re.fullmatch(r"[0-9a-f]{8}", result.target_parent_fingerprint)
    assert re.fullmatch(r"[0-9a-f]{8}", result.target_group_fingerprint)
    with pytest.raises(Exception):
        result.valid = False  # type: ignore[misc]


def test_same_names_do_not_override_parent_mismatch() -> None:
    notion = BindingFakeNotion()

    with pytest.raises(NotionTargetBindingError) as exc:
        validate_notion_target_binding(
            notion,
            notion.config(group="old", expected_parent_group="new"),
        )

    assert exc.value.code == TARGET_PARENT_MISMATCH
    assert notion.writes == []


def test_mixed_groups_are_rejected_before_parent_check() -> None:
    notion = BindingFakeNotion()
    config = replace(
        notion.config(),
        podcast_database_id=notion.role_ids["old"][PODCAST_LIBRARY],
    )

    with pytest.raises(NotionTargetBindingError) as exc:
        validate_notion_target_binding(notion, config)

    assert exc.value.code == CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP


@pytest.mark.parametrize(
    ("role", "property_name"),
    (
        (EXPRESSION_DATABASE, "Source Podcast"),
        (VOCABULARY_DATABASE, "Source"),
        (WEEKLY_REVIEW, "Podcasts"),
    ),
)
def test_cross_group_relations_are_rejected(
    role: str,
    property_name: str,
) -> None:
    notion = BindingFakeNotion()
    relation = notion.relation("new", role, property_name)
    relation["data_source_id"] = notion.role_ids["old"][PODCAST_LIBRARY]

    with pytest.raises(NotionTargetBindingError) as exc:
        validate_notion_target_binding(notion, notion.config())

    assert exc.value.code == TARGET_RELATION_OUTSIDE_GROUP


def test_dual_property_relation_is_rejected() -> None:
    notion = BindingFakeNotion()
    relation = notion.relation("new", EXPRESSION_DATABASE, "Source Podcast")
    relation.pop("single_property")
    relation["dual_property"] = {"synced_property_name": "Expressions"}

    with pytest.raises(NotionTargetBindingError) as exc:
        validate_notion_target_binding(notion, notion.config())

    assert exc.value.code == TARGET_RELATION_MODE_INVALID


def test_hyphenated_and_compact_ids_compare_equal() -> None:
    notion = BindingFakeNotion()
    compact = notion.parents["new"]
    hyphenated = (
        f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-"
        f"{compact[16:20]}-{compact[20:]}"
    )
    config = replace(notion.config(), target_parent_page_id=hyphenated.upper())

    result = validate_notion_target_binding(notion, config)

    assert result.valid is True


@pytest.mark.parametrize("endpoint", ("data_source", "database", "parent"))
def test_retrieve_failures_are_redacted(endpoint: str) -> None:
    notion = BindingFakeNotion()
    if endpoint == "data_source":
        notion.data_source_records.clear()
    elif endpoint == "database":
        notion.database_records.clear()
    else:
        notion.page_records.clear()

    with pytest.raises(NotionTargetBindingError) as exc:
        validate_notion_target_binding(notion, notion.config())

    assert exc.value.code == TARGET_BINDING_RETRIEVE_FAILED
    assert "private fake retrieve detail" not in str(exc.value)


@pytest.mark.parametrize(
    ("config", "expected_code"),
    (
        ("mismatch", TARGET_PARENT_MISMATCH),
        ("missing", TARGET_PARENT_NOT_CONFIGURED),
    ),
)
def test_transcript_publisher_stops_before_every_write(
    monkeypatch,
    config: str,
    expected_code: str,
) -> None:
    notion = BindingFakeNotion()
    selected_config = (
        notion.config(group="old", expected_parent_group="new")
        if config == "mismatch"
        else replace(notion.config(), target_parent_page_id="")
    )
    page_creates: list[dict[str, Any]] = []
    notion.pages.create = lambda **kwargs: page_creates.append(kwargs)
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: selected_config,
    )
    monkeypatch.setattr(
        uploader,
        "ensure_notion_target_binding_for_write",
        target_binding.ensure_notion_target_binding_for_write,
    )

    with pytest.raises(NotionTargetBindingError) as exc:
        uploader.create_podcast_page(
            PodcastUploadPayload(
                title="Safe fake title",
                source_url=None,
                source_type="Local Audio",
                transcript="Safe fake transcript.",
            ),
            notion=notion,
            podcast_database_id=selected_config.podcast_database_id,
        )

    assert exc.value.code == expected_code
    assert page_creates == []
    assert notion.writes == []


@pytest.mark.parametrize(
    "writer",
    (
        learning_publisher.ensure_expression_database_schema,
        learning_publisher.update_podcast_learning_page,
        learning_publisher.create_expression_page,
        learning_publisher.create_complete_podcast_learning_page,
        learning_publisher.update_complete_podcast_page_properties,
        learning_publisher.publish_complete_learning_materials,
        learning_publisher.publish_learning_materials,
        vocabulary_publisher.create_vocabulary_page,
        vocabulary_publisher.update_vocabulary_page,
        vocabulary_publisher.upsert_vocabulary_page,
        weekly_reflection_writer.publish_weekly_reflection,
        weekly_review_publisher.publish_weekly_review,
        uploader.create_podcast_page,
        create_example_data.create_podcast_page,
        create_example_data.create_expression_page,
        podcast_pipeline.NotionPodcastPublisher.create_podcast_page,
        podcast_pipeline.NotionPodcastPublisher.create_expression_pages,
        podcast_pipeline.NotionPodcastPublisher.insert_highlighted_transcript,
    ),
)
def test_every_production_writer_declares_target_binding_guard(writer) -> None:
    assert "ensure_notion_target_binding_for_write" in inspect.getsource(writer)
