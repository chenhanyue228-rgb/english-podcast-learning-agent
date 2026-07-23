from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

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
from src.notion import learning_publisher, target_binding
from src.notion.target_binding import validate_notion_target_binding

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
    assert (
        result.report.reviewed_pr_9_head
        == "3a667afbe9c07b406ef21f9b1afb5e068fd541f3"
    )
    assert (
        result.report.integrated_main_head
        == "a93c92ebc29ebbf1392f4e8089c99ac3326d9f78"
    )
    assert result.report.pr_9_status == "MERGED"
    assert result.report.final_pr_9_integration_verified is True
    assert result.report.workflow_behavior_verified is True
    assert result.report.target_binding_verified is True
    assert result.report.configured_parent_matches_expected is True
    assert result.report.all_data_sources_same_group is True
    assert result.report.internal_relations_verified is True
    assert len(result.report.target_parent_fingerprint) == 8
    assert len(result.report.target_group_fingerprint) == 8
    assert result.evidence.podcast_added_on_first_publish == 1
    assert result.evidence.expressions_added_on_first_publish == 2
    assert len(workspace.target_podcast_pages()) == 1
    assert len(workspace.target_expression_pages()) == 2
    first_snapshot_query = workspace.api_calls.index("data_sources.query")
    assert "data_sources.retrieve" in workspace.api_calls[:first_snapshot_query]
    assert "databases.retrieve" in workspace.api_calls[:first_snapshot_query]
    assert "pages.retrieve" in workspace.api_calls[:first_snapshot_query]
    assert not {
        "pages.create",
        "pages.update",
        "blocks.children.append",
        "data_sources.update",
        "databases.create",
        "databases.update",
        "pages.delete",
        "blocks.delete",
    }.intersection(workspace.api_calls[:first_snapshot_query])


def test_owner_acceptance_allows_verified_target_page_reads(
    monkeypatch,
) -> None:
    workspace = FakeNotion()
    monkeypatch.setattr(
        learning_publisher,
        "ensure_notion_target_binding_for_write",
        target_binding.ensure_notion_target_binding_for_write,
    )
    monkeypatch.setattr(
        learning_publisher,
        "ensure_notion_page_belongs_to_role",
        target_binding.ensure_notion_page_belongs_to_role,
    )

    result = OwnerAcceptanceRunner(workspace, workspace.config).run(
        complete_payload()
    )

    assert result.report.status == "passed"
    assert workspace.api_calls.count("pages.retrieve") >= 2


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
        reviewed_pr_9_head=workspace.config.vocabulary_data_source_id,
        integrated_main_head=workspace.config.weekly_data_source_id,
        pr_9_status=workspace.config.token,
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
    assert (
        '"reviewed_pr_9_head": '
        '"3a667afbe9c07b406ef21f9b1afb5e068fd541f3"'
        in rendered
    )
    assert (
        '"integrated_main_head": '
        '"a93c92ebc29ebbf1392f4e8089c99ac3326d9f78"'
        in rendered
    )
    assert '"pr_9_status": "MERGED"' in rendered
    assert '"final_pr_9_integration_verified": true' in rendered


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
    validate_notion_target_binding(
        workspace,
        workspace.config.as_notion_config(),
    )

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
        "NOTION_TARGET_PARENT_PAGE_ID": "target-parent",
    }

    config = load_acceptance_config(env=env)

    assert config.setup_state == "complete"
    assert len(set(config.data_source_ids.values())) == 4
    assert config.target_parent_page_id == "target-parent"


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    (
        ("parent", "target_parent_mismatch"),
        ("mixed", "configured_data_sources_not_same_group"),
        ("relation", "target_relation_outside_group"),
    ),
)
def test_target_binding_failure_prevents_snapshot_and_publisher(
    mutation: str,
    expected_code: str,
) -> None:
    workspace = FakeNotion()
    publisher_calls = 0

    def publisher(*_args, **_kwargs):
        nonlocal publisher_calls
        publisher_calls += 1

    if mutation == "parent":
        workspace.config = replace(
            workspace.config,
            target_parent_page_id="different-target-parent",
        )
    elif mutation == "mixed":
        original_retrieve = workspace.databases.retrieve
        podcast_database_id = workspace.database_id_by_data_source_id[
            workspace.config.podcast_data_source_id
        ]

        def mixed_retrieve(**kwargs):
            response = original_retrieve(**kwargs)
            if kwargs["database_id"] == podcast_database_id:
                response["parent"]["page_id"] = "different-target-parent"
            return response

        workspace.databases.retrieve = mixed_retrieve
    else:
        workspace.schemas[
            workspace.config.expression_data_source_id
        ]["Source Podcast"]["relation"]["data_source_id"] = (
            "outside-podcast-data-source"
        )

    with pytest.raises(AcceptanceFailure, match=expected_code):
        OwnerAcceptanceRunner(
            workspace,
            workspace.config,
            publisher=publisher,
        ).run(complete_payload())

    assert publisher_calls == 0
    assert workspace.data_sources.query_calls == []
    assert workspace.pages.create_calls == []
    assert workspace.pages.update_calls == []
    assert workspace.pages.delete_calls == []
    assert workspace.blocks.children.append_calls == []
    assert workspace.blocks.delete_calls == []
    assert workspace.data_sources.update_calls == []
    assert workspace.databases.create_calls == []
    assert workspace.databases.update_calls == []
