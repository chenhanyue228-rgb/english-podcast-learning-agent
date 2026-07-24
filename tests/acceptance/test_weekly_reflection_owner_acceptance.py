from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import pytest

from scripts.acceptance.weekly_reflection_owner_acceptance import (
    AcceptanceFailure,
    GuardViolation,
    LIVE_CONFIRMATION,
    WeeklyReflectionOwnerAcceptanceRunner,
    render_failure_report,
    render_redacted_report,
)
from src.notion.schema import PODCAST_LIBRARY, WEEKLY_REVIEW
from src.notion.weekly_reflection_writer import publish_weekly_reflection
from src.workflow.weekly_reflection_pipeline import WeeklyReflectionPipelineError
from tests.acceptance.fakes import (
    FakeBlocks,
    FakeDataSources,
    FakeNotion,
    FakePage,
    FakePages,
    date_property,
    relation_property,
    rich_text_property,
    title_property,
)


def sample_weekly_context() -> dict[str, Any]:
    return {
        "metadata": {
            "period_start": "2026-07-13",
            "period_end": "2026-07-20",
            "generated_at": "2026-07-20T12:00:00Z",
            "source": "Podcast Library",
        },
        "podcasts": [
            {
                "page_id": "weekly-source-podcast",
                "title": "Private source title",
                "date": "2026-07-17",
                "topic": "Negotiation",
                "difficulty": "Advanced",
                "url": "https://example.com/private-source",
                "summary": {
                    "english": "Private learning summary.",
                    "chinese": "私人学习摘要。",
                },
                "key_takeaways": ["Private learning takeaway."],
                "transcript_available": True,
            }
        ],
        "learning_expressions": [
            {
                "expression": "private expression",
                "category": "Business Phrase",
                "meaning": "Private meaning",
                "chinese_meaning": "私人含义",
                "usage_context": "Private context",
                "example": "Private example",
                "source_page_id": "weekly-source-podcast",
            }
        ],
        "ai_highlights": [],
        "user_vocabulary": [
            {
                "word": "private vocabulary",
                "context": "Private vocabulary context",
                "source_page_id": "weekly-source-podcast",
                "highlight_type": "pink",
            }
        ],
    }


def sample_reflection_context() -> dict[str, Any]:
    return {
        "weekly_theme": {
            "category": "Negotiation",
            "theme": "Private weekly theme",
        },
        "mindset_shifts": [
            {
                "before": "Private before.",
                "after": "Private after.",
                "evidence": [
                    {
                        "source": "Private source",
                        "supporting_concept": "Private concept",
                    }
                ],
                "confidence": 0.95,
            }
        ],
        "cross_content_patterns": ["Private cross-content pattern."],
        "professional_actions": ["Private professional action."],
    }


def sample_weekly_review() -> dict[str, Any]:
    return {
        "period": {
            "start_date": "2026-07-13",
            "end_date": "2026-07-20",
            "generated_at": "2026-07-20T12:00:00Z",
            "source": "Podcast Library",
        },
        "core_idea": {
            "idea": "Private transferable idea.",
            "why_it_matters": "Private professional significance.",
            "refined_understanding": "Private refined understanding.",
        },
        "mindset_shift": {
            "before": "Private old view.",
            "now": "Private new view.",
        },
        "ideas_worth_compounding": [
            {
                "idea": "Private idea one.",
                "why_it_matters": "Private reason one.",
                "application": "Private application one.",
                "source_reference": "Private source one.",
            },
            {
                "idea": "Private idea two.",
                "why_it_matters": "Private reason two.",
                "application": "Private application two.",
                "source_reference": "Private source two.",
            },
        ],
        "expressions_worth_reusing": [
            {
                "expression": "private expression one",
                "contextual_meaning": "Private contextual meaning one.",
                "reusable_example": "Private reusable example one.",
                "communication_function": "Constructive challenge",
            },
            {
                "expression": "private expression two",
                "contextual_meaning": "Private contextual meaning two.",
                "reusable_example": "Private reusable example two.",
                "communication_function": "Collaborative framing",
            },
            {
                "expression": "private expression three",
                "contextual_meaning": "Private contextual meaning three.",
                "reusable_example": "Private reusable example three.",
                "communication_function": "Long-term orientation",
            },
        ],
        "language_thinking_connection": (
            "Private language-thinking connection that is long enough to "
            "demonstrate a meaningful professional learning relationship."
        ),
        "next_week_application": {
            "scenario": "Private stakeholder scenario",
            "behavior": "Private observable behavior",
            "phrase_to_use": "Private professional phrase",
            "completion_condition": "Private completion condition",
        },
        "sources": [
            {
                "page_id": "weekly-source-podcast",
                "title": "Private source title",
                "url": "https://example.com/private-source",
            }
        ],
        "source_page_ids": ["weekly-source-podcast"],
        "source_podcast_ids": ["weekly-source-podcast"],
        "quality_score": 100,
    }


