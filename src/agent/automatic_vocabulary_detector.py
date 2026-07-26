"""Bounded, read-only detection of new exact pink-highlight occurrences."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional, Sequence

from src.agent.automatic_vocabulary_state import (
    STATUS_BASELINED,
    STATUS_CANCELLED,
    STATUS_QUIET_WAIT,
    STATUS_READY,
    AutomaticVocabularyStateError,
    AutomaticVocabularyStateStore,
    TargetNamespace,
    isoformat_utc,
    parse_timestamp,
    utc_now,
)
from src.agent.notion_page_scanner import (
    DEFAULT_WATERMARK_OVERLAP_SECONDS,
    ChangedPodcastPage,
    scan_podcast_pages_with_overlap,
)
from src.notion.config import NotionConfig, load_notion_config
from src.notion.highlight_reader import (
    PinkHighlightOccurrence,
    read_pink_highlight_occurrences,
)
from src.notion.pagination import (
    NOTION_PAGINATION_INVALID,
    NotionPaginationError,
)
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
)
from src.notion.target_binding import (
    NotionTargetBindingError,
    NotionTargetBindingResult,
    ensure_notion_page_belongs_to_role,
    normalize_notion_id,
    validate_notion_target_binding,
)
from src.notion.uploader import create_notion_client


FINGERPRINT_VERSION = 1
DEFAULT_QUIET_PERIOD_SECONDS = 90
DEFAULT_LEASE_SECONDS = 300
DEFAULT_STATE_DIRECTORY = Path("data/automatic_vocabulary")

ERROR_ARTIFACT_OUTSIDE_ALLOWLIST = "local_artifact_outside_allowlist"
ERROR_DETECTION_CYCLE_FAILED = "read_only_detection_failed"
ERROR_PENDING_PAGE_MEMBERSHIP = "pending_page_membership_invalid"


class AutomaticVocabularyDetectionError(RuntimeError):
    """A fixed-code, redacted failure from the read-only detector."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "SAFE_STOP",
            "error_code": self.code,
            "notion_writes": 0,
            "vocabulary_publisher_calls": 0,
        }


@dataclass(frozen=True)
class OccurrenceIdentity:
    occurrence_fingerprint: str
    location_fingerprint: str
    page_fingerprint: str
    block_fingerprint: str


@dataclass(frozen=True)
class ReadOnlyDetectionReport:
    status: str
    cycle_fingerprint: str
    workspace_fingerprint: str
    target_group_fingerprint: str
    pages_read: int
    occurrences_seen: int
    baselined: int
    quiet_wait: int
    ready_for_enrichment: int
    cancelled_before_ready: int
    ready_occurrence_fingerprints: tuple[str, ...]
    target_binding_valid: bool
    local_artifact_changes_allowed: bool
    notion_writes: int = 0
    vocabulary_publisher_calls: int = 0
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "cycle_fingerprint": self.cycle_fingerprint,
            "workspace_fingerprint": self.workspace_fingerprint,
            "target_group_fingerprint": self.target_group_fingerprint,
            "pages_read": self.pages_read,
            "occurrences_seen": self.occurrences_seen,
            "baselined": self.baselined,
            "quiet_wait": self.quiet_wait,
            "ready_for_enrichment": self.ready_for_enrichment,
            "cancelled_before_ready": self.cancelled_before_ready,
            "ready_occurrence_fingerprints": list(
                self.ready_occurrence_fingerprints
            ),
            "target_binding_valid": self.target_binding_valid,
            "local_artifact_changes_allowed": (
                self.local_artifact_changes_allowed
            ),
            "notion_writes": 0,
            "vocabulary_publisher_calls": 0,
            "error_code": self.error_code,
        }


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _short_fingerprint(value: str) -> str:
    return value[:12]


def _full_workspace_fingerprint(config: NotionConfig) -> str:
    return _sha256(normalize_notion_id(config.target_parent_page_id))


def _full_target_group_fingerprint(config: NotionConfig) -> str:
    roles = (
        (PODCAST_LIBRARY, config.podcast_database_id),
        (EXPRESSION_DATABASE, config.expression_database_id),
        (VOCABULARY_DATABASE, config.vocabulary_database_id),
        (WEEKLY_REVIEW, config.weekly_database_id),
    )
    material = "|".join(
        f"{role}:{normalize_notion_id(identifier)}"
        for role, identifier in roles
    )
    return _sha256(material)


def target_namespace(config: NotionConfig) -> TargetNamespace:
    return TargetNamespace(
        workspace_fingerprint=_full_workspace_fingerprint(config),
        target_group_fingerprint=_full_target_group_fingerprint(config),
    )


