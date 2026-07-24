"""Protected owner-acceptance harness for Weekly Reflection publishing.

The harness treats ``run_weekly_reflection_pipeline`` as a black box. It
validates the configured Notion target, snapshots all four data sources,
restricts writes to one newly-created Weekly Review page, and proves that an
exact retry creates no duplicate page, relation, or generated section.

Public reports contain only statuses, counts, booleans, stable error codes, and
irreversible fingerprints. Identifiers, URLs, tokens, raw Notion responses,
and learning content remain private in memory.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from scripts.acceptance.podcast_owner_acceptance import (
    AcceptanceConfig,
    AcceptanceConfigurationError,
    AcceptanceFailure,
    GuardViolation,
    _normalized_properties,
    load_acceptance_config,
)
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
    WORKSPACE_DATABASE_ORDER,
)
from src.notion.target_binding import (
    NotionTargetBindingError,
    validate_notion_target_binding,
)
from src.notion.weekly_reflection_writer import (
    WeeklyReflectionPublishPayload,
    load_reflection_context_json,
    load_weekly_review_json,
    weekly_reflection_body_blocks,
    weekly_reflection_page_properties,
)
from src.weekly_review.quality_checker import check_weekly_review_quality
from src.workflow.schema_validator import (
    WeeklyLearningContextValidationError,
    validate_weekly_learning_context,
)
from src.workflow.weekly_reflection_pipeline import (
    WeeklyReflectionPipelineError,
    run_weekly_reflection_pipeline,
)


LIVE_CONFIRMATION = "WEEKLY_REFLECTION_ACCEPTANCE_WRITES_TO_NOTION"
PRODUCTION_QUALITY_THRESHOLD = 85

_NOTION_URL_PATTERN = re.compile(
    r"https?://(?:www\.)?notion\.(?:so|site)/[^\s\"']+",
    re.IGNORECASE,
)
_NOTION_ID_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:[0-9a-f]{32}|"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
    r"[0-9a-f]{12})(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_LOCAL_SCAN_EXCLUDES = frozenset(
    {
        ".git",
        ".venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
    }
)


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _safe_fingerprint(value: object) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:8]


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _semantic_value(value: Any) -> Any:
    """Remove volatile Notion response metadata from a private snapshot."""
    if isinstance(value, Mapping):
        ignored = {
            "id",
            "object",
            "parent",
            "url",
            "public_url",
            "created_time",
            "last_edited_time",
            "created_by",
            "last_edited_by",
            "request_id",
            "has_children",
            "archived",
            "in_trash",
        }
        return {
            str(key): _semantic_value(item)
            for key, item in value.items()
            if str(key) not in ignored
        }
    if isinstance(value, list):
        return [_semantic_value(item) for item in value]
    if isinstance(value, tuple):
        return [_semantic_value(item) for item in value]
    return value


def _block_type(block: Mapping[str, Any]) -> str:
    return str(block.get("type", "") or "").strip()


def _rich_text_value(items: Any) -> str:
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
    return "".join(parts).strip()


def _block_text(block: Mapping[str, Any]) -> str:
    kind = _block_type(block)
    payload = block.get(kind)
    if not isinstance(payload, Mapping):
        return ""
    return _rich_text_value(payload.get("rich_text"))


def _heading_texts(blocks: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    return tuple(
        text
        for block in blocks
        if _block_type(block) in {"heading_1", "heading_2", "heading_3"}
        and (text := _block_text(block))
    )


def _duplicate_headings(blocks: Sequence[Mapping[str, Any]]) -> bool:
    headings = _heading_texts(blocks)
    return len(headings) != len(set(headings))


def _normalized_block_contract(block: Any) -> dict[str, Any]:
    if not isinstance(block, Mapping):
        return {"type": "invalid"}
    kind = _block_type(block) or "unknown"
    payload = block.get(kind)
    payload = payload if isinstance(payload, Mapping) else {}
    normalized: dict[str, Any] = {"type": kind}
    if kind == "table_row":
        cells = payload.get("cells")
        normalized["cells"] = (
            [_rich_text_value(cell) for cell in cells]
            if isinstance(cells, list)
            else []
        )
    else:
        text = _rich_text_value(payload.get("rich_text"))
        if text:
            normalized["text"] = text
    if kind == "to_do":
        normalized["checked"] = bool(payload.get("checked", False))
    if kind == "table":
        normalized.update(
            {
                "table_width": int(payload.get("table_width", 0) or 0),
                "has_column_header": bool(
                    payload.get("has_column_header", False)
                ),
                "has_row_header": bool(
                    payload.get("has_row_header", False)
                ),
            }
        )
    if kind == "table_of_contents":
        normalized["color"] = str(payload.get("color", "default"))
    children = payload.get("children")
    if isinstance(children, list):
        normalized["children"] = [
            _normalized_block_contract(child) for child in children
        ]
    return normalized


def _normalized_body_contract(
    blocks: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(_normalized_block_contract(block) for block in blocks)


def _tree_snapshot(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    snapshot: dict[str, str] = {}
    for candidate in root.rglob("*"):
        if not candidate.is_file():
            continue
        relative = candidate.relative_to(root)
        if any(part in _LOCAL_SCAN_EXCLUDES for part in relative.parts):
            continue
        snapshot[relative.as_posix()] = _digest_bytes(candidate.read_bytes())
    return snapshot


def _changed_local_paths(
    before: Mapping[str, str],
    after: Mapping[str, str],
) -> set[str]:
    return {
        path
        for path in set(before) | set(after)
        if before.get(path) != after.get(path)
    }


@dataclass(frozen=True, repr=False)
class WeeklyRecordSnapshot:
    page_id: str = field(repr=False)
    properties: Mapping[str, Any] = field(repr=False)
    body: tuple[Mapping[str, Any], ...] = field(repr=False)
    archived: bool = field(repr=False)
    in_trash: bool = field(repr=False)

    def semantic_fingerprint(self) -> str:
        return _canonical_json(
            {
                "properties": self.properties,
                "body": _normalized_body_contract(self.body),
                "archived": self.archived,
                "in_trash": self.in_trash,
            }
        )


@dataclass(frozen=True, repr=False)
class WeeklyWorkspaceSnapshot:
    records: Mapping[str, tuple[WeeklyRecordSnapshot, ...]] = field(
        repr=False
    )

    def pages(self, role: str) -> tuple[WeeklyRecordSnapshot, ...]:
        return self.records.get(role, ())

    def by_id(self, role: str) -> dict[str, WeeklyRecordSnapshot]:
        return {record.page_id: record for record in self.pages(role)}

    def safe_counts(self) -> dict[str, int]:
        return {role: len(self.pages(role)) for role in WORKSPACE_DATABASE_ORDER}


@dataclass(repr=False)
class WeeklyAcceptancePolicy:
    config: AcceptanceConfig = field(repr=False)
    source_page_ids: set[str] = field(default_factory=set, repr=False)
    readable_weekly_page_ids: set[str] = field(default_factory=set, repr=False)
    created_weekly_page_ids: set[str] = field(default_factory=set, repr=False)
    readable_block_ids: set[str] = field(default_factory=set, repr=False)
    block_owner_by_id: dict[str, str] = field(default_factory=dict, repr=False)
    expected_properties: Mapping[str, Any] = field(
        default_factory=dict,
        repr=False,
    )
    expected_body: tuple[Mapping[str, Any], ...] = field(
        default_factory=tuple,
        repr=False,
    )
    page_creates: int = 0
    page_updates: int = 0
    block_appends: int = 0
    block_deletes: int = 0

    @property
    def allowed_data_source_ids(self) -> frozenset[str]:
        return frozenset(self.config.data_source_ids.values())

    @property
    def readable_page_ids(self) -> frozenset[str]:
        return frozenset(
            {
                self.config.target_parent_page_id,
                *self.source_page_ids,
                *self.readable_weekly_page_ids,
                *self.created_weekly_page_ids,
            }
        )

    def configure_expected_payload(
        self,
        *,
        properties: Mapping[str, Any],
        body: Sequence[Mapping[str, Any]],
    ) -> None:
        self.expected_properties = _normalized_properties(properties)
        self.expected_body = _normalized_body_contract(body)

    def validate_data_source_read(self, data_source_id: str) -> None:
        if data_source_id not in self.allowed_data_source_ids:
            raise GuardViolation("unexpected_data_source_read_blocked")

    def register_weekly_page(self, page_id: str) -> None:
        if page_id:
            self.readable_weekly_page_ids.add(page_id)

    def validate_page_read(self, page_id: str) -> None:
        if page_id not in self.readable_page_ids:
            raise GuardViolation("unexpected_page_read_blocked")

    def validate_page_create(self, kwargs: Mapping[str, Any]) -> None:
        parent = kwargs.get("parent")
        parent = parent if isinstance(parent, Mapping) else {}
        if parent.get("data_source_id") != self.config.weekly_data_source_id:
            raise GuardViolation("non_weekly_write_blocked")
        if set(kwargs) - {"parent", "properties", "children"}:
            raise GuardViolation("unexpected_page_create_shape_blocked")
        if self.page_creates or self.created_weekly_page_ids:
            raise GuardViolation("duplicate_weekly_create_blocked")
        if _normalized_properties(kwargs.get("properties")) != (
            self.expected_properties
        ):
            raise GuardViolation("unexpected_weekly_properties_blocked")
        children = kwargs.get("children")
        if not isinstance(children, list) or (
            _normalized_body_contract(children) != self.expected_body
        ):
            raise GuardViolation("unexpected_weekly_body_blocked")

    def register_created_page(self, response: Any) -> None:
        page_id = (
            str(response.get("id", "")).strip()
            if isinstance(response, Mapping)
            else ""
        )
        if not page_id:
            raise GuardViolation("page_create_response_rejected")
        self.created_weekly_page_ids.add(page_id)
        self.readable_weekly_page_ids.add(page_id)
        self.page_creates += 1

    def validate_page_update(self, kwargs: Mapping[str, Any]) -> None:
        if "archived" in kwargs or "in_trash" in kwargs:
            raise GuardViolation("delete_or_archive_blocked")
        if set(kwargs) - {"page_id", "properties"}:
            raise GuardViolation("unexpected_page_update_shape_blocked")
        page_id = str(kwargs.get("page_id", "")).strip()
        if page_id not in self.created_weekly_page_ids:
            raise GuardViolation("preexisting_weekly_update_blocked")
        if _normalized_properties(kwargs.get("properties")) != (
            self.expected_properties
        ):
            raise GuardViolation("unexpected_weekly_properties_blocked")
        self.page_updates += 1

    def validate_block_read(self, block_id: str) -> None:
        if block_id not in (
            self.readable_weekly_page_ids
            | self.created_weekly_page_ids
            | self.readable_block_ids
        ):
            raise GuardViolation("unexpected_block_read_blocked")

    def register_block_results(self, owner_id: str, response: Any) -> None:
        if not isinstance(response, Mapping):
            return
        results = response.get("results")
        if not isinstance(results, list):
            return
        for block in results:
            if not isinstance(block, Mapping):
                continue
            block_id = str(block.get("id", "")).strip()
            if block_id:
                self.readable_block_ids.add(block_id)
                self.block_owner_by_id[block_id] = owner_id

    def validate_block_append(self, kwargs: Mapping[str, Any]) -> None:
        block_id = str(kwargs.get("block_id", "")).strip()
        if block_id not in self.created_weekly_page_ids:
            raise GuardViolation("non_weekly_block_append_blocked")
        if set(kwargs) - {"block_id", "children", "after"}:
            raise GuardViolation("unexpected_block_append_shape_blocked")
        children = kwargs.get("children")
        if not isinstance(children, list) or (
            _normalized_body_contract(children) != self.expected_body
        ):
            raise GuardViolation("unexpected_weekly_body_blocked")
        self.block_appends += 1

    def validate_block_delete(self, kwargs: Mapping[str, Any]) -> None:
        if set(kwargs) != {"block_id"}:
            raise GuardViolation("unexpected_block_delete_shape_blocked")
        block_id = str(kwargs.get("block_id", "")).strip()
        owner_id = self.block_owner_by_id.get(block_id)
        if owner_id not in self.created_weekly_page_ids:
            raise GuardViolation("delete_or_archive_blocked")
        self.block_deletes += 1


class _GuardedDataSources:
    def __init__(self, raw: Any, policy: WeeklyAcceptancePolicy) -> None:
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

    def update(self, **_kwargs: Any) -> Any:
        raise GuardViolation("schema_mutation_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_data_source_operation_blocked")


class _GuardedPages:
    def __init__(self, raw: Any, policy: WeeklyAcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def create(self, **kwargs: Any) -> Any:
        self._policy.validate_page_create(kwargs)
        response = self._raw.create(**kwargs)
        self._policy.register_created_page(response)
        return response

    def retrieve(self, **kwargs: Any) -> Any:
        self._policy.validate_page_read(str(kwargs.get("page_id", "")).strip())
        return self._raw.retrieve(**kwargs)

    def update(self, **kwargs: Any) -> Any:
        self._policy.validate_page_update(kwargs)
        return self._raw.update(**kwargs)

    def delete(self, **_kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_page_operation_blocked")


class _GuardedBlocksChildren:
    def __init__(self, raw: Any, policy: WeeklyAcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def list(self, **kwargs: Any) -> Any:
        owner_id = str(kwargs.get("block_id", "")).strip()
        self._policy.validate_block_read(owner_id)
        response = self._raw.list(**kwargs)
        self._policy.register_block_results(owner_id, response)
        return response

    def append(self, **kwargs: Any) -> Any:
        self._policy.validate_block_append(kwargs)
        return self._raw.append(**kwargs)

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_block_operation_blocked")


class _GuardedBlocks:
    def __init__(self, raw: Any, policy: WeeklyAcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy
        self.children = _GuardedBlocksChildren(raw.children, policy)

    def delete(self, **kwargs: Any) -> Any:
        self._policy.validate_block_delete(kwargs)
        return self._raw.delete(**kwargs)

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_block_operation_blocked")


class _GuardedDatabases:
    def __init__(self, raw: Any) -> None:
        self._raw = raw

    def retrieve(self, **kwargs: Any) -> Any:
        return self._raw.retrieve(**kwargs)

    def create(self, **_kwargs: Any) -> Any:
        raise GuardViolation("database_creation_blocked")

    def update(self, **_kwargs: Any) -> Any:
        raise GuardViolation("schema_mutation_blocked")

    def delete(self, **_kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_database_operation_blocked")


class WeeklyAcceptanceGuard:
    """Notion facade permitting only one scoped Weekly create/update cycle."""

    def __init__(self, notion: Any, policy: WeeklyAcceptancePolicy) -> None:
        self.policy = policy
        self.data_sources = _GuardedDataSources(notion.data_sources, policy)
        self.pages = _GuardedPages(notion.pages, policy)
        self.blocks = _GuardedBlocks(notion.blocks, policy)
        self.databases = _GuardedDatabases(notion.databases)


class WeeklyWorkspaceSnapshotter:
    """Capture private semantic snapshots for all configured data sources."""

    def __init__(
        self,
        notion: WeeklyAcceptanceGuard,
        config: AcceptanceConfig,
    ) -> None:
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
            pages.extend(item for item in results if isinstance(item, Mapping))
            if not response.get("has_more"):
                return pages
            next_cursor = str(response.get("next_cursor", "") or "").strip()
            if not next_cursor:
                raise AcceptanceFailure("invalid_data_source_pagination")
            cursor = next_cursor

    def _page_body(self, page_id: str) -> tuple[Mapping[str, Any], ...]:
        response = self.notion.blocks.children.list(
            block_id=page_id,
            page_size=100,
        )
        if not isinstance(response, Mapping):
            raise AcceptanceFailure("invalid_block_query_response")
        results = response.get("results")
        if not isinstance(results, list):
            raise AcceptanceFailure("invalid_block_query_response")
        expanded: list[Mapping[str, Any]] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            block = dict(item)
            kind = _block_type(block)
            payload = block.get(kind)
            payload = dict(payload) if isinstance(payload, Mapping) else {}
            inline_children = payload.get("children")
            block_id = str(block.get("id", "")).strip()
            if (
                not isinstance(inline_children, list)
                and bool(block.get("has_children"))
                and block_id
            ):
                payload["children"] = list(self._page_body(block_id))
                block[kind] = payload
            expanded.append(block)
        return tuple(expanded)

    def capture(self) -> WeeklyWorkspaceSnapshot:
        records: dict[str, tuple[WeeklyRecordSnapshot, ...]] = {}
        for role in WORKSPACE_DATABASE_ORDER:
            role_records: list[WeeklyRecordSnapshot] = []
            for page in self._query_all(self.config.data_source_ids[role]):
                page_id = str(page.get("id", "")).strip()
                if not page_id:
                    raise AcceptanceFailure("snapshot_page_identity_missing")
                body: tuple[Mapping[str, Any], ...] = ()
                if role == WEEKLY_REVIEW:
                    self.notion.policy.register_weekly_page(page_id)
                    body = self._page_body(page_id)
                role_records.append(
                    WeeklyRecordSnapshot(
                        page_id=page_id,
                        properties=_normalized_properties(
                            page.get("properties")
                        ),
                        body=body,
                        archived=bool(page.get("archived", False)),
                        in_trash=bool(page.get("in_trash", False)),
                    )
                )
            records[role] = tuple(role_records)
        return WeeklyWorkspaceSnapshot(records=records)


@dataclass(frozen=True, repr=False)
class WeeklyAcceptanceEvidence:
    before_counts: Mapping[str, int] = field(repr=False)
    after_first_counts: Mapping[str, int] = field(repr=False)
    after_retry_counts: Mapping[str, int] = field(repr=False)
    local_changes: tuple[str, ...] = field(repr=False)


@dataclass(frozen=True)
class WeeklyAcceptanceReport:
    status: str
    mode: str
    target_binding_verified: bool
    target_parent_fingerprint: str
    target_group_fingerprint: str
    schema_preflight: str
    snapshot_verification: str
    learning_context_verified: bool
    reflection_context_verified: bool
    weekly_review_verified: bool
    quality_gate_passed: bool
    quality_score: int
    planned_weekly_action: str
    guard_enforced: bool
    local_artifact_whitelist_verified: bool
    content_contract_verified: bool
    exact_retry_verified: bool
    secrets_redacted: bool
    counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "mode": self.mode,
            "target_binding_verified": self.target_binding_verified,
            "target_parent_fingerprint": self.target_parent_fingerprint,
            "target_group_fingerprint": self.target_group_fingerprint,
            "schema_preflight": self.schema_preflight,
            "snapshot_verification": self.snapshot_verification,
            "learning_context_verified": self.learning_context_verified,
            "reflection_context_verified": self.reflection_context_verified,
            "weekly_review_verified": self.weekly_review_verified,
            "quality_gate_passed": self.quality_gate_passed,
            "quality_score": int(self.quality_score),
            "planned_weekly_action": self.planned_weekly_action,
            "guard_enforced": self.guard_enforced,
            "local_artifact_whitelist_verified": (
                self.local_artifact_whitelist_verified
            ),
            "content_contract_verified": self.content_contract_verified,
            "exact_retry_verified": self.exact_retry_verified,
            "secrets_redacted": self.secrets_redacted,
            "counts": {
                str(key): int(value)
                for key, value in self.counts.items()
            },
        }


@dataclass(frozen=True, repr=False)
class WeeklyAcceptanceRunResult:
    report: WeeklyAcceptanceReport
    evidence: WeeklyAcceptanceEvidence = field(repr=False)


@dataclass(repr=False)
class _PreparedRun:
    policy: WeeklyAcceptancePolicy = field(repr=False)
    notion: WeeklyAcceptanceGuard = field(repr=False)
    snapshotter: WeeklyWorkspaceSnapshotter = field(repr=False)
    before: WeeklyWorkspaceSnapshot = field(repr=False)
    binding: Any = field(repr=False)
    weekly_context: Mapping[str, Any] = field(repr=False)
    local_before: Mapping[str, str] = field(repr=False)
    allowed_local_paths: frozenset[str] = field(repr=False)
    planned_action: str = "create"


def _role_records_equal(
    left: WeeklyWorkspaceSnapshot,
    right: WeeklyWorkspaceSnapshot,
    role: str,
) -> bool:
    left_records = left.by_id(role)
    right_records = right.by_id(role)
    return (
        set(left_records) == set(right_records)
        and all(
            left_records[page_id].semantic_fingerprint()
            == right_records[page_id].semantic_fingerprint()
            for page_id in left_records
        )
    )


def _assert_no_removed_or_archived(
    before: WeeklyWorkspaceSnapshot,
    after: WeeklyWorkspaceSnapshot,
) -> None:
    for role in WORKSPACE_DATABASE_ORDER:
        before_records = before.by_id(role)
        after_records = after.by_id(role)
        if not set(before_records).issubset(after_records):
            raise AcceptanceFailure("record_removed")
        for page_id, record in after_records.items():
            previous = before_records.get(page_id)
            if (
                previous is not None
                and (
                    record.archived != previous.archived
                    or record.in_trash != previous.in_trash
                )
            ):
                raise AcceptanceFailure("delete_or_archive_detected")


def _period_and_sources(
    weekly_review: Mapping[str, Any],
) -> tuple[str, str, tuple[str, ...]]:
    period = weekly_review.get("period")
    period = period if isinstance(period, Mapping) else {}
    start = str(period.get("start_date", "") or "").strip()
    end = str(period.get("end_date", "") or "").strip()
    source_ids = tuple(
        sorted(
            {
                str(item).strip()
                for item in (
                    weekly_review.get("source_page_ids")
                    or weekly_review.get("source_podcast_ids")
                    or []
                )
                if str(item).strip()
            }
        )
    )
    return start, end, source_ids


def _weekly_identity_matches(
    record: WeeklyRecordSnapshot,
    *,
    start_date: str,
    source_ids: tuple[str, ...],
) -> bool:
    record_source_ids = {
        str(item).strip()
        for item in (record.properties.get("Podcasts") or ())
        if str(item).strip()
    }
    return (
        str(record.properties.get("Date") or "").strip() == start_date
        and set(source_ids).issubset(record_source_ids)
    )


def _validate_learning_context(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        validated = validate_weekly_learning_context(payload)
    except WeeklyLearningContextValidationError:
        raise AcceptanceFailure("weekly_learning_context_invalid") from None
    podcasts = validated.get("podcasts")
    learning_assets = (
        list(validated.get("learning_expressions") or [])
        + list(validated.get("ai_highlights") or [])
        + list(validated.get("user_vocabulary") or [])
    )
    if not podcasts or not learning_assets:
        raise AcceptanceFailure("weekly_learning_context_empty")
    return validated


def _validate_reflection_context(
    payload: Mapping[str, Any],
) -> None:
    theme = payload.get("weekly_theme")
    shifts = payload.get("mindset_shifts")
    patterns = payload.get("cross_content_patterns")
    actions = payload.get("professional_actions")
    if (
        not isinstance(theme, Mapping)
        or not str(theme.get("category", "")).strip()
        or not str(theme.get("theme", "")).strip()
        or not isinstance(shifts, list)
        or not shifts
        or not isinstance(patterns, list)
        or not patterns
        or not all(str(item).strip() for item in patterns)
        or not isinstance(actions, list)
        or not actions
        or not all(str(item).strip() for item in actions)
    ):
        raise AcceptanceFailure("reflection_context_incomplete")
    for shift in shifts:
        evidence = shift.get("evidence") if isinstance(shift, Mapping) else None
        confidence = (
            shift.get("confidence") if isinstance(shift, Mapping) else None
        )
        if (
            not isinstance(shift, Mapping)
            or not str(shift.get("before", "")).strip()
            or not str(shift.get("after", "")).strip()
            or not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(item, Mapping)
                or not str(item.get("source", "")).strip()
                or not str(item.get("supporting_concept", "")).strip()
                for item in evidence
            )
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= float(confidence) <= 1
        ):
            raise AcceptanceFailure("reflection_context_incomplete")


def _validate_weekly_review_contract(
    weekly_review: Mapping[str, Any],
    weekly_context: Mapping[str, Any],
) -> None:
    required = {
        "period",
        "core_idea",
        "ideas_worth_compounding",
        "expressions_worth_reusing",
        "language_thinking_connection",
        "next_week_application",
        "sources",
    }
    if not required.issubset(weekly_review):
        raise AcceptanceFailure("weekly_review_incomplete")
    core = weekly_review.get("core_idea")
    ideas = weekly_review.get("ideas_worth_compounding")
    expressions = weekly_review.get("expressions_worth_reusing")
    application = weekly_review.get("next_week_application")
    source_ids = _period_and_sources(weekly_review)[2]
    context_source_ids = tuple(
        sorted(
            str(item.get("page_id", "")).strip()
            for item in weekly_context.get("podcasts", [])
            if isinstance(item, Mapping)
            and str(item.get("page_id", "")).strip()
        )
    )
    if (
        not isinstance(core, Mapping)
        or not all(
            str(core.get(key, "")).strip()
            for key in ("idea", "why_it_matters", "refined_understanding")
        )
        or not isinstance(ideas, list)
        or not ideas
        or any(
            not isinstance(item, Mapping)
            or not all(
                str(item.get(key, "")).strip()
                for key in (
                    "idea",
                    "why_it_matters",
                    "application",
                    "source_reference",
                )
            )
            for item in ideas
        )
        or not isinstance(expressions, list)
        or not expressions
        or any(
            not isinstance(item, Mapping)
            or not all(
                str(item.get(key, "")).strip()
                for key in (
                    "expression",
                    "contextual_meaning",
                    "reusable_example",
                    "communication_function",
                )
            )
            for item in expressions
        )
        or not str(
            weekly_review.get("language_thinking_connection", "")
        ).strip()
        or not isinstance(application, Mapping)
        or not all(
            str(application.get(key, "")).strip()
            for key in (
                "scenario",
                "behavior",
                "phrase_to_use",
                "completion_condition",
            )
        )
        or not source_ids
        or source_ids != context_source_ids
    ):
        raise AcceptanceFailure("weekly_review_incomplete")


def _expected_page_payload(
    weekly_review: Mapping[str, Any],
    reflection_context: Mapping[str, Any],
    quality_score: int,
) -> WeeklyReflectionPublishPayload:
    payload = WeeklyReflectionPublishPayload(
        weekly_review=weekly_review,
        reflection_context=reflection_context,
        quality_score=quality_score,
    )
    return payload


class WeeklyReflectionOwnerAcceptanceRunner:
    """Run protected dry-run or live first-publish/exact-retry acceptance."""

    def __init__(
        self,
        notion: Any,
        config: AcceptanceConfig,
        *,
        pipeline_runner: Callable[..., Any] = run_weekly_reflection_pipeline,
        project_root: Path = Path("."),
        weekly_learning_context_path: Path = Path(
            "output/weekly_learning_context.json"
        ),
        reflection_context_output_path: Path = Path(
            "output/reflection_context.json"
        ),
        weekly_review_output_path: Path = Path("output/weekly_review.json"),
        pipeline_run_output_path: Path = Path("output/pipeline_run.json"),
        logs_dir: Path = Path("logs"),
        quality_threshold: int = PRODUCTION_QUALITY_THRESHOLD,
    ) -> None:
        self.raw_notion = notion
        self.config = config
        self.pipeline_runner = pipeline_runner
        self.project_root = project_root.resolve()
        self.weekly_learning_context_path = (
            self.project_root / weekly_learning_context_path
            if not weekly_learning_context_path.is_absolute()
            else weekly_learning_context_path
        )
        self.reflection_context_output_path = (
            self.project_root / reflection_context_output_path
            if not reflection_context_output_path.is_absolute()
            else reflection_context_output_path
        )
        self.weekly_review_output_path = (
            self.project_root / weekly_review_output_path
            if not weekly_review_output_path.is_absolute()
            else weekly_review_output_path
        )
        self.pipeline_run_output_path = (
            self.project_root / pipeline_run_output_path
            if not pipeline_run_output_path.is_absolute()
            else pipeline_run_output_path
        )
        self.logs_dir = (
            self.project_root / logs_dir
            if not logs_dir.is_absolute()
            else logs_dir
        )
        self.quality_threshold = int(quality_threshold)

    def _load_context(self) -> Mapping[str, Any]:
        try:
            payload = json.loads(
                self.weekly_learning_context_path.read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            raise AcceptanceFailure("weekly_learning_context_missing") from None
        except (OSError, json.JSONDecodeError):
            raise AcceptanceFailure("weekly_learning_context_invalid") from None
        if not isinstance(payload, Mapping):
            raise AcceptanceFailure("weekly_learning_context_invalid")
        return _validate_learning_context(payload)

    def _allowed_local_paths(self) -> frozenset[str]:
        paths = {
            self.reflection_context_output_path,
            self.weekly_review_output_path,
            self.pipeline_run_output_path,
            self.project_root / "output/reflection_context_request.json",
            self.project_root / "output/weekly_review_request.json",
            self.project_root / "output/reflection_context.json",
            self.project_root / "output/weekly_review.json",
        }
        allowed = {
            path.resolve().relative_to(self.project_root).as_posix()
            for path in paths
            if path.resolve().is_relative_to(self.project_root)
        }
        return frozenset(allowed)

    def _validate_local_changes(
        self,
        before: Mapping[str, str],
        allowed: frozenset[str],
    ) -> tuple[str, ...]:
        after = _tree_snapshot(self.project_root)
        changed = _changed_local_paths(before, after)
        unapproved = {
            path
            for path in changed
            if path not in allowed
            and not (
                path.startswith(
                    self.logs_dir.resolve()
                    .relative_to(self.project_root)
                    .as_posix()
                    .rstrip("/")
                    + "/weekly_reflection_"
                )
                and path.endswith(".log")
            )
        }
        if unapproved:
            raise AcceptanceFailure(
                "weekly_artifact_whitelist_violation"
            )
        return tuple(sorted(changed))

    def _prepare(self) -> _PreparedRun:
        if self.config.setup_state != "complete":
            raise AcceptanceConfigurationError("setup_state_not_complete")
        weekly_context = self._load_context()
        source_page_ids = {
            str(item.get("page_id", "")).strip()
            for item in weekly_context.get("podcasts", [])
            if isinstance(item, Mapping)
            and str(item.get("page_id", "")).strip()
        }
        policy = WeeklyAcceptancePolicy(
            config=self.config,
            source_page_ids=source_page_ids,
        )
        notion = WeeklyAcceptanceGuard(self.raw_notion, policy)
        try:
            binding = validate_notion_target_binding(
                notion,
                self.config.as_notion_config(),
            )
        except NotionTargetBindingError as exc:
            raise AcceptanceFailure(
                f"target_binding_{exc.code}"
            ) from None
        snapshotter = WeeklyWorkspaceSnapshotter(notion, self.config)
        before = snapshotter.capture()
        podcast_page_ids = set(before.by_id(PODCAST_LIBRARY))
        if not source_page_ids.issubset(podcast_page_ids):
            raise AcceptanceFailure("weekly_source_podcast_missing")
        local_before = _tree_snapshot(self.project_root)
        return _PreparedRun(
            policy=policy,
            notion=notion,
            snapshotter=snapshotter,
            before=before,
            binding=binding,
            weekly_context=weekly_context,
            local_before=local_before,
            allowed_local_paths=self._allowed_local_paths(),
        )

    def _artifact_failure_code(self) -> str:
        request_paths = (
            self.project_root / "output/reflection_context_request.json",
            self.project_root / "output/weekly_review_request.json",
        )
        output_paths = (
            self.project_root / "output/reflection_context.json",
            self.project_root / "output/weekly_review.json",
        )
        for output in output_paths:
            if not output.exists():
                continue
            try:
                parsed = json.loads(output.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return "weekly_artifact_invalid"
            if not isinstance(parsed, Mapping):
                return "weekly_artifact_invalid"
        if any(request.exists() for request in request_paths) and any(
            not output.exists() for output in output_paths
        ):
            return "weekly_artifact_pending"
        return "weekly_pipeline_failed"

    def _run_pipeline(
        self,
        prepared: _PreparedRun,
        *,
        dry_run: bool,
    ) -> tuple[Any, tuple[str, ...]]:
        try:
            result = self.pipeline_runner(
                weekly_learning_context_path=self.weekly_learning_context_path,
                weekly_review_output_path=self.weekly_review_output_path,
                reflection_context_output_path=(
                    self.reflection_context_output_path
                ),
                notion=prepared.notion,
                weekly_reflection_database_id=(
                    self.config.weekly_data_source_id
                ),
                podcast_database_id=self.config.podcast_data_source_id,
                dry_run=dry_run,
                pipeline_run_output_path=self.pipeline_run_output_path,
                logs_dir=self.logs_dir,
            )
        except (AcceptanceFailure, GuardViolation):
            self._validate_local_changes(
                prepared.local_before,
                prepared.allowed_local_paths,
            )
            raise
        except WeeklyReflectionPipelineError:
            self._validate_local_changes(
                prepared.local_before,
                prepared.allowed_local_paths,
            )
            raise AcceptanceFailure(self._artifact_failure_code()) from None
        except Exception:
            self._validate_local_changes(
                prepared.local_before,
                prepared.allowed_local_paths,
            )
            raise AcceptanceFailure("weekly_pipeline_failed") from None
        changes = self._validate_local_changes(
            prepared.local_before,
            prepared.allowed_local_paths,
        )
        return result, changes

    def _validate_pipeline_result(
        self,
        prepared: _PreparedRun,
        result: Any,
    ) -> tuple[
        Mapping[str, Any],
        Mapping[str, Any],
        int,
        tuple[Mapping[str, Any], ...],
    ]:
        try:
            reflection_context = load_reflection_context_json(
                Path(result.reflection_context_path)
            )
            weekly_review = load_weekly_review_json(
                Path(result.weekly_review_path)
            )
        except Exception:
            raise AcceptanceFailure("weekly_artifact_invalid") from None
        _validate_reflection_context(reflection_context)
        _validate_weekly_review_contract(
            weekly_review,
            prepared.weekly_context,
        )
        report = getattr(result, "quality_report", {})
        if not isinstance(report, Mapping):
            raise AcceptanceFailure("quality_gate_failed")
        score = int(report.get("score", 0) or 0)
        independent_quality = check_weekly_review_quality(weekly_review)
        if (
            not bool(report.get("passed"))
            or score < self.quality_threshold
            or not independent_quality.passed
            or independent_quality.score < self.quality_threshold
        ):
            raise AcceptanceFailure("quality_gate_failed")

        start_date, _end_date, source_ids = _period_and_sources(weekly_review)
        matches = [
            record
            for record in prepared.before.pages(WEEKLY_REVIEW)
            if _weekly_identity_matches(
                record,
                start_date=start_date,
                source_ids=source_ids,
            )
        ]
        if len(matches) > 1:
            raise AcceptanceFailure("weekly_identity_not_unique")
        if matches:
            if matches[0].body or any(
                value not in {"", (), None}
                for key, value in matches[0].properties.items()
                if key not in {"Date", "Podcasts", "Week"}
            ):
                raise AcceptanceFailure(
                    "existing_weekly_content_protected"
                )
            raise AcceptanceFailure("weekly_identity_already_exists")

        page_payload = _expected_page_payload(
            weekly_review,
            reflection_context,
            score,
        )
        expected_properties = weekly_reflection_page_properties(page_payload)
        expected_body = tuple(
            weekly_reflection_body_blocks(
                page_payload,
                podcast_database_id=self.config.podcast_data_source_id,
            )
        )
        if _duplicate_headings(expected_body):
            raise AcceptanceFailure("duplicate_weekly_section")
        headings = set(_heading_texts(expected_body))
        required_headings = {
            "1. This Week's Core Idea",
            "3. Ideas Worth Compounding",
            "4. Expressions Worth Reusing",
            "5. Language-Thinking Connection",
            "6. One Application for Next Week",
            "7. Sources",
        }
        if not required_headings.issubset(headings):
            raise AcceptanceFailure("weekly_content_contract_incomplete")
        prepared.policy.configure_expected_payload(
            properties=expected_properties,
            body=expected_body,
        )
        return reflection_context, weekly_review, score, expected_body

    def _verify_dry_run_workspace(
        self,
        prepared: _PreparedRun,
    ) -> None:
        after = prepared.snapshotter.capture()
        if any(
            not _role_records_equal(prepared.before, after, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("dry_run_changed_workspace")
        if (
            prepared.policy.page_creates
            or prepared.policy.page_updates
            or prepared.policy.block_appends
            or prepared.policy.block_deletes
        ):
            raise AcceptanceFailure("dry_run_attempted_notion_write")

    def _verify_first_publish(
        self,
        prepared: _PreparedRun,
        first: WeeklyWorkspaceSnapshot,
        result: Any,
        expected_body: tuple[Mapping[str, Any], ...],
    ) -> WeeklyRecordSnapshot:
        _assert_no_removed_or_archived(prepared.before, first)
        for role in (
            PODCAST_LIBRARY,
            EXPRESSION_DATABASE,
            VOCABULARY_DATABASE,
        ):
            if not _role_records_equal(prepared.before, first, role):
                raise AcceptanceFailure("non_weekly_record_changed")

        before_weekly = prepared.before.by_id(WEEKLY_REVIEW)
        first_weekly = first.by_id(WEEKLY_REVIEW)
        new_ids = set(first_weekly) - set(before_weekly)
        if len(new_ids) != 1:
            raise AcceptanceFailure("first_publish_create_count_mismatch")
        target = first_weekly[next(iter(new_ids))]
        if target.properties != prepared.policy.expected_properties:
            raise AcceptanceFailure("published_weekly_content_mismatch")
        if _normalized_body_contract(target.body) != (
            _normalized_body_contract(expected_body)
        ):
            raise AcceptanceFailure("published_weekly_content_mismatch")
        if _duplicate_headings(target.body):
            raise AcceptanceFailure("duplicate_weekly_section")
        publish_result = getattr(result, "publish_result", None)
        if (
            publish_result is None
            or str(getattr(publish_result, "page_id", "")).strip()
            != target.page_id
        ):
            raise AcceptanceFailure("publisher_result_mismatch")
        for page_id, record in before_weekly.items():
            if (
                record.semantic_fingerprint()
                != first_weekly[page_id].semantic_fingerprint()
            ):
                raise AcceptanceFailure("unrelated_weekly_changed")
        return target

    def _verify_retry(
        self,
        prepared: _PreparedRun,
        first: WeeklyWorkspaceSnapshot,
        second: WeeklyWorkspaceSnapshot,
        result: Any,
    ) -> None:
        _assert_no_removed_or_archived(first, second)
        if any(
            not _role_records_equal(first, second, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("exact_retry_changed_workspace")
        publish_result = getattr(result, "publish_result", None)
        if publish_result is None:
            raise AcceptanceFailure("publisher_result_mismatch")
        if len(prepared.policy.created_weekly_page_ids) != 1:
            raise AcceptanceFailure("exact_retry_created_duplicate")
        target_id = next(iter(prepared.policy.created_weekly_page_ids))
        if str(getattr(publish_result, "page_id", "")).strip() != target_id:
            raise AcceptanceFailure("publisher_result_mismatch")
        target = second.by_id(WEEKLY_REVIEW).get(target_id)
        if target is None or _duplicate_headings(target.body):
            raise AcceptanceFailure("duplicate_weekly_section")

    def _report(
        self,
        prepared: _PreparedRun,
        *,
        mode: str,
        score: int,
        local_changes: tuple[str, ...],
        first: Optional[WeeklyWorkspaceSnapshot] = None,
        retry: Optional[WeeklyWorkspaceSnapshot] = None,
    ) -> WeeklyAcceptanceRunResult:
        before_counts = prepared.before.safe_counts()
        first_counts = first.safe_counts() if first else before_counts
        retry_counts = retry.safe_counts() if retry else first_counts
        report = WeeklyAcceptanceReport(
            status="passed",
            mode=mode,
            target_binding_verified=bool(prepared.binding.valid),
            target_parent_fingerprint=(
                prepared.binding.target_parent_fingerprint
            ),
            target_group_fingerprint=(
                prepared.binding.target_group_fingerprint
            ),
            schema_preflight="passed",
            snapshot_verification="passed",
            learning_context_verified=True,
            reflection_context_verified=True,
            weekly_review_verified=True,
            quality_gate_passed=True,
            quality_score=score,
            planned_weekly_action=prepared.planned_action,
            guard_enforced=True,
            local_artifact_whitelist_verified=True,
            content_contract_verified=True,
            exact_retry_verified=(mode == "live"),
            secrets_redacted=True,
            counts={
                "podcasts": len(
                    prepared.weekly_context.get("podcasts", [])
                ),
                "learning_expressions": len(
                    prepared.weekly_context.get(
                        "learning_expressions",
                        [],
                    )
                ),
                "user_vocabulary_signals": len(
                    prepared.weekly_context.get("user_vocabulary", [])
                ),
                "planned_weekly_create": 1,
                "planned_non_weekly_writes": 0,
                "first_weekly_created": (
                    first_counts[WEEKLY_REVIEW]
                    - before_counts[WEEKLY_REVIEW]
                ),
                "retry_weekly_created": (
                    retry_counts[WEEKLY_REVIEW]
                    - first_counts[WEEKLY_REVIEW]
                ),
                "podcast_delta": (
                    retry_counts[PODCAST_LIBRARY]
                    - before_counts[PODCAST_LIBRARY]
                ),
                "expression_delta": (
                    retry_counts[EXPRESSION_DATABASE]
                    - before_counts[EXPRESSION_DATABASE]
                ),
                "vocabulary_delta": (
                    retry_counts[VOCABULARY_DATABASE]
                    - before_counts[VOCABULARY_DATABASE]
                ),
                "duplicate_sections": 0,
                "duplicate_relations": 0,
            },
        )
        return WeeklyAcceptanceRunResult(
            report=report,
            evidence=WeeklyAcceptanceEvidence(
                before_counts=before_counts,
                after_first_counts=first_counts,
                after_retry_counts=retry_counts,
                local_changes=local_changes,
            ),
        )

    def dry_run(self) -> WeeklyAcceptanceRunResult:
        prepared = self._prepare()
        result, local_changes = self._run_pipeline(
            prepared,
            dry_run=True,
        )
        _reflection, _review, score, _body = (
            self._validate_pipeline_result(prepared, result)
        )
        self._verify_dry_run_workspace(prepared)
        return self._report(
            prepared,
            mode="dry-run",
            score=score,
            local_changes=local_changes,
        )

    def run(
        self,
        *,
        confirmation: str,
    ) -> WeeklyAcceptanceRunResult:
        if confirmation != LIVE_CONFIRMATION:
            raise AcceptanceFailure("live_confirmation_missing")
        prepared = self._prepare()
        preflight_result, preflight_changes = self._run_pipeline(
            prepared,
            dry_run=True,
        )
        _reflection, _review, score, expected_body = (
            self._validate_pipeline_result(prepared, preflight_result)
        )
        self._verify_dry_run_workspace(prepared)

        first_result, first_changes = self._run_pipeline(
            prepared,
            dry_run=False,
        )
        self._validate_pipeline_result(prepared, first_result)
        first = prepared.snapshotter.capture()
        self._verify_first_publish(
            prepared,
            first,
            first_result,
            expected_body,
        )

        retry_result, retry_changes = self._run_pipeline(
            prepared,
            dry_run=False,
        )
        self._validate_pipeline_result(prepared, retry_result)
        retry = prepared.snapshotter.capture()
        self._verify_retry(prepared, first, retry, retry_result)
        return self._report(
            prepared,
            mode="live",
            score=score,
            local_changes=tuple(
                sorted(
                    set(preflight_changes)
                    | set(first_changes)
                    | set(retry_changes)
                )
            ),
            first=first,
            retry=retry,
        )


_PUBLIC_FAILURE_CODES = frozenset(
    {
        "acceptance_execution_failed",
        "database_creation_blocked",
        "delete_or_archive_blocked",
        "delete_or_archive_detected",
        "dry_run_attempted_notion_write",
        "dry_run_changed_workspace",
        "duplicate_weekly_create_blocked",
        "duplicate_weekly_section",
        "exact_retry_changed_workspace",
        "exact_retry_created_duplicate",
        "existing_weekly_content_protected",
        "first_publish_create_count_mismatch",
        "four_data_sources_not_configured",
        "invalid_block_query_response",
        "invalid_data_source_pagination",
        "invalid_data_source_query_response",
        "live_confirmation_missing",
        "non_weekly_block_append_blocked",
        "non_weekly_record_changed",
        "non_weekly_write_blocked",
        "page_create_response_rejected",
        "preexisting_weekly_update_blocked",
        "published_weekly_content_mismatch",
        "publisher_result_mismatch",
        "quality_gate_failed",
        "record_removed",
        "reflection_context_incomplete",
        "schema_mutation_blocked",
        "setup_state_not_complete",
        "snapshot_page_identity_missing",
        "target_binding_configured_data_sources_not_same_group",
        "target_binding_target_binding_retrieve_failed",
        "target_binding_target_binding_validation_failed",
        "target_binding_target_database_ambiguous",
        "target_binding_target_database_missing",
        "target_binding_target_database_role_mismatch",
        "target_binding_target_parent_mismatch",
        "target_binding_target_parent_not_configured",
        "target_binding_target_relation_mode_invalid",
        "target_binding_target_relation_outside_group",
        "unexpected_block_append_shape_blocked",
        "unexpected_block_delete_shape_blocked",
        "unexpected_block_read_blocked",
        "unexpected_data_source_read_blocked",
        "unexpected_page_create_shape_blocked",
        "unexpected_page_read_blocked",
        "unexpected_page_update_shape_blocked",
        "unexpected_weekly_body_blocked",
        "unexpected_weekly_properties_blocked",
        "unrelated_weekly_changed",
        "unsupported_block_operation_blocked",
        "unsupported_data_source_operation_blocked",
        "unsupported_database_operation_blocked",
        "unsupported_page_operation_blocked",
        "weekly_artifact_invalid",
        "weekly_artifact_pending",
        "weekly_artifact_whitelist_violation",
        "weekly_content_contract_incomplete",
        "weekly_identity_already_exists",
        "weekly_identity_not_unique",
        "weekly_learning_context_empty",
        "weekly_learning_context_invalid",
        "weekly_learning_context_missing",
        "weekly_pipeline_failed",
        "weekly_review_incomplete",
        "weekly_source_podcast_missing",
    }
)


def render_redacted_report(
    report: WeeklyAcceptanceReport,
    *,
    secrets: Iterable[str] = (),
) -> str:
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
    safe_code = code if code in _PUBLIC_FAILURE_CODES else "acceptance_failed"
    return json.dumps(
        {
            "status": "failed",
            "failure": safe_code,
            "secrets_redacted": True,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


__all__ = [
    "AcceptanceConfigurationError",
    "AcceptanceFailure",
    "GuardViolation",
    "LIVE_CONFIRMATION",
    "PRODUCTION_QUALITY_THRESHOLD",
    "WeeklyAcceptanceGuard",
    "WeeklyAcceptancePolicy",
    "WeeklyAcceptanceReport",
    "WeeklyAcceptanceRunResult",
    "WeeklyReflectionOwnerAcceptanceRunner",
    "load_acceptance_config",
    "render_failure_report",
    "render_redacted_report",
]
