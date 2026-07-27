from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from src.agent.automatic_weekly_reflection_runtime import (
    AutomaticCodexReflectionProvider,
    AutomaticCodexWeeklyReviewProvider,
    AutomaticWeeklyReflectionError,
    RetryableAutomaticWeeklyReflectionError,
    WeeklyIdentityInspection,
    automatic_weekly_process_lock,
    inspect_weekly_identity,
    run_bounded_automatic_weekly_reflection,
    scheduled_period_if_due,
    validate_strict_reflection_artifact,
    validate_strict_weekly_artifact,
    verify_weekly_page_integrity,
)
from src.agent.weekly_reflection_scheduler import (
    WeeklyReflectionSchedule,
    save_schedule,
)
from src.notion.config import NotionConfig
from src.notion.weekly_reflection_writer import (
    WeeklyReflectionPublishPayload,
    weekly_reflection_body_blocks,
)
from src.skill_runtime.codex_cli import CodexRuntimeError
from src.weekly_review.reflection_analyzer import (
    PlaceholderReflectionProvider,
    ReflectionAnalyzer,
    ReflectionGenerationError,
    load_reflection_prompt,
    load_reflection_schema,
)
from src.workflow.weekly_reflection_pipeline import WeeklyReflectionPipelineError


LOCAL = ZoneInfo("Asia/Shanghai")
DUE = datetime(2026, 7, 25, 10, 0, tzinfo=LOCAL)


def _config(suffix: str = "") -> NotionConfig:
    return NotionConfig(
        token=f"private-token{suffix}",
        podcast_database_id=f"private-podcast{suffix}",
        expression_database_id=f"private-expression{suffix}",
        weekly_database_id=f"private-weekly{suffix}",
        vocabulary_database_id=f"private-vocabulary{suffix}",
        target_parent_page_id=f"private-parent{suffix}",
    )


def _schedule(*, enabled: bool = True) -> WeeklyReflectionSchedule:
    return WeeklyReflectionSchedule(
        enabled=enabled,
        weekday="saturday",
        hour=10,
        minute=0,
        timezone_mode="local",
        schema_version=1,
        effective_at="2026-07-01T00:00:00+00:00",
    )


def _weekly_context(
    *,
    today,
    generated_at: str,
    include_assets: bool = True,
) -> dict:
    podcast = {
        "page_id": "podcast-page",
        "title": "Negotiation",
        "date": today.isoformat(),
        "topic": "Negotiation",
        "difficulty": "Intermediate",
        "url": "https://example.com/audio",
        "summary": {
            "english": "Negotiation is relationship management.",
            "chinese": "谈判是关系管理。",
        },
        "key_takeaways": ["Listen before influencing."],
        "transcript_available": True,
    }
    expressions = (
        [
            {
                "expression": "challenge assumptions",
                "category": "Business Phrase",
                "meaning": "Question an idea constructively.",
                "chinese_meaning": "质疑假设",
                "usage_context": "A strategy meeting.",
                "example": "Let's challenge our assumptions.",
                "source_page_id": "podcast-page",
            }
        ]
        if include_assets
        else []
    )
    return {
        "metadata": {
            "period_start": (today - timedelta(days=7)).isoformat(),
            "period_end": today.isoformat(),
            "generated_at": generated_at,
            "source": "Podcast Library",
        },
        "podcasts": [podcast],
        "learning_expressions": expressions,
        "ai_highlights": [],
        "user_vocabulary": [],
    }


def _reflection() -> dict:
    return {
        "weekly_theme": {
            "category": "Negotiation",
            "theme": "Negotiation as relationship management",
        },
        "mindset_shifts": [
            {
                "before": "I treated negotiation as winning.",
                "after": "I now treat it as joint problem solving.",
                "evidence": [
                    {
                        "source": "Negotiation",
                        "supporting_concept": "Listen before influencing.",
                    }
                ],
                "confidence": 0.9,
            }
        ],
        "cross_content_patterns": [
            "Careful framing turns disagreement into joint inquiry.",
            "Shared outcomes make constraints easier to discuss.",
        ],
        "professional_actions": [
            "Restate the shared outcome before discussing constraints."
        ],
    }


def _weekly_review(context: dict) -> dict:
    metadata = context["metadata"]
    return {
        "period": {
            "start_date": metadata["period_start"],
            "end_date": metadata["period_end"],
            "generated_at": metadata["generated_at"],
            "source": metadata["source"],
        },
        "core_idea": {
            "idea": (
                "Disagreement improves when the problem becomes the shared "
                "object of attention."
            ),
            "why_it_matters": (
                "It changes conflict from positional defense into "
                "collaborative inquiry."
            ),
            "refined_understanding": (
                "Negotiation is relationship management supported by "
                "precise framing."
            ),
        },
        "mindset_shift": {
            "before": "I treated negotiation as winning.",
            "now": "I now treat it as joint problem solving.",
        },
        "ideas_worth_compounding": [
            {
                "idea": "Listening reveals the problem behind a position.",
                "why_it_matters": "It prevents solving the wrong problem.",
                "application": (
                    "Ask one clarifying question before proposing a solution."
                ),
                "source_reference": "Negotiation",
            },
            {
                "idea": "Framing makes disagreement feel shared.",
                "why_it_matters": (
                    "People collaborate more readily around a shared object."
                ),
                "application": (
                    "Name the shared outcome before discussing constraints."
                ),
                "source_reference": "Negotiation",
            },
        ],
        "expressions_worth_reusing": [
            {
                "expression": "challenge assumptions",
                "contextual_meaning": (
                    "Test beliefs without attacking people."
                ),
                "reusable_example": (
                    "Let's challenge our assumptions before choosing."
                ),
                "communication_function": "Constructive disagreement",
            },
            {
                "expression": "joint problem solving",
                "contextual_meaning": "Treat both sides as collaborators.",
                "reusable_example": (
                    "Let's approach this as joint problem solving."
                ),
                "communication_function": "Collaborative framing",
            },
            {
                "expression": "shared outcome",
                "contextual_meaning": "Name the result both sides want.",
                "reusable_example": (
                    "Can we begin by confirming the shared outcome?"
                ),
                "communication_function": "Goal alignment",
            },
        ],
        "language_thinking_connection": (
            "The phrase 'joint problem solving' supplies a professional "
            "frame in which the other person is a collaborator and the "
            "problem becomes the shared object of attention."
        ),
        "next_week_application": {
            "scenario": "A stakeholder challenges the launch sequence.",
            "behavior": (
                "Restate the shared outcome before discussing constraints."
            ),
            "phrase_to_use": "Let's treat this as joint problem solving.",
            "completion_condition": (
                "Use the phrase once and record whether positions become "
                "options."
            ),
        },
        "sources": [
            {
                "page_id": "podcast-page",
                "title": "Negotiation",
                "url": "https://example.com/audio",
            }
        ],
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "schedule": tmp_path / "schedule.json",
        "state": tmp_path / "state.json",
        "artifacts": tmp_path / "artifacts",
        "lock": tmp_path / "worker.lock",
        "status": tmp_path / "runtime_status.json",
        "log": tmp_path / "runtime.jsonl",
    }


