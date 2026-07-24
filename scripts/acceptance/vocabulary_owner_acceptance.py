"""Protected owner-acceptance harness for pink-highlight vocabulary publishing.

The harness exercises the existing highlight-to-Vocabulary workflow without
changing production behavior. It validates the configured Notion target,
captures read-only snapshots of all four data sources, enforces a Vocabulary-
only write allowlist, and proves that an exact retry creates no duplicates.

Public reports contain only statuses, counts, and irreversible target
fingerprints. Highlight text, page identifiers, URLs, tokens, raw responses,
and record bodies remain private in the in-memory evidence object.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Optional

from scripts.acceptance.podcast_owner_acceptance import (
    AcceptanceConfig,
    AcceptanceConfigurationError,
    AcceptanceFailure,
    GuardViolation,
    _normalized_properties,
    load_acceptance_config,
)
from src.agent.highlight_state import HIGHLIGHT_SYNC_STATE_PATH
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
    WORKSPACE_DATABASE_ORDER,
)
from src.notion.highlight_reader import read_pink_highlights
from src.notion.target_binding import (
    NotionTargetBindingError,
    ensure_notion_page_belongs_to_role,
    validate_notion_target_binding,
)
from src.skill_runtime.artifacts import CodexArtifactPendingError
from src.workflow.highlight_vocabulary_publish_pipeline import (
    publish_highlight_vocabulary,
)
from src.workflow.vocabulary_learning_pipeline import (
    build_vocabulary_learning_preview,
)


LIVE_CONFIRMATION = "VOCABULARY_ACCEPTANCE_WRITES_TO_NOTION"


def _word_key(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _state_digest(path: Path) -> str:
    if not path.exists():
        return "missing"
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True, repr=False)
class VocabularyRecordSnapshot:
    page_id: str = field(repr=False)
    properties: Mapping[str, Any] = field(repr=False)
    archived: bool = field(repr=False)
    in_trash: bool = field(repr=False)

    @property
    def word_key(self) -> str:
        return _word_key(self.properties.get("Name"))

    def fingerprint(self) -> str:
        return json.dumps(
            {
                "properties": self.properties,
                "archived": self.archived,
                "in_trash": self.in_trash,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True, repr=False)
class VocabularyWorkspaceSnapshot:
    records: Mapping[str, tuple[VocabularyRecordSnapshot, ...]] = field(
        repr=False
    )

    def pages(self, role: str) -> tuple[VocabularyRecordSnapshot, ...]:
        return self.records.get(role, ())

    def by_id(self, role: str) -> dict[str, VocabularyRecordSnapshot]:
        return {record.page_id: record for record in self.pages(role)}

    def safe_counts(self) -> dict[str, int]:
        return {role: len(self.pages(role)) for role in WORKSPACE_DATABASE_ORDER}


@dataclass(repr=False)
class VocabularyAcceptancePolicy:
    config: AcceptanceConfig = field(repr=False)
    source_page_id: str = field(repr=False)
    expected_word_keys: set[str] = field(default_factory=set, repr=False)
    existing_word_keys: set[str] = field(default_factory=set, repr=False)
    created_word_keys: set[str] = field(default_factory=set, repr=False)
    target_vocabulary_page_ids: set[str] = field(default_factory=set, repr=False)
    created_vocabulary_page_ids: set[str] = field(default_factory=set, repr=False)
    readable_block_ids: set[str] = field(default_factory=set, repr=False)

    def __post_init__(self) -> None:
        self.readable_block_ids.add(self.source_page_id)

    @property
    def allowed_data_source_ids(self) -> frozenset[str]:
        return frozenset(self.config.data_source_ids.values())

    @property
    def allowed_vocabulary_page_ids(self) -> frozenset[str]:
        return frozenset(
            self.target_vocabulary_page_ids
            | self.created_vocabulary_page_ids
        )

    def set_expected_words(self, words: Iterable[str]) -> None:
        self.expected_word_keys = {
            key for word in words if (key := _word_key(word))
        }

    def authorize_existing_targets(
        self,
        snapshot: VocabularyWorkspaceSnapshot,
    ) -> None:
        for record in snapshot.pages(VOCABULARY_DATABASE):
            if record.word_key in self.expected_word_keys:
                self.existing_word_keys.add(record.word_key)
                self.target_vocabulary_page_ids.add(record.page_id)

    def validate_data_source_read(self, data_source_id: str) -> None:
        if data_source_id not in self.allowed_data_source_ids:
            raise GuardViolation("unexpected_data_source_read_blocked")

    def validate_page_read(self, page_id: str) -> None:
        if page_id not in {
            self.config.target_parent_page_id,
            self.source_page_id,
            *self.allowed_vocabulary_page_ids,
        }:
            raise GuardViolation("unexpected_page_read_blocked")

    def validate_block_read(self, block_id: str) -> None:
        if block_id not in self.readable_block_ids:
            raise GuardViolation("unexpected_block_read_blocked")

    def register_block_results(self, response: Any) -> None:
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

    def _validate_vocabulary_properties(self, properties: Any) -> None:
        normalized = _normalized_properties(properties)
        word_key = _word_key(normalized.get("Name"))
        source_ids = normalized.get("Source")
        if (
            word_key not in self.expected_word_keys
            or not isinstance(source_ids, tuple)
            or source_ids != (self.source_page_id,)
        ):
            raise GuardViolation("unexpected_vocabulary_identity_blocked")

    def validate_page_create(self, kwargs: Mapping[str, Any]) -> str:
        parent = kwargs.get("parent")
        parent = parent if isinstance(parent, Mapping) else {}
        if parent.get("data_source_id") != self.config.vocabulary_data_source_id:
            raise GuardViolation("non_vocabulary_write_blocked")
        if set(kwargs) - {"parent", "properties", "children"}:
            raise GuardViolation("unexpected_page_create_shape_blocked")
        self._validate_vocabulary_properties(kwargs.get("properties"))

        normalized = _normalized_properties(kwargs.get("properties"))
        word_key = _word_key(normalized.get("Name"))
        if word_key in self.existing_word_keys | self.created_word_keys:
            raise GuardViolation("duplicate_vocabulary_create_blocked")
        return word_key

    def register_created_page(self, response: Any, word_key: str) -> None:
        page_id = (
            str(response.get("id", "")).strip()
            if isinstance(response, Mapping)
            else ""
        )
        if not page_id:
            raise GuardViolation("page_create_response_rejected")
        self.created_vocabulary_page_ids.add(page_id)
        self.created_word_keys.add(word_key)

    def validate_page_update(self, kwargs: Mapping[str, Any]) -> None:
        if "archived" in kwargs or "in_trash" in kwargs:
            raise GuardViolation("delete_or_archive_blocked")
        if set(kwargs) - {"page_id", "properties"}:
            raise GuardViolation("unexpected_page_update_shape_blocked")
        page_id = str(kwargs.get("page_id", "")).strip()
        if page_id not in self.allowed_vocabulary_page_ids:
            raise GuardViolation("unexpected_page_update_blocked")
        self._validate_vocabulary_properties(kwargs.get("properties"))


class _GuardedDataSources:
    def __init__(self, raw: Any, policy: VocabularyAcceptancePolicy) -> None:
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
    def __init__(self, raw: Any, policy: VocabularyAcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def create(self, **kwargs: Any) -> Any:
        word_key = self._policy.validate_page_create(kwargs)
        response = self._raw.create(**kwargs)
        self._policy.register_created_page(response, word_key)
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
    def __init__(self, raw: Any, policy: VocabularyAcceptancePolicy) -> None:
        self._raw = raw
        self._policy = policy

    def list(self, **kwargs: Any) -> Any:
        self._policy.validate_block_read(
            str(kwargs.get("block_id", "")).strip()
        )
        response = self._raw.list(**kwargs)
        self._policy.register_block_results(response)
        return response

    def append(self, **_kwargs: Any) -> Any:
        raise GuardViolation("block_append_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("unsupported_block_operation_blocked")


class _GuardedBlocks:
    def __init__(self, raw: Any, policy: VocabularyAcceptancePolicy) -> None:
        self.children = _GuardedBlocksChildren(raw.children, policy)

    def delete(self, **_kwargs: Any) -> Any:
        raise GuardViolation("delete_or_archive_blocked")

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


class VocabularyAcceptanceGuard:
    """Notion facade that permits only scoped Vocabulary page writes."""

    def __init__(self, notion: Any, policy: VocabularyAcceptancePolicy) -> None:
        self.policy = policy
        self.data_sources = _GuardedDataSources(notion.data_sources, policy)
        self.pages = _GuardedPages(notion.pages, policy)
        self.blocks = _GuardedBlocks(notion.blocks, policy)
        self.databases = _GuardedDatabases(notion.databases)


class VocabularyWorkspaceSnapshotter:
    """Capture properties-only snapshots for all configured data sources."""

    def __init__(
        self,
        notion: VocabularyAcceptanceGuard,
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
            cursor_value = response.get("next_cursor")
            cursor = str(cursor_value).strip() if cursor_value else ""
            if not cursor:
                raise AcceptanceFailure("invalid_data_source_pagination")

    def capture(self) -> VocabularyWorkspaceSnapshot:
        records: dict[str, tuple[VocabularyRecordSnapshot, ...]] = {}
        for role in WORKSPACE_DATABASE_ORDER:
            role_records: list[VocabularyRecordSnapshot] = []
            for page in self._query_all(self.config.data_source_ids[role]):
                page_id = str(page.get("id", "")).strip()
                if not page_id:
                    raise AcceptanceFailure("snapshot_page_identity_missing")
                role_records.append(
                    VocabularyRecordSnapshot(
                        page_id=page_id,
                        properties=_normalized_properties(page.get("properties")),
                        archived=bool(page.get("archived", False)),
                        in_trash=bool(page.get("in_trash", False)),
                    )
                )
            records[role] = tuple(role_records)
        return VocabularyWorkspaceSnapshot(records=records)


@dataclass(frozen=True, repr=False)
class VocabularyAcceptanceEvidence:
    highlights: tuple[Mapping[str, Any], ...] = field(repr=False)
    rejected: tuple[Mapping[str, Any], ...] = field(repr=False)
    planned_actions: Mapping[str, str] = field(repr=False)
    before_counts: Mapping[str, int] = field(repr=False)
    after_first_counts: Mapping[str, int] = field(repr=False)
    after_second_counts: Mapping[str, int] = field(repr=False)


@dataclass(frozen=True)
class VocabularyAcceptanceReport:
    status: str
    mode: str
    target_binding_verified: bool
    source_page_role_verified: bool
    target_parent_fingerprint: str
    target_group_fingerprint: str
    schema_preflight: str
    snapshot_verification: str
    state_unchanged: bool
    guard_enforced: bool
    secrets_redacted: bool
    counts: Mapping[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status if self.status == "passed" else "failed",
            "mode": self.mode if self.mode in {"dry-run", "live"} else "unknown",
            "target_binding_verified": bool(self.target_binding_verified),
            "source_page_role_verified": bool(
                self.source_page_role_verified
            ),
            "target_parent_fingerprint": (
                self.target_parent_fingerprint
                if re.fullmatch(r"[0-9a-f]{8}", self.target_parent_fingerprint)
                else "[REDACTED]"
            ),
            "target_group_fingerprint": (
                self.target_group_fingerprint
                if re.fullmatch(r"[0-9a-f]{8}", self.target_group_fingerprint)
                else "[REDACTED]"
            ),
            "schema_preflight": (
                self.schema_preflight
                if self.schema_preflight in {"passed", "failed"}
                else "failed"
            ),
            "snapshot_verification": (
                self.snapshot_verification
                if self.snapshot_verification in {"passed", "failed"}
                else "failed"
            ),
            "state_unchanged": bool(self.state_unchanged),
            "guard_enforced": bool(self.guard_enforced),
            "secrets_redacted": True,
            "counts": {
                key: int(self.counts.get(key, 0))
                for key in (
                    "highlights",
                    "approved",
                    "rejected",
                    "planned_create",
                    "planned_update",
                    "first_created",
                    "first_updated",
                    "retry_created",
                    "retry_updated",
                )
            },
        }


@dataclass(frozen=True)
class VocabularyAcceptanceRunResult:
    report: VocabularyAcceptanceReport
    evidence: VocabularyAcceptanceEvidence = field(repr=False)


@dataclass(repr=False)
class _PreparedRun:
    policy: VocabularyAcceptancePolicy = field(repr=False)
    notion: VocabularyAcceptanceGuard = field(repr=False)
    snapshotter: VocabularyWorkspaceSnapshotter = field(repr=False)
    before: VocabularyWorkspaceSnapshot = field(repr=False)
    raw_highlights: tuple[Mapping[str, Any], ...] = field(repr=False)
    preview: Mapping[str, Any] = field(repr=False)
    approved: tuple[Mapping[str, Any], ...] = field(repr=False)
    rejected: tuple[Mapping[str, Any], ...] = field(repr=False)
    planned_actions: Mapping[str, str] = field(repr=False)
    state_before: str = field(repr=False)
    binding: Any = field(repr=False)


PreviewBuilder = Callable[..., Mapping[str, Any]]
HighlightReader = Callable[..., list[dict[str, str]]]
Publisher = Callable[..., Any]


def _record_sets_equal(
    before: VocabularyWorkspaceSnapshot,
    after: VocabularyWorkspaceSnapshot,
    role: str,
) -> bool:
    before_by_id = before.by_id(role)
    after_by_id = after.by_id(role)
    return set(before_by_id) == set(after_by_id) and all(
        before_by_id[page_id].fingerprint()
        == after_by_id[page_id].fingerprint()
        for page_id in before_by_id
    )


def _target_records(
    snapshot: VocabularyWorkspaceSnapshot,
    expected_word_keys: set[str],
) -> dict[str, list[VocabularyRecordSnapshot]]:
    targets = {key: [] for key in expected_word_keys}
    for record in snapshot.pages(VOCABULARY_DATABASE):
        if record.word_key in targets:
            targets[record.word_key].append(record)
    return targets


def _assert_no_delete_or_archive(
    before: VocabularyWorkspaceSnapshot,
    after: VocabularyWorkspaceSnapshot,
) -> None:
    for role in WORKSPACE_DATABASE_ORDER:
        after_by_id = after.by_id(role)
        for record in before.pages(role):
            current = after_by_id.get(record.page_id)
            if current is None:
                raise AcceptanceFailure("record_deleted_or_archived")
            if (not record.archived and current.archived) or (
                not record.in_trash and current.in_trash
            ):
                raise AcceptanceFailure("record_deleted_or_archived")


class VocabularyOwnerAcceptanceRunner:
    """Run dry-run or guarded publish/retry acceptance for one Podcast page."""

    def __init__(
        self,
        notion: Any,
        config: AcceptanceConfig,
        *,
        highlight_reader: HighlightReader = read_pink_highlights,
        preview_builder: PreviewBuilder = build_vocabulary_learning_preview,
        publisher: Publisher = publish_highlight_vocabulary,
        state_path: Path = HIGHLIGHT_SYNC_STATE_PATH,
    ) -> None:
        self.raw_notion = notion
        self.config = config
        self.highlight_reader = highlight_reader
        self.preview_builder = preview_builder
        self.publisher = publisher
        self.state_path = state_path

    def _prepare(self, page_id: str) -> _PreparedRun:
        policy = VocabularyAcceptancePolicy(
            config=self.config,
            source_page_id=page_id,
        )
        notion = VocabularyAcceptanceGuard(self.raw_notion, policy)
        snapshotter = VocabularyWorkspaceSnapshotter(notion, self.config)
        try:
            binding = validate_notion_target_binding(
                notion,
                self.config.as_notion_config(),
            )
            ensure_notion_page_belongs_to_role(
                notion,
                page_id,
                PODCAST_LIBRARY,
            )
        except NotionTargetBindingError as exc:
            raise AcceptanceFailure(exc.code) from None

        state_before = _state_digest(self.state_path)
        before = snapshotter.capture()
        raw_highlights = tuple(
            item
            for item in self.highlight_reader(
                page_id=page_id,
                notion=notion,
            )
            if isinstance(item, Mapping)
        )
        try:
            with redirect_stdout(io.StringIO()):
                preview = self.preview_builder(page_id=page_id, notion=notion)
        except CodexArtifactPendingError:
            raise AcceptanceFailure("vocabulary_artifact_pending") from None
        if not isinstance(preview, Mapping):
            raise AcceptanceFailure("vocabulary_preview_invalid")
        if str(preview.get("page_id", "")).strip() != page_id:
            raise AcceptanceFailure("vocabulary_source_page_mismatch")

        approved = tuple(
            item
            for item in preview.get("approved_vocabulary", [])
            if isinstance(item, Mapping)
        )
        rejected = tuple(
            item
            for item in preview.get("rejected_candidates", [])
            if isinstance(item, Mapping)
        )
        total_highlights = preview.get("total_highlights")
        if (
            not isinstance(total_highlights, int)
            or total_highlights < 1
            or total_highlights != len(raw_highlights)
            or total_highlights != len(approved) + len(rejected)
        ):
            raise AcceptanceFailure("highlight_count_mismatch")

        word_keys: set[str] = set()
        raw_word_counts = Counter(
            str(item.get("text", "")).strip() for item in raw_highlights
        )
        pipeline_word_counts = Counter(
            [
                str(item.get("word", "")).strip() for item in approved
            ]
            + [
                str(item.get("word", "")).strip() for item in rejected
            ]
        )
        if raw_word_counts != pipeline_word_counts:
            raise AcceptanceFailure("highlight_target_changed")
        for item in approved:
            word = str(item.get("word", "")).strip()
            word_key = _word_key(word)
            if (
                not word_key
                or word_key in word_keys
                or str(item.get("source_page_id", "")).strip() != page_id
            ):
                raise AcceptanceFailure("approved_vocabulary_invalid")
            if not any(
                str(highlight.get("text", "")).strip() == word
                and str(highlight.get("context", "")).strip()
                == str(item.get("original_context", "")).strip()
                for highlight in raw_highlights
            ):
                raise AcceptanceFailure("highlight_context_changed")
            for field_name in (
                "original_context",
                "meaning",
                "chinese_meaning",
                "part_of_speech",
                "professional_category",
                "usage_example",
            ):
                if not str(item.get(field_name, "")).strip():
                    raise AcceptanceFailure("enrichment_artifact_incomplete")
            collocations = item.get("common_collocations")
            if not isinstance(collocations, list) or any(
                not isinstance(value, str) or not value.strip()
                for value in collocations
            ):
                raise AcceptanceFailure("enrichment_artifact_incomplete")
            word_keys.add(word_key)

        for item in rejected:
            if not str(item.get("word", "")).strip() or not str(
                item.get("reason", "")
            ).strip():
                raise AcceptanceFailure("rejected_candidate_invalid")

        policy.set_expected_words(
            str(item.get("word", "")).strip() for item in approved
        )
        targets = _target_records(before, policy.expected_word_keys)
        approved_words = {
            _word_key(item.get("word")): str(item.get("word", "")).strip()
            for item in approved
        }
        planned_actions: dict[str, str] = {}
        for word_key, records in targets.items():
            if len(records) > 1:
                raise AcceptanceFailure("vocabulary_identity_not_unique")
            if records:
                record = records[0]
                if str(record.properties.get("Name") or "").strip() != (
                    approved_words[word_key]
                ):
                    raise AcceptanceFailure(
                        "vocabulary_identity_normalization_mismatch"
                    )
                if any(
                    record.properties.get(field_name)
                    for field_name in (
                        "Personal Note",
                        "Last Review",
                    )
                ):
                    raise AcceptanceFailure(
                        "manual_vocabulary_fields_present"
                    )
                review_status = record.properties.get("Review Status")
                if review_status not in (None, "", "New"):
                    raise AcceptanceFailure(
                        "manual_vocabulary_fields_present"
                    )
                planned_actions[word_key] = "update"
            else:
                planned_actions[word_key] = "create"
        policy.authorize_existing_targets(before)

        if _state_digest(self.state_path) != state_before:
            raise AcceptanceFailure("highlight_state_changed")

        return _PreparedRun(
            policy=policy,
            notion=notion,
            snapshotter=snapshotter,
            before=before,
            raw_highlights=raw_highlights,
            preview=preview,
            approved=approved,
            rejected=rejected,
            planned_actions=planned_actions,
            state_before=state_before,
            binding=binding,
        )

    def _report(
        self,
        prepared: _PreparedRun,
        *,
        mode: str,
        first_created: int = 0,
        first_updated: int = 0,
        retry_created: int = 0,
        retry_updated: int = 0,
    ) -> VocabularyAcceptanceRunResult:
        report = VocabularyAcceptanceReport(
            status="passed",
            mode=mode,
            target_binding_verified=bool(prepared.binding.valid),
            source_page_role_verified=True,
            target_parent_fingerprint=(
                prepared.binding.target_parent_fingerprint
            ),
            target_group_fingerprint=(
                prepared.binding.target_group_fingerprint
            ),
            schema_preflight="passed",
            snapshot_verification="passed",
            state_unchanged=True,
            guard_enforced=True,
            secrets_redacted=True,
            counts={
                "highlights": int(prepared.preview["total_highlights"]),
                "approved": len(prepared.approved),
                "rejected": len(prepared.rejected),
                "planned_create": sum(
                    action == "create"
                    for action in prepared.planned_actions.values()
                ),
                "planned_update": sum(
                    action == "update"
                    for action in prepared.planned_actions.values()
                ),
                "first_created": first_created,
                "first_updated": first_updated,
                "retry_created": retry_created,
                "retry_updated": retry_updated,
            },
        )
        evidence = VocabularyAcceptanceEvidence(
            highlights=prepared.raw_highlights,
            rejected=prepared.rejected,
            planned_actions=prepared.planned_actions,
            before_counts=prepared.before.safe_counts(),
            after_first_counts={},
            after_second_counts={},
        )
        return VocabularyAcceptanceRunResult(report=report, evidence=evidence)

    def dry_run(self, page_id: str) -> VocabularyAcceptanceRunResult:
        prepared = self._prepare(page_id)
        after = prepared.snapshotter.capture()
        if any(
            not _record_sets_equal(prepared.before, after, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("dry_run_changed_workspace")
        if _state_digest(self.state_path) != prepared.state_before:
            raise AcceptanceFailure("highlight_state_changed")
        return self._report(prepared, mode="dry-run")

    def run(self, page_id: str) -> VocabularyAcceptanceRunResult:
        prepared = self._prepare(page_id)
        first_result = self.publisher(
            page_id,
            notion=prepared.notion,
            vocabulary_database_id=self.config.vocabulary_data_source_id,
        )
        first = prepared.snapshotter.capture()
        self._verify_first(prepared, first, first_result)

        second_result = self.publisher(
            page_id,
            notion=prepared.notion,
            vocabulary_database_id=self.config.vocabulary_data_source_id,
        )
        second = prepared.snapshotter.capture()
        self._verify_second(prepared, first, second, second_result)

        if _state_digest(self.state_path) != prepared.state_before:
            raise AcceptanceFailure("highlight_state_changed")

        result = self._report(
            prepared,
            mode="live",
            first_created=int(getattr(first_result, "created", -1)),
            first_updated=int(getattr(first_result, "updated", -1)),
            retry_created=int(getattr(second_result, "created", -1)),
            retry_updated=int(getattr(second_result, "updated", -1)),
        )
        return VocabularyAcceptanceRunResult(
            report=result.report,
            evidence=VocabularyAcceptanceEvidence(
                highlights=result.evidence.highlights,
                rejected=result.evidence.rejected,
                planned_actions=result.evidence.planned_actions,
                before_counts=prepared.before.safe_counts(),
                after_first_counts=first.safe_counts(),
                after_second_counts=second.safe_counts(),
            ),
        )

    def _verify_first(
        self,
        prepared: _PreparedRun,
        first: VocabularyWorkspaceSnapshot,
        publish_result: Any,
    ) -> None:
        _assert_no_delete_or_archive(prepared.before, first)
        for role in (
            PODCAST_LIBRARY,
            EXPRESSION_DATABASE,
            WEEKLY_REVIEW,
        ):
            if not _record_sets_equal(prepared.before, first, role):
                raise AcceptanceFailure("non_vocabulary_record_changed")

        before_vocab = prepared.before.by_id(VOCABULARY_DATABASE)
        first_vocab = first.by_id(VOCABULARY_DATABASE)
        if not set(before_vocab).issubset(first_vocab):
            raise AcceptanceFailure("vocabulary_record_removed")
        expected_new = sum(
            action == "create"
            for action in prepared.planned_actions.values()
        )
        if len(set(first_vocab) - set(before_vocab)) != expected_new:
            raise AcceptanceFailure("first_publish_create_count_mismatch")

        targets = _target_records(first, prepared.policy.expected_word_keys)
        if any(len(records) != 1 for records in targets.values()):
            raise AcceptanceFailure("vocabulary_identity_not_unique")

        target_ids = {
            records[0].page_id for records in targets.values() if records
        }
        for page_id, before_record in before_vocab.items():
            if (
                page_id not in target_ids
                and before_record.fingerprint()
                != first_vocab[page_id].fingerprint()
            ):
                raise AcceptanceFailure("unrelated_vocabulary_changed")

        if int(getattr(publish_result, "created", -1)) != expected_new:
            raise AcceptanceFailure("publisher_create_count_mismatch")
        expected_updates = len(prepared.approved) - expected_new
        if int(getattr(publish_result, "updated", -1)) != expected_updates:
            raise AcceptanceFailure("publisher_update_count_mismatch")

    def _verify_second(
        self,
        prepared: _PreparedRun,
        first: VocabularyWorkspaceSnapshot,
        second: VocabularyWorkspaceSnapshot,
        publish_result: Any,
    ) -> None:
        _assert_no_delete_or_archive(first, second)
        if any(
            not _record_sets_equal(first, second, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("exact_retry_changed_workspace")
        if int(getattr(publish_result, "created", -1)) != 0:
            raise AcceptanceFailure("exact_retry_created_duplicate")
        if int(getattr(publish_result, "updated", -1)) != len(
            prepared.approved
        ):
            raise AcceptanceFailure("exact_retry_update_count_mismatch")


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
_PUBLIC_FAILURE_CODES = frozenset(
    {
        "acceptance_execution_failed",
        "approved_vocabulary_invalid",
        "block_append_blocked",
        "database_creation_blocked",
        "delete_or_archive_blocked",
        "dry_run_changed_workspace",
        "duplicate_vocabulary_create_blocked",
        "enrichment_artifact_incomplete",
        "exact_retry_changed_workspace",
        "exact_retry_create_count_mismatch",
        "exact_retry_created_duplicate",
        "exact_retry_update_count_mismatch",
        "first_publish_create_count_mismatch",
        "four_data_sources_not_configured",
        "highlight_count_mismatch",
        "highlight_context_changed",
        "highlight_state_changed",
        "highlight_target_changed",
        "invalid_data_source_pagination",
        "invalid_data_source_query_response",
        "live_confirmation_missing",
        "manual_vocabulary_fields_present",
        "non_vocabulary_record_changed",
        "non_vocabulary_write_blocked",
        "page_create_response_rejected",
        "publisher_create_count_mismatch",
        "publisher_update_count_mismatch",
        "rejected_candidate_invalid",
        "schema_mutation_blocked",
        "setup_state_not_complete",
        "snapshot_page_identity_missing",
        "unexpected_block_read_blocked",
        "unexpected_data_source_read_blocked",
        "unexpected_page_create_shape_blocked",
        "unexpected_page_read_blocked",
        "unexpected_page_update_blocked",
        "unexpected_page_update_shape_blocked",
        "unexpected_vocabulary_identity_blocked",
        "unrelated_vocabulary_changed",
        "unsupported_block_operation_blocked",
        "unsupported_data_source_operation_blocked",
        "unsupported_database_operation_blocked",
        "unsupported_page_operation_blocked",
        "vocabulary_artifact_pending",
        "vocabulary_identity_not_unique",
        "vocabulary_identity_normalization_mismatch",
        "vocabulary_preview_invalid",
        "vocabulary_record_removed",
        "vocabulary_source_page_mismatch",
    }
)


def render_redacted_report(
    report: VocabularyAcceptanceReport,
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
    "VocabularyAcceptanceEvidence",
    "VocabularyAcceptanceGuard",
    "VocabularyAcceptancePolicy",
    "VocabularyAcceptanceReport",
    "VocabularyAcceptanceRunResult",
    "VocabularyOwnerAcceptanceRunner",
    "load_acceptance_config",
    "render_failure_report",
    "render_redacted_report",
]
