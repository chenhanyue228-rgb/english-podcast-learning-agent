from __future__ import annotations

from copy import deepcopy

import pytest

from scripts.acceptance.podcast_owner_acceptance import (
    AcceptanceFailure,
    AcceptanceGuard,
    AcceptancePolicy,
    AcceptanceReport,
    GuardViolation,
    OwnerAcceptanceRunner,
    PodcastIdentity,
    TemporarySnapshotStore,
    load_acceptance_config,
    render_failure_report,
    render_redacted_report,
)
from src.analyzer.models import (
    AIAnalysisResult,
    LearningItem,
    PodcastMetadata,
    SentencePattern,
    Summary,
)
from src.notion.learning_publisher import (
    CompletePodcastLearningPayload,
    LearningPublisherError,
    publish_complete_learning_materials,
)

from tests.acceptance.fakes import (
    FakeNotion,
    relation_property,
)


def analysis_result() -> AIAnalysisResult:
    return AIAnalysisResult(
        summary=Summary(
            english="A private summary.",
            chinese="私密摘要。",
            key_points=["A private key point."],
        ),
        podcast_metadata=PodcastMetadata(
            title="Owner acceptance episode",
            topic="Leadership",
            difficulty="Intermediate",
            short_summary="A private short summary.",
        ),
        learning_items=[
            LearningItem(
                text="take ownership",
                category="Business Phrase",
                meaning="Accept responsibility.",
                chinese_meaning="承担责任",
                usage_context="Private usage context.",
                context_sentence="Teams take ownership.",
                example_sentence="We took ownership.",
                highlight_color="blue",
                commonness="High",
            )
        ],
        sentence_patterns=[
            SentencePattern(
                text="What we are seeing is...",
                meaning="Introduce an observation.",
                chinese_meaning="介绍观察结果。",
                usage_context="Private pattern context.",
                context_sentence="What we are seeing is progress.",
                example_sentence="What we are seeing is change.",
                highlight_color="orange",
                commonness="Medium",
            )
        ],
    )


def complete_payload(
    *,
    source_url: str | None = "https://podcasts.apple.com/example?id=owner",
    source_type: str = "Podcast",
) -> CompletePodcastLearningPayload:
    return CompletePodcastLearningPayload(
        title="Input title",
        source_url=source_url,
        source_type=source_type,
        transcript="Private transcript with take ownership.",
        analysis=analysis_result(),
        processed_date="2026-07-23",
    )


def build_guard(workspace: FakeNotion) -> AcceptanceGuard:
    payload = complete_payload()
    policy = AcceptancePolicy(
        config=workspace.config,
        identity=PodcastIdentity.from_payload(payload),
        expected_expression_keys=frozenset(
            (item.text, item.category)
            for item in payload.analysis.all_learning_items()
        ),
    )
    return AcceptanceGuard(workspace, policy)


def test_first_publish_snapshot_comparison_passes() -> None:
    workspace = FakeNotion()

    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        complete_payload()
    )

    assert result.report.status == "passed"
    assert result.report.depends_on_pr_9 is True
    assert (
        result.report.initial_pr_9_head
        == "7a0d240cfb3c8ccf935ebc96bf7b671994e332ef"
    )
    assert result.report.final_pr_9_integration_verified is False
    assert result.evidence.podcast_added_on_first_publish == 1
    assert result.evidence.expressions_added_on_first_publish == 2
    assert len(workspace.target_podcast_pages()) == 1
    assert len(workspace.target_expression_pages()) == 2


def test_second_publish_adds_nothing() -> None:
    workspace = FakeNotion()

    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        complete_payload()
    )

    assert result.evidence.podcast_added_on_second_publish == 0
    assert result.evidence.expressions_added_on_second_publish == 0
    assert len(workspace.target_podcast_pages()) == 1
    assert len(workspace.target_expression_pages()) == 2


