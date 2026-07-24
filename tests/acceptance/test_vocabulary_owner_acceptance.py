from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.acceptance import run_vocabulary_owner_acceptance
from scripts.acceptance import vocabulary_owner_acceptance
from scripts.acceptance.vocabulary_owner_acceptance import (
    AcceptanceFailure,
    GuardViolation,
    LIVE_CONFIRMATION,
    VocabularyAcceptanceGuard,
    VocabularyAcceptancePolicy,
    VocabularyOwnerAcceptanceRunner,
    render_failure_report,
    render_redacted_report,
)
from src.notion.vocabulary_publisher import (
    VocabularyPublishPayload,
    vocabulary_page_properties,
)
from src.skill_runtime.artifacts import CodexArtifactPendingError
from src.skill_runtime.artifacts import prepare_codex_request
from src.enrichment.codex_provider import (
    VOCABULARY_ENRICHMENT_SCHEMA,
    VOCABULARY_INSTRUCTIONS,
    CodexVocabularyEnrichmentProvider,
)
from src.workflow import highlight_vocabulary_publish_pipeline
from tests.acceptance.fakes import (
    FakeNotion,
    relation_property,
    rich_text_property,
    title_property,
)


def _source_page(workspace: FakeNotion) -> str:
    return workspace.add_page(
        workspace.config.podcast_data_source_id,
        {
            "Title": title_property("BE 598"),
            "Short Summary": rich_text_property("Private source summary."),
        },
        page_id="be-598-podcast-page",
    )


def _preview(page_id: str) -> dict:
    return {
        "page_id": page_id,
        "total_highlights": 3,
        "rejected_candidates": [
            {"word": "X", "reason": "too short"},
        ],
        "pending_vocabulary": [],
        "approved_vocabulary": [
            {
                "word": "challenge assumptions",
                "original_context": "We should challenge assumptions early.",
                "meaning": "Question beliefs before deciding.",
                "chinese_meaning": "质疑假设",
                "part_of_speech": "phrase",
                "professional_category": "Decision Making",
                "usage_example": "The team challenged assumptions before investing.",
                "source_page_id": page_id,
                "common_collocations": ["challenge assumptions"],
                "review_status": "New",
            },
            {
                "word": "fundraising",
                "original_context": "Fundraising requires a clear narrative.",
                "meaning": "The process of raising capital.",
                "chinese_meaning": "融资",
                "part_of_speech": "noun",
                "professional_category": "Business",
                "usage_example": "Fundraising became the founder's priority.",
                "source_page_id": page_id,
                "common_collocations": ["fundraising round"],
                "review_status": "New",
            },
        ],
    }


def _runner(
    workspace: FakeNotion,
    page_id: str,
    state_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> VocabularyOwnerAcceptanceRunner:
    preview = _preview(page_id)

    def highlight_reader(*, page_id: str, notion=None):
        return [
            {
                "text": item["word"],
                "context": item.get("original_context", ""),
                "color": "pink_background",
                "block_id": f"block-{index}",
            }
            for index, item in enumerate(
                [
                    *preview["approved_vocabulary"],
                    {
                        "word": preview["rejected_candidates"][0]["word"],
                        "original_context": "X is too short.",
                    },
                ],
                start=1,
            )
        ]

    def preview_builder(*, page_id: str, notion=None):
        return preview

    monkeypatch.setattr(
        highlight_vocabulary_publish_pipeline,
        "build_vocabulary_learning_preview",
        preview_builder,
    )
    return VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=highlight_reader,
        preview_builder=preview_builder,
        read_only_preview_builder=preview_builder,
        state_path=state_path,
        artifact_root=state_path.parent / "artifact-data",
    )


def _target_vocabulary_pages(workspace: FakeNotion) -> list:
    return [
        page
        for page in workspace.pages_by_id.values()
        if page.data_source_id == workspace.config.vocabulary_data_source_id
        and page.page_id != "existing-vocabulary"
    ]


def test_dry_run_is_read_only_and_reports_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    state_path = tmp_path / "highlight-state.json"
    state_path.write_text('{"stable": true}', encoding="utf-8")

    result = _runner(
        workspace,
        page_id,
        state_path,
        monkeypatch,
    ).dry_run(page_id)

    assert result.report.mode == "dry-run"
    assert result.report.counts["highlights"] == 3
    assert result.report.counts["approved"] == 2
    assert result.report.counts["rejected"] == 1
    assert result.report.counts["planned_create"] == 2
    assert result.report.counts["planned_update"] == 0
    assert result.evidence.highlights[0]["text"] == "challenge assumptions"
    assert result.evidence.rejected[0]["reason"] == "too short"
    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []
    assert workspace.blocks.children.append_calls == []
    assert state_path.read_text(encoding="utf-8") == '{"stable": true}'


