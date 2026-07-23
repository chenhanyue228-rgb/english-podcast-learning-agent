"""Safe owner-acceptance harness for the complete podcast publisher.

The harness deliberately treats ``publish_complete_learning_materials`` as a
black box. It snapshots the configured Notion data sources, wraps the injected
Notion client with a strict write guard, invokes the production publisher
twice, and compares normalized in-memory state.

No identifier, URL, secret, raw API response, or record body is included in
the public report. Temporary snapshot evidence contains counts only and is
removed in ``finally``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from src.analyzer.models import LearningItem
from src.notion.check_workspace import validate_database
from src.notion.config import NotionConfig, load_dotenv, load_notion_config
from src.notion.learning_publisher import (
    CompletePodcastLearningPayload,
    publish_complete_learning_materials,
)
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    REQUIRED_DATABASE_PROPERTIES,
    REQUIRED_DATABASE_RELATIONS,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
    WORKSPACE_DATABASE_ORDER,
)


SETUP_STATE_ENV = "EPLA_NOTION_SETUP_STATE"
SETUP_STATE_COMPLETE = "complete"
DEPENDS_ON_PR_9 = True


class AcceptanceConfigurationError(RuntimeError):
    """Raised when owner-acceptance configuration is not safe to use."""


class AcceptanceFailure(AssertionError):
    """A redacted owner-acceptance failure identified only by a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GuardViolation(PermissionError):
    """A blocked Notion operation identified only by a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, repr=False)
class AcceptanceConfig:
    """Validated runtime configuration whose repr cannot expose secrets."""

    token: str = field(repr=False)
    podcast_data_source_id: str = field(repr=False)
    expression_data_source_id: str = field(repr=False)
    vocabulary_data_source_id: str = field(repr=False)
    weekly_data_source_id: str = field(repr=False)
    setup_state: str = field(repr=False, default=SETUP_STATE_COMPLETE)

    @classmethod
    def from_notion_config(
        cls,
        config: NotionConfig,
        setup_state: str = SETUP_STATE_COMPLETE,
    ) -> "AcceptanceConfig":
        return cls(
            token=config.token,
            podcast_data_source_id=config.podcast_database_id,
            expression_data_source_id=config.expression_database_id,
            vocabulary_data_source_id=config.vocabulary_database_id,
            weekly_data_source_id=config.weekly_database_id,
            setup_state=setup_state,
        )

    @property
    def data_source_ids(self) -> dict[str, str]:
        return {
            PODCAST_LIBRARY: self.podcast_data_source_id,
            EXPRESSION_DATABASE: self.expression_data_source_id,
            VOCABULARY_DATABASE: self.vocabulary_data_source_id,
            WEEKLY_REVIEW: self.weekly_data_source_id,
        }


def load_acceptance_config(
    env: Optional[Mapping[str, str]] = None,
    dotenv_path: Path = Path(".env"),
) -> AcceptanceConfig:
    """Read existing setup safely without printing or returning public values."""
    if env is None:
        load_dotenv(dotenv_path)
        env = os.environ

    setup_state = env.get(SETUP_STATE_ENV, "").strip()
    if setup_state != SETUP_STATE_COMPLETE:
        raise AcceptanceConfigurationError("setup_state_not_complete")

    notion_config = load_notion_config(env=env, dotenv_path=dotenv_path)
    acceptance_config = AcceptanceConfig.from_notion_config(
        notion_config,
        setup_state=setup_state,
    )
    configured_ids = list(acceptance_config.data_source_ids.values())
    if len(configured_ids) != 4 or len(set(configured_ids)) != 4:
        raise AcceptanceConfigurationError("four_data_sources_not_configured")
    return acceptance_config


def _rich_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        plain = item.get("plain_text")
        if isinstance(plain, str):
            parts.append(plain)
            continue
        text = item.get("text")
        if isinstance(text, Mapping):
            content = text.get("content")
            if isinstance(content, str):
                parts.append(content)
    return "".join(parts)


def _normalized_property(value: Any) -> Any:
    if not isinstance(value, Mapping):
        return None
    property_type = str(value.get("type", "")).strip()
    if property_type == "title" or "title" in value:
        return _rich_text(value.get("title"))
    if property_type == "rich_text" or "rich_text" in value:
        return _rich_text(value.get("rich_text"))
    if property_type == "select" or "select" in value:
        selected = value.get("select")
        return selected.get("name") if isinstance(selected, Mapping) else None
    if property_type == "url" or "url" in value:
        return value.get("url")
    if property_type == "date" or "date" in value:
        date_value = value.get("date")
        return date_value.get("start") if isinstance(date_value, Mapping) else None
    if property_type == "relation" or "relation" in value:
        relations = value.get("relation")
        if not isinstance(relations, list):
            return ()
        return tuple(
            str(relation.get("id", "")).strip()
            for relation in relations
            if isinstance(relation, Mapping) and relation.get("id")
        )
    if property_type == "checkbox" or "checkbox" in value:
        return bool(value.get("checkbox"))
    if property_type == "number" or "number" in value:
        return value.get("number")
    return None


def _normalized_properties(properties: Any) -> dict[str, Any]:
    if not isinstance(properties, Mapping):
        return {}
    return {
        str(name): _normalized_property(value)
        for name, value in properties.items()
    }


def _normalized_block(block: Any) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        return {"type": "invalid", "text": "", "children": []}
    block_type = str(block.get("type", "")).strip() or "unknown"
    payload = block.get(block_type)
    payload = payload if isinstance(payload, Mapping) else {}
    children = payload.get("children")
    normalized_children = (
        [_normalized_block(child) for child in children]
        if isinstance(children, list)
        else []
    )
    return {
        "type": block_type,
        "text": _rich_text(payload.get("rich_text")),
        "children": normalized_children,
    }


@dataclass(frozen=True)
class PageSnapshot:
    """Normalized page state retained only in memory."""

    page_id: str = field(repr=False)
    properties: Mapping[str, Any] = field(repr=False)
    body: tuple[Mapping[str, Any], ...] = field(repr=False)
    archived: bool = field(repr=False)
    in_trash: bool = field(repr=False)

    def property(self, name: str) -> Any:
        return self.properties.get(name)

    def fingerprint(self) -> str:
        return json.dumps(
            {
                "properties": self.properties,
                "body": self.body,
                "archived": self.archived,
                "in_trash": self.in_trash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """Four normalized Notion data-source snapshots."""

    records: Mapping[str, tuple[PageSnapshot, ...]] = field(repr=False)

    def pages(self, name: str) -> tuple[PageSnapshot, ...]:
        return self.records.get(name, ())

    def by_id(self, name: str) -> dict[str, PageSnapshot]:
        return {page.page_id: page for page in self.pages(name)}

    def safe_counts(self) -> dict[str, int]:
        return {name: len(self.pages(name)) for name in WORKSPACE_DATABASE_ORDER}


@dataclass(frozen=True)
class PodcastIdentity:
    """Public business identity; page IDs are intentionally absent."""

    title: str = field(repr=False)
    source_type: str = field(repr=False)
    source_url: Optional[str] = field(repr=False)

    @classmethod
    def from_payload(
        cls,
        payload: CompletePodcastLearningPayload,
    ) -> "PodcastIdentity":
        title = payload.analysis.podcast_metadata.title or payload.title
        return cls(
            title=title,
            source_type=payload.source_type,
            source_url=payload.source_url,
        )

    def matches(self, page: PageSnapshot) -> bool:
        if self.source_url:
            return page.property("URL") == self.source_url
        return (
            page.property("Title") == self.title
            and page.property("Source Type") == self.source_type
        )


def _expected_expression_items(
    payload: CompletePodcastLearningPayload,
) -> dict[tuple[str, str], LearningItem]:
    expected: dict[tuple[str, str], LearningItem] = {}
    for item in payload.analysis.all_learning_items():
        expected.setdefault((item.text, item.category), item)
    return expected


def _expression_key(page: PageSnapshot) -> tuple[str, str]:
    return (
        str(page.property("Expression") or ""),
        str(page.property("Category") or ""),
    )


def _expression_relations(page: PageSnapshot) -> tuple[str, ...]:
    relations = page.property("Source Podcast")
    return relations if isinstance(relations, tuple) else ()


@dataclass(repr=False)
class AcceptancePolicy:
    """Mutable in-memory scope used by the write guard."""

    config: AcceptanceConfig = field(repr=False)
    identity: PodcastIdentity = field(repr=False)
    expected_expression_keys: frozenset[tuple[str, str]] = field(repr=False)
    target_podcast_page_ids: set[str] = field(default_factory=set, repr=False)
    target_expression_page_ids: set[str] = field(default_factory=set, repr=False)
    created_podcast_page_ids: set[str] = field(default_factory=set, repr=False)
    created_expression_page_ids: set[str] = field(default_factory=set, repr=False)

    @property
    def allowed_data_source_ids(self) -> frozenset[str]:
        return frozenset(self.config.data_source_ids.values())

    @property
    def allowed_update_page_ids(self) -> frozenset[str]:
        return frozenset(
            self.target_podcast_page_ids
            | self.target_expression_page_ids
            | self.created_podcast_page_ids
            | self.created_expression_page_ids
        )

    @property
    def current_target_podcast_ids(self) -> frozenset[str]:
        return frozenset(
            self.target_podcast_page_ids | self.created_podcast_page_ids
        )

    def authorize_snapshot_scope(self, snapshot: WorkspaceSnapshot) -> None:
        target_pages = [
            page
            for page in snapshot.pages(PODCAST_LIBRARY)
            if self.identity.matches(page)
        ]
        if len(target_pages) > 1:
            raise AcceptanceFailure("podcast_identity_not_unique")
        self.target_podcast_page_ids.update(page.page_id for page in target_pages)
        if not self.target_podcast_page_ids:
            return
        target_id = next(iter(self.target_podcast_page_ids))
        for page in snapshot.pages(EXPRESSION_DATABASE):
            if (
                target_id in _expression_relations(page)
                and _expression_key(page) in self.expected_expression_keys
            ):
                self.target_expression_page_ids.add(page.page_id)

    def validate_data_source_read(self, data_source_id: str) -> None:
        if data_source_id not in self.allowed_data_source_ids:
            raise GuardViolation("unexpected_data_source_read_blocked")

    def validate_page_create(self, kwargs: Mapping[str, Any]) -> str:
        parent = kwargs.get("parent")
        parent = parent if isinstance(parent, Mapping) else {}
        data_source_id = str(parent.get("data_source_id", "")).strip()
        properties = kwargs.get("properties")
        properties = properties if isinstance(properties, Mapping) else {}

        if data_source_id == self.config.vocabulary_data_source_id:
            raise GuardViolation("vocabulary_write_blocked")
        if data_source_id == self.config.weekly_data_source_id:
            raise GuardViolation("weekly_review_write_blocked")
        if data_source_id == self.config.podcast_data_source_id:
            normalized = _normalized_properties(properties)
            if self.identity.source_url:
                identity_matches = normalized.get("URL") == self.identity.source_url
            else:
                identity_matches = (
                    normalized.get("Title") == self.identity.title
                    and normalized.get("Source Type") == self.identity.source_type
                )
            if not identity_matches or self.current_target_podcast_ids:
                raise GuardViolation("unexpected_podcast_create_blocked")
            return PODCAST_LIBRARY
        if data_source_id == self.config.expression_data_source_id:
            normalized = _normalized_properties(properties)
            key = (
                str(normalized.get("Expression") or ""),
                str(normalized.get("Category") or ""),
            )
            relation_ids = normalized.get("Source Podcast")
            if (
                key not in self.expected_expression_keys
                or not isinstance(relation_ids, tuple)
                or len(relation_ids) != 1
                or relation_ids[0] not in self.current_target_podcast_ids
            ):
                raise GuardViolation("unexpected_expression_create_blocked")
            return EXPRESSION_DATABASE
        raise GuardViolation("unexpected_page_create_blocked")

    def register_created_page(self, kind: str, page_id: str) -> None:
        if not page_id:
            raise GuardViolation("page_create_response_rejected")
        if kind == PODCAST_LIBRARY:
            self.created_podcast_page_ids.add(page_id)
        elif kind == EXPRESSION_DATABASE:
            self.created_expression_page_ids.add(page_id)

    def validate_page_update(self, kwargs: Mapping[str, Any]) -> None:
        if "archived" in kwargs or "in_trash" in kwargs:
            raise GuardViolation("delete_or_archive_blocked")
        page_id = str(kwargs.get("page_id", "")).strip()
        if page_id not in self.allowed_update_page_ids:
            raise GuardViolation("unexpected_page_update_blocked")
        if set(kwargs) - {"page_id", "properties"}:
            raise GuardViolation("unexpected_page_update_shape_blocked")


class _GuardedDataSources:
    def __init__(self, raw: Any, policy: AcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def retrieve(self, **kwargs: Any) -> Any:
        self._policy.validate_data_source_read(
            str(kwargs.get("data_source_id", "")).strip()
        )
        return self._raw.retrieve(**kwargs)

    def query(self, **kwargs: Any) -> Any:
        self._policy.validate_data_source_read(
            str(kwargs.get("data_source_id", "")).strip()
        )
        return self._raw.query(**kwargs)

    def update(self, **kwargs: Any) -> Any:
        raise GuardViolation("schema_mutation_blocked")

    def __getattr__(self, name: str) -> Any:
        raise GuardViolation("unsupported_data_source_operation_blocked")


class _GuardedPages:
    def __init__(self, raw: Any, policy: AcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def create(self, **kwargs: Any) -> Any:
        kind = self._policy.validate_page_create(kwargs)
        response = self._raw.create(**kwargs)
        page_id = (
            str(response.get("id", "")).strip()
            if isinstance(response, Mapping)
            else ""
        )
        self._policy.register_created_page(kind, page_id)
        return response

    def update(self, **kwargs: Any) -> Any:
        self._policy.validate_page_update(kwargs)
        return self._raw.update(**kwargs)

    def delete(self, **kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, name: str) -> Any:
        raise GuardViolation("unsupported_page_operation_blocked")


class _GuardedBlocksChildren:
    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def list(self, **kwargs: Any) -> Any:
        return self._raw.list(**kwargs)

    def append(self, **kwargs: Any) -> Any:
        raise GuardViolation("block_append_blocked")

    def __getattr__(self, name: str) -> Any:
        raise GuardViolation("unsupported_block_operation_blocked")


class _GuardedBlocks:
    def __init__(self, raw: Any) -> None:
        self.children = _GuardedBlocksChildren(raw.children)

    def delete(self, **kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, name: str) -> Any:
        raise GuardViolation("unsupported_block_operation_blocked")


class _GuardedDatabases:
    def create(self, **kwargs: Any) -> Any:
        raise GuardViolation("database_creation_blocked")

    def update(self, **kwargs: Any) -> Any:
        raise GuardViolation("schema_mutation_blocked")

    def delete(self, **kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, name: str) -> Any:
        raise GuardViolation("unsupported_database_operation_blocked")


class AcceptanceGuard:
    """Notion client facade exposing only the acceptance allowlist."""

    def __init__(self, notion: Any, policy: AcceptancePolicy) -> None:
        self.policy = policy
        self.data_sources = _GuardedDataSources(notion.data_sources, policy)
        self.pages = _GuardedPages(notion.pages, policy)
        self.blocks = _GuardedBlocks(notion.blocks)
        self.databases = _GuardedDatabases()


class WorkspaceSnapshotter:
    """Capture normalized read-only snapshots of all four data sources."""

    def __init__(self, notion: AcceptanceGuard, config: AcceptanceConfig) -> None:
        self.notion = notion
        self.config = config

    def _query_all(self, data_source_id: str) -> list[Mapping[str, Any]]:
        pages: list[Mapping[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            kwargs: dict[str, Any] = {
                "data_source_id": data_source_id,
                "page_size": 100,
            }
            if cursor:
                kwargs["start_cursor"] = cursor
            response = self.notion.data_sources.query(**kwargs)
            if not isinstance(response, Mapping):
                raise AcceptanceFailure("invalid_data_source_query_response")
            results = response.get("results")
            if not isinstance(results, list):
                raise AcceptanceFailure("invalid_data_source_query_response")
            pages.extend(result for result in results if isinstance(result, Mapping))
            if not response.get("has_more"):
                return pages
            cursor_value = response.get("next_cursor")
            cursor = str(cursor_value).strip() if cursor_value is not None else ""
            if not cursor:
                raise AcceptanceFailure("invalid_data_source_pagination")

    def _body(self, page_id: str) -> tuple[Mapping[str, Any], ...]:
        blocks: list[Mapping[str, Any]] = []
        cursor: Optional[str] = None
        while True:
            kwargs: dict[str, Any] = {"block_id": page_id, "page_size": 100}
            if cursor:
                kwargs["start_cursor"] = cursor
            response = self.notion.blocks.children.list(**kwargs)
            if not isinstance(response, Mapping):
                raise AcceptanceFailure("invalid_block_query_response")
            results = response.get("results")
            if not isinstance(results, list):
                raise AcceptanceFailure("invalid_block_query_response")
            blocks.extend(_normalized_block(block) for block in results)
            if not response.get("has_more"):
                return tuple(blocks)
            cursor_value = response.get("next_cursor")
            cursor = str(cursor_value).strip() if cursor_value is not None else ""
            if not cursor:
                raise AcceptanceFailure("invalid_block_pagination")

    def capture(self) -> WorkspaceSnapshot:
        records: dict[str, tuple[PageSnapshot, ...]] = {}
        for name in WORKSPACE_DATABASE_ORDER:
            pages: list[PageSnapshot] = []
            for raw_page in self._query_all(self.config.data_source_ids[name]):
                page_id = str(raw_page.get("id", "")).strip()
                if not page_id:
                    raise AcceptanceFailure("snapshot_page_identity_missing")
                pages.append(
                    PageSnapshot(
                        page_id=page_id,
                        properties=_normalized_properties(raw_page.get("properties")),
                        body=self._body(page_id),
                        archived=bool(raw_page.get("archived", False)),
                        in_trash=bool(raw_page.get("in_trash", False)),
                    )
                )
            records[name] = tuple(pages)
        return WorkspaceSnapshot(records=records)


class TemporarySnapshotStore:
    """Counts-only temporary evidence that is always removed by the runner."""

    def __init__(self, root: Optional[Path] = None) -> None:
        root_path = str(root) if root is not None else None
        self.path = Path(
            tempfile.mkdtemp(prefix="epla-owner-acceptance-", dir=root_path)
        )
        self.cleaned = False

    def persist(self, label: str, snapshot: WorkspaceSnapshot) -> None:
        safe_label = re.sub(r"[^a-z0-9_-]+", "-", label.casefold()).strip("-")
        if not safe_label:
            raise AcceptanceFailure("invalid_snapshot_label")
        output_path = self.path / f"{safe_label}.json"
        output_path.write_text(
            json.dumps(
                {"label": safe_label, "counts": snapshot.safe_counts()},
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def cleanup(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)
        self.cleaned = not self.path.exists()


def _assert_workspace_schema_ready(
    notion: AcceptanceGuard,
    config: AcceptanceConfig,
) -> None:
    ids = config.data_source_ids
    for name in WORKSPACE_DATABASE_ORDER:
        try:
            response = notion.data_sources.retrieve(data_source_id=ids[name])
        except Exception as exc:
            if isinstance(exc, GuardViolation):
                raise
            raise AcceptanceFailure("workspace_data_source_unavailable") from None
        if not isinstance(response, Mapping):
            raise AcceptanceFailure("workspace_schema_incomplete")
        relation_targets = {
            property_name: ids[target_name]
            for property_name, target_name in (
                REQUIRED_DATABASE_RELATIONS.get(name) or {}
            ).items()
        }
        validation = validate_database(
            name,
            dict(response),
            REQUIRED_DATABASE_PROPERTIES[name],
            relation_targets,
        )
        if not validation.is_valid:
            raise AcceptanceFailure("workspace_schema_incomplete")


def _assert_record_sets_equal(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    name: str,
    failure_code: str,
) -> None:
    before_by_id = before.by_id(name)
    after_by_id = after.by_id(name)
    if set(before_by_id) != set(after_by_id):
        raise AcceptanceFailure(failure_code)
    if any(
        before_by_id[page_id].fingerprint()
        != after_by_id[page_id].fingerprint()
        for page_id in before_by_id
    ):
        raise AcceptanceFailure(failure_code)


def _assert_no_delete_or_archive(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
) -> None:
    for name in WORKSPACE_DATABASE_ORDER:
        after_by_id = after.by_id(name)
        for page in before.pages(name):
            current = after_by_id.get(page.page_id)
            if current is None:
                raise AcceptanceFailure("record_deleted_or_archived")
            if (not page.archived and current.archived) or (
                not page.in_trash and current.in_trash
            ):
                raise AcceptanceFailure("record_deleted_or_archived")


def _assert_other_records_unchanged(
    before: WorkspaceSnapshot,
    after: WorkspaceSnapshot,
    target_podcast_id: str,
) -> None:
    for name in (PODCAST_LIBRARY, EXPRESSION_DATABASE):
        before_by_id = before.by_id(name)
        after_by_id = after.by_id(name)
        excluded_ids = {target_podcast_id} if name == PODCAST_LIBRARY else {
            page.page_id
            for page in before.pages(EXPRESSION_DATABASE)
            if target_podcast_id in _expression_relations(page)
        }
        before_other = set(before_by_id) - excluded_ids
        after_other = {
            page_id
            for page_id, page in after_by_id.items()
            if (
                page_id != target_podcast_id
                if name == PODCAST_LIBRARY
                else target_podcast_id not in _expression_relations(page)
            )
        }
        if before_other != after_other:
            raise AcceptanceFailure("unrelated_record_changed")
        if any(
            before_by_id[page_id].fingerprint()
            != after_by_id[page_id].fingerprint()
            for page_id in before_other
        ):
            raise AcceptanceFailure("unrelated_record_changed")


def _section_counts(page: PageSnapshot) -> dict[str, int]:
    expected_sections = {
        "Summary",
        "Expressions",
        "Highlight Legend",
        "Highlighted Transcript",
    }
    counts = {section: 0 for section in expected_sections}
    for block in page.body:
        text = str(block.get("text", ""))
        if text in counts:
            counts[text] += 1
    return counts


def _assert_podcast_page_complete(
    page: PageSnapshot,
    payload: CompletePodcastLearningPayload,
) -> None:
    identity = PodcastIdentity.from_payload(payload)
    expected_properties = {
        "Title": identity.title,
        "Source Type": identity.source_type,
        "Date": payload.processed_date,
        "Topic": payload.analysis.podcast_metadata.topic,
        "Difficulty": payload.analysis.podcast_metadata.difficulty,
        "Short Summary": payload.analysis.podcast_metadata.short_summary,
    }
    if identity.source_url:
        expected_properties["URL"] = identity.source_url
    for property_name, expected_value in expected_properties.items():
        if not expected_value or page.property(property_name) != expected_value:
            raise AcceptanceFailure("podcast_properties_incomplete")
    if not identity.source_url and page.property("URL") not in {None, ""}:
        raise AcceptanceFailure("podcast_identity_mismatch")
    counts = _section_counts(page)
    if any(counts[section] != 1 for section in counts):
        raise AcceptanceFailure("podcast_body_structure_invalid")


def _assert_expected_expressions(
    snapshot: WorkspaceSnapshot,
    target_podcast_id: str,
    expected: Mapping[tuple[str, str], LearningItem],
) -> tuple[PageSnapshot, ...]:
    related = tuple(
        page
        for page in snapshot.pages(EXPRESSION_DATABASE)
        if target_podcast_id in _expression_relations(page)
    )
    if len(related) != len(expected):
        raise AcceptanceFailure("expression_count_mismatch")
    by_key: dict[tuple[str, str], list[PageSnapshot]] = {}
    for page in related:
        by_key.setdefault(_expression_key(page), []).append(page)
    if set(by_key) != set(expected):
        raise AcceptanceFailure("expression_missing_or_unexpected")
    if any(len(pages) != 1 for pages in by_key.values()):
        raise AcceptanceFailure("expression_duplicate")
    for key, item in expected.items():
        page = by_key[key][0]
        if page.property("Commonness") != (item.commonness or "Medium"):
            raise AcceptanceFailure("expression_properties_incomplete")
        if page.property("Review Status") != "New":
            raise AcceptanceFailure("expression_properties_incomplete")
        if _expression_relations(page) != (target_podcast_id,):
            raise AcceptanceFailure("expression_relation_mismatch")
    return related


@dataclass(frozen=True)
class AcceptanceEvidence:
    podcast_added_on_first_publish: int
    expressions_added_on_first_publish: int
    podcast_added_on_second_publish: int
    expressions_added_on_second_publish: int
    expected_expression_count: int


class SnapshotVerifier:
    """Business-level acceptance assertions over normalized snapshots."""

    def __init__(
        self,
        payload: CompletePodcastLearningPayload,
        allow_partial_recovery: bool,
    ) -> None:
        self.payload = payload
        self.identity = PodcastIdentity.from_payload(payload)
        self.expected = _expected_expression_items(payload)
        self.allow_partial_recovery = allow_partial_recovery

    def target_pages(
        self,
        snapshot: WorkspaceSnapshot,
    ) -> tuple[PageSnapshot, ...]:
        return tuple(
            page
            for page in snapshot.pages(PODCAST_LIBRARY)
            if self.identity.matches(page)
        )

    def assert_pre_publish_state(self, snapshot: WorkspaceSnapshot) -> None:
        targets = self.target_pages(snapshot)
        if len(targets) > 1:
            raise AcceptanceFailure("podcast_identity_not_unique")
        if targets and not self.allow_partial_recovery:
            raise AcceptanceFailure("target_podcast_already_exists")
        if not targets:
            return
        target = targets[0]
        related = [
            page
            for page in snapshot.pages(EXPRESSION_DATABASE)
            if target.page_id in _expression_relations(page)
        ]
        keys = [_expression_key(page) for page in related]
        if (
            any(key not in self.expected for key in keys)
            or len(keys) != len(set(keys))
        ):
            raise AcceptanceFailure("partial_recovery_scope_invalid")

    def verify_first(
        self,
        before: WorkspaceSnapshot,
        after: WorkspaceSnapshot,
    ) -> AcceptanceEvidence:
        before_targets = self.target_pages(before)
        after_targets = self.target_pages(after)
        if len(after_targets) != 1:
            raise AcceptanceFailure("podcast_identity_not_unique")
        target = after_targets[0]
        _assert_podcast_page_complete(target, self.payload)
        expressions = _assert_expected_expressions(
            after,
            target.page_id,
            self.expected,
        )

        podcast_added = (
            len(after.pages(PODCAST_LIBRARY))
            - len(before.pages(PODCAST_LIBRARY))
        )
        expression_added = (
            len(after.pages(EXPRESSION_DATABASE))
            - len(before.pages(EXPRESSION_DATABASE))
        )
        if before_targets:
            if not self.allow_partial_recovery or podcast_added != 0:
                raise AcceptanceFailure("first_publish_podcast_delta_invalid")
            if before_targets[0].page_id != target.page_id:
                raise AcceptanceFailure("podcast_identity_changed")
            before_related_count = sum(
                1
                for page in before.pages(EXPRESSION_DATABASE)
                if target.page_id in _expression_relations(page)
            )
            if expression_added != len(self.expected) - before_related_count:
                raise AcceptanceFailure("first_publish_expression_delta_invalid")
        else:
            if podcast_added != 1:
                raise AcceptanceFailure("first_publish_podcast_delta_invalid")
            if expression_added != len(self.expected):
                raise AcceptanceFailure("first_publish_expression_delta_invalid")

        new_podcast_ids = (
            set(after.by_id(PODCAST_LIBRARY))
            - set(before.by_id(PODCAST_LIBRARY))
        )
        expected_new_podcast_ids = set() if before_targets else {target.page_id}
        if new_podcast_ids != expected_new_podcast_ids:
            raise AcceptanceFailure("unexpected_podcast_created")

        new_expression_ids = (
            set(after.by_id(EXPRESSION_DATABASE))
            - set(before.by_id(EXPRESSION_DATABASE))
        )
        if not new_expression_ids.issubset(
            {page.page_id for page in expressions}
        ):
            raise AcceptanceFailure("unexpected_expression_created")

        _assert_record_sets_equal(
            before,
            after,
            VOCABULARY_DATABASE,
            "vocabulary_database_changed",
        )
        _assert_record_sets_equal(
            before,
            after,
            WEEKLY_REVIEW,
            "weekly_review_changed",
        )
        _assert_other_records_unchanged(before, after, target.page_id)
        _assert_no_delete_or_archive(before, after)
        return AcceptanceEvidence(
            podcast_added_on_first_publish=podcast_added,
            expressions_added_on_first_publish=expression_added,
            podcast_added_on_second_publish=0,
            expressions_added_on_second_publish=0,
            expected_expression_count=len(self.expected),
        )

    def verify_second(
        self,
        first: WorkspaceSnapshot,
        second: WorkspaceSnapshot,
        evidence: AcceptanceEvidence,
    ) -> AcceptanceEvidence:
        first_targets = self.target_pages(first)
        second_targets = self.target_pages(second)
        if len(first_targets) != 1 or len(second_targets) != 1:
            raise AcceptanceFailure("podcast_identity_not_unique")
        if first_targets[0].page_id != second_targets[0].page_id:
            raise AcceptanceFailure("podcast_identity_changed")
        _assert_podcast_page_complete(second_targets[0], self.payload)

        podcast_added = (
            len(second.pages(PODCAST_LIBRARY))
            - len(first.pages(PODCAST_LIBRARY))
        )
        expression_added = (
            len(second.pages(EXPRESSION_DATABASE))
            - len(first.pages(EXPRESSION_DATABASE))
        )
        if podcast_added != 0:
            raise AcceptanceFailure("second_publish_podcast_delta_invalid")
        if expression_added != 0:
            raise AcceptanceFailure("second_publish_expression_delta_invalid")

        _assert_record_sets_equal(
            first,
            second,
            PODCAST_LIBRARY,
            "podcast_body_or_properties_changed_on_retry",
        )
        _assert_record_sets_equal(
            first,
            second,
            EXPRESSION_DATABASE,
            "expression_identity_set_changed_on_retry",
        )
        _assert_record_sets_equal(
            first,
            second,
            VOCABULARY_DATABASE,
            "vocabulary_database_changed",
        )
        _assert_record_sets_equal(
            first,
            second,
            WEEKLY_REVIEW,
            "weekly_review_changed",
        )
        _assert_expected_expressions(
            second,
            second_targets[0].page_id,
            self.expected,
        )
        _assert_no_delete_or_archive(first, second)
        return AcceptanceEvidence(
            podcast_added_on_first_publish=evidence.podcast_added_on_first_publish,
            expressions_added_on_first_publish=(
                evidence.expressions_added_on_first_publish
            ),
            podcast_added_on_second_publish=podcast_added,
            expressions_added_on_second_publish=expression_added,
            expected_expression_count=evidence.expected_expression_count,
        )


@dataclass(frozen=True)
class AcceptanceReport:
    """Public report containing only fixed labels, booleans, and counts."""

    status: str
    depends_on_pr_9: bool
    pre_publish_snapshot: str
    first_publish_verification: str
    second_publish_verification: str
    guard_enforced: bool
    secrets_redacted: bool
    snapshot_cleanup_confirmed: bool
    counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        safe_counts = {
            key: value
            for key, value in self.counts.items()
            if key in _PUBLIC_COUNT_KEYS and isinstance(value, int)
        }
        return {
            "status": (
                self.status
                if self.status in _PUBLIC_CHECK_VALUES
                else "[REDACTED]"
            ),
            "depends_on_pr_9": bool(self.depends_on_pr_9),
            "pre_publish_snapshot": (
                self.pre_publish_snapshot
                if self.pre_publish_snapshot in _PUBLIC_CHECK_VALUES
                else "[REDACTED]"
            ),
            "first_publish_verification": (
                self.first_publish_verification
                if self.first_publish_verification in _PUBLIC_CHECK_VALUES
                else "[REDACTED]"
            ),
            "second_publish_verification": (
                self.second_publish_verification
                if self.second_publish_verification in _PUBLIC_CHECK_VALUES
                else "[REDACTED]"
            ),
            "guard_enforced": bool(self.guard_enforced),
            "secrets_redacted": True,
            "snapshot_cleanup_confirmed": bool(
                self.snapshot_cleanup_confirmed
            ),
            "counts": safe_counts,
        }


@dataclass(frozen=True)
class AcceptanceRunResult:
    report: AcceptanceReport
    evidence: AcceptanceEvidence = field(repr=False)


Publisher = Callable[..., Any]
SnapshotStoreFactory = Callable[[], TemporarySnapshotStore]


class OwnerAcceptanceRunner:
    """Run one guarded publish, one exact retry, and redacted verification."""

    def __init__(
        self,
        notion: Any,
        config: AcceptanceConfig,
        publisher: Publisher = publish_complete_learning_materials,
        snapshot_store_factory: SnapshotStoreFactory = TemporarySnapshotStore,
    ) -> None:
        self.raw_notion = notion
        self.config = config
        self.publisher = publisher
        self.snapshot_store_factory = snapshot_store_factory

    def run(
        self,
        payload: CompletePodcastLearningPayload,
        *,
        allow_partial_recovery: bool = False,
    ) -> AcceptanceRunResult:
        expected_items = _expected_expression_items(payload)
        policy = AcceptancePolicy(
            config=self.config,
            identity=PodcastIdentity.from_payload(payload),
            expected_expression_keys=frozenset(expected_items),
        )
        guarded_notion = AcceptanceGuard(self.raw_notion, policy)
        snapshotter = WorkspaceSnapshotter(guarded_notion, self.config)
        verifier = SnapshotVerifier(payload, allow_partial_recovery)
        snapshot_store = self.snapshot_store_factory()
        evidence: Optional[AcceptanceEvidence] = None
        pending_error: Optional[BaseException] = None

        try:
            _assert_workspace_schema_ready(guarded_notion, self.config)
            before = snapshotter.capture()
            snapshot_store.persist("before", before)
            verifier.assert_pre_publish_state(before)
            policy.authorize_snapshot_scope(before)

            self.publisher(
                payload,
                notion=guarded_notion,
                podcast_database_id=self.config.podcast_data_source_id,
                expression_database_id=self.config.expression_data_source_id,
            )
            first = snapshotter.capture()
            snapshot_store.persist("after-first", first)
            evidence = verifier.verify_first(before, first)

            self.publisher(
                payload,
                notion=guarded_notion,
                podcast_database_id=self.config.podcast_data_source_id,
                expression_database_id=self.config.expression_data_source_id,
            )
            second = snapshotter.capture()
            snapshot_store.persist("after-second", second)
            evidence = verifier.verify_second(first, second, evidence)
        except (AcceptanceFailure, GuardViolation) as exc:
            pending_error = exc
        except Exception:
            pending_error = AcceptanceFailure("acceptance_execution_failed")
        finally:
            snapshot_store.cleanup()

        if pending_error is not None:
            raise pending_error
        if evidence is None:
            raise AcceptanceFailure("acceptance_evidence_missing")
        if not snapshot_store.cleaned:
            raise AcceptanceFailure("temporary_snapshot_cleanup_failed")

        report = AcceptanceReport(
            status="passed",
            depends_on_pr_9=DEPENDS_ON_PR_9,
            pre_publish_snapshot="passed",
            first_publish_verification="passed",
            second_publish_verification="passed",
            guard_enforced=True,
            secrets_redacted=True,
            snapshot_cleanup_confirmed=True,
            counts={
                "podcast_added_on_first_publish": (
                    evidence.podcast_added_on_first_publish
                ),
                "expressions_added_on_first_publish": (
                    evidence.expressions_added_on_first_publish
                ),
                "podcast_added_on_second_publish": (
                    evidence.podcast_added_on_second_publish
                ),
                "expressions_added_on_second_publish": (
                    evidence.expressions_added_on_second_publish
                ),
                "expected_expression_count": evidence.expected_expression_count,
            },
        )
        return AcceptanceRunResult(report=report, evidence=evidence)


_NOTION_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?notion\.(?:so|site)/[^\s\"']+",
    re.IGNORECASE,
)
_NOTION_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[0-9a-f]{32}|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"
    r"(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_PUBLIC_CHECK_VALUES = frozenset({"passed", "failed", "skipped"})
_PUBLIC_COUNT_KEYS = frozenset(
    {
        "podcast_added_on_first_publish",
        "expressions_added_on_first_publish",
        "podcast_added_on_second_publish",
        "expressions_added_on_second_publish",
        "expected_expression_count",
    }
)
_PUBLIC_FAILURE_CODES = frozenset(
    {
        "acceptance_evidence_missing",
        "acceptance_execution_failed",
        "acceptance_failed",
        "acceptance_input_or_execution_failed",
        "block_append_blocked",
        "database_creation_blocked",
        "delete_or_archive_blocked",
        "expression_count_mismatch",
        "expression_duplicate",
        "expression_identity_set_changed_on_retry",
        "expression_missing_or_unexpected",
        "expression_properties_incomplete",
        "expression_relation_mismatch",
        "first_publish_expression_delta_invalid",
        "first_publish_podcast_delta_invalid",
        "four_data_sources_not_configured",
        "invalid_block_pagination",
        "invalid_block_query_response",
        "invalid_data_source_pagination",
        "invalid_data_source_query_response",
        "invalid_snapshot_label",
        "live_confirmation_missing",
        "page_create_response_rejected",
        "partial_recovery_scope_invalid",
        "podcast_body_or_properties_changed_on_retry",
        "podcast_body_structure_invalid",
        "podcast_identity_changed",
        "podcast_identity_mismatch",
        "podcast_identity_not_unique",
        "podcast_properties_incomplete",
        "record_deleted_or_archived",
        "schema_mutation_blocked",
        "second_publish_expression_delta_invalid",
        "second_publish_podcast_delta_invalid",
        "setup_state_not_complete",
        "snapshot_page_identity_missing",
        "target_podcast_already_exists",
        "temporary_snapshot_cleanup_failed",
        "unexpected_data_source_read_blocked",
        "unexpected_expression_create_blocked",
        "unexpected_expression_created",
        "unexpected_page_create_blocked",
        "unexpected_page_update_blocked",
        "unexpected_page_update_shape_blocked",
        "unexpected_podcast_create_blocked",
        "unexpected_podcast_created",
        "unrelated_record_changed",
        "unsupported_acceptance_source",
        "unsupported_block_operation_blocked",
        "unsupported_data_source_operation_blocked",
        "unsupported_database_operation_blocked",
        "unsupported_page_operation_blocked",
        "vocabulary_database_changed",
        "vocabulary_write_blocked",
        "weekly_review_changed",
        "weekly_review_write_blocked",
        "workspace_data_source_unavailable",
        "workspace_schema_incomplete",
    }
)


def render_redacted_report(
    report: AcceptanceReport,
    *,
    secrets: Iterable[str] = (),
) -> str:
    """Serialize a public report and defensively remove supplied secrets."""
    rendered = json.dumps(
        report.to_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    for secret in secrets:
        if secret:
            rendered = rendered.replace(secret, "[REDACTED]")
    rendered = _NOTION_URL_PATTERN.sub("[REDACTED]", rendered)
    rendered = _NOTION_ID_PATTERN.sub("[REDACTED]", rendered)
    return rendered


def render_failure_report(code: str) -> str:
    """Render only a stable failure code; underlying API errors stay private."""
    safe_code = code if code in _PUBLIC_FAILURE_CODES else "acceptance_failed"
    return json.dumps(
        {
            "status": "failed",
            "depends_on_pr_9": DEPENDS_ON_PR_9,
            "failure": safe_code,
            "secrets_redacted": True,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
