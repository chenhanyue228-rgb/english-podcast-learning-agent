"""Target-scoped SQLite state for read-only vocabulary detection."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator, Optional


STATE_SCHEMA_VERSION = 1
BINDING_VERSION = 1

STATUS_BASELINED = "BASELINED"
STATUS_QUIET_WAIT = "OBSERVED/QUIET_WAIT"
STATUS_READY = "READY_FOR_ENRICHMENT"
STATUS_CANCELLED = "CANCELLED_BEFORE_READY"


class AutomaticVocabularyStateError(RuntimeError):
    """Raised when read-only detector state cannot be used safely."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class TargetNamespace:
    workspace_fingerprint: str
    target_group_fingerprint: str
    binding_version: int = BINDING_VERSION


@dataclass(frozen=True)
class BindingState:
    baseline_completed: bool
    watermark: str
    lease_owner: str
    lease_expires_at: str


@dataclass(frozen=True)
class StoredOccurrence:
    occurrence_fingerprint: str
    location_fingerprint: str
    page_id: str
    status: str
    first_observed_at: str
    last_seen_at: str
    last_changed_at: str
    quiet_eligible_at: str
    baseline: bool


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: str) -> Optional[datetime]:
    cleaned = str(value or "").strip()
    if not cleaned:
        return None
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class AutomaticVocabularyStateStore:
    """Transactional target namespace, observation, and cycle metadata."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=5,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS state_version (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    version INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO state_version(singleton, version)
                    VALUES (1, 1);

                CREATE TABLE IF NOT EXISTS target_bindings (
                    workspace_fingerprint TEXT NOT NULL,
                    target_group_fingerprint TEXT NOT NULL,
                    binding_version INTEGER NOT NULL,
                    baseline_completed INTEGER NOT NULL DEFAULT 0,
                    watermark TEXT NOT NULL DEFAULT '',
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_expires_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (
                        workspace_fingerprint,
                        target_group_fingerprint,
                        binding_version
                    )
                );

                CREATE TABLE IF NOT EXISTS page_observations (
                    workspace_fingerprint TEXT NOT NULL,
                    target_group_fingerprint TEXT NOT NULL,
                    binding_version INTEGER NOT NULL,
                    page_id TEXT NOT NULL,
                    page_fingerprint TEXT NOT NULL,
                    last_edited_time TEXT NOT NULL,
                    last_successful_read TEXT NOT NULL,
                    last_read_outcome TEXT NOT NULL,
                    PRIMARY KEY (
                        workspace_fingerprint,
                        target_group_fingerprint,
                        binding_version,
                        page_id
                    )
                );

                CREATE TABLE IF NOT EXISTS highlight_occurrences (
                    workspace_fingerprint TEXT NOT NULL,
                    target_group_fingerprint TEXT NOT NULL,
                    binding_version INTEGER NOT NULL,
                    occurrence_fingerprint TEXT NOT NULL,
                    location_fingerprint TEXT NOT NULL,
                    page_id TEXT NOT NULL,
                    block_fingerprint TEXT NOT NULL,
                    position_descriptor TEXT NOT NULL,
                    exact_text TEXT NOT NULL,
                    exact_context TEXT NOT NULL,
                    color TEXT NOT NULL,
                    first_observed_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    last_changed_at TEXT NOT NULL,
                    quiet_eligible_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    baseline INTEGER NOT NULL,
                    PRIMARY KEY (
                        workspace_fingerprint,
                        target_group_fingerprint,
                        binding_version,
                        occurrence_fingerprint
                    )
                );
                CREATE INDEX IF NOT EXISTS idx_highlight_location
                    ON highlight_occurrences(
                        workspace_fingerprint,
                        target_group_fingerprint,
                        binding_version,
                        page_id,
                        location_fingerprint
                    );

                CREATE TABLE IF NOT EXISTS detection_cycles (
                    cycle_id TEXT PRIMARY KEY,
                    workspace_fingerprint TEXT NOT NULL,
                    target_group_fingerprint TEXT NOT NULL,
                    binding_version INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    watermark_start TEXT NOT NULL,
                    watermark_end TEXT NOT NULL,
                    pages_read INTEGER NOT NULL,
                    occurrences_seen INTEGER NOT NULL,
                    ready_count INTEGER NOT NULL,
                    error_code TEXT NOT NULL
                );
                COMMIT;
                """
            )
            version = connection.execute(
                "SELECT version FROM state_version WHERE singleton = 1"
            ).fetchone()
            if version is None or int(version["version"]) != STATE_SCHEMA_VERSION:
                raise AutomaticVocabularyStateError(
                    "state_schema_version_unsupported"
                )
        os.chmod(self.path, 0o600)

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _namespace_values(namespace: TargetNamespace) -> tuple[str, str, int]:
        return (
            namespace.workspace_fingerprint,
            namespace.target_group_fingerprint,
            namespace.binding_version,
        )

    def ensure_binding(
        self,
        connection: sqlite3.Connection,
        namespace: TargetNamespace,
        now: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO target_bindings(
                workspace_fingerprint,
                target_group_fingerprint,
                binding_version,
                created_at,
                last_seen_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(
                workspace_fingerprint,
                target_group_fingerprint,
                binding_version
            ) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (*self._namespace_values(namespace), now, now),
        )

    def get_binding(self, namespace: TargetNamespace) -> BindingState:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT baseline_completed, watermark, lease_owner, lease_expires_at
                FROM target_bindings
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                """,
                self._namespace_values(namespace),
            ).fetchone()
        if row is None:
            return BindingState(False, "", "", "")
        return BindingState(
            baseline_completed=bool(row["baseline_completed"]),
            watermark=str(row["watermark"]),
            lease_owner=str(row["lease_owner"]),
            lease_expires_at=str(row["lease_expires_at"]),
        )

    def acquire_lease(
        self,
        namespace: TargetNamespace,
        owner: str,
        now: datetime,
        ttl_seconds: int,
    ) -> None:
        now_text = isoformat_utc(now)
        expiry = isoformat_utc(now + timedelta(seconds=max(1, ttl_seconds)))
        with self.transaction() as connection:
            self.ensure_binding(connection, namespace, now_text)
            row = connection.execute(
                """
                SELECT lease_owner, lease_expires_at
                FROM target_bindings
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                """,
                self._namespace_values(namespace),
            ).fetchone()
            current_owner = str(row["lease_owner"]) if row else ""
            current_expiry = parse_timestamp(str(row["lease_expires_at"])) if row else None
            if current_owner and current_owner != owner and current_expiry and current_expiry > now:
                raise AutomaticVocabularyStateError("cycle_already_running")
            connection.execute(
                """
                UPDATE target_bindings
                SET lease_owner = ?, lease_expires_at = ?, last_seen_at = ?
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                """,
                (owner, expiry, now_text, *self._namespace_values(namespace)),
            )

    def release_lease(self, namespace: TargetNamespace, owner: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                """
                UPDATE target_bindings
                SET lease_owner = '', lease_expires_at = ''
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                  AND lease_owner = ?
                """,
                (*self._namespace_values(namespace), owner),
            )

    def assert_active_lease(
        self,
        connection: sqlite3.Connection,
        namespace: TargetNamespace,
        owner: str,
        now: datetime,
    ) -> None:
        """Atomically prove the current worker still owns an unexpired lease."""
        current_time = now
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        current_time = current_time.astimezone(timezone.utc)
        row = connection.execute(
            """
            SELECT lease_owner, lease_expires_at
            FROM target_bindings
            WHERE workspace_fingerprint = ?
              AND target_group_fingerprint = ?
              AND binding_version = ?
            """,
            self._namespace_values(namespace),
        ).fetchone()
        expires_at = (
            parse_timestamp(str(row["lease_expires_at"]))
            if row is not None
            else None
        )
        if (
            row is None
            or str(row["lease_owner"]) != owner
            or expires_at is None
            or expires_at <= current_time
        ):
            raise AutomaticVocabularyStateError("cycle_lease_lost")

    def occurrences_for_page(
        self,
        connection: sqlite3.Connection,
        namespace: TargetNamespace,
        page_id: str,
    ) -> list[StoredOccurrence]:
        rows = connection.execute(
            """
            SELECT occurrence_fingerprint, location_fingerprint, page_id, status,
                   first_observed_at, last_seen_at, last_changed_at,
                   quiet_eligible_at, baseline
            FROM highlight_occurrences
            WHERE workspace_fingerprint = ?
              AND target_group_fingerprint = ?
              AND binding_version = ?
              AND page_id = ?
            """,
            (*self._namespace_values(namespace), page_id),
        ).fetchall()
        return [
            StoredOccurrence(
                occurrence_fingerprint=str(row["occurrence_fingerprint"]),
                location_fingerprint=str(row["location_fingerprint"]),
                page_id=str(row["page_id"]),
                status=str(row["status"]),
                first_observed_at=str(row["first_observed_at"]),
                last_seen_at=str(row["last_seen_at"]),
                last_changed_at=str(row["last_changed_at"]),
                quiet_eligible_at=str(row["quiet_eligible_at"]),
                baseline=bool(row["baseline"]),
            )
            for row in rows
        ]

    def page_last_edited_time(
        self,
        connection: sqlite3.Connection,
        namespace: TargetNamespace,
        page_id: str,
    ) -> str:
        row = connection.execute(
            """
            SELECT last_edited_time
            FROM page_observations
            WHERE workspace_fingerprint = ?
              AND target_group_fingerprint = ?
              AND binding_version = ?
              AND page_id = ?
            """,
            (*self._namespace_values(namespace), page_id),
        ).fetchone()
        return str(row["last_edited_time"]) if row else ""

    def list_occurrence_statuses(
        self,
        namespace: TargetNamespace,
    ) -> list[StoredOccurrence]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT occurrence_fingerprint, location_fingerprint, page_id,
                       status, first_observed_at, last_seen_at, last_changed_at,
                       quiet_eligible_at, baseline
                FROM highlight_occurrences
                WHERE workspace_fingerprint = ?
                  AND target_group_fingerprint = ?
                  AND binding_version = ?
                ORDER BY occurrence_fingerprint
                """,
                self._namespace_values(namespace),
            ).fetchall()
        return [
            StoredOccurrence(
                occurrence_fingerprint=str(row["occurrence_fingerprint"]),
                location_fingerprint=str(row["location_fingerprint"]),
                page_id=str(row["page_id"]),
                status=str(row["status"]),
                first_observed_at=str(row["first_observed_at"]),
                last_seen_at=str(row["last_seen_at"]),
                last_changed_at=str(row["last_changed_at"]),
                quiet_eligible_at=str(row["quiet_eligible_at"]),
                baseline=bool(row["baseline"]),
            )
            for row in rows
        ]

    def pending_pages(
        self,
        namespace: TargetNamespace,
    ) -> list[tuple[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT p.page_id, p.last_edited_time
                FROM page_observations AS p
                JOIN highlight_occurrences AS h
                  ON h.workspace_fingerprint = p.workspace_fingerprint
                 AND h.target_group_fingerprint = p.target_group_fingerprint
                 AND h.binding_version = p.binding_version
                 AND h.page_id = p.page_id
                WHERE p.workspace_fingerprint = ?
                  AND p.target_group_fingerprint = ?
                  AND p.binding_version = ?
                  AND h.status = ?
                ORDER BY p.page_id
                """,
                (*self._namespace_values(namespace), STATUS_QUIET_WAIT),
            ).fetchall()
        return [
            (str(row["page_id"]), str(row["last_edited_time"]))
            for row in rows
        ]