def _with_ids(blocks: list[dict[str, Any]], prefix: str) -> list[dict[str, Any]]:
    assigned: list[dict[str, Any]] = []
    for index, block in enumerate(blocks, start=1):
        item = deepcopy(block)
        item["id"] = f"{prefix}-block-{index}"
        assigned.append(item)
    return assigned


class WeeklyFakeDataSources(FakeDataSources):
    def _matches(self, page: FakePage, query_filter: Mapping[str, Any]) -> bool:
        if "date" in query_filter:
            expected = query_filter["date"].get("equals")
            actual = page.properties.get(
                str(query_filter.get("property", "")),
                {},
            ).get("date")
            return (
                isinstance(actual, Mapping)
                and actual.get("start") == expected
            )
        return super()._matches(page, query_filter)


class WeeklyFakePages(FakePages):
    def create(self, **kwargs: Any) -> dict[str, Any]:
        data_source_id = kwargs["parent"]["data_source_id"]
        if data_source_id != self.workspace.config.weekly_data_source_id:
            return super().create(**kwargs)
        self.create_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("pages.create")
        page_id = self.workspace.next_id("target-weekly")
        self.workspace.pages_by_id[page_id] = FakePage(
            page_id=page_id,
            data_source_id=data_source_id,
            properties=deepcopy(kwargs.get("properties", {})),
            children=_with_ids(
                deepcopy(kwargs.get("children", [])),
                page_id,
            ),
        )
        return {"id": page_id, "url": f"https://notion.so/{page_id}"}


class WeeklyFakeBlocks(FakeBlocks):
    def __init__(self, workspace: "WeeklyFakeNotion") -> None:
        super().__init__(workspace)
        self.workspace = workspace

    def delete(self, **kwargs: Any) -> dict[str, Any]:
        self.delete_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.delete")
        block_id = kwargs["block_id"]
        for page in self.workspace.pages_by_id.values():
            page.children = [
                item
                for item in page.children
                if str(item.get("id", "")) != block_id
            ]
        return {"id": block_id}


class WeeklyFakeBlocksChildren:
    def __init__(self, workspace: "WeeklyFakeNotion") -> None:
        self.workspace = workspace
        self.list_calls: list[dict[str, Any]] = []
        self.append_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> dict[str, Any]:
        self.list_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.children.list")
        page = self.workspace.pages_by_id[kwargs["block_id"]]
        return {
            "results": deepcopy(page.children),
            "has_more": False,
            "next_cursor": None,
        }

    def append(self, **kwargs: Any) -> dict[str, Any]:
        self.append_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.children.append")
        page_id = kwargs["block_id"]
        start = len(self.workspace.pages_by_id[page_id].children)
        children = _with_ids(
            deepcopy(kwargs.get("children", [])),
            f"{page_id}-append-{start}",
        )
        self.workspace.pages_by_id[page_id].children.extend(children)
        return {"results": deepcopy(children)}