def _context_extractor(*, notion, output_path, today, generated_at):
    assert notion is not None
    context = _weekly_context(today=today, generated_at=generated_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(context), encoding="utf-8")
    return context, SimpleNamespace(), output_path


class CodexFixture:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.private_env_seen: list[dict[str, str] | None] = []

    def __call__(self, **kwargs):
        stage = kwargs["stage"]
        self.calls.append(stage)
        self.private_env_seen.append(kwargs.get("env"))
        request = json.loads(
            kwargs["request_path"].read_text(encoding="utf-8")
        )
        weekly_context = request["input"]["weekly_learning_context"]
        if "reflection analysis" in stage:
            payload = _reflection()
            if len(weekly_context["podcasts"]) <= 1:
                payload["cross_content_patterns"] = []
        else:
            payload = _weekly_review(weekly_context)
        validated = kwargs["validator"](payload)
        kwargs["output_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_path"].write_text(
            json.dumps(validated),
            encoding="utf-8",
        )
        return validated


class RuntimeEndpoint:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "weekly-page"}


class RuntimeNotion:
    def __init__(self) -> None:
        self.pages = RuntimeEndpoint()
        self.blocks = SimpleNamespace(children=SimpleNamespace())
        self.data_sources = SimpleNamespace()
        self.databases = SimpleNamespace()


def _pipeline(**kwargs):
    context = json.loads(
        kwargs["weekly_learning_context_path"].read_text(encoding="utf-8")
    )
    reflection = kwargs["reflection_provider"].generate(
        "reflection prompt",
        {"weekly_learning_context": context},
    )
    review = kwargs["weekly_review_provider"].generate(
        "weekly prompt",
        {
            "weekly_learning_context": context,
            "reflection_context": reflection,
        },
    )
    if not kwargs["dry_run"]:
        kwargs["notion"].pages.create(
            parent={
                "data_source_id": kwargs[
                    "weekly_reflection_database_id"
                ]
            },
            properties={},
            children=[],
        )
    return SimpleNamespace(weekly_review=review)


def _pipeline_fails_before_write(**kwargs):
    context = json.loads(
        kwargs["weekly_learning_context_path"].read_text(encoding="utf-8")
    )
    reflection = kwargs["reflection_provider"].generate(
        "reflection prompt",
        {"weekly_learning_context": context},
    )
    review = kwargs["weekly_review_provider"].generate(
        "weekly prompt",
        {
            "weekly_learning_context": context,
            "reflection_context": reflection,
        },
    )
    if not kwargs["dry_run"]:
        raise RuntimeError("failure-before-write")
    return SimpleNamespace(weekly_review=review)


def _trusted_weekly_body(artifact_root: Path) -> list[dict]:
    reflection_path = next(
        artifact_root.glob("**/reflection_context.json")
    )
    weekly_path = next(
        artifact_root.glob("**/weekly_review_codex.json")
    )
    payload = WeeklyReflectionPublishPayload(
        weekly_review=json.loads(
            weekly_path.read_text(encoding="utf-8")
        ),
        reflection_context=json.loads(
            reflection_path.read_text(encoding="utf-8")
        ),
    )
    return weekly_reflection_body_blocks(payload)


def _run(
    tmp_path: Path,
    *,
    now: datetime = DUE,
    context_extractor=_context_extractor,
    pipeline_runner=_pipeline,
    identity_counter=None,
    codex_generator=None,
    binding_validator=None,
):
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    counts = iter((0, 1))
    return run_bounded_automatic_weekly_reflection(
        now=now,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=(
            binding_validator
            or (lambda *_args, **_kwargs: SimpleNamespace(valid=True))
        ),
        context_extractor=context_extractor,
        pipeline_runner=pipeline_runner,
        identity_counter=(
            identity_counter
            or (lambda *_args, **_kwargs: next(counts))
        ),
        codex_generator=codex_generator or CodexFixture(),
    )


def _prepare_publish_intent_without_write(
    tmp_path: Path,
) -> tuple[dict[str, Path], CodexFixture, object]:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    codex = CodexFixture()
    report = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=_pipeline_fails_before_write,
        identity_counter=lambda *_a, **_k: 0,
        codex_generator=codex,
    )
    return paths, codex, report


def test_due_logic_before_at_after_and_sleep_catch_up() -> None:
    schedule = _schedule()

    assert (
        scheduled_period_if_due(
            datetime(2026, 7, 25, 9, 59, tzinfo=LOCAL),
            schedule,
        )
        is None
    )
    exact = scheduled_period_if_due(DUE, schedule)
    after = scheduled_period_if_due(
        datetime(2026, 7, 25, 10, 1, tzinfo=LOCAL),
        schedule,
    )
    wake = scheduled_period_if_due(
        datetime(2026, 7, 26, 11, 0, tzinfo=LOCAL),
        schedule,
    )

    assert exact is not None and exact.key == "2026-W30"
    assert after is not None and after.key == exact.key
    assert wake is not None and wake.key == exact.key


