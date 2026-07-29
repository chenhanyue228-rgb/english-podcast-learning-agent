from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.acceptance import (
    run_automatic_vocabulary_owner_acceptance as cli,
)
from scripts.acceptance.automatic_vocabulary_owner_acceptance import (
    ACCEPTANCE_CONTEXT,
    ACCEPTANCE_WORD,
    LIVE_CONFIRMATION,
    AcceptanceFailure,
    AutomaticVocabularyAcceptanceGuard,
    AutomaticVocabularyAcceptancePolicy,
    AutomaticVocabularyOwnerAcceptanceRunner,
    GuardViolation,
    render_failure_report,
    render_redacted_report,
)
from src.notion.schema import EXPRESSION_DATABASE
from tests.acceptance.fakes import FakeNotion


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


class AcceptanceClock:
    def __init__(self) -> None:
        self.current = NOW

    def __call__(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


def _artifact() -> dict:
    return {
        "word": ACCEPTANCE_WORD,
        "original_context": ACCEPTANCE_CONTEXT,
        "meaning": "Set clear limits before making a commitment.",
        "chinese_meaning": "在承诺前明确决策边界。",
        "part_of_speech": "phrase",
        "professional_category": "Leadership",
        "usage_example": (
            "The leadership team should calibrate decision boundaries "
            "before approving the investment."
        ),
        "common_collocations": [
            "calibrate boundaries",
            "decision boundaries",
        ],
    }


def _runner(
    tmp_path: Path,
    workspace: FakeNotion,
) -> AutomaticVocabularyOwnerAcceptanceRunner:
    clock = AcceptanceClock()

    def codex_generator(**_kwargs):
        artifact = _artifact()
        Path(_kwargs["output_path"]).write_text(
            json.dumps(artifact, ensure_ascii=False),
            encoding="utf-8",
        )
        return artifact

    return AutomaticVocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        state_path=tmp_path / "state.sqlite3",
        artifact_root=tmp_path / "artifacts",
        lock_path=tmp_path / "worker.lock",
        log_path=tmp_path / "runtime.jsonl",
        clock=clock,
        sleep=clock.sleep,
        processor_options={"codex_generator": codex_generator},
    )


