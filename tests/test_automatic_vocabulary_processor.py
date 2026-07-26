from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from src.agent.automatic_vocabulary_detector import target_namespace
from src.agent.automatic_vocabulary_processor import (
    AutomaticVocabularyProcessingError,
    run_automatic_vocabulary_processing_cycle,
)
from src.agent.automatic_vocabulary_state import (
    STATUS_PUBLISHED,
    STATUS_PUBLISHING,
    STATUS_READY,
    AutomaticVocabularyStateStore,
)
from src.notion.schema import PODCAST_LIBRARY, VOCABULARY_DATABASE
from src.notion.vocabulary_publisher import (
    upsert_automatic_vocabulary_occurrence,
)
from tests.acceptance.fakes import (
    FakeNotion,
    date_property,
    relation_property,
    rich_text_property,
    select_property,
    title_property,
)


NOW = datetime(2026, 7, 26, 9, 0, tzinfo=timezone.utc)
WORD = "challenge assumptions"
CONTEXT = (
    "Strong negotiators challenge assumptions before proposing a solution."
)


def _source_page(workspace: FakeNotion) -> str:
    return workspace.add_page(
        workspace.config.podcast_data_source_id,
        {
            "Title": title_property("Target podcast"),
            "URL": {"type": "url", "url": "https://example.com/target"},
            "Source Type": select_property("Podcast"),
            "Date": date_property("2026-07-26"),
            "Topic": select_property("Negotiation"),
            "Difficulty": select_property("Intermediate"),
            "Short Summary": rich_text_property("Summary"),
        },
        page_id="target-source-podcast",
    )


def _state(
    tmp_path: Path,
    workspace: FakeNotion,
    *,
    occurrences: list[tuple[str, str, str]],
) -> tuple[Path, AutomaticVocabularyStateStore]:
    path = tmp_path / "automatic.sqlite3"
    store = AutomaticVocabularyStateStore(path)
    store.initialize()
    namespace = target_namespace(workspace.config.as_notion_config())
    with sqlite3.connect(path) as connection:
        for fingerprint, word, context in occurrences:
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
                    namespace.workspace_fingerprint,
                    namespace.target_group_fingerprint,
                    namespace.binding_version,
                    fingerprint,
                    f"location-{fingerprint}",
                    "target-source-podcast",
                    f"block-{fingerprint}",
                    "rich_text:0",
                    word,
                    context,
                    "pink_background",
                    "2026-07-26T08:00:00Z",
                    "2026-07-26T08:00:00Z",
                    "2026-07-26T08:00:00Z",
                    "2026-07-26T08:01:30Z",
                    STATUS_READY,
                    0,
                ),
            )
    return path, store


def _artifact(word: str, context: str) -> dict[str, Any]:
    return {
        "word": word,
        "original_context": context,
        "meaning": "Question beliefs before deciding.",
        "chinese_meaning": "在决策前质疑既有假设。",
        "part_of_speech": "phrase",
        "professional_category": "Negotiation",
        "usage_example": (
            "The team should challenge assumptions before committing."
        ),
        "common_collocations": [
            "challenge existing assumptions",
            "challenge strategic assumptions",
        ],
    }


