from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.agent.automatic_vocabulary_runtime import (
    automatic_vocabulary_process_lock,
    default_process_lock_path,
    run_bounded_automatic_vocabulary_cycle,
)
from src.notion.config import NotionConfig


def _config() -> NotionConfig:
    return NotionConfig(
        token="private-token",
        podcast_database_id="private-podcast",
        expression_database_id="private-expression",
        weekly_database_id="private-weekly",
        vocabulary_database_id="private-vocabulary",
        target_parent_page_id="private-parent",
    )


def _detection(**_kwargs):
    return SimpleNamespace(
        status="READY_FOR_ENRICHMENT",
        cycle_fingerprint="detection-cycle-private",
        pages_read=1,
        occurrences_seen=2,
        ready_for_enrichment=1,
        target_binding_valid=True,
    )


def _processing(**_kwargs):
    return SimpleNamespace(
        status="PASS",
        cycle_fingerprint="processor-cycle-private",
        candidates=1,
        enriched=1,
        published=1,
        created=1,
        updated=0,
        codex_calls=1,
        vocabulary_publisher_calls=1,
        retryable_failures=0,
        target_binding_valid=True,
        historical_group_reads=0,
        historical_group_writes=0,
        error_codes=(),
    )


def test_bounded_runtime_runs_detection_then_processing(tmp_path: Path) -> None:
    calls: list[str] = []

    def detector(**kwargs):
        calls.append("detection")
        assert kwargs["notion"] is notion
        return _detection(**kwargs)

    def processor(**kwargs):
        calls.append("processing")
        assert kwargs["notion"] is notion
        return _processing(**kwargs)

    notion = object()
    report = run_bounded_automatic_vocabulary_cycle(
        notion=notion,
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        artifact_root=tmp_path / "artifacts",
        lock_path=tmp_path / "worker.lock",
        log_path=tmp_path / "runtime.jsonl",
        detector=detector,
        processor=processor,
    )

    assert calls == ["detection", "processing"]
    assert report.status == "PASS"
    assert report.created == 1
    assert report.historical_group_reads == 0
    assert report.historical_group_writes == 0


def test_process_lock_skips_overlapping_worker(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    notion_factory_calls = 0

    def notion_factory(_token: str):
        nonlocal notion_factory_calls
        notion_factory_calls += 1
        return object()

    with automatic_vocabulary_process_lock(lock_path):
        report = run_bounded_automatic_vocabulary_cycle(
            config=_config(),
            state_path=tmp_path / "state.sqlite3",
            lock_path=lock_path,
            log_path=None,
            detector=_detection,
            processor=_processing,
            notion_factory=notion_factory,
        )

    assert report.status == "OVERLAP_SKIPPED"
    assert report.process_lock_acquired is False
    assert report.error_code == "automatic_vocabulary_cycle_overlap"
    assert notion_factory_calls == 0


def test_runtime_failure_is_redacted_and_processing_does_not_run(
    tmp_path: Path,
) -> None:
    private_value = "private-learning-content"
    processing_calls = 0

    def fail(**_kwargs):
        raise RuntimeError(private_value)

    def processor(**_kwargs):
        nonlocal processing_calls
        processing_calls += 1
        return _processing()

    report = run_bounded_automatic_vocabulary_cycle(
        notion=object(),
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        lock_path=tmp_path / "worker.lock",
        log_path=tmp_path / "runtime.jsonl",
        detector=fail,
        processor=processor,
    )

    rendered = json.dumps(report.to_dict())
    assert report.status == "SAFE_STOP"
    assert report.error_code == "automatic_vocabulary_runtime_failed"
    assert private_value not in rendered
    assert processing_calls == 0


def test_lock_is_released_after_cycle_failure(tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"

    first = run_bounded_automatic_vocabulary_cycle(
        notion=object(),
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        lock_path=lock_path,
        log_path=None,
        detector=lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("private")
        ),
        processor=_processing,
    )
    second = run_bounded_automatic_vocabulary_cycle(
        notion=object(),
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        lock_path=lock_path,
        log_path=None,
        detector=_detection,
        processor=_processing,
    )

    assert first.status == "SAFE_STOP"
    assert second.status == "PASS"


def test_runtime_log_contains_only_redacted_report(tmp_path: Path) -> None:
    log_path = tmp_path / "runtime.jsonl"

    run_bounded_automatic_vocabulary_cycle(
        notion=object(),
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        lock_path=tmp_path / "worker.lock",
        log_path=log_path,
        detector=_detection,
        processor=_processing,
    )

    rendered = log_path.read_text(encoding="utf-8")
    assert "private-token" not in rendered
    assert "private-podcast" not in rendered
    assert "private-parent" not in rendered
    assert json.loads(rendered)["status"] == "PASS"
    assert (log_path.stat().st_mode & 0o777) == 0o600


def test_runtime_log_failure_returns_redacted_safe_stop(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "not-a-log"
    directory.mkdir()

    report = run_bounded_automatic_vocabulary_cycle(
        notion=object(),
        config=_config(),
        state_path=tmp_path / "state.sqlite3",
        lock_path=tmp_path / "worker.lock",
        log_path=directory,
        detector=_detection,
        processor=_processing,
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "automatic_vocabulary_log_write_failed"


def test_default_lock_path_is_scoped_to_state_path(tmp_path: Path) -> None:
    first = default_process_lock_path(tmp_path / "a.sqlite3")
    second = default_process_lock_path(tmp_path / "b.sqlite3")

    assert first != second
    assert first.name.endswith(".worker.lock")
