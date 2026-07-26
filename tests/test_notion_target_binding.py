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
    TARGET_PAGE_OUTSIDE_GROUP,
    TARGET_PARENT_MISMATCH,
    TARGET_PARENT_NOT_CONFIGURED,
    TARGET_RELATION_MODE_INVALID,
    TARGET_RELATION_OUTSIDE_GROUP,
    NotionTargetBindingError,
    ensure_notion_page_belongs_to_role,
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


class _PageApi(_ReadApi):
    def __init__(
        self,
        records: dict[str, dict[str, Any]],
        calls: list[tuple[str, str]],
        writes: list[tuple[str, dict[str, Any]]],
    ) -> None:
        super().__init__(records, calls, "pages")
        self.mutable_records = records
        self.writes = writes
        self._created = 0

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self._created += 1
        page_id = f"created-page-{self._created}"
        parent = deepcopy(kwargs.get("parent", {}))
        self.mutable_records[normalize_notion_id(page_id)] = {
            "id": page_id,
            "parent": parent,
            "properties": deepcopy(kwargs.get("properties", {})),
            "archived": False,
            "in_trash": False,
        }
        self.calls.append(("pages.create", normalize_notion_id(page_id)))
        self.writes.append(("pages.create", deepcopy(kwargs)))
        return {"id": page_id, "url": "https://example.invalid/redacted"}

    def update(self, **kwargs: Any) -> dict[str, Any]:
        page_id = str(kwargs.get("page_id", ""))
        self.calls.append(("pages.update", normalize_notion_id(page_id)))
        self.writes.append(("pages.update", deepcopy(kwargs)))
        return {"id": page_id, "url": "https://example.invalid/redacted"}


class _DataSourceApi(_ReadApi):
    def __init__(
        self,
        records: Mapping[str, Mapping[str, Any]],
        calls: list[tuple[str, str]],
    ) -> None:
        super().__init__(records, calls, "data_sources")
        self.query_results: list[dict[str, Any]] = []

    def query(self, **kwargs: Any) -> dict[str, Any]:
        data_source_id = str(kwargs.get("data_source_id", ""))
        self.calls.append(
            ("data_sources.query", normalize_notion_id(data_source_id))
        )
        return {"results": deepcopy(self.query_results)}


class _BlocksChildrenApi:
    def __init__(
        self,
        calls: list[tuple[str, str]],
        writes: list[tuple[str, dict[str, Any]]],
    ) -> None:
        self.calls = calls
        self.writes = writes

    def append(self, **kwargs: Any) -> dict[str, Any]:
        block_id = str(kwargs.get("block_id", ""))
        self.calls.append(("blocks.children.append", normalize_notion_id(block_id)))
        self.writes.append(("blocks.children.append", deepcopy(kwargs)))
        return {"results": []}


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
        self.page_ids: dict[str, dict[str, str]] = {
            group: {} for group in ("old", "new")
        }
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
                page_id = f"{ROLE_SLUGS[role]}-{group}-page"
                self.page_ids[group][role] = page_id
                pages[page_id] = {
                    "id": page_id,
                    "parent": {
                        "type": "data_source_id",
                        "data_source_id": data_source_id,
                    },
                    "properties": {},
                    "archived": False,
                    "in_trash": False,
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
        self.data_sources = _DataSourceApi(
            self.data_source_records,
            self.calls,
        )
        self.databases = _ReadApi(
            self.database_records, self.calls, "databases"
        )
        self.pages = _PageApi(self.page_records, self.calls, self.writes)
        self.blocks = SimpleNamespace(
            children=_BlocksChildrenApi(self.calls, self.writes)
        )

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


def test_page_role_proof_rejects_old_group_without_writes() -> None:
    notion = BindingFakeNotion()

    with pytest.raises(NotionTargetBindingError) as exc:
        ensure_notion_page_belongs_to_role(
            notion,
            notion.page_ids["old"][PODCAST_LIBRARY],
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_page_role_proof_accepts_current_group_and_caches_read() -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]

    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=notion.config(),
    )
    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=notion.config(),
    )

    page_reads = [
        call
        for call in notion.calls
        if call == ("pages.retrieve", normalize_notion_id(page_id))
    ]
    assert len(page_reads) == 1
    assert notion.writes == []