def test_default_dry_run_loads_existing_artifacts_without_local_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    preview = _preview(page_id)
    artifact_root = tmp_path / "data"
    provider = CodexVocabularyEnrichmentProvider(
        request_dir=artifact_root / "vocabulary_enrichment_requests",
        output_dir=artifact_root / "vocabulary_enrichment",
    )
    for item in preview["approved_vocabulary"]:
        request_path, output_path = provider._paths(item["word"])
        prepare_codex_request(
            stage="vocabulary_enrichment",
            instructions=VOCABULARY_INSTRUCTIONS,
            input_payload={
                "word": item["word"],
                "context": item["original_context"],
            },
            schema=VOCABULARY_ENRICHMENT_SCHEMA,
            request_path=request_path,
            output_path=output_path,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(item, ensure_ascii=False),
            encoding="utf-8",
        )

    monkeypatch.setattr(
        vocabulary_owner_acceptance,
        "CodexVocabularyEnrichmentProvider",
        lambda: provider,
    )
    marker = tmp_path / "production-preview-called"

    def writey_production_preview(**_kwargs):
        marker.write_text("unexpected", encoding="utf-8")
        return preview

    raw_highlights = [
        {
            "text": item["word"],
            "context": item.get("original_context", ""),
        }
        for item in [
            *preview["approved_vocabulary"],
            {
                "word": preview["rejected_candidates"][0]["word"],
                "original_context": "X is too short.",
            },
        ]
    ]
    before = {
        path.relative_to(artifact_root).as_posix(): path.read_bytes()
        for path in artifact_root.rglob("*")
        if path.is_file()
    }

    result = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=lambda **_kwargs: raw_highlights,
        preview_builder=writey_production_preview,
        state_path=artifact_root / "highlight_sync_state.json",
        artifact_root=artifact_root,
    ).dry_run(page_id)

    after = {
        path.relative_to(artifact_root).as_posix(): path.read_bytes()
        for path in artifact_root.rglob("*")
        if path.is_file()
    }
    assert result.report.mode == "dry-run"
    assert result.report.counts["approved"] == 2
    assert marker.exists() is False
    assert after == before


def test_live_run_creates_then_exact_retry_updates_without_duplicates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    state_path = tmp_path / "highlight-state.json"
    state_path.write_text('{"stable": true}', encoding="utf-8")

    result = _runner(
        workspace,
        page_id,
        state_path,
        monkeypatch,
    ).run(page_id)

    assert result.report.mode == "live"
    assert result.report.counts["first_created"] == 2
    assert result.report.counts["first_updated"] == 0
    assert result.report.counts["retry_created"] == 0
    assert result.report.counts["retry_updated"] == 2
    assert len(_target_vocabulary_pages(workspace)) == 2
    assert len(workspace.pages.create_calls) == 2
    assert len(workspace.pages.update_calls) == 2
    assert state_path.read_text(encoding="utf-8") == '{"stable": true}'


def test_live_run_verifies_published_fields_against_enrichment_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    runner = _runner(
        workspace,
        page_id,
        tmp_path / "state.json",
        monkeypatch,
    )

    def incomplete_publisher(
        page_id: str,
        *,
        notion,
        vocabulary_database_id: str,
    ):
        for item in _preview(page_id)["approved_vocabulary"]:
            notion.pages.create(
                parent={"data_source_id": vocabulary_database_id},
                properties={
                    "Name": title_property(item["word"]),
                    "Source": relation_property(page_id),
                },
            )
        return SimpleNamespace(created=2, updated=0)

    runner.publisher = incomplete_publisher

    with pytest.raises(
        AcceptanceFailure,
        match="published_vocabulary_content_mismatch",
    ):
        runner.run(page_id)