def test_due_logic_keeps_only_the_latest_unfinished_period() -> None:
    schedule = _schedule()
    friday = scheduled_period_if_due(
        datetime(2026, 7, 31, 9, 59, tzinfo=LOCAL),
        schedule,
    )
    next_saturday = scheduled_period_if_due(
        datetime(2026, 8, 1, 10, 0, tzinfo=LOCAL),
        schedule,
    )

    assert friday is not None and friday.key == "2026-W30"
    assert (
        next_saturday is not None
        and next_saturday.key == "2026-W31"
    )


def test_schedule_effective_at_prevents_historical_backfill() -> None:
    schedule = deepcopy(_schedule())
    schedule = WeeklyReflectionSchedule(
        **{
            **schedule.to_dict(),
            "effective_at": "2026-07-25T03:00:00+00:00",
        }
    )

    assert (
        scheduled_period_if_due(
            datetime(2026, 7, 25, 12, 0, tzinfo=LOCAL),
            schedule,
        )
        is None
    )


def test_not_due_and_paused_do_not_load_notion(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    calls = 0

    def config_loader():
        nonlocal calls
        calls += 1
        return _config()

    save_schedule(_schedule(), paths["schedule"])
    not_due = run_bounded_automatic_weekly_reflection(
        now=datetime(2026, 7, 25, 9, 59, tzinfo=LOCAL),
        schedule_path=paths["schedule"],
        config_loader=config_loader,
        runtime_status_path=paths["status"],
        log_path=paths["log"],
    )
    save_schedule(_schedule(enabled=False), paths["schedule"])
    paused = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        config_loader=config_loader,
        runtime_status_path=paths["status"],
        log_path=paths["log"],
    )

    assert not_due.status == "NOT_DUE"
    assert paused.status == "PAUSED"
    assert calls == 0


def test_first_publish_and_exact_retry_use_two_then_zero_codex_calls(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    codex = CodexFixture()
    identity_values = iter((0, 1))

    first = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=_pipeline,
        identity_counter=lambda *_a, **_k: next(identity_values),
        codex_generator=codex,
    )
    retry = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=5),
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=lambda **_kwargs: pytest.fail(
            "completed period must not be extracted again"
        ),
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "completed period must not enter pipeline"
        ),
        identity_counter=lambda *_a, **_k: pytest.fail(
            "completed local state must short-circuit"
        ),
        codex_generator=codex,
    )

    assert first.status == "PASS"
    assert first.reflection_codex_calls == 1
    assert first.weekly_review_codex_calls == 1
    assert first.weekly_created == 1
    assert first.weekly_updated == 0
    assert first.quality_score == 100
    assert retry.status == "ALREADY_COMPLETED"
    assert retry.reflection_codex_calls == 0
    assert retry.weekly_review_codex_calls == 0
    assert len(codex.calls) == 2
    assert first.podcast_writes == 0
    assert first.expression_writes == 0
    assert first.vocabulary_writes == 0
    assert first.schema_writes == 0
    assert first.historical_group_reads == 0
    assert first.historical_group_writes == 0


def test_crash_after_publish_reconciles_without_codex_or_second_write(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    codex = CodexFixture()
    first_identity = iter((0,))
    pipeline_calls = 0

    def crash_after_publish(**kwargs):
        nonlocal pipeline_calls
        pipeline_calls += 1
        result = _pipeline(**kwargs)
        if not kwargs["dry_run"]:
            raise RuntimeError("crash-after-publish")
        return result

    first = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=crash_after_publish,
        identity_counter=lambda *_a, **_k: next(first_identity),
        codex_generator=codex,
    )
    trusted_body = _trusted_weekly_body(paths["artifacts"])
    recovered_notion = SimpleNamespace(
        data_sources=_IdentityDataSources(
            [_identity_page(relations=["podcast-page"])]
        ),
        blocks=SimpleNamespace(
            children=_IdentityChildren(trusted_body)
        ),
    )
    second = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=2),
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=recovered_notion,
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "existing identity must reconcile before generation"
        ),
        codex_generator=codex,
    )

    assert first.status == "SAFE_STOP"
    assert first.weekly_created == 1
    assert second.status == "ALREADY_COMPLETED"
    assert second.reflection_codex_calls == 0
    assert second.weekly_review_codex_calls == 0
    assert len(codex.calls) == 2
    assert pipeline_calls == 2


def test_retry_reuses_validated_artifacts_after_pre_publish_failure(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    codex = CodexFixture()

    def fail_after_generation(**kwargs):
        generated = _pipeline(**kwargs).weekly_review
        compatibility_payload = {
            **generated,
            "source_page_ids": ["podcast-page"],
            "source_podcast_ids": ["podcast-page"],
        }
        kwargs["weekly_review_output_path"].write_text(
            json.dumps(compatibility_payload),
            encoding="utf-8",
        )
        raise WeeklyReflectionPipelineError("transient-before-publish")

    first = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=fail_after_generation,
        identity_counter=lambda *_a, **_k: 0,
        codex_generator=codex,
    )
    identity_values = iter((0, 1))
    recovered = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=15),
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=_pipeline,
        identity_counter=lambda *_a, **_k: next(identity_values),
        codex_generator=codex,
    )

    assert first.status == "RETRYABLE_FAILURE"
    assert first.reflection_codex_calls == 1
    assert first.weekly_review_codex_calls == 1
    assert recovered.status == "PASS"
    assert recovered.reflection_codex_calls == 0
    assert recovered.weekly_review_codex_calls == 0
    assert len(codex.calls) == 2