@pytest.mark.parametrize(
    ("remove_id", "returned_id"),
    (
        (True, None),
        (False, ""),
        (False, "----"),
        (False, None),
        (False, 123),
        (False, {}),
        (False, []),
        (False, "different-private-page-id"),
    ),
)
def test_page_role_proof_rejects_missing_malformed_or_mismatched_page_id(
    remove_id,
    returned_id,
) -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    record = notion.page_records[normalize_notion_id(page_id)]
    if remove_id:
        record.pop("id")
    else:
        record["id"] = returned_id

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert str(raised.value) == TARGET_PAGE_OUTSIDE_GROUP
    assert "different-private-page-id" not in str(raised.value)
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


def test_page_role_proof_accepts_normalized_equivalent_page_id() -> None:
    notion = BindingFakeNotion()
    compact = "1234567890abcdef1234567890abcdef"
    hyphenated = (
        f"{compact[:8]}-{compact[8:12]}-{compact[12:16]}-"
        f"{compact[16:20]}-{compact[20:]}"
    )
    notion.page_records[compact] = {
        "id": compact.upper(),
        "parent": {
            "type": "data_source_id",
            "data_source_id": notion.role_ids["new"][PODCAST_LIBRARY],
        },
        "properties": {},
        "archived": False,
        "in_trash": False,
    }

    ensure_notion_page_belongs_to_role(
        notion,
        hyphenated,
        PODCAST_LIBRARY,
        config=notion.config(),
    )

    assert (
        "pages.retrieve",
        compact,
    ) in notion.calls
    assert (
        compact,
        PODCAST_LIBRARY,
    ) in notion._epla_target_page_role_proofs
    assert notion.writes == []


@pytest.mark.parametrize("flag", ("archived", "in_trash"))
def test_page_role_proof_requires_lifecycle_field(flag) -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    notion.page_records[normalize_notion_id(page_id)].pop(flag)

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


@pytest.mark.parametrize("flag", ("archived", "in_trash"))
@pytest.mark.parametrize(
    "value",
    (None, "false", 0, {}, [], True),
)
def test_page_role_proof_rejects_non_bool_or_true_lifecycle_value(
    flag,
    value,
) -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    notion.page_records[normalize_notion_id(page_id)][flag] = value

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


@pytest.mark.parametrize(
    "parent",
    (
        None,
        {},
        {"type": "page_id", "page_id": "private-parent"},
        {"type": "data_source_id"},
        {"type": "data_source_id", "data_source_id": None},
        {"type": "data_source_id", "data_source_id": 123},
        {"type": "data_source_id", "data_source_id": ""},
        {"type": "data_source_id", "data_source_id": "----"},
    ),
)
def test_page_role_proof_rejects_malformed_parent(parent) -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    notion.page_records[normalize_notion_id(page_id)]["parent"] = parent

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert "private-parent" not in str(raised.value)
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


def test_page_role_proof_failure_does_not_pollute_cache() -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    record = notion.page_records[normalize_notion_id(page_id)]
    record["id"] = "different-private-page-id"

    with pytest.raises(NotionTargetBindingError):
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert not hasattr(notion, "_epla_target_page_role_proofs")
    record["id"] = page_id

    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=notion.config(),
    )

    page_reads = [
        call
        for call in notion.calls
        if call == ("pages.retrieve", normalize_notion_id(page_id))
    ]
    assert len(page_reads) == 2
    assert (
        normalize_notion_id(page_id),
        PODCAST_LIBRARY,
    ) in notion._epla_target_page_role_proofs
    assert notion.writes == []


def test_page_role_proof_retrieve_failure_is_redacted() -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    validate_notion_target_binding(notion, notion.config())

    def fail_retrieve(**_kwargs):
        raise RuntimeError("private SDK detail and private page id")

    notion.pages.retrieve = fail_retrieve

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_BINDING_RETRIEVE_FAILED
    assert str(raised.value) == TARGET_BINDING_RETRIEVE_FAILED
    assert "private SDK detail" not in str(raised.value)
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


def test_page_role_proof_rejects_non_mapping_retrieve_result() -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    validate_notion_target_binding(notion, notion.config())
    notion.pages.retrieve = lambda **_kwargs: []

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
        )

    assert raised.value.code == TARGET_BINDING_RETRIEVE_FAILED
    assert not hasattr(notion, "_epla_target_page_role_proofs")
    assert notion.writes == []


def test_page_role_proof_force_refresh_reads_current_metadata() -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]

    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=notion.config(),
    )
    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=notion.config(),
        force_refresh=True,
    )

    page_reads = [
        call
        for call in notion.calls
        if call == ("pages.retrieve", normalize_notion_id(page_id))
    ]
    assert len(page_reads) == 2
    assert notion.writes == []


