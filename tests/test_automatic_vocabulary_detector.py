from __future__ import annotations

import json
import inspect
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.automatic_vocabulary_detector import (
    ERROR_ARTIFACT_OUTSIDE_ALLOWLIST,
    AutomaticVocabularyDetectionError,
    allowed_state_artifacts,
    default_state_path,
    exact_occurrence_identity,
    run_read_only_detection_cycle,
    target_namespace,
    validate_local_artifact_changes,
)
import src.agent.automatic_vocabulary_detector as detector_module
from src.agent.automatic_vocabulary_state import (
    STATUS_BASELINED,
    STATUS_CANCELLED,
    STATUS_QUIET_WAIT,
    STATUS_READY,
    AutomaticVocabularyStateStore,
)
from src.notion.config import NotionConfig
from src.notion.highlight_reader import PinkHighlightOccurrence


NOW = datetime(2026, 7, 26, 8, 0, tzinfo=timezone.utc)


def config(group: str = "a") -> NotionConfig:
    return NotionConfig(
        token="redacted-test-token",
        podcast_database_id=f"podcast-{group}",
        expression_database_id=f"expression-{group}",
        weekly_database_id=f"weekly-{group}",
        vocabulary_database_id=f"vocabulary-{group}",
        target_parent_page_id=f"parent-{group}",
    )


def binding_pass(_notion, _config):
    return SimpleNamespace(valid=True)


def rich_text(text: str, color: str = "pink") -> dict:
    return {
        "plain_text": text,
        "text": {"content": text},
        "annotations": {"color": color},
    }


def paragraph(
    block_id: str,
    highlighted_text: str,
    suffix: str = " supports a professional decision.",
) -> dict:
    return {
        "id": block_id,
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                rich_text(highlighted_text),
                rich_text(suffix, "default"),
            ]
        },
    }


class FakeDataSources:
    def __init__(self, owner) -> None:
        self.owner = owner

    def query(self, **kwargs):
        self.owner.query_calls.append(kwargs)
        return {
            "results": list(self.owner.pages),
            "has_more": False,
            "next_cursor": None,
        }


class FakeChildren:
    def __init__(self, owner) -> None:
        self.owner = owner

    def list(self, **kwargs):
        self.owner.block_calls.append(kwargs)
        if self.owner.fail_block_reads:
            raise RuntimeError("redacted fake read failure")
        return {
            "results": list(
                self.owner.blocks_by_parent.get(kwargs["block_id"], [])
            ),
            "has_more": False,
            "next_cursor": None,
        }

    def append(self, **_kwargs):
        self.owner.write_calls += 1
        raise AssertionError("write must not be called")


class FakePages:
    def __init__(self, owner) -> None:
        self.owner = owner

    def create(self, **_kwargs):
        self.owner.write_calls += 1
        raise AssertionError("write must not be called")

    def update(self, **_kwargs):
        self.owner.write_calls += 1
        raise AssertionError("write must not be called")


class FakeNotion:
    def __init__(self) -> None:
        self.pages = [
            {
                "id": "page-1",
                "last_edited_time": "2026-07-26T08:00:00Z",
            }
        ]
        self.blocks_by_parent = {
            "page-1": [paragraph("block-1", "assumptions")]
        }
        self.query_calls = []
        self.block_calls = []
        self.write_calls = 0
        self.fail_block_reads = False
        self.data_sources = FakeDataSources(self)
        self.blocks = SimpleNamespace(children=FakeChildren(self))
        self.pages_api = FakePages(self)


def cycle(
    notion: FakeNotion,
    state_path: Path,
    at: datetime,
    cfg: NotionConfig | None = None,
):
    return run_read_only_detection_cycle(
        notion=notion,
        config=cfg or config(),
        state_path=state_path,
        now=at,
        binding_validator=binding_pass,
    )


def occurrence(
    *,
    text: str = "Fundraising!",
    block_id: str = "block-1",
    context: str = "Fundraising! supports the strategy.",
    rich_text_index: int = 0,
    page_id: str = "page-1",
) -> PinkHighlightOccurrence:
    return PinkHighlightOccurrence(
        page_id=page_id,
        block_id=block_id,
        block_type="paragraph",
        block_path=(0,),
        rich_text_index=rich_text_index,
        start_offset=0,
        end_offset=len(text),
        row_index=None,
        cell_index=None,
        text=text,
        color="pink",
        context=context,
    )