def test_state_file_cannot_be_reused_for_another_target_group(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    identities = iter((0, 1))

    first = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=RuntimeNotion(),
        config=_config("-one"),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=_pipeline,
        identity_counter=lambda *_a, **_k: next(identities),
        codex_generator=CodexFixture(),
    )
    second = run_bounded_automatic_weekly_reflection(
        now=DUE,
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion_factory=lambda _token: pytest.fail(
            "namespace mismatch must stop before Notion"
        ),
        config=_config("-two"),
    )

    assert first.status == "PASS"
    assert second.status == "SAFE_STOP"
    assert second.error_code == "weekly_runtime_state_namespace_mismatch"


def test_insufficient_data_skips_codex_and_notion_writer(
    tmp_path: Path,
) -> None:
    def extractor(*, notion, output_path, today, generated_at):
        context = _weekly_context(
            today=today,
            generated_at=generated_at,
            include_assets=False,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(context), encoding="utf-8")
        return context, SimpleNamespace(), output_path

    pipeline_calls = 0

    def pipeline(**_kwargs):
        nonlocal pipeline_calls
        pipeline_calls += 1

    report = _run(
        tmp_path,
        context_extractor=extractor,
        pipeline_runner=pipeline,
        identity_counter=lambda *_a, **_k: pytest.fail(
            "identity query is unnecessary for insufficient data"
        ),
    )

    assert report.status == "SKIPPED_INSUFFICIENT_DATA"
    assert report.reflection_codex_calls == 0
    assert report.weekly_review_codex_calls == 0
    assert report.weekly_created == 0
    assert pipeline_calls == 0


def test_target_binding_failure_prevents_context_and_pipeline(
    tmp_path: Path,
) -> None:
    report = _run(
        tmp_path,
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=False),
        context_extractor=lambda **_kwargs: pytest.fail(
            "invalid binding must stop extraction"
        ),
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "invalid binding must stop pipeline"
        ),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "target_binding_invalid"
    assert report.weekly_created == 0
    assert report.reflection_codex_calls == 0


def test_quality_failure_stops_before_live_pipeline(tmp_path: Path) -> None:
    calls: list[bool] = []

    def pipeline(**kwargs):
        calls.append(kwargs["dry_run"])
        context = json.loads(
            kwargs["weekly_learning_context_path"].read_text(
                encoding="utf-8"
            )
        )
        review = _weekly_review(context)
        review["ideas_worth_compounding"][0]["idea"] = review["core_idea"][
            "idea"
        ]
        return SimpleNamespace(weekly_review=review)

    report = _run(
        tmp_path,
        pipeline_runner=pipeline,
        identity_counter=lambda *_a, **_k: 0,
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_quality_gate_failed"
    assert report.weekly_created == 0
    assert calls == [True]


def test_duplicate_weekly_identity_fails_closed_before_codex(
    tmp_path: Path,
) -> None:
    report = _run(
        tmp_path,
        identity_counter=lambda *_a, **_k: 2,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "ambiguous identity must not publish"
        ),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_identity_not_unique"
    assert report.weekly_created == 0
    assert report.reflection_codex_calls == 0


def test_same_period_with_different_relation_fails_closed(
    tmp_path: Path,
) -> None:
    report = _run(
        tmp_path,
        identity_counter=lambda *_a, **_k: WeeklyIdentityInspection(
            same_period_count=1,
            exact_identity_count=0,
        ),
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "conflicting period must not publish"
        ),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_identity_conflict"
    assert report.weekly_created == 0


def test_partial_weekly_extraction_is_retryable_and_does_not_publish(
    tmp_path: Path,
) -> None:
    def extractor(*, notion, output_path, today, generated_at):
        context = _weekly_context(today=today, generated_at=generated_at)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(context), encoding="utf-8")
        return context, SimpleNamespace(failures=1), output_path

    report = _run(
        tmp_path,
        context_extractor=extractor,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "partial extraction must not publish"
        ),
    )

    assert report.status == "RETRYABLE_FAILURE"
    assert report.error_code == "weekly_learning_extraction_incomplete"
    assert report.weekly_created == 0
    assert report.reflection_codex_calls == 0


def test_process_overlap_skips_before_notion_client_use(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])

    with automatic_weekly_process_lock(paths["lock"]):
        report = run_bounded_automatic_weekly_reflection(
            now=DUE,
            schedule_path=paths["schedule"],
            state_path=paths["state"],
            artifact_root=paths["artifacts"],
            lock_path=paths["lock"],
            runtime_status_path=paths["status"],
            log_path=paths["log"],
            config=_config(),
            notion_factory=lambda _token: pytest.fail(
                "overlap must skip before client creation"
            ),
        )

    assert report.status == "OVERLAP_SKIPPED"
    assert report.error_code == "weekly_runtime_overlap"
    assert report.process_lock_acquired is False


def test_strict_artifacts_reject_extra_fields_and_period_mismatch() -> None:
    reflection = _reflection()
    reflection["unexpected"] = "private"
    with pytest.raises(AutomaticWeeklyReflectionError) as reflection_error:
        validate_strict_reflection_artifact(reflection)
    assert reflection_error.value.code == "reflection_artifact_schema_invalid"

    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    review = _weekly_review(context)
    review["period"]["end_date"] = "2026-01-01"
    with pytest.raises(AutomaticWeeklyReflectionError) as weekly_error:
        validate_strict_weekly_artifact(review, context)
    assert weekly_error.value.code == "weekly_artifact_period_mismatch"


def test_strict_artifacts_reject_nested_type_errors() -> None:
    reflection = _reflection()
    reflection["mindset_shifts"][0]["evidence"][0]["source"] = 123
    with pytest.raises(AutomaticWeeklyReflectionError) as reflection_error:
        validate_strict_reflection_artifact(reflection)
    assert reflection_error.value.code == "reflection_artifact_schema_invalid"

    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    review = _weekly_review(context)
    review["core_idea"]["idea"] = []
    with pytest.raises(AutomaticWeeklyReflectionError) as weekly_error:
        validate_strict_weekly_artifact(review, context)
    assert weekly_error.value.code == "weekly_artifact_schema_invalid"