class WeeklyFakeNotion(FakeNotion):
    def __init__(self) -> None:
        super().__init__()
        self.data_sources = WeeklyFakeDataSources(self)
        self.pages = WeeklyFakePages(self)
        self.blocks = WeeklyFakeBlocks(self)
        self.blocks.children = WeeklyFakeBlocksChildren(self)
        self.add_page(
            self.config.podcast_data_source_id,
            {
                "Title": title_property("Private source title"),
                "URL": {"type": "url", "url": "https://example.com/private-source"},
                "Source Type": {
                    "type": "select",
                    "select": {"name": "Podcast"},
                },
                "Date": date_property("2026-07-17"),
                "Topic": {"type": "select", "select": {"name": "Negotiation"}},
                "Difficulty": {
                    "type": "select",
                    "select": {"name": "Advanced"},
                },
                "Short Summary": rich_text_property("Private summary"),
            },
            page_id="weekly-source-podcast",
        )


def _write_context(root: Path, payload: Mapping[str, Any] | None = None) -> Path:
    path = root / "output/weekly_learning_context.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload or sample_weekly_context(), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _pipeline(
    *,
    mutate_after_publish=None,
    fail: str | None = None,
):
    calls = {"count": 0, "live_count": 0}

    def run(**kwargs: Any) -> Any:
        calls["count"] += 1
        reflection_path = Path(kwargs["reflection_context_output_path"])
        review_path = Path(kwargs["weekly_review_output_path"])
        run_path = Path(kwargs["pipeline_run_output_path"])
        logs_dir = Path(kwargs["logs_dir"])
        reflection_path.parent.mkdir(parents=True, exist_ok=True)
        logs_dir.mkdir(parents=True, exist_ok=True)
        (reflection_path.parent / "reflection_context_request.json").write_text(
            "{}",
            encoding="utf-8",
        )
        (reflection_path.parent / "weekly_review_request.json").write_text(
            "{}",
            encoding="utf-8",
        )
        if fail == "pending":
            raise WeeklyReflectionPipelineError("artifact pending")
        if fail == "invalid":
            reflection_path.write_text("{", encoding="utf-8")
            raise WeeklyReflectionPipelineError("artifact invalid")
        reflection_path.write_text(
            json.dumps(sample_reflection_context(), ensure_ascii=False),
            encoding="utf-8",
        )
        review_path.write_text(
            json.dumps(sample_weekly_review(), ensure_ascii=False),
            encoding="utf-8",
        )
        run_path.write_text(
            json.dumps({"status": "success"}),
            encoding="utf-8",
        )
        (logs_dir / f"weekly_reflection_fake_{calls['count']}.log").write_text(
            "status=success",
            encoding="utf-8",
        )
        publish_result = None
        if not kwargs["dry_run"]:
            calls["live_count"] += 1
            publish_result = publish_weekly_reflection(
                sample_weekly_review(),
                sample_reflection_context(),
                notion=kwargs["notion"],
                weekly_reflection_database_id=(
                    kwargs["weekly_reflection_database_id"]
                ),
                podcast_database_id=kwargs["podcast_database_id"],
            )
            if mutate_after_publish is not None:
                mutate_after_publish(
                    kwargs["notion"],
                    publish_result,
                    calls["live_count"],
                )
        return SimpleNamespace(
            reflection_context_path=reflection_path,
            weekly_review_path=review_path,
            weekly_learning_context=sample_weekly_context(),
            reflection_context=sample_reflection_context(),
            weekly_review=sample_weekly_review(),
            quality_report={
                "passed": True,
                "score": 100,
                "issues": [],
                "suggestions": [],
            },
            publish_result=publish_result,
            dry_run=kwargs["dry_run"],
        )

    return run


def _runner(
    tmp_path: Path,
    notion: WeeklyFakeNotion | None = None,
    *,
    pipeline_runner=None,
) -> tuple[WeeklyReflectionOwnerAcceptanceRunner, WeeklyFakeNotion]:
    active_notion = notion or WeeklyFakeNotion()
    _write_context(tmp_path)
    runner = WeeklyReflectionOwnerAcceptanceRunner(
        active_notion,
        active_notion.config,
        pipeline_runner=pipeline_runner or _pipeline(),
        project_root=tmp_path,
    )
    return runner, active_notion


def test_dry_run_has_zero_notion_writes(tmp_path: Path) -> None:
    runner, notion = _runner(tmp_path)
    result = runner.dry_run()

    assert result.report.mode == "dry-run"
    assert result.report.quality_score == 100
    assert result.report.counts["planned_non_weekly_writes"] == 0
    assert not notion.pages.create_calls
    assert not notion.pages.update_calls
    assert not notion.blocks.children.append_calls
    assert not notion.blocks.delete_calls