def test_live_run_requires_at_least_one_approved_candidate(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    preview = {
        "page_id": page_id,
        "total_highlights": 1,
        "rejected_candidates": [
            {"word": "X", "reason": "too short"},
        ],
        "pending_vocabulary": [],
        "approved_vocabulary": [],
    }
    publisher_calls = 0

    def publisher(*_args, **_kwargs):
        nonlocal publisher_calls
        publisher_calls += 1

    runner = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=lambda **_kwargs: [
            {"text": "X", "context": "X is too short."}
        ],
        preview_builder=lambda **_kwargs: preview,
        publisher=publisher,
        state_path=tmp_path / "state.json",
    )

    with pytest.raises(AcceptanceFailure, match="no_approved_vocabulary"):
        runner.run(page_id)

    assert publisher_calls == 0
    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_existing_target_is_updated_without_creating_duplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    payload = VocabularyPublishPayload(
        word="challenge assumptions",
        source_page_id=page_id,
        meaning="Old meaning.",
    )
    workspace.add_page(
        workspace.config.vocabulary_data_source_id,
        vocabulary_page_properties(payload),
        page_id="existing-target-vocabulary",
    )

    result = _runner(
        workspace,
        page_id,
        tmp_path / "missing-state.json",
        monkeypatch,
    ).run(page_id)

    assert result.report.counts["planned_create"] == 1
    assert result.report.counts["planned_update"] == 1
    assert result.report.counts["first_created"] == 1
    assert result.report.counts["first_updated"] == 1
    assert result.report.counts["retry_created"] == 0
    assert result.report.counts["retry_updated"] == 2
    assert len(_target_vocabulary_pages(workspace)) == 2


