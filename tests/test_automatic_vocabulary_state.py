from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.agent.automatic_vocabulary_state import (
    STATUS_ENRICHING,
    STATUS_PUBLISHED,
    STATUS_PUBLISHING,
    STATUS_READY,
    STATUS_RETRYABLE_FAILURE,
    STATUS_VALIDATED,
    AutomaticVocabularyStateError,
    AutomaticVocabularyStateStore,
    TargetNamespace,
)


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def namespace(group: str = "group-a") -> TargetNamespace:
    return TargetNamespace(
        workspace_fingerprint="workspace-a",
        target_group_fingerprint=group,
    )


def test_initialize_creates_versioned_sqlite_tables(tmp_path) -> None:
    path = tmp_path / "detector.sqlite3"
    store = AutomaticVocabularyStateStore(path)

    store.initialize()

    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        version = connection.execute(
            "SELECT version FROM state_version WHERE singleton = 1"
        ).fetchone()[0]
    assert {
        "state_version",
        "target_bindings",
        "page_observations",
        "highlight_occurrences",
        "vocabulary_processing",
        "detection_cycles",
    }.issubset(tables)
    assert version == 1


def test_state_file_permissions_are_owner_only(tmp_path) -> None:
    path = tmp_path / "detector.sqlite3"

    AutomaticVocabularyStateStore(path).initialize()

    assert os.stat(path).st_mode & 0o777 == 0o600