def test_strict_artifacts_reject_empty_core_content() -> None:
    reflection = _reflection()
    reflection["mindset_shifts"][0]["evidence"] = []
    with pytest.raises(AutomaticWeeklyReflectionError) as reflection_error:
        validate_strict_reflection_artifact(reflection)
    assert (
        reflection_error.value.code
        == "reflection_artifact_schema_invalid"
    )

    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    review = _weekly_review(context)
    review["core_idea"]["idea"] = ""
    review["expressions_worth_reusing"][0]["expression"] = " "
    with pytest.raises(AutomaticWeeklyReflectionError) as weekly_error:
        validate_strict_weekly_artifact(review, context)
    assert weekly_error.value.code == "weekly_artifact_incomplete"


def test_single_source_runtime_accepts_empty_cross_content_patterns(
    tmp_path: Path,
) -> None:
    class SingleSourceCodex(CodexFixture):
        def __call__(self, **kwargs):
            if "reflection analysis" not in kwargs["stage"]:
                return super().__call__(**kwargs)
            self.calls.append(kwargs["stage"])
            self.private_env_seen.append(kwargs.get("env"))
            payload = _reflection()
            payload["cross_content_patterns"] = []
            validated = kwargs["validator"](payload)
            kwargs["output_path"].parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            kwargs["output_path"].write_text(
                json.dumps(validated),
                encoding="utf-8",
            )
            return validated

    report = _run(
        tmp_path,
        codex_generator=SingleSourceCodex(),
    )

    assert report.status == "PASS", report.to_dict()
    assert report.reflection_codex_calls == 1
    assert report.weekly_review_codex_calls == 1
    assert report.weekly_created == 1


def test_single_source_runtime_accepts_empty_mindset_shifts(
    tmp_path: Path,
) -> None:
    class SingleSourceCodex(CodexFixture):
        def __call__(self, **kwargs):
            self.calls.append(kwargs["stage"])
            self.private_env_seen.append(kwargs.get("env"))
            if "reflection analysis" in kwargs["stage"]:
                payload = _reflection()
                payload["mindset_shifts"] = []
                payload["cross_content_patterns"] = []
            else:
                request = json.loads(
                    kwargs["request_path"].read_text(encoding="utf-8")
                )
                payload = _weekly_review(
                    request["input"]["weekly_learning_context"]
                )
                payload["mindset_shift"] = None
            validated = kwargs["validator"](payload)
            kwargs["output_path"].parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            kwargs["output_path"].write_text(
                json.dumps(validated),
                encoding="utf-8",
            )
            return validated

    report = _run(
        tmp_path,
        codex_generator=SingleSourceCodex(),
    )

    assert report.status == "PASS", report.to_dict()
    assert report.reflection_codex_calls == 1
    assert report.weekly_review_codex_calls == 1
    assert report.weekly_created == 1


@pytest.mark.parametrize(
    ("case_name", "podcast_count", "payload_mutator", "expected_pass"),
    (
        (
            "single_minimal",
            1,
            lambda payload: payload.update(
                mindset_shifts=[],
                cross_content_patterns=[],
            ),
            True,
        ),
        (
            "single_rich",
            1,
            lambda payload: payload.update(
                cross_content_patterns=[],
            ),
            True,
        ),
        (
            "single_with_cross_content",
            1,
            lambda payload: None,
            False,
        ),
        (
            "multiple_without_mindset_shift",
            2,
            lambda payload: payload.update(
                mindset_shifts=[],
            ),
            True,
        ),
        (
            "multiple_rich",
            2,
            lambda payload: None,
            True,
        ),
        (
            "multiple_without_cross_content",
            2,
            lambda payload: payload.update(
                cross_content_patterns=[],
            ),
            False,
        ),
        (
            "multiple_with_one_cross_content_pattern",
            2,
            lambda payload: payload.update(
                cross_content_patterns=["one pattern"],
            ),
            False,
        ),
        (
            "missing_professional_action",
            1,
            lambda payload: payload.update(
                professional_actions=[],
            ),
            False,
        ),
        (
            "mindset_shift_without_evidence",
            1,
            lambda payload: payload["mindset_shifts"][0].update(
                evidence=[],
            ),
            False,
        ),
        (
            "empty_weekly_theme",
            1,
            lambda payload: payload["weekly_theme"].update(theme=""),
            False,
        ),
        (
            "empty_mindset_transition",
            1,
            lambda payload: payload["mindset_shifts"][0].update(before=""),
            False,
        ),
        (
            "empty_evidence_reference",
            1,
            lambda payload: payload["mindset_shifts"][0]["evidence"][0].update(
                source="",
            ),
            False,
        ),
        (
            "empty_cross_content_item",
            2,
            lambda payload: payload.update(
                cross_content_patterns=[""],
            ),
            False,
        ),
        (
            "empty_professional_action",
            1,
            lambda payload: payload.update(
                professional_actions=[""],
            ),
            False,
        ),
        (
            "multiple_professional_actions",
            1,
            lambda payload: payload.update(
                professional_actions=["first", "second"],
            ),
            False,
        ),
        (
            "multiple_mindset_shifts",
            1,
            lambda payload: payload["mindset_shifts"].append(
                deepcopy(payload["mindset_shifts"][0]),
            ),
            False,
        ),
        (
            "unsupported_root_field",
            1,
            lambda payload: payload.update(unexpected="value"),
            False,
        ),
    ),
)
def test_reflection_validation_compatibility_matrix(
    case_name: str,
    podcast_count: int,
    payload_mutator,
    expected_pass: bool,
) -> None:
    class StaticProvider:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def generate(self, _prompt, _context):
            return deepcopy(self.payload)

    payload = _reflection()
    payload_mutator(payload)
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    while len(context["podcasts"]) < podcast_count:
        context["podcasts"].append(deepcopy(context["podcasts"][0]))

    base_passed = True
    try:
        ReflectionAnalyzer(
            provider=StaticProvider(payload),
        ).generate(context)
    except ReflectionGenerationError:
        base_passed = False

    automatic_passed = True
    try:
        validate_strict_reflection_artifact(
            payload,
            require_cross_content_patterns=podcast_count > 1,
        )
    except AutomaticWeeklyReflectionError:
        automatic_passed = False

    assert base_passed is expected_pass, case_name
    assert automatic_passed is expected_pass, case_name