@pytest.mark.parametrize("flag", ("archived", "in_trash"))
def test_page_role_proof_rejects_archived_or_trashed_page(flag) -> None:
    notion = BindingFakeNotion()
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    notion.page_records[normalize_notion_id(page_id)][flag] = True

    with pytest.raises(NotionTargetBindingError) as raised:
        ensure_notion_page_belongs_to_role(
            notion,
            page_id,
            PODCAST_LIBRARY,
            config=notion.config(),
            force_refresh=True,
        )

    assert raised.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def _restore_writer_guards(monkeypatch, module) -> None:
    monkeypatch.setattr(
        module,
        "ensure_notion_target_binding_for_write",
        target_binding.ensure_notion_target_binding_for_write,
    )
    monkeypatch.setattr(
        module,
        "ensure_notion_page_belongs_to_role",
        target_binding.ensure_notion_page_belongs_to_role,
    )


def test_podcast_update_rejects_old_group_page_before_writes(monkeypatch) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, learning_publisher)
    analysis = SimpleNamespace(all_learning_items=lambda: [])

    with pytest.raises(NotionTargetBindingError) as exc:
        learning_publisher.update_podcast_learning_page(
            notion,
            notion.page_ids["old"][PODCAST_LIBRARY],
            analysis,
            "Safe transcript.",
        )

    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_podcast_update_reads_current_page_before_original_writes(
    monkeypatch,
) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, learning_publisher)
    monkeypatch.setattr(
        learning_publisher,
        "podcast_update_properties",
        lambda _analysis: {"Short Summary": {"rich_text": []}},
    )
    monkeypatch.setattr(
        learning_publisher,
        "analysis_summary_text",
        lambda _analysis: "Safe summary.",
    )
    monkeypatch.setattr(
        learning_publisher,
        "podcast_body_blocks",
        lambda **_kwargs: [],
    )
    page_id = notion.page_ids["new"][PODCAST_LIBRARY]

    learning_publisher.update_podcast_learning_page(
        notion,
        page_id,
        SimpleNamespace(all_learning_items=lambda: []),
        "Safe transcript.",
    )

    assert [name for name, _ in notion.writes] == [
        "pages.update",
        "blocks.children.append",
    ]
    page_read_index = notion.calls.index(
        ("pages.retrieve", normalize_notion_id(page_id))
    )
    update_index = notion.calls.index(("pages.update", normalize_notion_id(page_id)))
    assert page_read_index < update_index


def test_expression_relation_rejects_old_group_and_preserves_payload(
    monkeypatch,
) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, learning_publisher)
    monkeypatch.setattr(
        learning_publisher,
        "learning_item_payload",
        lambda _item: {},
    )
    monkeypatch.setattr(
        learning_publisher,
        "expression_body_blocks",
        lambda *_args, **_kwargs: [],
    )
    item = SimpleNamespace(
        text="safe expression",
        category="Business Phrase",
        commonness="High",
        context_sentence="Safe context.",
    )

    with pytest.raises(NotionTargetBindingError) as exc:
        learning_publisher.create_expression_page(
            notion,
            notion.role_ids["new"][EXPRESSION_DATABASE],
            notion.page_ids["old"][PODCAST_LIBRARY],
            item,
        )
    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []

    current_page_id = notion.page_ids["new"][PODCAST_LIBRARY]
    created_page_id = learning_publisher.create_expression_page(
        notion,
        notion.role_ids["new"][EXPRESSION_DATABASE],
        current_page_id,
        item,
    )
    assert created_page_id.startswith("created-page-")
    create_payload = notion.writes[-1][1]
    assert create_payload["properties"]["Source Podcast"] == {
        "relation": [{"id": current_page_id}]
    }