def default_state_path(namespace: TargetNamespace) -> Path:
    return DEFAULT_STATE_DIRECTORY / (
        f"highlight_detector_{_short_fingerprint(namespace.target_group_fingerprint)}.sqlite3"
    )


def allowed_state_artifacts(state_path: Path) -> frozenset[Path]:
    resolved = state_path.resolve()
    return frozenset(
        {
            resolved,
            Path(str(resolved) + "-journal"),
            Path(str(resolved) + "-shm"),
            Path(str(resolved) + "-wal"),
        }
    )


def validate_local_artifact_changes(
    changed_paths: Iterable[Path],
    state_path: Path,
) -> None:
    allowed = allowed_state_artifacts(state_path)
    unexpected = {
        Path(path).resolve()
        for path in changed_paths
        if Path(path).resolve() not in allowed
    }
    if unexpected:
        raise AutomaticVocabularyDetectionError(
            ERROR_ARTIFACT_OUTSIDE_ALLOWLIST
        )


def exact_occurrence_identity(
    occurrence: PinkHighlightOccurrence,
    namespace: TargetNamespace,
    *,
    fingerprint_version: int = FINGERPRINT_VERSION,
) -> OccurrenceIdentity:
    page_fingerprint = _sha256(
        f"page-v{fingerprint_version}:{occurrence.page_id}"
    )
    block_fingerprint = _sha256(
        f"block-v{fingerprint_version}:{occurrence.block_id}"
    )
    location_payload = {
        "fingerprint_version": fingerprint_version,
        "workspace_fingerprint": namespace.workspace_fingerprint,
        "target_group_fingerprint": namespace.target_group_fingerprint,
        "page_id": occurrence.page_id,
        "block_id": occurrence.block_id,
        "position": occurrence.position_descriptor,
    }
    location_fingerprint = _sha256(
        json.dumps(
            location_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    occurrence_payload = {
        **location_payload,
        "text": occurrence.text,
        "context": occurrence.context,
        "color": occurrence.color,
    }
    occurrence_fingerprint = _sha256(
        json.dumps(
            occurrence_payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return OccurrenceIdentity(
        occurrence_fingerprint=occurrence_fingerprint,
        location_fingerprint=location_fingerprint,
        page_fingerprint=page_fingerprint,
        block_fingerprint=block_fingerprint,
    )


def _latest_watermark(
    current: str,
    pages: Sequence[ChangedPodcastPage],
) -> str:
    latest = parse_timestamp(current)
    latest_text = current
    for page in pages:
        candidate = parse_timestamp(page.last_edited_time)
        if candidate is not None and (
            latest is None or candidate > latest
        ):
            latest = candidate
            latest_text = isoformat_utc(candidate)
    return latest_text


def _prove_pending_page_membership(
    notion: Any,
    page_id: str,
    config: NotionConfig,
) -> None:
    ensure_notion_page_belongs_to_role(
        notion,
        page_id,
        PODCAST_LIBRARY,
        config=config,
        force_refresh=True,
    )


def _insert_or_restart_occurrence(
    connection: sqlite3.Connection,
    namespace: TargetNamespace,
    occurrence: PinkHighlightOccurrence,
    identity: OccurrenceIdentity,
    now_text: str,
    quiet_eligible_at: str,
    *,
    baseline: bool,
) -> None:
    status = STATUS_BASELINED if baseline else STATUS_QUIET_WAIT
    connection.execute(
        """
        INSERT INTO highlight_occurrences(
            workspace_fingerprint,
            target_group_fingerprint,
            binding_version,
            occurrence_fingerprint,
            location_fingerprint,
            page_id,
            block_fingerprint,
            position_descriptor,
            exact_text,
            exact_context,
            color,
            first_observed_at,
            last_seen_at,
            last_changed_at,
            quiet_eligible_at,
            status,
            baseline
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            workspace_fingerprint,
            target_group_fingerprint,
            binding_version,
            occurrence_fingerprint
        ) DO UPDATE SET
            location_fingerprint = excluded.location_fingerprint,
            page_id = excluded.page_id,
            block_fingerprint = excluded.block_fingerprint,
            position_descriptor = excluded.position_descriptor,
            exact_text = excluded.exact_text,
            exact_context = excluded.exact_context,
            color = excluded.color,
            first_observed_at = excluded.first_observed_at,
            last_seen_at = excluded.last_seen_at,
            last_changed_at = excluded.last_changed_at,
            quiet_eligible_at = excluded.quiet_eligible_at,
            status = excluded.status,
            baseline = excluded.baseline
        """,
        (
            namespace.workspace_fingerprint,
            namespace.target_group_fingerprint,
            namespace.binding_version,
            identity.occurrence_fingerprint,
            identity.location_fingerprint,
            occurrence.page_id,
            identity.block_fingerprint,
            occurrence.position_descriptor,
            occurrence.text,
            occurrence.context,
            occurrence.color,
            now_text,
            now_text,
            now_text,
            quiet_eligible_at,
            status,
            int(baseline),
        ),
    )


def _observe_page(
    connection: sqlite3.Connection,
    *,
    store: AutomaticVocabularyStateStore,
    namespace: TargetNamespace,
    page: ChangedPodcastPage,
    occurrences: Sequence[PinkHighlightOccurrence],
    baseline: bool,
    now: datetime,
    quiet_period_seconds: int,
) -> tuple[int, int, int, list[str]]:
    now_text = isoformat_utc(now)
    quiet_eligible_at = isoformat_utc(
        now + timedelta(seconds=max(0, quiet_period_seconds))
    )
    existing = store.occurrences_for_page(
        connection,
        namespace,
        page.page_id,
    )
    previous_page_edit = store.page_last_edited_time(
        connection,
        namespace,
        page.page_id,
    )
    page_edit_changed = bool(
        previous_page_edit
        and page.last_edited_time
        and previous_page_edit != page.last_edited_time
    )
    existing_by_fingerprint = {
        item.occurrence_fingerprint: item for item in existing
    }
    current_fingerprints: set[str] = set()
    quiet_wait = 0
    ready = 0
    cancelled = 0
    ready_fingerprints: list[str] = []
    cancelled_fingerprints: set[str] = set()

    for occurrence in occurrences:
        identity = exact_occurrence_identity(occurrence, namespace)
        current_fingerprints.add(identity.occurrence_fingerprint)
        for prior in existing:
            if (
                prior.location_fingerprint == identity.location_fingerprint
                and prior.occurrence_fingerprint
                != identity.occurrence_fingerprint
                and prior.status != STATUS_CANCELLED
            ):
                connection.execute(
                    """
                    UPDATE highlight_occurrences
                    SET status = ?, last_seen_at = ?
                    WHERE workspace_fingerprint = ?
                      AND target_group_fingerprint = ?
                      AND binding_version = ?
                      AND occurrence_fingerprint = ?
                    """,
                    (
                        STATUS_CANCELLED,
                        now_text,
                        namespace.workspace_fingerprint,
                        namespace.target_group_fingerprint,
                        namespace.binding_version,
                        prior.occurrence_fingerprint,
                    ),
                )
                cancelled += 1
                cancelled_fingerprints.add(
                    prior.occurrence_fingerprint
                )

        prior = existing_by_fingerprint.get(
            identity.occurrence_fingerprint
        )
        if prior is None or prior.status == STATUS_CANCELLED:
            _insert_or_restart_occurrence(
                connection,
                namespace,
                occurrence,
                identity,
                now_text,
                quiet_eligible_at,
                baseline=baseline,
            )
            if not baseline:
                quiet_wait += 1
            continue

        next_status = prior.status
        effective_eligible_at = prior.quiet_eligible_at
        effective_last_changed_at = prior.last_changed_at
        if prior.status == STATUS_QUIET_WAIT:
            if page_edit_changed:
                effective_eligible_at = quiet_eligible_at
                effective_last_changed_at = now_text
            eligible_at = parse_timestamp(effective_eligible_at)
            if eligible_at is not None and now >= eligible_at:
                next_status = STATUS_READY
                ready += 1
                ready_fingerprints.append(
                    identity.occurrence_fingerprint
                )
            else:
                quiet_wait += 1
        elif prior.status == STATUS_READY:
            ready += 1
            ready_fingerprints.append(identity.occurrence_fingerprint)

        connection.execute(
            """
            UPDATE highlight_occurrences
            SET last_seen_at = ?,
                last_changed_at = ?,
                quiet_eligible_at = ?,
                status = ?
            WHERE workspace_fingerprint = ?
              AND target_group_fingerprint = ?
              AND binding_version = ?
              AND occurrence_fingerprint = ?
            """,
            (
                now_text,
                effective_last_changed_at,
                effective_eligible_at,
                next_status,
                namespace.workspace_fingerprint,
                namespace.target_group_fingerprint,
                namespace.binding_version,
                identity.occurrence_fingerprint,
            ),
        )

    for prior in existing:
        if (
            prior.occurrence_fingerprint not in current_fingerprints
            and prior.occurrence_fingerprint
            not in cancelled_fingerprints
            and prior.status in {STATUS_BASELINED, STATUS_QUIET_WAIT}
        ):
            connection.execute(
                """
                UPDATE highlight_occurrences
                SET status = ?, last_seen_at = ?
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                  AND occurrence_fingerprint = ?
                """,
                (
                    STATUS_CANCELLED,
                    now_text,
                    namespace.workspace_fingerprint,
                    namespace.target_group_fingerprint,
                    namespace.binding_version,
                    prior.occurrence_fingerprint,
                ),
            )
            cancelled += 1
            cancelled_fingerprints.add(prior.occurrence_fingerprint)

    page_fingerprint = _sha256(
        f"page-v{FINGERPRINT_VERSION}:{page.page_id}"
    )
    connection.execute(
        """
        INSERT INTO page_observations(
            workspace_fingerprint,
            target_group_fingerprint,
            binding_version,
            page_id,
            page_fingerprint,
            last_edited_time,
            last_successful_read,
            last_read_outcome
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(
            workspace_fingerprint,
            target_group_fingerprint,
            binding_version,
            page_id
        ) DO UPDATE SET
            page_fingerprint = excluded.page_fingerprint,
            last_edited_time = excluded.last_edited_time,
            last_successful_read = excluded.last_successful_read,
            last_read_outcome = excluded.last_read_outcome
        """,
        (
            namespace.workspace_fingerprint,
            namespace.target_group_fingerprint,
            namespace.binding_version,
            page.page_id,
            page_fingerprint,
            page.last_edited_time,
            now_text,
            "success",
        ),
    )
    return quiet_wait, ready, cancelled, ready_fingerprints


def run_read_only_detection_cycle(
    *,
    notion: Any = None,
    config: Optional[NotionConfig] = None,
    state_path: Optional[Path] = None,
    now: Optional[datetime] = None,
    quiet_period_seconds: int = DEFAULT_QUIET_PERIOD_SECONDS,
    overlap_seconds: int = DEFAULT_WATERMARK_OVERLAP_SECONDS,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    binding_validator: Callable[
        [Any, NotionConfig], NotionTargetBindingResult
    ] = validate_notion_target_binding,
    pending_page_validator: Callable[
        [Any, str, NotionConfig], None
    ] = _prove_pending_page_membership,
    commit_clock: Callable[[], datetime] = utc_now,
    before_commit: Optional[
        Callable[
            [
                AutomaticVocabularyStateStore,
                TargetNamespace,
                str,
            ],
            None,
        ]
    ] = None,
    local_artifact_changes: Iterable[Path] = (),
) -> ReadOnlyDetectionReport:
    """Run one finite read-only cycle and stop at readiness."""
    config = config or load_notion_config()
    notion = notion or create_notion_client(config.token)
    binding = binding_validator(notion, config)
    if not binding.valid:
        raise AutomaticVocabularyDetectionError(
            "target_binding_invalid"
        )

    namespace = target_namespace(config)
    resolved_state_path = state_path or default_state_path(namespace)
    validate_local_artifact_changes(
        local_artifact_changes,
        resolved_state_path,
    )
    store = AutomaticVocabularyStateStore(resolved_state_path)
    store.initialize()

    cycle_now = now or datetime.now(timezone.utc)
    if cycle_now.tzinfo is None:
        cycle_now = cycle_now.replace(tzinfo=timezone.utc)
    cycle_now = cycle_now.astimezone(timezone.utc)
    cycle_id = uuid.uuid4().hex
    owner = f"cycle-{cycle_id}"
    store.acquire_lease(
        namespace,
        owner,
        cycle_now,
        ttl_seconds=lease_seconds,
    )

    try:
        binding_state = store.get_binding(namespace)
        pages = scan_podcast_pages_with_overlap(
            notion=notion,
            podcast_database_id=config.podcast_database_id,
            watermark=binding_state.watermark,
            overlap_seconds=overlap_seconds,
        )
        page_ids = {page.page_id for page in pages}
        for pending_page_id, last_edited_time in store.pending_pages(
            namespace
        ):
            if pending_page_id not in page_ids:
                try:
                    pending_page_validator(
                        notion,
                        pending_page_id,
                        config,
                    )
                except NotionTargetBindingError:
                    raise AutomaticVocabularyDetectionError(
                        ERROR_PENDING_PAGE_MEMBERSHIP
                    ) from None
                pages.append(
                    ChangedPodcastPage(
                        page_id=pending_page_id,
                        last_edited_time=last_edited_time,
                    )
                )
                page_ids.add(pending_page_id)
        page_occurrences = [
            (
                page,
                read_pink_highlight_occurrences(
                    page_id=page.page_id,
                    notion=notion,
                ),
            )
            for page in pages
        ]
        baseline = not binding_state.baseline_completed
        watermark_end = _latest_watermark(
            binding_state.watermark,
            pages,
        )
        baselined = 0
        quiet_wait = 0
        ready = 0
        cancelled = 0
        ready_fingerprints: list[str] = []
        occurrence_count = sum(
            len(occurrences)
            for _, occurrences in page_occurrences
        )
        now_text = isoformat_utc(cycle_now)

        if before_commit is not None:
            before_commit(store, namespace, owner)
        commit_now = commit_clock()
        if commit_now.tzinfo is None:
            commit_now = commit_now.replace(tzinfo=timezone.utc)
        commit_now = commit_now.astimezone(timezone.utc)
        commit_now_text = isoformat_utc(commit_now)
        with store.transaction() as connection:
            store.assert_active_lease(
                connection,
                namespace,
                owner,
                commit_now,
            )
            store.ensure_binding(
                connection,
                namespace,
                commit_now_text,
            )
            for page, occurrences in page_occurrences:
                if baseline:
                    baselined += len(occurrences)
                (
                    page_quiet,
                    page_ready,
                    page_cancelled,
                    page_ready_fingerprints,
                ) = _observe_page(
                    connection,
                    store=store,
                    namespace=namespace,
                    page=page,
                    occurrences=occurrences,
                    baseline=baseline,
                    now=cycle_now,
                    quiet_period_seconds=quiet_period_seconds,
                )
                quiet_wait += page_quiet
                ready += page_ready
                cancelled += page_cancelled
                ready_fingerprints.extend(
                    page_ready_fingerprints
                )

            connection.execute(
                """
                UPDATE target_bindings
                SET baseline_completed = 1,
                    watermark = ?,
                    last_seen_at = ?
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                """,
                (
                    watermark_end,
                    commit_now_text,
                    namespace.workspace_fingerprint,
                    namespace.target_group_fingerprint,
                    namespace.binding_version,
                ),
            )
            connection.execute(
                """
                INSERT INTO detection_cycles(
                    cycle_id,
                    workspace_fingerprint,
                    target_group_fingerprint,
                    binding_version,
                    started_at,
                    completed_at,
                    status,
                    watermark_start,
                    watermark_end,
                    pages_read,
                    occurrences_seen,
                    ready_count,
                    error_code
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
                """,
                (
                    cycle_id,
                    namespace.workspace_fingerprint,
                    namespace.target_group_fingerprint,
                    namespace.binding_version,
                    now_text,
                    commit_now_text,
                    (
                        STATUS_BASELINED
                        if baseline
                        else (
                            STATUS_READY
                            if ready
                            else STATUS_QUIET_WAIT
                        )
                    ),
                    binding_state.watermark,
                    watermark_end,
                    len(pages),
                    occurrence_count,
                    ready,
                ),
            )
    except AutomaticVocabularyDetectionError:
        raise
    except NotionPaginationError:
        raise AutomaticVocabularyDetectionError(
            NOTION_PAGINATION_INVALID
        ) from None
    except AutomaticVocabularyStateError as exc:
        raise AutomaticVocabularyDetectionError(exc.code) from None
    except Exception:
        raise AutomaticVocabularyDetectionError(
            ERROR_DETECTION_CYCLE_FAILED
        ) from None
    finally:
        store.release_lease(namespace, owner)

    status = (
        STATUS_BASELINED
        if baseline
        else (STATUS_READY if ready else STATUS_QUIET_WAIT)
    )
    return ReadOnlyDetectionReport(
        status=status,
        cycle_fingerprint=_short_fingerprint(_sha256(cycle_id)),
        workspace_fingerprint=_short_fingerprint(
            namespace.workspace_fingerprint
        ),
        target_group_fingerprint=_short_fingerprint(
            namespace.target_group_fingerprint
        ),
        pages_read=len(pages),
        occurrences_seen=occurrence_count,
        baselined=baselined,
        quiet_wait=quiet_wait,
        ready_for_enrichment=ready,
        cancelled_before_ready=cancelled,
        ready_occurrence_fingerprints=tuple(
            _short_fingerprint(value)
            for value in sorted(set(ready_fingerprints))
        ),
        target_binding_valid=True,
        local_artifact_changes_allowed=True,
    )