def test_reflection_schema_and_prompt_contract_are_aligned() -> None:
    prompt = load_reflection_prompt()
    schema = load_reflection_schema()
    properties = schema["properties"]
    theme = properties["weekly_theme"]
    shift = properties["mindset_shifts"]
    evidence = shift["items"]["properties"]["evidence"]
    confidence = shift["items"]["properties"]["confidence"]
    patterns = properties["cross_content_patterns"]
    actions = properties["professional_actions"]

    assert "at most one mindset shift" in prompt
    assert "only when source evidence supports" in prompt
    assert "For a multi-source week, extract 2-4" in prompt
    assert "For a single-source week, leave cross-content patterns empty" in prompt
    assert "Produce one concrete professional action" in prompt
    assert schema["additionalProperties"] is False
    assert theme["additionalProperties"] is False
    assert theme["properties"]["category"]["minLength"] == 1
    assert theme["properties"]["theme"]["minLength"] == 1
    assert shift["maxItems"] == 1
    assert evidence["minItems"] == 1
    assert confidence["minimum"] == 0
    assert confidence["maximum"] == 1
    assert patterns["maxItems"] == 4
    assert patterns["items"]["minLength"] == 1
    assert actions["minItems"] == 1
    assert actions["maxItems"] == 1


def test_placeholder_single_source_keeps_cross_content_empty() -> None:
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )

    reflection = ReflectionAnalyzer(
        provider=PlaceholderReflectionProvider(),
    ).generate(context)

    assert reflection["cross_content_patterns"] == []


def test_placeholder_multi_source_minimal_week_generates_two_patterns() -> None:
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
        include_assets=False,
    )
    second = deepcopy(context["podcasts"][0])
    second["topic"] = "Leadership"
    context["podcasts"].append(second)

    reflection = ReflectionAnalyzer(
        provider=PlaceholderReflectionProvider(),
    ).generate(context)

    assert len(reflection["cross_content_patterns"]) == 2


def test_weekly_artifact_cannot_invent_mindset_shift() -> None:
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    reflection = _reflection()
    reflection["mindset_shifts"] = []

    with pytest.raises(AutomaticWeeklyReflectionError) as error:
        validate_strict_weekly_artifact(
            _weekly_review(context),
            context,
            reflection,
        )

    assert error.value.code == "weekly_artifact_mindset_mismatch"


def test_weekly_artifact_allows_null_mindset_without_reflection_shift() -> None:
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    reflection = _reflection()
    reflection["mindset_shifts"] = []
    review = _weekly_review(context)
    review["mindset_shift"] = None

    validated = validate_strict_weekly_artifact(
        review,
        context,
        reflection,
    )

    assert validated["mindset_shift"] is None


def test_weekly_codex_schema_uses_supported_nullable_object(
    tmp_path: Path,
) -> None:
    captured = {}
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    reflection = _reflection()
    reflection["mindset_shifts"] = []

    def generator(**kwargs):
        captured.update(kwargs)
        review = _weekly_review(context)
        review["mindset_shift"] = None
        return kwargs["validator"](review)

    provider = AutomaticCodexWeeklyReviewProvider(
        request_path=tmp_path / "request.json",
        output_path=tmp_path / "output.json",
        generator=generator,
    )

    result = provider.generate(
        "prompt",
        {
            "weekly_learning_context": context,
            "reflection_context": reflection,
        },
    )
    mindset_schema = captured["schema"]["properties"]["mindset_shift"]

    assert result["mindset_shift"] is None
    assert "oneOf" not in mindset_schema
    assert mindset_schema["type"] == ["object", "null"]
    assert mindset_schema["required"] == ["before", "now"]
    assert mindset_schema["additionalProperties"] is False
    assert set(mindset_schema["properties"]) == {"before", "now"}


def test_weekly_nullable_mindset_schema_still_rejects_primitive() -> None:
    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    review = _weekly_review(context)
    review["mindset_shift"] = "unsupported"

    with pytest.raises(AutomaticWeeklyReflectionError) as error:
        validate_strict_weekly_artifact(review, context)

    assert error.value.code == "weekly_artifact_schema_invalid"