def test_legacy_podcast_pipeline_rejects_old_relation_and_append(
    monkeypatch,
) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, podcast_pipeline)
    publisher = podcast_pipeline.NotionPodcastPublisher(
        notion,
        notion.role_ids["new"][PODCAST_LIBRARY],
        notion.role_ids["new"][EXPRESSION_DATABASE],
    )
    old_page_id = notion.page_ids["old"][PODCAST_LIBRARY]
    transcript = podcast_pipeline.Transcript(text="Safe transcript.")
    expression = podcast_pipeline.LearningExpression(
        text="safe expression",
        category="Business Phrase",
        meaning="Safe meaning.",
        color="Blue",
    )

    with pytest.raises(NotionTargetBindingError) as relation_exc:
        publisher.create_expression_pages(
            old_page_id,
            transcript,
            [expression],
        )
    assert relation_exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []

    with pytest.raises(NotionTargetBindingError) as append_exc:
        publisher.insert_highlighted_transcript(
            old_page_id,
            transcript,
            SimpleNamespace(summary="Safe summary."),
            [expression],
        )
    assert append_exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_example_data_relation_rejects_old_group_page(monkeypatch) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, create_example_data)

    with pytest.raises(NotionTargetBindingError) as exc:
        create_example_data.create_expression_page(
            notion,
            notion.role_ids["new"][EXPRESSION_DATABASE],
            notion.page_ids["old"][PODCAST_LIBRARY],
            create_example_data.SAMPLE_EXPRESSIONS[0],
        )

    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_vocabulary_source_and_target_pages_must_belong_to_roles(
    monkeypatch,
) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, vocabulary_publisher)
    payload = vocabulary_publisher.VocabularyPublishPayload(
        word="assumption",
        source_page_id=notion.page_ids["old"][PODCAST_LIBRARY],
    )

    with pytest.raises(NotionTargetBindingError) as source_exc:
        vocabulary_publisher.create_vocabulary_page(
            payload,
            notion=notion,
            vocabulary_database_id=notion.role_ids["new"][VOCABULARY_DATABASE],
        )
    assert source_exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []

    with pytest.raises(NotionTargetBindingError) as target_exc:
        vocabulary_publisher.update_vocabulary_page(
            notion.page_ids["old"][VOCABULARY_DATABASE],
            vocabulary_publisher.VocabularyPublishPayload(word="assumption"),
            notion=notion,
        )
    assert target_exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_legacy_weekly_update_rejects_old_group_page(monkeypatch) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, weekly_review_publisher)
    old_page_id = notion.page_ids["old"][WEEKLY_REVIEW]
    notion.data_sources.query_results = [
        notion.page_records[normalize_notion_id(old_page_id)]
    ]
    payload = weekly_review_publisher.WeeklyReviewPublishPayload(
        week="2026-W27",
        executive_summary={},
        knowledge_insights=[],
        expression_upgrade=[],
        vocabulary_memory=[],
        career_reflection={},
        next_learning_direction=[],
    )

    with pytest.raises(NotionTargetBindingError) as exc:
        weekly_review_publisher.publish_weekly_review(
            payload,
            notion=notion,
            weekly_database_id=notion.role_ids["new"][WEEKLY_REVIEW],
            vocabulary_database_id=notion.role_ids["new"][VOCABULARY_DATABASE],
        )

    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


def test_weekly_relation_rejects_old_group_source_before_writes(
    monkeypatch,
) -> None:
    notion = BindingFakeNotion()
    monkeypatch.setattr(
        target_binding,
        "load_notion_config",
        lambda: notion.config(),
    )
    _restore_writer_guards(monkeypatch, weekly_reflection_writer)
    weekly_review = {
        "period": {
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
            "generated_at": "2026-07-07T12:00:00Z",
            "source": "Podcast Library",
        },
        "core_idea": {
            "idea": "Safe idea.",
            "why_it_matters": "Safe reason.",
            "refined_understanding": "Safe understanding.",
        },
        "mindset_shift": {"before": "Before.", "now": "Now."},
        "ideas_worth_compounding": [],
        "expressions_worth_reusing": [],
        "language_thinking_connection": "Safe connection.",
        "next_week_application": {
            "scenario": "Safe scenario.",
            "behavior": "Safe behavior.",
            "phrase_to_use": "Safe phrase.",
            "completion_condition": "Safe completion.",
        },
        "sources": [],
        "source_page_ids": [
            notion.page_ids["old"][PODCAST_LIBRARY],
        ],
    }
    reflection_context = {
        "weekly_theme": {
            "category": "Communication",
            "theme": "Safe theme",
        },
        "mindset_shifts": [
            {
                "before": "Before.",
                "after": "After.",
                "evidence": [
                    {
                        "source": "Safe source.",
                        "supporting_concept": "Safe concept.",
                    }
                ],
                "confidence": 0.8,
            }
        ],
        "cross_content_patterns": ["Safe pattern."],
        "professional_actions": ["Safe action."],
    }

    with pytest.raises(NotionTargetBindingError) as exc:
        weekly_reflection_writer.publish_weekly_reflection(
            weekly_review,
            reflection_context,
            notion=notion,
            weekly_reflection_database_id=notion.role_ids["new"][WEEKLY_REVIEW],
            podcast_database_id=notion.role_ids["new"][PODCAST_LIBRARY],
        )

    assert exc.value.code == TARGET_PAGE_OUTSIDE_GROUP
    assert notion.writes == []


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
    source = inspect.getsource(writer)
    assert (
        "ensure_notion_target_binding_for_write" in source
        or "ensure_notion_page_belongs_to_role" in source
    )