def test_duplicate_vocabulary_identity_stops_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    payload = VocabularyPublishPayload(
        word="fundraising",
        source_page_id=page_id,
    )
    for suffix in ("one", "two"):
        workspace.add_page(
            workspace.config.vocabulary_data_source_id,
            vocabulary_page_properties(payload),
            page_id=f"duplicate-{suffix}",
        )

    with pytest.raises(
        AcceptanceFailure,
        match="vocabulary_identity_not_unique",
    ):
        _runner(
            workspace,
            page_id,
            tmp_path / "state.json",
            monkeypatch,
        ).run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_manual_fields_stop_existing_target_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    payload = VocabularyPublishPayload(
        word="fundraising",
        source_page_id=page_id,
        personal_note="Keep this private note.",
    )
    workspace.add_page(
        workspace.config.vocabulary_data_source_id,
        vocabulary_page_properties(payload),
        page_id="manual-target",
    )

    with pytest.raises(
        AcceptanceFailure,
        match="manual_vocabulary_fields_present",
    ):
        _runner(
            workspace,
            page_id,
            tmp_path / "state.json",
            monkeypatch,
        ).run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_incomplete_enrichment_stops_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    preview = _preview(page_id)
    preview["approved_vocabulary"][0]["meaning"] = ""

    def preview_builder(*, page_id: str, notion=None):
        return preview

    runner = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=lambda **_kwargs: [
            {
                "text": item["word"],
                "context": item.get("original_context", ""),
            }
            for item in [
                *preview["approved_vocabulary"],
                {
                    "word": preview["rejected_candidates"][0]["word"],
                    "original_context": "X is too short.",
                },
            ]
        ],
        preview_builder=preview_builder,
        state_path=tmp_path / "state.json",
    )

    with pytest.raises(
        AcceptanceFailure,
        match="enrichment_artifact_incomplete",
    ):
        runner.run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_exact_highlight_target_must_match_pipeline_word(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    preview = _preview(page_id)

    def highlight_reader(*, page_id: str, notion=None):
        return [
            {
                "text": "challenge assumption",
                "context": preview["approved_vocabulary"][0][
                    "original_context"
                ],
            },
            {
                "text": "fundraising",
                "context": preview["approved_vocabulary"][1][
                    "original_context"
                ],
            },
            {"text": "X", "context": "X is too short."},
        ]

    runner = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=highlight_reader,
        preview_builder=lambda **_kwargs: preview,
        read_only_preview_builder=lambda **_kwargs: preview,
        state_path=tmp_path / "state.json",
        artifact_root=tmp_path / "artifact-data",
    )

    with pytest.raises(AcceptanceFailure, match="highlight_target_changed"):
        runner.dry_run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_approved_context_must_match_highlight_context(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    preview = _preview(page_id)

    def highlight_reader(*, page_id: str, notion=None):
        return [
            {
                "text": "challenge assumptions",
                "context": "A different sentence.",
            },
            {
                "text": "fundraising",
                "context": preview["approved_vocabulary"][1][
                    "original_context"
                ],
            },
            {"text": "X", "context": "X is too short."},
        ]

    runner = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        highlight_reader=highlight_reader,
        preview_builder=lambda **_kwargs: preview,
        read_only_preview_builder=lambda **_kwargs: preview,
        state_path=tmp_path / "state.json",
        artifact_root=tmp_path / "artifact-data",
    )

    with pytest.raises(AcceptanceFailure, match="highlight_context_changed"):
        runner.dry_run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_case_only_existing_identity_mismatch_stops_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    payload = VocabularyPublishPayload(
        word="Fundraising",
        source_page_id=page_id,
    )
    workspace.add_page(
        workspace.config.vocabulary_data_source_id,
        vocabulary_page_properties(payload),
        page_id="case-mismatch-target",
    )

    with pytest.raises(
        AcceptanceFailure,
        match="vocabulary_identity_normalization_mismatch",
    ):
        _runner(
            workspace,
            page_id,
            tmp_path / "state.json",
            monkeypatch,
        ).run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_pending_codex_artifact_is_a_stable_safe_stop(
    tmp_path: Path,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)

    def preview_builder(*, page_id: str, notion=None):
        raise CodexArtifactPendingError("private artifact paths")

    runner = VocabularyOwnerAcceptanceRunner(
        workspace,
        workspace.config,
        read_only_preview_builder=preview_builder,
        preview_builder=preview_builder,
        state_path=tmp_path / "state.json",
        artifact_root=tmp_path / "artifact-data",
    )

    with pytest.raises(
        AcceptanceFailure,
        match="vocabulary_artifact_pending",
    ):
        runner.dry_run(page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_guard_blocks_non_vocabulary_writes() -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    policy = VocabularyAcceptancePolicy(
        config=workspace.config,
        source_page_id=page_id,
    )
    policy.set_expected_words(["fundraising"])
    guard = VocabularyAcceptanceGuard(workspace, policy)

    with pytest.raises(GuardViolation, match="non_vocabulary_write_blocked"):
        guard.pages.create(
            parent={
                "data_source_id": workspace.config.expression_data_source_id
            },
            properties={},
        )
    with pytest.raises(GuardViolation, match="block_append_blocked"):
        guard.blocks.children.append(block_id=page_id, children=[])
    with pytest.raises(GuardViolation, match="schema_mutation_blocked"):
        guard.data_sources.update(
            data_source_id=workspace.config.vocabulary_data_source_id,
            properties={},
        )
    with pytest.raises(GuardViolation, match="delete_or_archive_blocked"):
        guard.pages.delete(page_id=page_id)


def test_source_page_must_belong_to_podcast_library(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    wrong_page_id = workspace.add_page(
        workspace.config.expression_data_source_id,
        {"Expression": title_property("wrong role")},
        page_id="wrong-role-page",
    )

    with pytest.raises(
        AcceptanceFailure,
        match="target_page_outside_group",
    ):
        _runner(
            workspace,
            wrong_page_id,
            tmp_path / "state.json",
            monkeypatch,
        ).dry_run(wrong_page_id)

    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []


def test_public_reports_are_redacted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = FakeNotion()
    page_id = _source_page(workspace)
    result = _runner(
        workspace,
        page_id,
        tmp_path / "state.json",
        monkeypatch,
    ).dry_run(page_id)
    secrets = [
        workspace.config.token,
        workspace.config.target_parent_page_id,
        *workspace.config.data_source_ids.values(),
        page_id,
        "https://notion.so/private-page",
    ]

    rendered = render_redacted_report(result.report, secrets=secrets)
    failure = render_failure_report(workspace.config.token)

    assert all(secret not in rendered for secret in secrets)
    assert all(secret not in failure for secret in secrets)
    assert '"secrets_redacted": true' in rendered
    assert json.loads(failure)["failure"] == "acceptance_failed"


def test_live_cli_requires_exact_confirmation_before_client_creation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client_calls = 0

    def forbidden_client(*_args, **_kwargs):
        nonlocal client_calls
        client_calls += 1
        raise AssertionError("client must not be created")

    monkeypatch.setattr(
        run_vocabulary_owner_acceptance,
        "create_notion_client",
        forbidden_client,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_vocabulary_owner_acceptance.py",
            "--page-id",
            "private-page-id",
            "--confirmation",
            LIVE_CONFIRMATION + "-wrong",
        ],
    )

    assert run_vocabulary_owner_acceptance.main() == 2
    assert client_calls == 0
    assert json.loads(capsys.readouterr().out)["failure"] == (
        "live_confirmation_missing"
    )