def test_exact_occurrence_fingerprint_is_deterministic() -> None:
    identity_a = exact_occurrence_identity(
        occurrence(),
        target_namespace(config()),
    )
    identity_b = exact_occurrence_identity(
        occurrence(),
        target_namespace(config()),
    )

    assert identity_a == identity_b


@pytest.mark.parametrize(
    "changed",
    [
        occurrence(text="fundraising!"),
        occurrence(context="A different exact context."),
        occurrence(block_id="block-2"),
        occurrence(rich_text_index=1),
    ],
)
def test_exact_occurrence_fingerprint_changes_with_exact_identity(
    changed,
) -> None:
    original = exact_occurrence_identity(
        occurrence(),
        target_namespace(config()),
    )

    assert exact_occurrence_identity(
        changed,
        target_namespace(config()),
    ).occurrence_fingerprint != original.occurrence_fingerprint


def test_target_namespace_changes_occurrence_identity() -> None:
    first = exact_occurrence_identity(
        occurrence(),
        target_namespace(config("a")),
    )
    second = exact_occurrence_identity(
        occurrence(),
        target_namespace(config("b")),
    )

    assert first.occurrence_fingerprint != second.occurrence_fingerprint


def test_fingerprint_version_is_part_of_identity() -> None:
    namespace = target_namespace(config())

    version_one = exact_occurrence_identity(
        occurrence(),
        namespace,
        fingerprint_version=1,
    )
    version_two = exact_occurrence_identity(
        occurrence(),
        namespace,
        fingerprint_version=2,
    )

    assert version_one.occurrence_fingerprint != (
        version_two.occurrence_fingerprint
    )


def test_identical_text_across_pages_remains_distinct() -> None:
    namespace = target_namespace(config())

    first = exact_occurrence_identity(
        occurrence(page_id="page-1"),
        namespace,
    )
    second = exact_occurrence_identity(
        occurrence(page_id="page-2"),
        namespace,
    )

    assert first.occurrence_fingerprint != second.occurrence_fingerprint


@pytest.mark.parametrize(
    ("first_text", "second_text"),
    [
        ("Assumption", "assumption"),
        ("assumption", "assumptions"),
        ("assumption", "assumption!"),
    ],
)
def test_case_plural_and_punctuation_are_never_normalized(
    first_text,
    second_text,
) -> None:
    namespace = target_namespace(config())

    first = exact_occurrence_identity(
        occurrence(text=first_text),
        namespace,
    )
    second = exact_occurrence_identity(
        occurrence(text=second_text),
        namespace,
    )

    assert first.occurrence_fingerprint != second.occurrence_fingerprint


def test_default_state_path_is_target_group_scoped() -> None:
    assert default_state_path(target_namespace(config("a"))) != (
        default_state_path(target_namespace(config("b")))
    )


def test_state_artifact_allowlist_contains_only_sqlite_sidecars(
    tmp_path,
) -> None:
    state_path = tmp_path / "state.sqlite3"

    artifacts = allowed_state_artifacts(state_path)

    assert state_path.resolve() in artifacts
    assert len(artifacts) == 4


def test_artifact_allowlist_rejects_unexpected_file(tmp_path) -> None:
    state_path = tmp_path / "state.sqlite3"

    with pytest.raises(AutomaticVocabularyDetectionError) as raised:
        validate_local_artifact_changes(
            [tmp_path / "unexpected.json"],
            state_path,
        )

    assert raised.value.code == ERROR_ARTIFACT_OUTSIDE_ALLOWLIST


