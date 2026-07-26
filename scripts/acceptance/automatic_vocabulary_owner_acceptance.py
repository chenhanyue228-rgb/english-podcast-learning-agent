"""Protected owner acceptance for the automatic pink-highlight runtime.

The harness validates Target Binding, snapshots the current target group, and
enforces strict write ceilings around one controlled Podcast page, one pink
highlight append, and one Vocabulary create. Public reports contain no
learning text, raw identifiers, URLs, tokens, paths, or response bodies.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
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
from scripts.acceptance.vocabulary_owner_acceptance import (
    VocabularyRecordSnapshot,
    VocabularyWorkspaceSnapshot,
    VocabularyWorkspaceSnapshotter,
)
from src.agent.automatic_vocabulary_runtime import (
    AutomaticVocabularyRuntimeReport,
    run_bounded_automatic_vocabulary_cycle,
)
from src.agent.automatic_vocabulary_state import STATUS_PUBLISHED
from src.enrichment.automatic_vocabulary_schema import (
    AutomaticVocabularyArtifactError,
    validate_automatic_vocabulary_artifact,
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


LIVE_CONFIRMATION = (
    "AUTOMATIC_VOCABULARY_OWNER_ACCEPTANCE_WRITES_TO_NOTION"
)
ACCEPTANCE_WORD = "calibrate decision boundaries"
ACCEPTANCE_CONTEXT = (
    "Leaders calibrate decision boundaries before commitments."
)
BASELINE_WORD = "existing baseline marker"
BASELINE_CONTEXT = (
    "The existing baseline marker remains historical."
)
DEFAULT_QUIET_PERIOD_SECONDS = 90


def _word_key(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _rich_text(value: str, *, color: str = "default") -> dict[str, Any]:
    return {
        "type": "text",
        "text": {"content": value},
        "annotations": {"color": color},
        "plain_text": value,
    }


def _paragraph(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": items},
    }


def _title_property(value: str) -> dict[str, Any]:
    return {"title": [_rich_text(value)]}


def _rich_text_property(value: str) -> dict[str, Any]:
    return {"rich_text": [_rich_text(value)] if value else []}


def _select_property(value: str) -> dict[str, Any]:
    return {"select": {"name": value}}


def _date_property(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def _url_property(value: str) -> dict[str, Any]:
    return {"url": value}


def _snapshot_fingerprints(
    snapshot: VocabularyWorkspaceSnapshot,
    role: str,
) -> dict[str, str]:
    return {
        record.page_id: record.fingerprint()
        for record in snapshot.pages(role)
    }


def _existing_records_unchanged(
    before: VocabularyWorkspaceSnapshot,
    after: VocabularyWorkspaceSnapshot,
    role: str,
) -> bool:
    before_records = _snapshot_fingerprints(before, role)
    after_records = _snapshot_fingerprints(after, role)
    return set(before_records).issubset(after_records) and all(
        after_records[page_id] == fingerprint
        for page_id, fingerprint in before_records.items()
    )


def _tree_fingerprint(blocks: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            blocks,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _block_text(block: Mapping[str, Any]) -> str:
    block_type = str(block.get("type", "")).strip()
    payload = block.get(block_type)
    rich_text = (
        payload.get("rich_text")
        if isinstance(payload, Mapping)
        else None
    )
    if not isinstance(rich_text, list):
        return ""
    return "".join(
        str(
            item.get("plain_text")
            or (
                item.get("text", {}).get("content", "")
                if isinstance(item.get("text"), Mapping)
                else ""
            )
        )
        for item in rich_text
        if isinstance(item, Mapping)
    )


def _expected_body_structure(
    artifact: Mapping[str, Any],
) -> list[tuple[str, str]]:
    expected = [
        ("heading_1", ACCEPTANCE_WORD),
        ("heading_2", "Context"),
        ("paragraph", ACCEPTANCE_CONTEXT),
        ("heading_2", "Meaning"),
        ("paragraph", str(artifact["meaning"])),
        ("heading_2", "Chinese Meaning"),
        ("paragraph", str(artifact["chinese_meaning"])),
        ("heading_2", "Part of Speech"),
        ("paragraph", str(artifact["part_of_speech"])),
        ("heading_2", "Professional Context"),
        ("paragraph", str(artifact["professional_category"])),
        ("heading_2", "Usage Example"),
        ("paragraph", str(artifact["usage_example"])),
        ("heading_2", "Common Collocations"),
    ]
    expected.extend(
        ("bulleted_list_item", str(value))
        for value in artifact["common_collocations"]
    )
    expected.extend(
        [
            ("heading_2", "Personal Note"),
            ("paragraph", ""),
            ("heading_2", "Source"),
            ("paragraph", "Podcast Library source linked."),
            ("heading_2", "Review Status"),
            ("paragraph", "New"),
        ]
    )
    return expected


@dataclass(repr=False)
class AutomaticVocabularyAcceptancePolicy:
    """Fail-closed allowlist for the complete live acceptance sequence."""

    config: AcceptanceConfig = field(repr=False)
    controlled_title: str = field(repr=False)
    controlled_url: str = field(repr=False)
    expected_word: str = field(repr=False, default=ACCEPTANCE_WORD)
    expected_context: str = field(
        repr=False,
        default=ACCEPTANCE_CONTEXT,
    )
    controlled_podcast_page_id: str = field(default="", repr=False)
    vocabulary_page_id: str = field(default="", repr=False)
    readable_podcast_page_ids: set[str] = field(
        default_factory=set,
        repr=False,
    )
    readable_vocabulary_page_ids: set[str] = field(
        default_factory=set,
        repr=False,
    )
    readable_block_ids: set[str] = field(default_factory=set, repr=False)
    database_ids: set[str] = field(default_factory=set, repr=False)
    counts: dict[str, int] = field(
        default_factory=lambda: {
            "podcast_created": 0,
            "highlight_writes": 0,
            "vocabulary_created": 0,
            "vocabulary_updated": 0,
            "expression_writes": 0,
            "weekly_writes": 0,
            "schema_writes": 0,
            "delete_archive": 0,
            "historical_reads": 0,
            "historical_writes": 0,
        }
    )

    @property
    def data_source_roles(self) -> dict[str, str]:
        return {
            identifier: role
            for role, identifier in self.config.data_source_ids.items()
        }

    def validate_data_source_read(self, identifier: str) -> str:
        role = self.data_source_roles.get(identifier)
        if role is None:
            self.counts["historical_reads"] += 1
            raise GuardViolation("historical_group_read_blocked")
        return role

    def register_data_source(self, response: Any) -> None:
        if not isinstance(response, Mapping):
            return
        parent = response.get("parent")
        if isinstance(parent, Mapping):
            identifier = str(parent.get("database_id", "")).strip()
            if identifier:
                self.database_ids.add(identifier)

    def register_query(self, role: str, response: Any) -> None:
        if not isinstance(response, Mapping):
            return
        results = response.get("results")
        if not isinstance(results, list):
            return
        for item in results:
            if not isinstance(item, Mapping):
                continue
            page_id = str(item.get("id", "")).strip()
            if not page_id:
                continue
            if role == PODCAST_LIBRARY:
                self.readable_podcast_page_ids.add(page_id)
                self.readable_block_ids.add(page_id)
            elif role == VOCABULARY_DATABASE:
                self.readable_vocabulary_page_ids.add(page_id)

    def validate_database_read(self, identifier: str) -> None:
        if identifier not in self.database_ids:
            self.counts["historical_reads"] += 1
            raise GuardViolation("historical_group_read_blocked")

    def validate_page_read(self, page_id: str) -> None:
        if page_id in {
            self.config.target_parent_page_id,
            self.controlled_podcast_page_id,
            self.vocabulary_page_id,
            *self.readable_podcast_page_ids,
            *self.readable_vocabulary_page_ids,
        }:
            return
        self.counts["historical_reads"] += 1
        raise GuardViolation("historical_group_read_blocked")

    def validate_block_read(self, block_id: str) -> None:
        if block_id not in self.readable_block_ids:
            self.counts["historical_reads"] += 1
            raise GuardViolation("historical_group_read_blocked")

    def register_blocks(self, response: Any) -> None:
        if not isinstance(response, Mapping):
            return
        results = response.get("results")
        if not isinstance(results, list):
            return
        for item in results:
            if not isinstance(item, Mapping):
                continue
            block_id = str(item.get("id", "")).strip()
            if block_id:
                self.readable_block_ids.add(block_id)

    def _validate_podcast_create(
        self,
        kwargs: Mapping[str, Any],
    ) -> None:
        if self.counts["podcast_created"] >= 1:
            raise GuardViolation("podcast_write_limit_exceeded")
        properties = _normalized_properties(kwargs.get("properties"))
        if (
            properties.get("Title") != self.controlled_title
            or properties.get("URL") != self.controlled_url
            or properties.get("Source Type") != "Podcast"
        ):
            raise GuardViolation("controlled_podcast_identity_invalid")
        children = kwargs.get("children")
        if not isinstance(children, list) or len(children) != 1:
            raise GuardViolation("controlled_podcast_payload_invalid")
        rich_text = (
            children[0].get("paragraph", {}).get("rich_text")
            if isinstance(children[0], Mapping)
            else None
        )
        if not isinstance(rich_text, list):
            raise GuardViolation("controlled_podcast_payload_invalid")
        source = "".join(
            str(item.get("plain_text") or item.get("text", {}).get("content", ""))
            for item in rich_text
            if isinstance(item, Mapping)
        )
        pink = [
            item
            for item in rich_text
            if isinstance(item, Mapping)
            and isinstance(item.get("annotations"), Mapping)
            and item["annotations"].get("color")
            in {"pink", "pink_background"}
        ]
        if (
            source != BASELINE_CONTEXT
            or len(pink) != 1
            or str(
                pink[0].get("plain_text")
                or pink[0].get("text", {}).get("content", "")
            )
            != BASELINE_WORD
        ):
            raise GuardViolation("controlled_podcast_payload_invalid")
        self.counts["podcast_created"] += 1

    def _validate_vocabulary_create(
        self,
        kwargs: Mapping[str, Any],
    ) -> None:
        if (
            self.counts["vocabulary_created"] >= 1
            or not self.controlled_podcast_page_id
        ):
            raise GuardViolation("vocabulary_write_limit_exceeded")
        properties = _normalized_properties(kwargs.get("properties"))
        if (
            properties.get("Name") != self.expected_word
            or properties.get("Original Context")
            != self.expected_context
            or properties.get("Source")
            != (self.controlled_podcast_page_id,)
            or properties.get("Source Page ID")
            != self.controlled_podcast_page_id
        ):
            raise GuardViolation("automatic_vocabulary_identity_invalid")
        children = kwargs.get("children")
        if not isinstance(children, list) or not children:
            raise GuardViolation("automatic_vocabulary_body_incomplete")
        self.counts["vocabulary_created"] += 1

    def validate_page_create(self, kwargs: Mapping[str, Any]) -> str:
        if set(kwargs) - {"parent", "properties", "children"}:
            raise GuardViolation("page_create_shape_invalid")
        parent = kwargs.get("parent")
        identifier = (
            str(parent.get("data_source_id", "")).strip()
            if isinstance(parent, Mapping)
            else ""
        )
        if identifier == self.config.podcast_data_source_id:
            self._validate_podcast_create(kwargs)
            return PODCAST_LIBRARY
        if identifier == self.config.vocabulary_data_source_id:
            self._validate_vocabulary_create(kwargs)
            return VOCABULARY_DATABASE
        if identifier == self.config.expression_data_source_id:
            self.counts["expression_writes"] += 1
            raise GuardViolation("expression_write_blocked")
        if identifier == self.config.weekly_data_source_id:
            self.counts["weekly_writes"] += 1
            raise GuardViolation("weekly_write_blocked")
        self.counts["historical_writes"] += 1
        raise GuardViolation("historical_group_write_blocked")

    def register_created_page(self, role: str, response: Any) -> None:
        page_id = (
            str(response.get("id", "")).strip()
            if isinstance(response, Mapping)
            else ""
        )
        if not page_id:
            raise GuardViolation("page_create_response_invalid")
        if role == PODCAST_LIBRARY:
            self.controlled_podcast_page_id = page_id
            self.readable_podcast_page_ids.add(page_id)
            self.readable_block_ids.add(page_id)
        else:
            self.vocabulary_page_id = page_id
            self.readable_vocabulary_page_ids.add(page_id)
            self.readable_block_ids.add(page_id)

    def validate_page_update(self, kwargs: Mapping[str, Any]) -> None:
        if "archived" in kwargs or "in_trash" in kwargs:
            self.counts["delete_archive"] += 1
            raise GuardViolation("delete_or_archive_blocked")
        page_id = str(kwargs.get("page_id", "")).strip()
        if page_id == self.vocabulary_page_id:
            self.counts["vocabulary_updated"] += 1
            raise GuardViolation("vocabulary_update_blocked")
        raise GuardViolation("non_target_page_update_blocked")

    def validate_highlight_append(
        self,
        block_id: str,
        children: Any,
    ) -> None:
        if (
            block_id != self.controlled_podcast_page_id
            or self.counts["highlight_writes"] >= 1
            or not isinstance(children, list)
            or len(children) != 1
        ):
            raise GuardViolation("highlight_write_limit_exceeded")
        block = children[0]
        rich_text = (
            block.get("paragraph", {}).get("rich_text")
            if isinstance(block, Mapping)
            else None
        )
        if not isinstance(rich_text, list):
            raise GuardViolation("controlled_highlight_invalid")
        source = "".join(
            str(item.get("plain_text") or item.get("text", {}).get("content", ""))
            for item in rich_text
            if isinstance(item, Mapping)
        )
        pink = [
            item
            for item in rich_text
            if isinstance(item, Mapping)
            and isinstance(item.get("annotations"), Mapping)
            and item["annotations"].get("color")
            in {"pink", "pink_background"}
        ]
        if (
            source != self.expected_context
            or len(pink) != 1
            or str(
                pink[0].get("plain_text")
                or pink[0].get("text", {}).get("content", "")
            )
            != self.expected_word
        ):
            raise GuardViolation("controlled_highlight_invalid")
        self.counts["highlight_writes"] += 1


class _GuardedDataSources:
    def __init__(
        self,
        raw: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self._raw = raw
        self._policy = policy

    def retrieve(self, **kwargs: Any) -> Any:
        identifier = str(kwargs.get("data_source_id", "")).strip()
        self._policy.validate_data_source_read(identifier)
        response = self._raw.retrieve(**kwargs)
        self._policy.register_data_source(response)
        return response

    def query(self, **kwargs: Any) -> Any:
        identifier = str(kwargs.get("data_source_id", "")).strip()
        role = self._policy.validate_data_source_read(identifier)
        response = self._raw.query(**kwargs)
        self._policy.register_query(role, response)
        return response

    def update(self, **_kwargs: Any) -> Any:
        self._policy.counts["schema_writes"] += 1
        raise GuardViolation("schema_mutation_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("data_source_operation_blocked")


class _GuardedDatabases:
    def __init__(
        self,
        raw: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self._raw = raw
        self._policy = policy

    def retrieve(self, **kwargs: Any) -> Any:
        identifier = str(kwargs.get("database_id", "")).strip()
        self._policy.validate_database_read(identifier)
        return self._raw.retrieve(**kwargs)

    def create(self, **_kwargs: Any) -> Any:
        self._policy.counts["schema_writes"] += 1
        raise GuardViolation("database_creation_blocked")

    def update(self, **_kwargs: Any) -> Any:
        self._policy.counts["schema_writes"] += 1
        raise GuardViolation("schema_mutation_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("database_operation_blocked")


class _GuardedPages:
    def __init__(
        self,
        raw: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self._raw = raw
        self._policy = policy

    def create(self, **kwargs: Any) -> Any:
        role = self._policy.validate_page_create(kwargs)
        response = self._raw.create(**kwargs)
        self._policy.register_created_page(role, response)
        return response

    def retrieve(self, **kwargs: Any) -> Any:
        page_id = str(kwargs.get("page_id", "")).strip()
        self._policy.validate_page_read(page_id)
        return self._raw.retrieve(**kwargs)

    def update(self, **kwargs: Any) -> Any:
        self._policy.validate_page_update(kwargs)
        raise AssertionError("unreachable")

    def delete(self, **_kwargs: Any) -> Any:
        self._policy.counts["delete_archive"] += 1
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("page_operation_blocked")


class _GuardedBlockChildren:
    def __init__(
        self,
        raw: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self._raw = raw
        self._policy = policy

    def list(self, **kwargs: Any) -> Any:
        block_id = str(kwargs.get("block_id", "")).strip()
        self._policy.validate_block_read(block_id)
        response = self._raw.list(**kwargs)
        self._policy.register_blocks(response)
        return response

    def append(self, **kwargs: Any) -> Any:
        block_id = str(kwargs.get("block_id", "")).strip()
        self._policy.validate_highlight_append(
            block_id,
            kwargs.get("children"),
        )
        return self._raw.append(**kwargs)

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("block_operation_blocked")


class _GuardedBlocks:
    def __init__(
        self,
        raw: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self.children = _GuardedBlockChildren(raw.children, policy)
        self._policy = policy

    def update(self, **_kwargs: Any) -> Any:
        raise GuardViolation("block_update_blocked")

    def delete(self, **_kwargs: Any) -> Any:
        self._policy.counts["delete_archive"] += 1
        raise GuardViolation("delete_or_archive_blocked")

    def __getattr__(self, _name: str) -> Any:
        raise GuardViolation("block_operation_blocked")


class AutomaticVocabularyAcceptanceGuard:
    """Notion facade constrained to the live acceptance write budget."""

    def __init__(
        self,
        notion: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        self.policy = policy
        self.data_sources = _GuardedDataSources(
            notion.data_sources,
            policy,
        )
        self.databases = _GuardedDatabases(notion.databases, policy)
        self.pages = _GuardedPages(notion.pages, policy)
        self.blocks = _GuardedBlocks(notion.blocks, policy)


@dataclass(frozen=True)
class AutomaticVocabularyAcceptanceReport:
    status: str
    mode: str
    target_binding_valid: bool
    baseline_verified: bool
    quiet_period_verified: bool
    exact_word_verified: bool
    exact_context_verified: bool
    properties_complete: bool
    body_complete: bool
    source_relation_verified: bool
    occurrence_fingerprint_verified: bool
    exact_retry_verified: bool
    logs_redacted: bool
    target_parent_fingerprint: str
    target_group_fingerprint: str
    counts: Mapping[str, int]
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        safe = asdict(self)
        safe["counts"] = {
            key: int(self.counts.get(key, 0))
            for key in (
                "podcast_created",
                "highlight_writes",
                "quiet_period_vocabulary_writes",
                "vocabulary_created",
                "vocabulary_updated",
                "retry_created",
                "retry_updated",
                "codex_calls",
                "expression_writes",
                "weekly_writes",
                "schema_writes",
                "delete_archive",
                "historical_reads",
                "historical_writes",
                "user_commands",
            )
        }
        return safe


@dataclass(frozen=True, repr=False)
class AutomaticVocabularyAcceptanceResult:
    report: AutomaticVocabularyAcceptanceReport
    controlled_podcast_page_id: str = field(repr=False, default="")
    vocabulary_page_id: str = field(repr=False, default="")


Runtime = Callable[..., AutomaticVocabularyRuntimeReport]


class AutomaticVocabularyOwnerAcceptanceRunner:
    """Run dry-run or guarded baseline/publish/retry acceptance."""

    def __init__(
        self,
        notion: Any,
        config: AcceptanceConfig,
        *,
        runtime: Runtime = run_bounded_automatic_vocabulary_cycle,
        state_path: Path,
        artifact_root: Path,
        lock_path: Path,
        log_path: Path,
        clock: Callable[[], datetime] = (
            lambda: datetime.now(timezone.utc)
        ),
        sleep: Callable[[float], None] = time.sleep,
        quiet_period_seconds: int = DEFAULT_QUIET_PERIOD_SECONDS,
        processor_options: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self.raw_notion = notion
        self.config = config
        self.runtime = runtime
        self.state_path = Path(state_path)
        self.artifact_root = Path(artifact_root)
        self.lock_path = Path(lock_path)
        self.log_path = Path(log_path)
        self.clock = clock
        self.sleep = sleep
        self.quiet_period_seconds = quiet_period_seconds
        self.processor_options = dict(processor_options or {})

    def _policy(self) -> AutomaticVocabularyAcceptancePolicy:
        nonce = uuid.uuid4().hex
        return AutomaticVocabularyAcceptancePolicy(
            config=self.config,
            controlled_title=f"Automatic Vocabulary Acceptance {nonce[:8]}",
            controlled_url=(
                "https://example.invalid/"
                f"automatic-vocabulary-acceptance/{nonce}"
            ),
        )

    def _prepare(
        self,
    ) -> tuple[
        AutomaticVocabularyAcceptancePolicy,
        AutomaticVocabularyAcceptanceGuard,
        VocabularyWorkspaceSnapshotter,
        VocabularyWorkspaceSnapshot,
        Any,
    ]:
        policy = self._policy()
        notion = AutomaticVocabularyAcceptanceGuard(
            self.raw_notion,
            policy,
        )
        try:
            binding = validate_notion_target_binding(
                notion,
                self.config.as_notion_config(),
            )
        except NotionTargetBindingError as exc:
            raise AcceptanceFailure(exc.code) from None
        snapshotter = VocabularyWorkspaceSnapshotter(
            notion,
            self.config,
        )
        before = snapshotter.capture()
        if any(
            record.word_key == _word_key(ACCEPTANCE_WORD)
            for record in before.pages(VOCABULARY_DATABASE)
        ):
            raise AcceptanceFailure(
                "acceptance_vocabulary_identity_exists"
            )
        return policy, notion, snapshotter, before, binding

    def _runtime(
        self,
        notion: AutomaticVocabularyAcceptanceGuard,
        *,
        at: datetime,
    ) -> AutomaticVocabularyRuntimeReport:
        return self.runtime(
            notion=notion,
            config=self.config.as_notion_config(),
            state_path=self.state_path,
            artifact_root=self.artifact_root,
            lock_path=self.lock_path,
            log_path=self.log_path,
            now=at,
            detector_options={
                "quiet_period_seconds": self.quiet_period_seconds,
                "commit_clock": self.clock,
            },
            processor_options={
                "clock": self.clock,
                **self.processor_options,
            },
        )

    @staticmethod
    def _controlled_podcast_properties(
        policy: AutomaticVocabularyAcceptancePolicy,
        current_date: str,
    ) -> dict[str, Any]:
        return {
            "Title": _title_property(policy.controlled_title),
            "URL": _url_property(policy.controlled_url),
            "Source Type": _select_property("Podcast"),
            "Date": _date_property(current_date),
            "Topic": _select_property("Leadership"),
            "Difficulty": _select_property("Intermediate"),
            "Short Summary": _rich_text_property(
                "Controlled automatic vocabulary acceptance."
            ),
        }

    @staticmethod
    def _highlight_block() -> dict[str, Any]:
        return _paragraph(
            [
                _rich_text("Leaders "),
                _rich_text(
                    ACCEPTANCE_WORD,
                    color="pink_background",
                ),
                _rich_text(" before commitments."),
            ]
        )

    @staticmethod
    def _baseline_block() -> dict[str, Any]:
        return _paragraph(
            [
                _rich_text("The "),
                _rich_text(
                    BASELINE_WORD,
                    color="pink_background",
                ),
                _rich_text(" remains historical."),
            ]
        )

    @staticmethod
    def _vocabulary_record(
        snapshot: VocabularyWorkspaceSnapshot,
    ) -> VocabularyRecordSnapshot:
        matches = [
            record
            for record in snapshot.pages(VOCABULARY_DATABASE)
            if record.word_key == _word_key(ACCEPTANCE_WORD)
        ]
        if len(matches) != 1:
            raise AcceptanceFailure(
                "acceptance_vocabulary_identity_invalid"
            )
        return matches[0]

    def _verify_vocabulary(
        self,
        notion: AutomaticVocabularyAcceptanceGuard,
        snapshot: VocabularyWorkspaceSnapshot,
        policy: AutomaticVocabularyAcceptancePolicy,
        artifact: Mapping[str, Any],
    ) -> tuple[VocabularyRecordSnapshot, str]:
        record = self._vocabulary_record(snapshot)
        properties = record.properties
        required_nonempty = (
            "Name",
            "Original Context",
            "Meaning",
            "Professional Category",
            "Source",
            "Source Page ID",
            "First Seen",
            "Review Status",
            "Usage Example",
        )
        if any(not properties.get(name) for name in required_nonempty):
            raise AcceptanceFailure(
                "automatic_vocabulary_properties_incomplete"
            )
        if properties.get("Name") != ACCEPTANCE_WORD:
            raise AcceptanceFailure("exact_word_mismatch")
        if properties.get("Original Context") != ACCEPTANCE_CONTEXT:
            raise AcceptanceFailure("exact_context_mismatch")
        if properties.get("Source") != (
            policy.controlled_podcast_page_id,
        ):
            raise AcceptanceFailure("source_relation_mismatch")

        response = notion.blocks.children.list(
            block_id=record.page_id,
            page_size=100,
        )
        blocks = (
            response.get("results")
            if isinstance(response, Mapping)
            else None
        )
        if not isinstance(blocks, list) or not blocks:
            raise AcceptanceFailure("automatic_vocabulary_body_incomplete")
        actual_structure = [
            (str(block.get("type", "")).strip(), _block_text(block))
            for block in blocks
            if isinstance(block, Mapping)
        ]
        if actual_structure != _expected_body_structure(artifact):
            raise AcceptanceFailure("automatic_vocabulary_body_incomplete")
        return record, _tree_fingerprint(blocks)

    def _verify_occurrence_state(
        self,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> dict[str, Any]:
        try:
            with sqlite3.connect(self.state_path) as connection:
                rows = connection.execute(
                    """
                    SELECT occurrence_fingerprint, exact_text, exact_context,
                           status, published_page_id
                    FROM highlight_occurrences
                    LEFT JOIN vocabulary_processing USING (
                        workspace_fingerprint,
                        target_group_fingerprint,
                        binding_version,
                        occurrence_fingerprint
                    )
                    WHERE page_id = ? AND baseline = 0
                    """,
                    (policy.controlled_podcast_page_id,),
                ).fetchall()
        except Exception:
            raise AcceptanceFailure(
                "occurrence_state_verification_failed"
            ) from None
        if (
            len(rows) != 1
            or len(str(rows[0][0])) != 64
            or rows[0][1] != ACCEPTANCE_WORD
            or rows[0][2] != ACCEPTANCE_CONTEXT
            or rows[0][3] != STATUS_PUBLISHED
            or str(rows[0][4]) != policy.vocabulary_page_id
        ):
            raise AcceptanceFailure(
                "occurrence_state_verification_failed"
            )
        artifact_path = (
            self.artifact_root
            / "outputs"
            / f"{rows[0][0]}.json"
        )
        try:
            payload = json.loads(
                artifact_path.read_text(encoding="utf-8")
            )
            if not isinstance(payload, Mapping):
                raise ValueError
            return validate_automatic_vocabulary_artifact(
                payload,
                exact_word=ACCEPTANCE_WORD,
                exact_context=ACCEPTANCE_CONTEXT,
            )
        except (
            OSError,
            json.JSONDecodeError,
            ValueError,
            AutomaticVocabularyArtifactError,
        ):
            raise AcceptanceFailure(
                "occurrence_artifact_verification_failed"
            ) from None

    def _verify_runtime_logs(
        self,
        policy: AutomaticVocabularyAcceptancePolicy,
    ) -> None:
        try:
            rendered = self.log_path.read_text(encoding="utf-8")
            lines = [
                json.loads(line)
                for line in rendered.splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError):
            raise AcceptanceFailure(
                "runtime_log_verification_failed"
            ) from None
        if len(lines) != 4 or any(
            not isinstance(line, Mapping) for line in lines
        ):
            raise AcceptanceFailure(
                "runtime_log_verification_failed"
            )
        private_values = (
            self.config.token,
            self.config.target_parent_page_id,
            *self.config.data_source_ids.values(),
            policy.controlled_title,
            policy.controlled_url,
            policy.controlled_podcast_page_id,
            policy.vocabulary_page_id,
            ACCEPTANCE_WORD,
            ACCEPTANCE_CONTEXT,
        )
        if any(
            value and value in rendered for value in private_values
        ):
            raise AcceptanceFailure("runtime_log_not_redacted")
        if _NOTION_URL_PATTERN.search(rendered) or (
            _NOTION_ID_PATTERN.search(rendered)
        ):
            raise AcceptanceFailure("runtime_log_not_redacted")

    @staticmethod
    def _assert_non_target_unchanged(
        before: VocabularyWorkspaceSnapshot,
        after: VocabularyWorkspaceSnapshot,
    ) -> None:
        for role in (EXPRESSION_DATABASE, WEEKLY_REVIEW):
            if not _existing_records_unchanged(before, after, role):
                raise AcceptanceFailure("non_target_database_changed")
            if len(before.pages(role)) != len(after.pages(role)):
                raise AcceptanceFailure("non_target_database_changed")
        if not _existing_records_unchanged(
            before,
            after,
            PODCAST_LIBRARY,
        ):
            raise AcceptanceFailure("existing_podcast_changed")
        if not _existing_records_unchanged(
            before,
            after,
            VOCABULARY_DATABASE,
        ):
            raise AcceptanceFailure("existing_vocabulary_changed")

    def _report(
        self,
        *,
        mode: str,
        binding: Any,
        policy: AutomaticVocabularyAcceptancePolicy,
        baseline_verified: bool = False,
        quiet_verified: bool = False,
        exact_verified: bool = False,
        complete_verified: bool = False,
        relation_verified: bool = False,
        fingerprint_verified: bool = False,
        retry_verified: bool = False,
        quiet_writes: int = 0,
        retry_created: int = 0,
        retry_updated: int = 0,
        codex_calls: int = 0,
        logs_redacted: bool = False,
    ) -> AutomaticVocabularyAcceptanceReport:
        counts = dict(policy.counts)
        counts.update(
            {
                "quiet_period_vocabulary_writes": quiet_writes,
                "retry_created": retry_created,
                "retry_updated": retry_updated,
                "codex_calls": codex_calls,
                "user_commands": 0,
            }
        )
        return AutomaticVocabularyAcceptanceReport(
            status="passed",
            mode=mode,
            target_binding_valid=bool(binding.valid),
            baseline_verified=baseline_verified,
            quiet_period_verified=quiet_verified,
            exact_word_verified=exact_verified,
            exact_context_verified=exact_verified,
            properties_complete=complete_verified,
            body_complete=complete_verified,
            source_relation_verified=relation_verified,
            occurrence_fingerprint_verified=fingerprint_verified,
            exact_retry_verified=retry_verified,
            logs_redacted=logs_redacted,
            target_parent_fingerprint=(
                binding.target_parent_fingerprint
            ),
            target_group_fingerprint=(
                binding.target_group_fingerprint
            ),
            counts=counts,
        )

    def dry_run(self) -> AutomaticVocabularyAcceptanceResult:
        policy, _notion, snapshotter, before, binding = self._prepare()
        after = snapshotter.capture()
        if any(
            _snapshot_fingerprints(before, role)
            != _snapshot_fingerprints(after, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("dry_run_changed_workspace")
        report = self._report(
            mode="dry-run",
            binding=binding,
            policy=policy,
            logs_redacted=True,
        )
        return AutomaticVocabularyAcceptanceResult(report=report)

    def run(
        self,
        *,
        confirmation: str,
    ) -> AutomaticVocabularyAcceptanceResult:
        if confirmation != LIVE_CONFIRMATION:
            raise AcceptanceFailure("live_confirmation_missing")
        policy, notion, snapshotter, before, binding = self._prepare()

        baseline_at = self.clock()
        notion.pages.create(
            parent={
                "data_source_id": self.config.podcast_data_source_id
            },
            properties=self._controlled_podcast_properties(
                policy,
                baseline_at.date().isoformat(),
            ),
            children=[self._baseline_block()],
        )
        baseline = self._runtime(notion, at=baseline_at)
        if (
            baseline.status != "BASELINED"
            or baseline.occurrences_seen < 1
            or baseline.created != 0
            or baseline.updated != 0
            or baseline.published != 0
        ):
            raise AcceptanceFailure("first_baseline_invalid")

        notion.blocks.children.append(
            block_id=policy.controlled_podcast_page_id,
            children=[self._highlight_block()],
        )
        quiet = self._runtime(notion, at=self.clock())
        quiet_writes = quiet.created + quiet.updated
        if (
            quiet_writes != 0
            or quiet.published != 0
            or quiet.ready_for_enrichment != 0
        ):
            raise AcceptanceFailure("quiet_period_write_detected")
        after_quiet = snapshotter.capture()
        if len(after_quiet.pages(VOCABULARY_DATABASE)) != len(
            before.pages(VOCABULARY_DATABASE)
        ):
            raise AcceptanceFailure("quiet_period_write_detected")

        self.sleep(float(self.quiet_period_seconds + 1))
        first = self._runtime(notion, at=self.clock())
        if (
            first.status != "PASS"
            or first.created != 1
            or first.updated != 0
            or first.published != 1
            or first.codex_calls != 1
        ):
            raise AcceptanceFailure("first_publish_invalid")
        after_first = snapshotter.capture()
        self._assert_non_target_unchanged(before, after_first)
        if len(after_first.pages(PODCAST_LIBRARY)) != (
            len(before.pages(PODCAST_LIBRARY)) + 1
        ):
            raise AcceptanceFailure("podcast_write_count_invalid")
        if len(after_first.pages(VOCABULARY_DATABASE)) != (
            len(before.pages(VOCABULARY_DATABASE)) + 1
        ):
            raise AcceptanceFailure("vocabulary_write_count_invalid")
        artifact = self._verify_occurrence_state(policy)
        record, first_body_fingerprint = self._verify_vocabulary(
            notion,
            after_first,
            policy,
            artifact,
        )
        policy.vocabulary_page_id = record.page_id

        retry = self._runtime(notion, at=self.clock())
        if (
            retry.created != 0
            or retry.updated != 0
            or retry.published != 0
            or retry.codex_calls != 0
        ):
            raise AcceptanceFailure("exact_retry_invalid")
        after_retry = snapshotter.capture()
        if any(
            _snapshot_fingerprints(after_first, role)
            != _snapshot_fingerprints(after_retry, role)
            for role in WORKSPACE_DATABASE_ORDER
        ):
            raise AcceptanceFailure("exact_retry_changed_workspace")
        _retry_record, retry_body_fingerprint = self._verify_vocabulary(
            notion,
            after_retry,
            policy,
            artifact,
        )
        if retry_body_fingerprint != first_body_fingerprint:
            raise AcceptanceFailure("exact_retry_duplicated_body")

        if any(
            policy.counts[key] != 0
            for key in (
                "vocabulary_updated",
                "expression_writes",
                "weekly_writes",
                "schema_writes",
                "delete_archive",
                "historical_reads",
                "historical_writes",
            )
        ):
            raise AcceptanceFailure("acceptance_write_budget_exceeded")
        self._verify_runtime_logs(policy)
        report = self._report(
            mode="live",
            binding=binding,
            policy=policy,
            baseline_verified=True,
            quiet_verified=True,
            exact_verified=True,
            complete_verified=True,
            relation_verified=True,
            fingerprint_verified=True,
            retry_verified=True,
            quiet_writes=quiet_writes,
            retry_created=retry.created,
            retry_updated=retry.updated,
            codex_calls=first.codex_calls,
            logs_redacted=True,
        )
        return AutomaticVocabularyAcceptanceResult(
            report=report,
            controlled_podcast_page_id=policy.controlled_podcast_page_id,
            vocabulary_page_id=policy.vocabulary_page_id,
        )


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
        "acceptance_vocabulary_identity_exists",
        "acceptance_vocabulary_identity_invalid",
        "acceptance_write_budget_exceeded",
        "automatic_vocabulary_body_incomplete",
        "automatic_vocabulary_identity_invalid",
        "automatic_vocabulary_properties_incomplete",
        "block_operation_blocked",
        "block_update_blocked",
        "controlled_highlight_invalid",
        "controlled_podcast_identity_invalid",
        "controlled_podcast_payload_invalid",
        "database_creation_blocked",
        "database_operation_blocked",
        "data_source_operation_blocked",
        "delete_or_archive_blocked",
        "dry_run_changed_workspace",
        "exact_context_mismatch",
        "exact_retry_changed_workspace",
        "exact_retry_duplicated_body",
        "exact_retry_invalid",
        "exact_word_mismatch",
        "expression_write_blocked",
        "first_baseline_invalid",
        "first_publish_invalid",
        "four_data_sources_not_configured",
        "highlight_write_limit_exceeded",
        "historical_group_read_blocked",
        "historical_group_write_blocked",
        "live_confirmation_missing",
        "non_target_database_changed",
        "occurrence_state_verification_failed",
        "occurrence_artifact_verification_failed",
        "page_create_response_invalid",
        "page_create_shape_invalid",
        "page_operation_blocked",
        "podcast_write_count_invalid",
        "podcast_write_limit_exceeded",
        "quiet_period_write_detected",
        "runtime_log_not_redacted",
        "runtime_log_verification_failed",
        "schema_mutation_blocked",
        "setup_state_not_complete",
        "source_relation_mismatch",
        "vocabulary_update_blocked",
        "vocabulary_write_count_invalid",
        "vocabulary_write_limit_exceeded",
        "weekly_write_blocked",
    }
)


def render_redacted_report(
    report: AutomaticVocabularyAcceptanceReport,
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
    safe_code = code if code in _PUBLIC_FAILURE_CODES else (
        "acceptance_failed"
    )
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
    "ACCEPTANCE_CONTEXT",
    "ACCEPTANCE_WORD",
    "AutomaticVocabularyAcceptanceGuard",
    "AutomaticVocabularyAcceptancePolicy",
    "AutomaticVocabularyAcceptanceReport",
    "AutomaticVocabularyAcceptanceResult",
    "AutomaticVocabularyOwnerAcceptanceRunner",
    "LIVE_CONFIRMATION",
    "load_acceptance_config",
    "render_failure_report",
    "render_redacted_report",
]
