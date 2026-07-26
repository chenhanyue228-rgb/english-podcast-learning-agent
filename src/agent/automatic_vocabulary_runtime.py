"""One-shot automatic vocabulary runtime with overlap protection."""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional

from src.agent.automatic_vocabulary_detector import (
    AutomaticVocabularyDetectionError,
    default_state_path,
    run_read_only_detection_cycle,
    target_namespace,
)
from src.agent.automatic_vocabulary_processor import (
    AutomaticVocabularyProcessingError,
    run_automatic_vocabulary_processing_cycle,
)
from src.agent.automatic_vocabulary_state import AutomaticVocabularyStateError
from src.notion.config import NotionConfig, load_notion_config
from src.notion.uploader import create_notion_client


DEFAULT_RUNTIME_LOG_PATH = Path(
    "logs/automatic_vocabulary/runtime.jsonl"
)
DEFAULT_PROCESS_LOCK_SUFFIX = ".worker.lock"


class AutomaticVocabularyRuntimeError(RuntimeError):
    """A redacted runtime failure identified by a stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AutomaticVocabularyProcessBusy(AutomaticVocabularyRuntimeError):
    """Raised when another bounded worker owns the process lock."""


@dataclass(frozen=True)
class AutomaticVocabularyRuntimeReport:
    """Public one-shot report containing no learning content or raw IDs."""

    status: str
    cycle_fingerprint: str
    detection_status: str
    processing_status: str
    pages_read: int
    occurrences_seen: int
    ready_for_enrichment: int
    candidates: int
    enriched: int
    published: int
    created: int
    updated: int
    codex_calls: int
    vocabulary_publisher_calls: int
    retryable_failures: int
    target_binding_valid: bool
    process_lock_acquired: bool
    historical_group_reads: int
    historical_group_writes: int
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Detector = Callable[..., Any]
Processor = Callable[..., Any]


def default_process_lock_path(state_path: Path) -> Path:
    return Path(f"{state_path}{DEFAULT_PROCESS_LOCK_SUFFIX}")


def _private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)


@contextmanager
def automatic_vocabulary_process_lock(path: Path) -> Iterator[None]:
    """Acquire one non-blocking OS lock for the complete bounded cycle."""
    resolved = Path(path)
    _private_parent(resolved)
    descriptor = os.open(resolved, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(resolved, 0o600)
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            raise AutomaticVocabularyProcessBusy(
                "automatic_vocabulary_cycle_overlap"
            ) from None
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def append_redacted_runtime_log(
    report: AutomaticVocabularyRuntimeReport,
    path: Path = DEFAULT_RUNTIME_LOG_PATH,
) -> None:
    """Append one structured report whose schema excludes private values."""
    resolved = Path(path)
    _private_parent(resolved)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                report.to_dict(),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        handle.write("\n")
    os.chmod(resolved, 0o600)


def _cycle_fingerprint(value: Any) -> str:
    candidate = str(value or "")
    return candidate[:12] if candidate else ""


def _empty_report(
    *,
    status: str,
    process_lock_acquired: bool,
    error_code: str = "",
) -> AutomaticVocabularyRuntimeReport:
    return AutomaticVocabularyRuntimeReport(
        status=status,
        cycle_fingerprint="",
        detection_status="NOT_RUN",
        processing_status="NOT_RUN",
        pages_read=0,
        occurrences_seen=0,
        ready_for_enrichment=0,
        candidates=0,
        enriched=0,
        published=0,
        created=0,
        updated=0,
        codex_calls=0,
        vocabulary_publisher_calls=0,
        retryable_failures=0,
        target_binding_valid=False,
        process_lock_acquired=process_lock_acquired,
        historical_group_reads=0,
        historical_group_writes=0,
        error_code=error_code,
    )


def _runtime_status(detection: Any, processing: Any) -> str:
    if str(processing.status) == "SAFE_STOP":
        return "SAFE_STOP"
    if str(processing.status) == "PARTIAL":
        return "PARTIAL"
    if int(processing.published) > 0:
        return "PASS"
    if str(detection.status) == "BASELINED":
        return "BASELINED"
    if int(detection.ready_for_enrichment) > 0:
        return "READY_NO_WORK"
    return "NO_WORK"


def _error_code(exc: BaseException) -> str:
    code = getattr(exc, "code", "")
    if isinstance(code, str) and code:
        return code
    return "automatic_vocabulary_runtime_failed"


def _write_log_or_fail_closed(
    report: AutomaticVocabularyRuntimeReport,
    log_path: Optional[Path],
) -> AutomaticVocabularyRuntimeReport:
    if log_path is None:
        return report
    try:
        append_redacted_runtime_log(report, log_path)
    except Exception:
        return replace(
            report,
            status="SAFE_STOP",
            error_code="automatic_vocabulary_log_write_failed",
        )
    return report


def run_bounded_automatic_vocabulary_cycle(
    *,
    notion: Any = None,
    config: Optional[NotionConfig] = None,
    state_path: Optional[Path] = None,
    artifact_root: Path = Path(
        "data/automatic_vocabulary/enrichment"
    ),
    lock_path: Optional[Path] = None,
    log_path: Optional[Path] = DEFAULT_RUNTIME_LOG_PATH,
    now: Optional[datetime] = None,
    detector: Detector = run_read_only_detection_cycle,
    processor: Processor = run_automatic_vocabulary_processing_cycle,
    config_loader: Callable[[], NotionConfig] = load_notion_config,
    notion_factory: Callable[[str], Any] = create_notion_client,
    detector_options: Optional[Mapping[str, Any]] = None,
    processor_options: Optional[Mapping[str, Any]] = None,
) -> AutomaticVocabularyRuntimeReport:
    """Run detection then processing once; never wait or loop."""
    resolved_config = config
    try:
        resolved_config = resolved_config or config_loader()
        namespace = target_namespace(resolved_config)
        resolved_state_path = state_path or default_state_path(namespace)
        resolved_lock_path = lock_path or default_process_lock_path(
            resolved_state_path
        )
    except Exception as exc:
        report = _empty_report(
            status="SAFE_STOP",
            process_lock_acquired=False,
            error_code=_error_code(exc),
        )
        return _write_log_or_fail_closed(report, log_path)

    cycle_now = now or datetime.now(timezone.utc)
    if cycle_now.tzinfo is None:
        cycle_now = cycle_now.replace(tzinfo=timezone.utc)
    cycle_now = cycle_now.astimezone(timezone.utc)

    try:
        with automatic_vocabulary_process_lock(resolved_lock_path):
            resolved_notion = notion or notion_factory(
                resolved_config.token
            )
            detection = detector(
                notion=resolved_notion,
                config=resolved_config,
                state_path=resolved_state_path,
                now=cycle_now,
                **dict(detector_options or {}),
            )
            processing = processor(
                notion=resolved_notion,
                config=resolved_config,
                state_path=resolved_state_path,
                artifact_root=artifact_root,
                now=cycle_now,
                **dict(processor_options or {}),
            )
            report = AutomaticVocabularyRuntimeReport(
                status=_runtime_status(detection, processing),
                cycle_fingerprint=_cycle_fingerprint(
                    processing.cycle_fingerprint
                    or detection.cycle_fingerprint
                ),
                detection_status=str(detection.status),
                processing_status=str(processing.status),
                pages_read=int(detection.pages_read),
                occurrences_seen=int(detection.occurrences_seen),
                ready_for_enrichment=int(
                    detection.ready_for_enrichment
                ),
                candidates=int(processing.candidates),
                enriched=int(processing.enriched),
                published=int(processing.published),
                created=int(processing.created),
                updated=int(processing.updated),
                codex_calls=int(processing.codex_calls),
                vocabulary_publisher_calls=int(
                    processing.vocabulary_publisher_calls
                ),
                retryable_failures=int(
                    processing.retryable_failures
                ),
                target_binding_valid=bool(
                    detection.target_binding_valid
                    and processing.target_binding_valid
                ),
                process_lock_acquired=True,
                historical_group_reads=int(
                    processing.historical_group_reads
                ),
                historical_group_writes=int(
                    processing.historical_group_writes
                ),
                error_code=(
                    str(processing.error_codes[0])
                    if processing.error_codes
                    else ""
                ),
            )
    except AutomaticVocabularyProcessBusy as exc:
        report = _empty_report(
            status="OVERLAP_SKIPPED",
            process_lock_acquired=False,
            error_code=exc.code,
        )
    except (
        AutomaticVocabularyDetectionError,
        AutomaticVocabularyProcessingError,
        AutomaticVocabularyStateError,
    ) as exc:
        report = _empty_report(
            status="SAFE_STOP",
            process_lock_acquired=True,
            error_code=_error_code(exc),
        )
    except Exception:
        report = _empty_report(
            status="SAFE_STOP",
            process_lock_acquired=True,
            error_code="automatic_vocabulary_runtime_failed",
        )

    return _write_log_or_fail_closed(report, log_path)


__all__ = [
    "AutomaticVocabularyProcessBusy",
    "AutomaticVocabularyRuntimeError",
    "AutomaticVocabularyRuntimeReport",
    "append_redacted_runtime_log",
    "automatic_vocabulary_process_lock",
    "default_process_lock_path",
    "run_bounded_automatic_vocabulary_cycle",
]