class CodexRunner:
    def __init__(
        self,
        *,
        extra_field: bool = False,
        tool_event: bool = False,
    ) -> None:
        self.calls = 0
        self.extra_field = extra_field
        self.tool_event = tool_event
        self.environments: list[dict[str, str]] = []

    def __call__(
        self,
        command: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        self.calls += 1
        self.environments.append(dict(kwargs["env"]))
        input_data = json.loads(kwargs["input"].splitlines()[-1])
        artifact = _artifact(
            input_data["word"],
            input_data["context"],
        )
        if self.extra_field:
            artifact["unexpected"] = "never expose this value"
        output_path = Path(
            command[command.index("--output-last-message") + 1]
        )
        output_path.write_text(
            json.dumps(artifact, ensure_ascii=False),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=(
                '{"type":"command_execution"}'
                if self.tool_event
                else '{"type":"agent_message"}'
            ),
            stderr="",
        )


def _run(
    tmp_path: Path,
    workspace: FakeNotion,
    state_path: Path,
    runner: CodexRunner,
    **overrides: Any,
):
    return run_automatic_vocabulary_processing_cycle(
        notion=workspace,
        config=workspace.config.as_notion_config(),
        state_path=state_path,
        artifact_root=tmp_path / "artifacts",
        now=NOW,
        clock=lambda: NOW,
        codex_executable=tmp_path / "codex",
        codex_env={
            "HOME": str(tmp_path),
            "PATH": "/usr/bin:/bin",
            "NOTION_TOKEN": "must-not-pass",
            "OPENAI_API_KEY": "must-not-pass",
        },
        codex_runner=runner,
        **overrides,
    )


def test_first_publish_populates_properties_body_and_relation(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, store = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    runner = CodexRunner()

    report = _run(
        tmp_path,
        workspace,
        state_path,
        runner,
    )

    assert report.status == "PASS"
    assert report.created == 1
    assert report.updated == 0
    assert report.codex_calls == 1
    assert report.published == 1
    assert runner.calls == 1
    assert all(
        "NOTION" not in key.upper()
        for key in runner.environments[0]
    )
    assert "OPENAI_API_KEY" not in runner.environments[0]

    create = next(
        call
        for call in workspace.pages.create_calls
        if call["parent"]["data_source_id"]
        == workspace.config.vocabulary_data_source_id
    )
    properties = create["properties"]
    assert properties["Name"]["title"][0]["text"]["content"] == WORD
    assert properties["Original Context"]["rich_text"][0]["text"][
        "content"
    ] == CONTEXT
    assert properties["Professional Category"] == {
        "select": {"name": "Phrase"}
    }
    assert properties["Source"] == {
        "relation": [{"id": "target-source-podcast"}]
    }
    headings = [
        block[f"heading_{block['type'][-1]}"]["rich_text"][0]["text"][
            "content"
        ]
        for block in create["children"]
        if block["type"] in {"heading_1", "heading_2"}
    ]
    assert "Chinese Meaning" in headings
    assert "Part of Speech" in headings
    assert "Common Collocations" in headings
    stored = store.get_processing_occurrence(
        target_namespace(workspace.config.as_notion_config()),
        "occurrence-a",
    )
    assert stored is not None
    assert stored.status == STATUS_PUBLISHED


def test_exact_retry_skips_codex_and_publisher(tmp_path: Path) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    first_runner = CodexRunner()
    _run(tmp_path, workspace, state_path, first_runner)
    create_count = len(workspace.pages.create_calls)
    update_count = len(workspace.pages.update_calls)

    second_runner = CodexRunner()
    report = _run(
        tmp_path,
        workspace,
        state_path,
        second_runner,
    )

    assert report.status == "NO_WORK"
    assert report.candidates == 0
    assert report.codex_calls == 0
    assert report.vocabulary_publisher_calls == 0
    assert len(workspace.pages.create_calls) == create_count
    assert len(workspace.pages.update_calls) == update_count


def test_same_word_different_occurrences_are_processed_separately(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    second_context = (
        "Leaders challenge assumptions during strategic planning."
    )
    state_path, store = _state(
        tmp_path,
        workspace,
        occurrences=[
            ("occurrence-a", WORD, CONTEXT),
            ("occurrence-b", WORD, second_context),
        ],
    )
    runner = CodexRunner()

    report = _run(
        tmp_path,
        workspace,
        state_path,
        runner,
    )

    assert report.published == 2
    assert report.created == 1
    assert report.updated == 1
    assert report.codex_calls == 2
    namespace = target_namespace(workspace.config.as_notion_config())
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-a",
    ).status == STATUS_PUBLISHED
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-b",
    ).status == STATUS_PUBLISHED


def test_strict_artifact_failure_never_calls_publisher(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, store = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )

    report = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(extra_field=True),
    )

    assert report.status == "SAFE_STOP"
    assert report.vocabulary_publisher_calls == 0
    assert report.error_codes == ("schema_validation_failed",)
    assert not any(
        call["parent"]["data_source_id"]
        == workspace.config.vocabulary_data_source_id
        for call in workspace.pages.create_calls
    )
    stored = store.get_processing_occurrence(
        target_namespace(workspace.config.as_notion_config()),
        "occurrence-a",
    )
    assert stored.last_error_code == "schema_validation_failed"


def test_invalid_artifact_is_regenerated_on_retry(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    first = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(extra_field=True),
    )

    valid_runner = CodexRunner()
    second = _run(
        tmp_path,
        workspace,
        state_path,
        valid_runner,
    )

    assert first.status == "SAFE_STOP"
    assert second.status == "PASS"
    assert second.codex_calls == 1
    assert second.created == 1
    assert valid_runner.calls == 1