def test_target_binding_failure_stops_before_pipeline(tmp_path: Path) -> None:
    notion = WeeklyFakeNotion()
    notion.schemas[notion.config.weekly_data_source_id].pop("Week")
    runner, _ = _runner(tmp_path, notion)

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code.startswith("target_binding_")


def test_empty_weekly_learning_context_is_rejected(tmp_path: Path) -> None:
    notion = WeeklyFakeNotion()
    payload = sample_weekly_context()
    payload["podcasts"] = []
    payload["learning_expressions"] = []
    payload["user_vocabulary"] = []
    _write_context(tmp_path, payload)
    runner = WeeklyReflectionOwnerAcceptanceRunner(
        notion,
        notion.config,
        pipeline_runner=_pipeline(),
        project_root=tmp_path,
    )

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == "weekly_learning_context_empty"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("pending", "weekly_artifact_pending"),
        ("invalid", "weekly_artifact_invalid"),
    ],
)
def test_artifact_pending_or_invalid_fails_closed(
    tmp_path: Path,
    failure: str,
    expected: str,
) -> None:
    runner, _ = _runner(
        tmp_path,
        pipeline_runner=_pipeline(fail=failure),
    )

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == expected


def test_quality_gate_failure_is_rejected(tmp_path: Path) -> None:
    base = _pipeline()

    def low_quality(**kwargs: Any) -> Any:
        result = base(**kwargs)
        result.quality_report = {"passed": False, "score": 70}
        return result

    runner, _ = _runner(tmp_path, pipeline_runner=low_quality)

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == "quality_gate_failed"


def _seed_matching_weekly(
    notion: WeeklyFakeNotion,
    *,
    page_id: str,
    with_body: bool,
) -> None:
    notion.add_page(
        notion.config.weekly_data_source_id,
        {
            "Week": title_property("Private existing week"),
            "Date": date_property("2026-07-13"),
            "Podcasts": relation_property("weekly-source-podcast"),
        },
        page_id=page_id,
        children=(
            _with_ids(
                [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {
                                    "type": "text",
                                    "text": {"content": "Private manual content"},
                                }
                            ]
                        },
                    }
                ],
                page_id,
            )
            if with_body
            else []
        ),
    )


def test_duplicate_weekly_identity_fails_closed(tmp_path: Path) -> None:
    notion = WeeklyFakeNotion()
    _seed_matching_weekly(notion, page_id="matching-weekly-1", with_body=False)
    _seed_matching_weekly(notion, page_id="matching-weekly-2", with_body=False)
    runner, _ = _runner(tmp_path, notion)

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == "weekly_identity_not_unique"
    assert not notion.pages.update_calls


def test_existing_manual_content_is_protected(tmp_path: Path) -> None:
    notion = WeeklyFakeNotion()
    _seed_matching_weekly(notion, page_id="manual-weekly", with_body=True)
    runner, _ = _runner(tmp_path, notion)

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == "existing_weekly_content_protected"
    assert not notion.pages.update_calls
    assert not notion.blocks.delete_calls


def test_non_weekly_write_is_blocked(tmp_path: Path) -> None:
    base = _pipeline()

    def bad_pipeline(**kwargs: Any) -> Any:
        kwargs["notion"].pages.create(
            parent={
                "data_source_id": (
                    kwargs["notion"].policy.config.podcast_data_source_id
                )
            },
            properties={},
        )
        return base(**kwargs)

    runner, _ = _runner(tmp_path, pipeline_runner=bad_pipeline)

    with pytest.raises(GuardViolation) as exc:
        runner.run(confirmation=LIVE_CONFIRMATION)

    assert exc.value.code == "non_weekly_write_blocked"