def test_runtime_blocks_weekly_mindset_shift_without_reflection_evidence(
    tmp_path: Path,
) -> None:
    class MismatchedCodex(CodexFixture):
        def __call__(self, **kwargs):
            self.calls.append(kwargs["stage"])
            self.private_env_seen.append(kwargs.get("env"))
            if "reflection analysis" in kwargs["stage"]:
                payload = _reflection()
                payload["mindset_shifts"] = []
                payload["cross_content_patterns"] = []
            else:
                request = json.loads(
                    kwargs["request_path"].read_text(encoding="utf-8")
                )
                payload = _weekly_review(
                    request["input"]["weekly_learning_context"]
                )
            validated = kwargs["validator"](payload)
            kwargs["output_path"].parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            kwargs["output_path"].write_text(
                json.dumps(validated),
                encoding="utf-8",
            )
            return validated

    report = _run(
        tmp_path,
        codex_generator=MismatchedCodex(),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_artifact_mindset_mismatch"
    assert report.weekly_created == 0


def test_multi_source_provider_rejects_empty_cross_content_patterns(
    tmp_path: Path,
) -> None:
    def generator(**kwargs):
        payload = _reflection()
        payload["cross_content_patterns"] = []
        return kwargs["validator"](payload)

    context = _weekly_context(
        today=DUE.date(),
        generated_at=DUE.isoformat(),
    )
    context["podcasts"].append(dict(context["podcasts"][0]))
    provider = AutomaticCodexReflectionProvider(
        request_path=tmp_path / "request.json",
        output_path=tmp_path / "output.json",
        generator=generator,
    )

    with pytest.raises(AutomaticWeeklyReflectionError) as error:
        provider.generate(
            "prompt",
            {"weekly_learning_context": context},
        )

    assert error.value.code == "reflection_artifact_incomplete"


def test_malformed_codex_output_never_reaches_pipeline(tmp_path: Path) -> None:
    def malformed_generator(**kwargs):
        payload = _reflection()
        payload["unexpected"] = "private"
        return kwargs["validator"](payload)

    report = _run(
        tmp_path,
        codex_generator=malformed_generator,
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "reflection_artifact_schema_invalid"
    assert report.weekly_created == 0


def test_unattended_runtime_blocks_update_and_delete_capabilities(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def pipeline(**kwargs):
        context = json.loads(
            kwargs["weekly_learning_context_path"].read_text(
                encoding="utf-8"
            )
        )
        reflection = kwargs["reflection_provider"].generate(
            "reflection prompt",
            {"weekly_learning_context": context},
        )
        review = kwargs["weekly_review_provider"].generate(
            "weekly prompt",
            {
                "weekly_learning_context": context,
                "reflection_context": reflection,
            },
        )
        if kwargs["dry_run"]:
            return SimpleNamespace(weekly_review=review)
        calls.append("update-attempt")
        kwargs["notion"].pages.update(
            page_id="existing",
            properties={},
        )
        pytest.fail("guard must stop before a block deletion")

    report = _run(
        tmp_path,
        pipeline_runner=pipeline,
        identity_counter=lambda *_a, **_k: 0,
    )

    assert calls == ["update-attempt"]
    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_unattended_update_blocked"
    assert report.weekly_created == 0
    assert report.deletes_or_archives == 0


def test_codex_timeout_retries_on_later_bounded_invocation(
    tmp_path: Path,
) -> None:
    paths = _paths(tmp_path)
    save_schedule(_schedule(), paths["schedule"])
    good = CodexFixture()
    calls = 0

    def flaky_generator(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise CodexRuntimeError("codex_timeout")
        return good(**kwargs)

    identities = iter((0, 0, 1))
    common = {
        "schedule_path": paths["schedule"],
        "state_path": paths["state"],
        "artifact_root": paths["artifacts"],
        "lock_path": paths["lock"],
        "runtime_status_path": paths["status"],
        "log_path": paths["log"],
        "notion": RuntimeNotion(),
        "config": _config(),
        "binding_validator": (
            lambda *_a, **_k: SimpleNamespace(valid=True)
        ),
        "context_extractor": _context_extractor,
        "pipeline_runner": _pipeline,
        "identity_counter": lambda *_a, **_k: next(identities),
        "codex_generator": flaky_generator,
    }

    failed = run_bounded_automatic_weekly_reflection(
        now=DUE,
        **common,
    )
    recovered = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=15),
        **common,
    )

    assert failed.status == "RETRYABLE_FAILURE"
    assert failed.error_code == "codex_timeout"
    assert recovered.status == "PASS"
    assert recovered.reflection_codex_calls == 1
    assert recovered.weekly_review_codex_calls == 1


def test_provider_passes_bounded_isolated_codex_contract(tmp_path: Path) -> None:
    captured = {}

    def generator(**kwargs):
        captured.update(kwargs)
        payload = _reflection()
        payload["cross_content_patterns"] = []
        return kwargs["validator"](payload)

    provider = AutomaticCodexReflectionProvider(
        request_path=tmp_path / "request.json",
        output_path=tmp_path / "output.json",
        timeout_seconds=37,
        env={
            "PATH": "/usr/bin",
            "NOTION_TOKEN": "must-not-reach-child",
            "OPENAI_API_KEY": "must-not-reach-child",
        },
        generator=generator,
    )
    result = provider.generate(
        "prompt",
        {
            "weekly_learning_context": _weekly_context(
                today=DUE.date(),
                generated_at=DUE.isoformat(),
            )
        },
    )

    assert result["weekly_theme"]["theme"]
    assert captured["timeout_seconds"] == 37
    assert captured["stage"] == "automatic weekly reflection analysis"
    assert captured["env"]["NOTION_TOKEN"] == "must-not-reach-child"
    assert provider.calls == 1


def test_runtime_log_is_redacted_and_owner_only(tmp_path: Path) -> None:
    report = _run(
        tmp_path,
        binding_validator=lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("private-learning-content")
        ),
    )
    log_path = _paths(tmp_path)["log"]
    rendered = log_path.read_text(encoding="utf-8")

    assert report.status == "SAFE_STOP"
    assert "private-learning-content" not in rendered
    assert "private-token" not in rendered
    assert "private-podcast" not in rendered
    assert (log_path.stat().st_mode & 0o777) == 0o600


class _IdentityDataSources:
    def __init__(self, pages: list[dict]) -> None:
        self.pages = pages

    def query(self, **_kwargs):
        return {
            "results": self.pages,
            "has_more": False,
            "next_cursor": None,
        }


class _IdentityChildren:
    def __init__(self, blocks: list[dict]) -> None:
        self.blocks = blocks

    def list(self, **_kwargs):
        return {
            "results": self.blocks,
            "has_more": False,
            "next_cursor": None,
        }


def _identity_page(*, relations: list[str]) -> dict:
    return {
        "id": "weekly-page",
        "properties": {
            "Date": {
                "date": {
                    "start": "2026-07-18",
                    "end": None,
                }
            },
            "Podcasts": {
                "relation": [{"id": item} for item in relations]
            },
        },
    }


def _complete_weekly_blocks() -> list[dict]:
    headings = [
        "1. This Week's Core Idea",
        "3. Ideas Worth Compounding",
        "4. Expressions Worth Reusing",
        "5. Language-Thinking Connection",
        "6. One Application for Next Week",
        "7. Sources",
    ]
    return [
        {
            "type": "table_of_contents",
            "table_of_contents": {"color": "default"},
        },
        *[
            {
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {"content": heading},
                        }
                    ]
                },
            }
            for heading in headings
        ],
    ]