def test_duplicate_podcast_body_fails_acceptance() -> None:
    workspace = FakeNotion()
    workspace.duplicate_body_on_target_update = True

    with pytest.raises(
        AcceptanceFailure,
        match="podcast_body_structure_invalid",
    ):
        OwnerAcceptanceRunner(workspace, workspace.config).run(complete_payload())


def test_missing_expression_fails_acceptance() -> None:
    workspace = FakeNotion()
    calls = 0

    def publisher(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = publish_complete_learning_materials(*args, **kwargs)
        if calls == 1:
            missing = workspace.target_expression_pages()[-1]
            del workspace.pages_by_id[missing.page_id]
        return result

    with pytest.raises(AcceptanceFailure, match="expression_count_mismatch"):
        OwnerAcceptanceRunner(
            workspace,
            workspace.config,
            publisher=publisher,
        ).run(complete_payload())


def test_duplicate_expression_fails_acceptance() -> None:
    workspace = FakeNotion()
    calls = 0

    def publisher(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = publish_complete_learning_materials(*args, **kwargs)
        if calls == 1:
            original = workspace.target_expression_pages()[0]
            duplicate = deepcopy(original)
            duplicate.page_id = workspace.next_id("target-expression")
            workspace.pages_by_id[duplicate.page_id] = duplicate
        return result

    with pytest.raises(AcceptanceFailure, match="expression_count_mismatch"):
        OwnerAcceptanceRunner(
            workspace,
            workspace.config,
            publisher=publisher,
        ).run(complete_payload())


def test_wrong_expression_relation_fails_acceptance() -> None:
    workspace = FakeNotion()
    calls = 0

    def publisher(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = publish_complete_learning_materials(*args, **kwargs)
        if calls == 1:
            expression = workspace.target_expression_pages()[0]
            expression.properties["Source Podcast"] = relation_property(
                "existing-podcast"
            )
        return result

    with pytest.raises(
        AcceptanceFailure,
        match="expression_count_mismatch",
    ):
        OwnerAcceptanceRunner(
            workspace,
            workspace.config,
            publisher=publisher,
        ).run(complete_payload())


def test_vocabulary_write_is_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="vocabulary_write_blocked"):
        guard.pages.create(
            parent={"data_source_id": workspace.config.vocabulary_data_source_id},
            properties={},
        )


def test_weekly_review_write_is_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="weekly_review_write_blocked"):
        guard.pages.create(
            parent={"data_source_id": workspace.config.weekly_data_source_id},
            properties={},
        )


def test_database_creation_is_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="database_creation_blocked"):
        guard.databases.create(parent={"page_id": "private-parent"})
    assert workspace.databases.create_calls == []


def test_schema_mutation_is_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="schema_mutation_blocked"):
        guard.data_sources.update(
            data_source_id=workspace.config.expression_data_source_id,
            properties={"Unexpected": {"type": "rich_text"}},
        )
    assert workspace.data_sources.update_calls == []


def test_unexpected_page_update_is_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="unexpected_page_update_blocked"):
        guard.pages.update(page_id="existing-podcast", properties={})
    assert workspace.pages.update_calls == []


def test_delete_and_archive_are_blocked() -> None:
    workspace = FakeNotion()
    guard = build_guard(workspace)

    with pytest.raises(GuardViolation, match="delete_or_archive_blocked"):
        guard.pages.delete(page_id="existing-podcast")
    with pytest.raises(GuardViolation, match="delete_or_archive_blocked"):
        guard.pages.update(page_id="existing-podcast", archived=True)
    assert workspace.pages.delete_calls == []
    assert workspace.pages.update_calls == []