def test_tool_rejected_candidate_cannot_be_published_on_retry(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    first = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(tool_event=True),
    )

    valid_runner = CodexRunner()
    second = _run(
        tmp_path,
        workspace,
        state_path,
        valid_runner,
    )

    assert first.status == "SAFE_STOP"
    assert first.error_codes == ("codex_tool_use_blocked",)
    assert first.vocabulary_publisher_calls == 0
    assert second.status == "PASS"
    assert second.codex_calls == 1
    assert second.created == 1
    assert valid_runner.calls == 1


def test_target_binding_failure_happens_before_codex_or_write(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    workspace.schemas[
        workspace.config.vocabulary_data_source_id
    ].pop("Meaning")
    runner = CodexRunner()

    with pytest.raises(AutomaticVocabularyProcessingError):
        _run(tmp_path, workspace, state_path, runner)

    assert runner.calls == 0
    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_query_failure_is_retryable_and_never_creates(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )
    original_query = workspace.data_sources.query

    def failing_query(**kwargs: Any):
        if (
            kwargs["data_source_id"]
            == workspace.config.vocabulary_data_source_id
        ):
            raise RuntimeError("private query failure")
        return original_query(**kwargs)

    workspace.data_sources.query = failing_query
    report = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_codes == ("vocabulary_identity_query_failed",)
    assert not any(
        call["parent"]["data_source_id"]
        == workspace.config.vocabulary_data_source_id
        for call in workspace.pages.create_calls
    )


def test_duplicate_vocabulary_identity_fails_closed(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    properties = {
        "Name": title_property(WORD),
        "Original Context": rich_text_property(CONTEXT),
        "Meaning": rich_text_property("Meaning"),
        "Professional Category": select_property("Phrase"),
        "Source": relation_property("target-source-podcast"),
        "Source Page ID": rich_text_property("target-source-podcast"),
        "First Seen": date_property("2026-07-26"),
        "Review Status": select_property("New"),
        "Last Review": {"type": "date", "date": None},
        "Usage Example": rich_text_property("Example"),
        "Personal Note": {"type": "rich_text", "rich_text": []},
    }
    workspace.add_page(
        workspace.config.vocabulary_data_source_id,
        properties,
        page_id="duplicate-vocabulary-a",
    )
    workspace.add_page(
        workspace.config.vocabulary_data_source_id,
        properties,
        page_id="duplicate-vocabulary-b",
    )
    state_path, _ = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )

    report = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_codes == ("vocabulary_identity_not_unique",)
    assert workspace.pages.update_calls == []


def test_restart_from_publishing_reconciles_without_second_codex_call(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, store = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )

    def interrupted_publisher(*_args: Any, **_kwargs: Any):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(
            tmp_path,
            workspace,
            state_path,
            CodexRunner(),
            publisher=interrupted_publisher,
        )
    namespace = target_namespace(workspace.config.as_notion_config())
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-a",
    ).status == STATUS_PUBLISHING

    runner = CodexRunner()
    report = _run(
        tmp_path,
        workspace,
        state_path,
        runner,
    )

    assert report.status == "PASS"
    assert report.codex_calls == 0
    assert report.created == 1
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-a",
    ).status == STATUS_PUBLISHED


def test_restart_after_successful_create_does_not_duplicate_page(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    _source_page(workspace)
    state_path, store = _state(
        tmp_path,
        workspace,
        occurrences=[("occurrence-a", WORD, CONTEXT)],
    )

    def create_then_interrupt(payload, **kwargs):
        upsert_automatic_vocabulary_occurrence(
            payload,
            notion=kwargs["notion"],
            vocabulary_database_id=kwargs["vocabulary_database_id"],
        )
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(
            tmp_path,
            workspace,
            state_path,
            CodexRunner(),
            publisher=create_then_interrupt,
        )
    namespace = target_namespace(workspace.config.as_notion_config())
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-a",
    ).status == STATUS_PUBLISHING
    vocabulary_pages_after_crash = [
        page
        for page in workspace.pages_by_id.values()
        if page.data_source_id
        == workspace.config.vocabulary_data_source_id
        and page.page_id != "existing-vocabulary"
    ]
    assert len(vocabulary_pages_after_crash) == 1

    report = _run(
        tmp_path,
        workspace,
        state_path,
        CodexRunner(),
    )
    vocabulary_pages_after_retry = [
        page
        for page in workspace.pages_by_id.values()
        if page.data_source_id
        == workspace.config.vocabulary_data_source_id
        and page.page_id != "existing-vocabulary"
    ]

    assert report.codex_calls == 0
    assert report.created == 0
    assert report.updated == 1
    assert len(vocabulary_pages_after_retry) == 1
    assert store.get_processing_occurrence(
        namespace,
        "occurrence-a",
    ).status == STATUS_PUBLISHED