def test_dry_run_validates_target_without_notion_write(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()

    result = _runner(tmp_path, workspace).dry_run()

    assert result.report.status == "passed"
    assert result.report.mode == "dry-run"
    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []
    assert workspace.blocks.children.append_calls == []
    assert not (tmp_path / "state.sqlite3").exists()


def test_live_confirmation_is_required_before_any_write(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()

    with pytest.raises(AcceptanceFailure) as raised:
        _runner(tmp_path, workspace).run(confirmation="")

    assert raised.value.code == "live_confirmation_missing"
    assert workspace.pages.create_calls == []
    assert workspace.blocks.children.append_calls == []


def test_fake_live_acceptance_proves_baseline_publish_and_exact_retry(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()

    result = _runner(tmp_path, workspace).run(
        confirmation=LIVE_CONFIRMATION
    )

    report = result.report
    assert report.status == "passed"
    assert report.mode == "live"
    assert report.target_binding_valid is True
    assert report.baseline_verified is True
    assert report.quiet_period_verified is True
    assert report.exact_word_verified is True
    assert report.exact_context_verified is True
    assert report.properties_complete is True
    assert report.body_complete is True
    assert report.source_relation_verified is True
    assert report.occurrence_fingerprint_verified is True
    assert report.exact_retry_verified is True
    assert report.counts["podcast_created"] == 1
    assert report.counts["highlight_writes"] == 1
    assert report.counts["quiet_period_vocabulary_writes"] == 0
    assert report.counts["vocabulary_created"] == 1
    assert report.counts["vocabulary_updated"] == 0
    assert report.counts["retry_created"] == 0
    assert report.counts["retry_updated"] == 0
    assert report.counts["codex_calls"] == 1
    assert report.counts["expression_writes"] == 0
    assert report.counts["weekly_writes"] == 0
    assert report.counts["schema_writes"] == 0
    assert report.counts["delete_archive"] == 0
    assert report.counts["historical_reads"] == 0
    assert report.counts["historical_writes"] == 0
    assert len(workspace.pages.create_calls) == 2
    assert len(workspace.blocks.children.append_calls) == 1
    assert workspace.pages.update_calls == []


def test_target_binding_failure_stops_before_write(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    workspace.schemas[
        workspace.config.vocabulary_data_source_id
    ].pop("First Seen")

    with pytest.raises(AcceptanceFailure):
        _runner(tmp_path, workspace).dry_run()

    assert workspace.pages.create_calls == []
    assert workspace.blocks.children.append_calls == []


def test_guard_blocks_non_target_schema_and_destructive_writes() -> None:
    workspace = FakeNotion()
    policy = AutomaticVocabularyAcceptancePolicy(
        workspace.config,
        controlled_title="Controlled",
        controlled_url="https://example.invalid/controlled",
    )
    notion = AutomaticVocabularyAcceptanceGuard(workspace, policy)

    with pytest.raises(GuardViolation, match="expression_write_blocked"):
        notion.pages.create(
            parent={
                "data_source_id": workspace.config.data_source_ids[
                    EXPRESSION_DATABASE
                ]
            },
            properties={},
            children=[],
        )
    with pytest.raises(GuardViolation, match="schema_mutation_blocked"):
        notion.data_sources.update(data_source_id="anything")
    with pytest.raises(GuardViolation, match="delete_or_archive_blocked"):
        notion.pages.delete(page_id="anything")

    assert policy.counts["expression_writes"] == 1
    assert policy.counts["schema_writes"] == 1
    assert policy.counts["delete_archive"] == 1


def test_reports_and_failures_are_redacted(tmp_path: Path) -> None:
    workspace = FakeNotion()
    result = _runner(tmp_path, workspace).run(
        confirmation=LIVE_CONFIRMATION
    )

    rendered = render_redacted_report(
        result.report,
        secrets=(
            workspace.config.token,
            workspace.config.target_parent_page_id,
            *workspace.config.data_source_ids.values(),
            result.controlled_podcast_page_id,
            result.vocabulary_page_id,
        ),
    )
    failure = render_failure_report("private raw exception")

    assert ACCEPTANCE_WORD not in rendered
    assert ACCEPTANCE_CONTEXT not in rendered
    assert workspace.config.token not in rendered
    assert result.controlled_podcast_page_id not in rendered
    assert "private raw exception" not in failure
    assert json.loads(failure)["failure"] == "acceptance_failed"


@pytest.mark.parametrize("corruption", ["empty", "duplicate"])
def test_body_validation_rejects_empty_or_duplicate_sections(
    tmp_path: Path,
    corruption: str,
) -> None:
    workspace = FakeNotion()
    original_create = workspace.pages.create

    def corrupting_create(**kwargs):
        response = original_create(**kwargs)
        if (
            kwargs["parent"]["data_source_id"]
            == workspace.config.vocabulary_data_source_id
        ):
            page = workspace.pages_by_id[response["id"]]
            if corruption == "empty":
                for block in page.children:
                    if block.get("type") == "paragraph":
                        block["paragraph"]["rich_text"] = []
            else:
                page.children.extend(
                    json.loads(json.dumps(page.children))
                )
        return response

    workspace.pages.create = corrupting_create

    with pytest.raises(AcceptanceFailure) as raised:
        _runner(tmp_path, workspace).run(
            confirmation=LIVE_CONFIRMATION
        )

    assert raised.value.code == "automatic_vocabulary_body_incomplete"


def test_cli_rejects_live_run_before_loading_config(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "load_acceptance_config",
        lambda: (_ for _ in ()).throw(
            AssertionError("must not load config")
        ),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_automatic_vocabulary_owner_acceptance.py",
            "--confirmation",
            "wrong",
        ],
    )

    assert cli.main() == 2
    assert "live_confirmation_missing" in capsys.readouterr().out