def test_live_first_publish_and_exact_retry(tmp_path: Path) -> None:
    runner, notion = _runner(tmp_path)
    result = runner.run(confirmation=LIVE_CONFIRMATION)

    assert result.report.mode == "live"
    assert result.report.exact_retry_verified is True
    assert result.report.counts["first_weekly_created"] == 1
    assert result.report.counts["retry_weekly_created"] == 0
    assert result.report.counts["podcast_delta"] == 0
    assert result.report.counts["expression_delta"] == 0
    assert result.report.counts["vocabulary_delta"] == 0
    assert len(notion.pages.create_calls) == 1
    assert len(notion.pages.update_calls) == 1


def test_duplicate_section_on_retry_is_rejected(tmp_path: Path) -> None:
    def duplicate(
        notion: Any,
        publish_result: Any,
        call_number: int,
    ) -> None:
        if call_number != 2:
            return
        page = notion._raw.pages_by_id[publish_result.page_id] if hasattr(
            notion,
            "_raw",
        ) else None
        if page is None:
            page = notion.pages._raw.workspace.pages_by_id[
                publish_result.page_id
            ]
        page.children.extend(deepcopy(page.children))

    runner, _ = _runner(
        tmp_path,
        pipeline_runner=_pipeline(mutate_after_publish=duplicate),
    )

    with pytest.raises(AcceptanceFailure) as exc:
        runner.run(confirmation=LIVE_CONFIRMATION)

    assert exc.value.code in {
        "exact_retry_changed_workspace",
        "duplicate_weekly_section",
    }


def test_relation_mismatch_is_rejected(tmp_path: Path) -> None:
    def corrupt_relation(
        notion: Any,
        publish_result: Any,
        call_number: int,
    ) -> None:
        if call_number != 1:
            return
        page = notion.pages._raw.workspace.pages_by_id[publish_result.page_id]
        page.properties["Podcasts"] = relation_property("wrong-podcast")

    runner, _ = _runner(
        tmp_path,
        pipeline_runner=_pipeline(mutate_after_publish=corrupt_relation),
    )

    with pytest.raises(AcceptanceFailure) as exc:
        runner.run(confirmation=LIVE_CONFIRMATION)

    assert exc.value.code == "published_weekly_content_mismatch"


@pytest.mark.parametrize(
    "operation",
    ["archive", "delete"],
)
def test_delete_or_archive_is_blocked(
    tmp_path: Path,
    operation: str,
) -> None:
    base = _pipeline()

    def destructive_pipeline(**kwargs: Any) -> Any:
        result = base(**kwargs)
        if kwargs["dry_run"]:
            return result
        if operation == "archive":
            kwargs["notion"].pages.update(
                page_id=result.publish_result.page_id,
                archived=True,
            )
        else:
            kwargs["notion"].pages.delete(
                page_id=result.publish_result.page_id,
            )
        return result

    runner, _ = _runner(
        tmp_path,
        pipeline_runner=destructive_pipeline,
    )

    with pytest.raises(GuardViolation) as exc:
        runner.run(confirmation=LIVE_CONFIRMATION)

    assert exc.value.code == "delete_or_archive_blocked"


def test_local_artifact_whitelist_blocks_unexpected_file(
    tmp_path: Path,
) -> None:
    base = _pipeline()

    def rogue_pipeline(**kwargs: Any) -> Any:
        result = base(**kwargs)
        (tmp_path / "unexpected.txt").write_text(
            "unexpected",
            encoding="utf-8",
        )
        return result

    runner, _ = _runner(tmp_path, pipeline_runner=rogue_pipeline)

    with pytest.raises(AcceptanceFailure) as exc:
        runner.dry_run()

    assert exc.value.code == "weekly_artifact_whitelist_violation"


def test_reports_are_redacted(tmp_path: Path) -> None:
    runner, notion = _runner(tmp_path)
    result = runner.dry_run()
    rendered = render_redacted_report(
        result.report,
        secrets=(
            notion.config.token,
            notion.config.target_parent_page_id,
            *notion.config.data_source_ids.values(),
        ),
    )

    assert notion.config.token not in rendered
    assert "weekly-source-podcast" not in rendered
    assert "https://" not in rendered
    assert "Private" not in rendered
    assert "target_parent_fingerprint" in rendered
    failure = render_failure_report("not-a-public-code")
    assert "acceptance_failed" in failure
    assert "not-a-public-code" not in failure