def test_new_namespace_starts_without_baseline_or_watermark(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()

    state = store.get_binding(namespace())

    assert state.baseline_completed is False
    assert state.watermark == ""


def test_target_groups_have_isolated_binding_state(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    store.acquire_lease(namespace("group-a"), "owner-a", NOW, 60)
    store.release_lease(namespace("group-a"), "owner-a")

    assert store.get_binding(namespace("group-a")) is not None
    assert store.get_binding(namespace("group-b")).baseline_completed is False
    assert store.get_binding(namespace("group-b")).watermark == ""


def test_active_lease_blocks_overlapping_cycle(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    store.acquire_lease(namespace(), "owner-a", NOW, 60)

    with pytest.raises(AutomaticVocabularyStateError) as raised:
        store.acquire_lease(namespace(), "owner-b", NOW, 60)

    assert raised.value.code == "cycle_already_running"


def test_expired_lease_can_be_reclaimed(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    store.acquire_lease(namespace(), "owner-a", NOW, 1)

    store.acquire_lease(
        namespace(),
        "owner-b",
        NOW + timedelta(seconds=2),
        60,
    )

    assert store.get_binding(namespace()).lease_owner == "owner-b"


def test_release_lease_only_releases_matching_owner(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    store.acquire_lease(namespace(), "owner-a", NOW, 60)

    store.release_lease(namespace(), "owner-b")
    assert store.get_binding(namespace()).lease_owner == "owner-a"

    store.release_lease(namespace(), "owner-a")
    assert store.get_binding(namespace()).lease_owner == ""


def test_transaction_rolls_back_partial_state_on_failure(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()

    with pytest.raises(RuntimeError):
        with store.transaction() as connection:
            store.ensure_binding(
                connection,
                namespace(),
                "2026-07-26T08:00:00Z",
            )
            connection.execute(
                """
                UPDATE target_bindings
                SET watermark = 'should-not-commit'
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                """,
                (
                    namespace().workspace_fingerprint,
                    namespace().target_group_fingerprint,
                    namespace().binding_version,
                ),
            )
            raise RuntimeError("simulated")

    assert store.get_binding(namespace()).watermark == ""


def test_initialize_is_idempotent(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")

    store.initialize()
    store.initialize()

    with sqlite3.connect(store.path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM state_version"
        ).fetchone()[0] == 1


def test_unknown_state_schema_version_fails_closed(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE state_version SET version = 99 WHERE singleton = 1"
        )

    with pytest.raises(AutomaticVocabularyStateError) as raised:
        store.initialize()

    assert raised.value.code == "state_schema_version_unsupported"


def _insert_ready_occurrence(
    store: AutomaticVocabularyStateStore,
    *,
    fingerprint: str = "occurrence-a",
) -> None:
    with sqlite3.connect(store.path) as connection:
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
            """,
            (
                namespace().workspace_fingerprint,
                namespace().target_group_fingerprint,
                namespace().binding_version,
                fingerprint,
                f"location-{fingerprint}",
                "podcast-page",
                "block",
                "rich_text:0",
                "assumption",
                "We should question that assumption.",
                "pink_background",
                "2026-07-26T08:00:00Z",
                "2026-07-26T08:00:00Z",
                "2026-07-26T08:00:00Z",
                "2026-07-26T08:01:30Z",
                STATUS_READY,
                0,
            ),
        )


def test_processing_state_machine_persists_and_excludes_published(
    tmp_path,
) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    _insert_ready_occurrence(store)
    store.acquire_lease(namespace(), "processor", NOW, 60)

    candidate = store.list_processing_candidates(namespace())[0]
    assert candidate.status == STATUS_READY
    assert candidate.exact_text == "assumption"

    enriching = store.transition_processing(
        namespace(),
        candidate.occurrence_fingerprint,
        owner="processor",
        now=NOW,
        expected_statuses=(STATUS_READY,),
        new_status=STATUS_ENRICHING,
        increment_attempt=True,
    )
    assert enriching.status == STATUS_ENRICHING
    assert enriching.attempts == 1

    validated = store.transition_processing(
        namespace(),
        candidate.occurrence_fingerprint,
        owner="processor",
        now=NOW,
        expected_statuses=(STATUS_ENRICHING,),
        new_status=STATUS_VALIDATED,
        artifact_digest="artifact-digest",
    )
    assert validated.artifact_digest == "artifact-digest"

    store.transition_processing(
        namespace(),
        candidate.occurrence_fingerprint,
        owner="processor",
        now=NOW,
        expected_statuses=(STATUS_VALIDATED,),
        new_status=STATUS_PUBLISHING,
    )
    published = store.transition_processing(
        namespace(),
        candidate.occurrence_fingerprint,
        owner="processor",
        now=NOW,
        expected_statuses=(STATUS_PUBLISHING,),
        new_status=STATUS_PUBLISHED,
        published_page_id="vocabulary-page",
    )

    assert published.status == STATUS_PUBLISHED
    assert published.published_page_id == "vocabulary-page"
    assert store.list_processing_candidates(namespace()) == []


def test_retryable_failure_is_processable_after_restart(tmp_path) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    _insert_ready_occurrence(store)
    store.acquire_lease(namespace(), "processor", NOW, 60)

    failed = store.transition_processing(
        namespace(),
        "occurrence-a",
        owner="processor",
        now=NOW,
        expected_statuses=(STATUS_READY,),
        new_status=STATUS_RETRYABLE_FAILURE,
        error_code="codex_timeout",
    )

    assert failed.last_error_code == "codex_timeout"
    resumed = AutomaticVocabularyStateStore(store.path)
    resumed.initialize()
    assert resumed.list_processing_candidates(namespace())[0].status == (
        STATUS_RETRYABLE_FAILURE
    )


def test_processing_transition_requires_active_matching_lease(
    tmp_path,
) -> None:
    store = AutomaticVocabularyStateStore(tmp_path / "state.sqlite3")
    store.initialize()
    _insert_ready_occurrence(store)
    store.acquire_lease(namespace(), "processor-a", NOW, 60)

    with pytest.raises(AutomaticVocabularyStateError) as raised:
        store.transition_processing(
            namespace(),
            "occurrence-a",
            owner="processor-b",
            now=NOW,
            expected_statuses=(STATUS_READY,),
            new_status=STATUS_ENRICHING,
        )

    assert raised.value.code == "cycle_lease_lost"
