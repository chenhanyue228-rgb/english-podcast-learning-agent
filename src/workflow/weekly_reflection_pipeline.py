"""Weekly Reflection orchestration pipeline."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional
from time import perf_counter

from src.notion.config import load_notion_config
from src.notion.uploader import create_notion_client
from src.notion.weekly_reflection_writer import (
    WeeklyReflectionPublishResult,
    WeeklyReflectionWriterError,
    load_reflection_context_json,
    load_weekly_review_json,
    load_weekly_reflection_database_id,
    publish_weekly_reflection,
)
from src.weekly_review.generator import WeeklyReviewGenerationError, run_weekly_review_generation
from src.weekly_review.reflection_analyzer import (
    ReflectionGenerationError,
    load_weekly_learning_context,
    run_reflection_analysis,
)
from src.workflow.pipeline_run import (
    PipelineRunRecord,
    create_pipeline_logger,
    create_pipeline_run_record,
    log_pipeline_step,
    save_pipeline_run_record,
)


LOGGER = logging.getLogger(__name__)

DEFAULT_WEEKLY_LEARNING_CONTEXT_PATH = Path("output/weekly_learning_context.json")
DEFAULT_WEEKLY_REVIEW_PATH = Path("output/weekly_review.json")
DEFAULT_REFLECTION_CONTEXT_PATH = Path("output/reflection_context.json")


class WeeklyReflectionPipelineError(RuntimeError):
    """Raised when the weekly reflection workflow cannot complete."""


@dataclass(frozen=True)
class WeeklyReflectionPipelineResult:
    weekly_learning_context_path: Path
    reflection_context_path: Path
    weekly_review_path: Path
    quality_report: dict[str, Any]
    publish_result: Optional[WeeklyReflectionPublishResult]
    weekly_learning_context: Mapping[str, Any]
    reflection_context: Mapping[str, Any]
    weekly_review: Mapping[str, Any]
    pipeline_run_path: Path
    log_path: Path
    dry_run: bool


def _load_weekly_learning_context(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise WeeklyReflectionPipelineError(f"Weekly learning context does not exist: {path}")
    return load_weekly_learning_context(path)


def _period_label(weekly_learning_context: Mapping[str, Any]) -> str:
    metadata = weekly_learning_context.get("metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}
    start_date = str(metadata.get("period_start", "") or "").strip()
    end_date = str(metadata.get("period_end", "") or "").strip()
    if start_date and end_date:
        return f"{start_date}..{end_date}"
    return start_date or end_date or ""


def _finalize_run_record(
    run_record: PipelineRunRecord,
    pipeline_run_output_path: Path,
    status: str,
) -> Path:
    run_record.finalize(status=status, completed_at=datetime.now(timezone.utc).isoformat())
    return save_pipeline_run_record(run_record, pipeline_run_output_path)


def _set_step_status(run_record: PipelineRunRecord, logger: logging.Logger, run_id: str, step: str, status: str, duration: float, error: str | None = None) -> None:
    run_record.set_step(step, status)
    log_pipeline_step(logger, run_id, step, status, duration_seconds=duration, error=error)


def run_weekly_reflection_pipeline(
    weekly_learning_context_path: Path = DEFAULT_WEEKLY_LEARNING_CONTEXT_PATH,
    weekly_review_output_path: Path = DEFAULT_WEEKLY_REVIEW_PATH,
    reflection_context_output_path: Path = DEFAULT_REFLECTION_CONTEXT_PATH,
    notion: Optional[Any] = None,
    weekly_reflection_database_id: Optional[str] = None,
    podcast_database_id: Optional[str] = None,
    dry_run: bool = False,
    pipeline_run_output_path: Path = Path("output/pipeline_run.json"),
    logs_dir: Path = Path("logs"),
) -> WeeklyReflectionPipelineResult:
    weekly_learning_context_path = weekly_learning_context_path.resolve()
    weekly_review_output_path = weekly_review_output_path.resolve()
    reflection_context_output_path = reflection_context_output_path.resolve()
    pipeline_run_output_path = pipeline_run_output_path.resolve()
    logs_dir = logs_dir.resolve()

    run_record = create_pipeline_run_record(period="")
    logger, log_path, handler = create_pipeline_logger(run_record.run_id, logs_dir)
    overall_status = "success"
    period_label = ""
    publish_result: Optional[WeeklyReflectionPublishResult] = None

    try:
        step_started_at = perf_counter()
        weekly_learning_context = _load_weekly_learning_context(weekly_learning_context_path)
        period_label = _period_label(weekly_learning_context)
        run_record.period = period_label
        _set_step_status(run_record, logger, run_record.run_id, "extraction", "success", perf_counter() - step_started_at)
    except Exception as exc:
        _set_step_status(run_record, logger, run_record.run_id, "extraction", "failed", perf_counter() - step_started_at, error=str(exc))
        overall_status = "failed"
        _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
        handler.close()
        logger.handlers.clear()
        raise WeeklyReflectionPipelineError(f"Failed step: Extraction\nReason: {exc}") from exc

    try:
        step_started_at = perf_counter()
        reflection_result = run_reflection_analysis(
            weekly_learning_context_path,
            output_path=reflection_context_output_path,
        )
        _set_step_status(run_record, logger, run_record.run_id, "reflection", "success", perf_counter() - step_started_at)
    except (ReflectionGenerationError, Exception) as exc:
        _set_step_status(run_record, logger, run_record.run_id, "reflection", "failed", perf_counter() - step_started_at, error=str(exc))
        overall_status = "failed"
        _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
        handler.close()
        logger.handlers.clear()
        raise WeeklyReflectionPipelineError(f"Failed step: Reflection Analysis\nReason: {exc}") from exc

    try:
        step_started_at = perf_counter()
        weekly_review_result = run_weekly_review_generation(
            weekly_learning_context_path,
            output_path=weekly_review_output_path,
        )
        _set_step_status(run_record, logger, run_record.run_id, "generation", "success", perf_counter() - step_started_at)
        quality_status = "passed" if weekly_review_result.quality_report.get("passed", False) else "failed"
        _set_step_status(
            run_record,
            logger,
            run_record.run_id,
            "quality_gate",
            quality_status,
            0.0,
        )
    except (WeeklyReviewGenerationError, Exception) as exc:
        step_name = "quality_gate" if "quality gate" in str(exc).lower() else "generation"
        _set_step_status(run_record, logger, run_record.run_id, step_name, "failed", perf_counter() - step_started_at, error=str(exc))
        overall_status = "failed"
        _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
        handler.close()
        logger.handlers.clear()
        raise WeeklyReflectionPipelineError(f"Failed step: Weekly Review / Quality Gate\nReason: {exc}") from exc

    try:
        reflection_context = load_reflection_context_json(reflection_context_output_path)
        weekly_review = load_weekly_review_json(weekly_review_output_path)
    except Exception as exc:
        run_record.set_step("notion", "failed")
        log_pipeline_step(
            logger,
            run_record.run_id,
            "notion",
            "failed",
            duration_seconds=0.0,
            error=str(exc),
        )
        overall_status = "failed"
        _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
        handler.close()
        logger.handlers.clear()
        raise WeeklyReflectionPipelineError(f"Failed step: Artifact Validation\nReason: {exc}") from exc

    try:
        if dry_run:
            run_record.set_step("notion", "skipped")
            log_pipeline_step(
                logger,
                run_record.run_id,
                "notion",
                "skipped",
                duration_seconds=0.0,
                error=None,
            )
        else:
            step_started_at = perf_counter()
            config = load_notion_config()
            notion = notion or create_notion_client(config.token)
            weekly_reflection_database_id = weekly_reflection_database_id or load_weekly_reflection_database_id()
            publish_result = publish_weekly_reflection(
                weekly_review,
                reflection_context,
                notion=notion,
                weekly_reflection_database_id=weekly_reflection_database_id,
                podcast_database_id=podcast_database_id or config.podcast_database_id,
                pipeline_run_id=run_record.run_id,
                reflection_context_id=getattr(reflection_result.output_path, "stem", str(reflection_result.output_path)),
            )
            _set_step_status(run_record, logger, run_record.run_id, "notion", "success", perf_counter() - step_started_at)
    except (WeeklyReflectionWriterError, Exception) as exc:
        _set_step_status(run_record, logger, run_record.run_id, "notion", "failed", perf_counter() - step_started_at, error=str(exc))
        overall_status = "failed"
        _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
        handler.close()
        logger.handlers.clear()
        raise WeeklyReflectionPipelineError(f"Failed step: Notion Publish\nReason: {exc}") from exc

    overall_status = "success"
    _finalize_run_record(run_record, pipeline_run_output_path, overall_status)
    handler.close()
    logger.handlers.clear()

    if publish_result is not None:
        LOGGER.info("Weekly reflection page published.")
    return WeeklyReflectionPipelineResult(
        weekly_learning_context_path=weekly_learning_context_path,
        reflection_context_path=reflection_result.output_path,
        weekly_review_path=weekly_review_result.output_path,
        quality_report=weekly_review_result.quality_report or {},
        publish_result=publish_result,
        weekly_learning_context=weekly_learning_context,
        reflection_context=reflection_context,
        weekly_review=weekly_review,
        pipeline_run_path=pipeline_run_output_path,
        log_path=log_path,
        dry_run=dry_run,
    )