def test_identity_inspection_uses_exact_relation_and_complete_body() -> None:
    notion = SimpleNamespace(
        data_sources=_IdentityDataSources(
            [_identity_page(relations=["podcast-page"])]
        ),
        blocks=SimpleNamespace(
            children=_IdentityChildren(_complete_weekly_blocks())
        ),
    )

    inspection = inspect_weekly_identity(
        notion,
        "weekly-data-source",
        start_date="2026-07-18",
        end_date="2026-07-25",
        source_page_ids=["podcast-page"],
    )
    verify_weekly_page_integrity(notion, inspection.exact_page_id)

    assert inspection.same_period_count == 1
    assert inspection.exact_identity_count == 1
    assert inspection.exact_page_id == "weekly-page"


def test_existing_weekly_page_missing_toc_fails_reconciliation() -> None:
    notion = SimpleNamespace(
        blocks=SimpleNamespace(
            children=_IdentityChildren(_complete_weekly_blocks()[1:])
        )
    )

    with pytest.raises(AutomaticWeeklyReflectionError) as error:
        verify_weekly_page_integrity(notion, "weekly-page")

    assert error.value.code == "weekly_existing_page_incomplete"


def test_manual_same_identity_page_fails_closed_before_pipeline(
    tmp_path: Path,
) -> None:
    notion = SimpleNamespace(
        data_sources=_IdentityDataSources(
            [
                _identity_page(relations=["podcast-page"])
            ]
        ),
        blocks=SimpleNamespace(
            children=_IdentityChildren(_complete_weekly_blocks())
        ),
    )

    inspection = inspect_weekly_identity(
        notion,
        "weekly-data-source",
        start_date="2026-07-18",
        end_date="2026-07-25",
        source_page_ids=["podcast-page"],
    )
    report = _run(
        tmp_path,
        identity_counter=lambda *_a, **_k: inspection,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "manual page must not enter pipeline"
        ),
    )

    assert report.status == "SAFE_STOP"
    assert report.error_code == "weekly_existing_page_unmanaged"
    assert report.weekly_created == 0


def test_publish_intent_does_not_adopt_manual_same_identity_page(
    tmp_path: Path,
) -> None:
    paths, codex, first = _prepare_publish_intent_without_write(
        tmp_path
    )
    notion = SimpleNamespace(
        data_sources=_IdentityDataSources(
            [_identity_page(relations=["podcast-page"])]
        ),
        blocks=SimpleNamespace(
            children=_IdentityChildren(_complete_weekly_blocks())
        ),
    )

    recovered = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=2),
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=notion,
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "manual page must stop before generation"
        ),
        codex_generator=codex,
    )

    assert first.status == "SAFE_STOP"
    assert first.weekly_created == 0
    assert recovered.status == "SAFE_STOP"
    assert recovered.error_code == "weekly_existing_page_unmanaged"
    assert len(codex.calls) == 2


def test_modified_artifact_invalidates_crash_recovery_intent(
    tmp_path: Path,
) -> None:
    paths, codex, first = _prepare_publish_intent_without_write(
        tmp_path
    )
    trusted_body = _trusted_weekly_body(paths["artifacts"])
    weekly_path = next(
        paths["artifacts"].glob("**/weekly_review_codex.json")
    )
    weekly_path.write_text(
        weekly_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    notion = SimpleNamespace(
        data_sources=_IdentityDataSources(
            [_identity_page(relations=["podcast-page"])]
        ),
        blocks=SimpleNamespace(
            children=_IdentityChildren(trusted_body)
        ),
    )

    recovered = run_bounded_automatic_weekly_reflection(
        now=DUE + timedelta(minutes=2),
        schedule_path=paths["schedule"],
        state_path=paths["state"],
        artifact_root=paths["artifacts"],
        lock_path=paths["lock"],
        runtime_status_path=paths["status"],
        log_path=paths["log"],
        notion=notion,
        config=_config(),
        binding_validator=lambda *_a, **_k: SimpleNamespace(valid=True),
        context_extractor=_context_extractor,
        pipeline_runner=lambda **_kwargs: pytest.fail(
            "modified artifact must stop before generation"
        ),
        codex_generator=codex,
    )

    assert first.status == "SAFE_STOP"
    assert recovered.status == "SAFE_STOP"
    assert recovered.error_code == "weekly_existing_page_unmanaged"
    assert len(codex.calls) == 2


def test_existing_weekly_page_with_duplicate_toc_fails_reconciliation() -> None:
    blocks = _complete_weekly_blocks()
    notion = SimpleNamespace(
        blocks=SimpleNamespace(
            children=_IdentityChildren([blocks[0], *blocks])
        )
    )

    with pytest.raises(AutomaticWeeklyReflectionError) as error:
        verify_weekly_page_integrity(notion, "weekly-page")

    assert error.value.code == "weekly_existing_page_incomplete"


def test_identity_query_failure_is_retryable() -> None:
    notion = SimpleNamespace(
        data_sources=SimpleNamespace(
            query=lambda **_kwargs: (_ for _ in ()).throw(
                RuntimeError("private")
            )
        )
    )

    with pytest.raises(RetryableAutomaticWeeklyReflectionError) as error:
        inspect_weekly_identity(
            notion,
            "weekly-data-source",
            start_date="2026-07-18",
            end_date="2026-07-25",
            source_page_ids=["podcast-page"],
        )

    assert error.value.code == "weekly_identity_query_failed"