def test_all_public_reports_are_redacted() -> None:
    workspace = FakeNotion()
    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        complete_payload()
    )
    sensitive_values = [
        workspace.config.token,
        *workspace.config.data_source_ids.values(),
        *workspace.pages_by_id,
        "https://podcasts.apple.com/example?id=owner",
        "https://notion.so/private-page",
        "Private transcript with take ownership.",
        "private context",
    ]

    rendered = render_redacted_report(
        result.report,
        secrets=sensitive_values,
    )
    tainted_report = AcceptanceReport(
        status=workspace.config.token,
        depends_on_pr_9=True,
        initial_pr_9_head=workspace.config.expression_data_source_id,
        final_pr_9_integration_verified=False,
        pre_publish_snapshot="https://notion.so/private-page",
        first_publish_verification="passed",
        second_publish_verification="passed",
        guard_enforced=True,
        secrets_redacted=False,
        snapshot_cleanup_confirmed=True,
        counts={workspace.config.podcast_data_source_id: 99},
    )
    tainted = render_redacted_report(tainted_report)
    failure = render_failure_report(workspace.config.token)

    assert all(value not in rendered for value in sensitive_values)
    assert all(value not in tainted for value in sensitive_values)
    assert all(value not in failure for value in sensitive_values)
    assert '"secrets_redacted": true' in rendered
    assert '"secrets_redacted": true' in tainted
    assert '"secrets_redacted": true' in failure
    assert (
        '"initial_pr_9_head": '
        '"7a0d240cfb3c8ccf935ebc96bf7b671994e332ef"'
        in rendered
    )
    assert '"final_pr_9_integration_verified": false' in rendered


def test_temporary_snapshots_are_deleted_in_finally(tmp_path) -> None:
    workspace = FakeNotion()
    stores: list[TemporarySnapshotStore] = []

    def store_factory() -> TemporarySnapshotStore:
        store = TemporarySnapshotStore(root=tmp_path)
        stores.append(store)
        return store

    def exploding_publisher(*args, **kwargs):
        raise RuntimeError(
            "secret-owner-token https://notion.so/private-page private body"
        )

    with pytest.raises(AcceptanceFailure, match="acceptance_execution_failed"):
        OwnerAcceptanceRunner(
            workspace,
            workspace.config,
            publisher=exploding_publisher,
            snapshot_store_factory=store_factory,
        ).run(complete_payload())

    assert len(stores) == 1
    assert stores[0].cleaned is True
    assert not stores[0].path.exists()
    assert list(tmp_path.iterdir()) == []


def test_pr_9_partial_failure_recovery_reaches_acceptable_final_state() -> None:
    workspace = FakeNotion()
    payload = complete_payload()
    workspace.pages.fail_expression_create_at = 2

    with pytest.raises(LearningPublisherError):
        publish_complete_learning_materials(
            payload,
            notion=workspace,
            podcast_database_id=workspace.config.podcast_data_source_id,
            expression_database_id=workspace.config.expression_data_source_id,
        )

    assert len(workspace.target_podcast_pages()) == 1
    assert len(workspace.target_expression_pages()) == 1
    workspace.pages.fail_expression_create_at = None

    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        payload,
        allow_partial_recovery=True,
    )

    assert result.report.status == "passed"
    assert result.evidence.podcast_added_on_first_publish == 0
    assert result.evidence.expressions_added_on_first_publish == 1
    assert result.evidence.podcast_added_on_second_publish == 0
    assert result.evidence.expressions_added_on_second_publish == 0
    assert len(workspace.target_expression_pages()) == 2


def test_local_audio_identity_uses_title_and_source_type() -> None:
    workspace = FakeNotion()

    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        complete_payload(source_url=None, source_type="Local Audio")
    )

    assert result.report.status == "passed"
    assert len(workspace.target_podcast_pages()) == 1


def test_config_requires_complete_setup_and_four_distinct_data_sources() -> None:
    env = {
        "EPLA_NOTION_SETUP_STATE": "complete",
        "NOTION_TOKEN": "private-token",
        "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast",
        "NOTION_EXPRESSION_DATABASE_ID": "expression",
        "NOTION_VOCABULARY_DATABASE_ID": "vocabulary",
        "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly",
    }

    config = load_acceptance_config(env=env)

    assert config.setup_state == "complete"
    assert len(set(config.data_source_ids.values())) == 4