def test_first_enable_baselines_existing_highlights(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"

    report = cycle(notion, state_path, NOW)

    assert report.status == STATUS_BASELINED
    assert report.baselined == 1
    assert report.ready_for_enrichment == 0
    stored = AutomaticVocabularyStateStore(
        state_path
    ).list_occurrence_statuses(target_namespace(config()))
    assert [item.status for item in stored] == [STATUS_BASELINED]


def test_local_state_preserves_exact_text_and_context(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"

    cycle(notion, state_path, NOW)

    with sqlite3.connect(state_path) as connection:
        exact_text, exact_context = connection.execute(
            """
            SELECT exact_text, exact_context
            FROM highlight_occurrences
            """
        ).fetchone()
    assert exact_text == "assumptions"
    assert exact_context == (
        "assumptions supports a professional decision."
    )


def test_empty_first_enable_still_completes_baseline(tmp_path) -> None:
    notion = FakeNotion()
    notion.blocks_by_parent["page-1"] = []
    state_path = tmp_path / "state.sqlite3"

    report = cycle(notion, state_path, NOW)

    assert report.status == STATUS_BASELINED
    assert report.baselined == 0
    assert AutomaticVocabularyStateStore(
        state_path
    ).get_binding(target_namespace(config())).baseline_completed is True


def test_new_highlight_enters_quiet_wait_after_baseline(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.pages[0]["last_edited_time"] = "2026-07-26T08:01:00Z"
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )

    report = cycle(notion, state_path, NOW + timedelta(minutes=1))

    assert report.status == STATUS_QUIET_WAIT
    assert report.quiet_wait == 1
    assert report.ready_for_enrichment == 0


def test_quiet_wait_does_not_promote_before_90_seconds(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))

    report = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=2, seconds=29),
    )

    assert report.ready_for_enrichment == 0
    assert report.quiet_wait == 1


def test_page_edit_resets_quiet_period_deadline(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    notion.pages[0]["last_edited_time"] = "2026-07-26T08:01:00Z"
    cycle(notion, state_path, NOW + timedelta(minutes=1))
    notion.pages[0]["last_edited_time"] = "2026-07-26T08:02:20Z"

    report = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=2, seconds=30),
    )

    assert report.ready_for_enrichment == 0
    assert report.quiet_wait == 1
    promoted = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=4),
    )
    assert promoted.ready_for_enrichment == 1


def test_unchanged_occurrence_promotes_at_90_seconds(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))

    report = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=2, seconds=30),
    )

    assert report.status == STATUS_READY
    assert report.ready_for_enrichment == 1
    assert len(report.ready_occurrence_fingerprints) == 1


def test_pending_page_is_rechecked_even_outside_global_overlap(
    tmp_path,
) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))
    notion.pages = [
        {
            "id": "page-2",
            "last_edited_time": "2026-07-26T09:00:00Z",
        }
    ]
    notion.blocks_by_parent["page-2"] = []

    report = cycle(notion, state_path, NOW + timedelta(hours=1))

    assert report.ready_for_enrichment == 1
    assert {call["block_id"] for call in notion.block_calls} >= {
        "page-1",
        "page-2",
    }


def test_repeated_ready_scan_is_idempotent_in_state(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))
    cycle(notion, state_path, NOW + timedelta(minutes=3))

    cycle(notion, state_path, NOW + timedelta(minutes=4))

    with sqlite3.connect(state_path) as connection:
        occurrence_count = connection.execute(
            "SELECT COUNT(*) FROM highlight_occurrences"
        ).fetchone()[0]
    assert occurrence_count == 2


def test_context_change_cancels_prior_occurrence_and_restarts_timer(
    tmp_path,
) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising", " supports strategy.")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))
    notion.blocks_by_parent["page-1"][1] = paragraph(
        "block-2",
        "fundraising",
        " supports investor communication.",
    )

    report = cycle(notion, state_path, NOW + timedelta(minutes=2))

    statuses = [
        item.status
        for item in AutomaticVocabularyStateStore(
            state_path
        ).list_occurrence_statuses(target_namespace(config()))
        if item.page_id == "page-1" and not item.baseline
    ]
    assert report.cancelled_before_ready == 1
    assert STATUS_CANCELLED in statuses
    assert STATUS_QUIET_WAIT in statuses


def test_removed_occurrence_is_cancelled_before_ready(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.blocks_by_parent["page-1"].append(
        paragraph("block-2", "fundraising")
    )
    cycle(notion, state_path, NOW + timedelta(minutes=1))
    notion.blocks_by_parent["page-1"] = [
        notion.blocks_by_parent["page-1"][0]
    ]

    report = cycle(notion, state_path, NOW + timedelta(minutes=2))

    assert report.cancelled_before_ready == 1
    assert STATUS_CANCELLED in {
        item.status
        for item in AutomaticVocabularyStateStore(
            state_path
        ).list_occurrence_statuses(target_namespace(config()))
    }


def test_read_failure_does_not_advance_watermark(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    before = AutomaticVocabularyStateStore(
        state_path
    ).get_binding(target_namespace(config())).watermark
    notion.pages[0]["last_edited_time"] = "2026-07-26T08:10:00Z"
    notion.fail_block_reads = True

    with pytest.raises(AutomaticVocabularyDetectionError) as raised:
        cycle(notion, state_path, NOW + timedelta(minutes=10))

    after = AutomaticVocabularyStateStore(
        state_path
    ).get_binding(target_namespace(config())).watermark
    assert raised.value.code == "read_only_detection_failed"
    assert after == before


def test_process_lease_is_released_after_read_failure(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    cycle(notion, state_path, NOW)
    notion.fail_block_reads = True
    with pytest.raises(AutomaticVocabularyDetectionError):
        cycle(notion, state_path, NOW + timedelta(minutes=1))
    notion.fail_block_reads = False

    report = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=2),
    )

    assert report.notion_writes == 0


def test_restart_reloads_existing_baseline_instead_of_rebaselining(
    tmp_path,
) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"
    first = cycle(notion, state_path, NOW)

    second = cycle(
        notion,
        state_path,
        NOW + timedelta(minutes=1),
    )

    assert first.baselined == 1
    assert second.baselined == 0
    stored = AutomaticVocabularyStateStore(
        state_path
    ).list_occurrence_statuses(target_namespace(config()))
    assert [item.status for item in stored] == [STATUS_BASELINED]


def test_cycle_never_calls_notion_write_methods(tmp_path) -> None:
    notion = FakeNotion()

    report = cycle(notion, tmp_path / "state.sqlite3", NOW)

    assert notion.write_calls == 0
    assert report.notion_writes == 0
    assert report.vocabulary_publisher_calls == 0


def test_detector_source_has_no_publisher_or_notion_mutation_calls() -> None:
    source = inspect.getsource(detector_module)

    assert "from src.notion.vocabulary_publisher" not in source
    assert "import src.notion.vocabulary_publisher" not in source
    assert "pages.create" not in source
    assert "pages.update" not in source
    assert "children.append" not in source
    assert "data_sources.update" not in source


def test_only_configured_podcast_data_source_is_queried(tmp_path) -> None:
    notion = FakeNotion()
    cfg = config("target")

    cycle(notion, tmp_path / "state.sqlite3", NOW, cfg=cfg)

    assert {
        call["data_source_id"] for call in notion.query_calls
    } == {cfg.podcast_database_id}


def test_report_contains_no_learning_content_or_raw_identifiers(
    tmp_path,
) -> None:
    notion = FakeNotion()
    cfg = config("private-raw-identifier")

    report = cycle(
        notion,
        tmp_path / "state.sqlite3",
        NOW,
        cfg=cfg,
    )
    rendered = json.dumps(report.to_dict(), sort_keys=True)

    assert "assumptions" not in rendered
    assert "page-1" not in rendered
    assert cfg.podcast_database_id not in rendered
    assert cfg.target_parent_page_id not in rendered
    assert len(report.workspace_fingerprint) == 12
    assert len(report.target_group_fingerprint) == 12


def test_state_does_not_import_legacy_global_json(tmp_path) -> None:
    legacy = tmp_path / "highlight_sync_state.json"
    legacy.write_text(
        json.dumps(
            {
                "processed_highlights_by_page": {
                    "page-1": ["future-new-highlight"]
                }
            }
        ),
        encoding="utf-8",
    )
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"

    report = cycle(notion, state_path, NOW)

    assert report.baselined == 1
    assert state_path.exists()
    assert legacy.exists()


def test_each_successful_run_records_one_bounded_cycle(tmp_path) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"

    cycle(notion, state_path, NOW)
    cycle(notion, state_path, NOW + timedelta(minutes=1))

    with sqlite3.connect(state_path) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM detection_cycles"
        ).fetchone()[0]
    assert count == 2


def test_binding_failure_stops_before_query_and_state_creation(
    tmp_path,
) -> None:
    notion = FakeNotion()
    state_path = tmp_path / "state.sqlite3"

    with pytest.raises(AutomaticVocabularyDetectionError) as raised:
        run_read_only_detection_cycle(
            notion=notion,
            config=config(),
            state_path=state_path,
            now=NOW,
            binding_validator=lambda *_args: SimpleNamespace(valid=False),
        )

    assert raised.value.code == "target_binding_invalid"
    assert notion.query_calls == []
    assert not state_path.exists()
