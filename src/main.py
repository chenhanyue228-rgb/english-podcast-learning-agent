"""Command line entrypoint for podcast extraction and Notion publishing.

Usage:
    python src/main.py <source>

Default flow:
    source extraction -> speech to text -> Codex analysis request JSON

Publishing flow:
    source/transcript + Codex-generated analysis JSON -> complete Notion pages
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import configure_logging, load_settings
from src.analyzer.ai_client import SkillAIWorkflowError, read_generated_analysis_file
from src.analyzer.learning_analyzer import (
    LearningAnalyzer,
    LearningAnalyzerError,
    TranscriptAnalysisInput,
)
from src.analyzer.validators import AnalysisValidationError
from src.analyzer.weekly_review_analyzer import (
    WeeklyReviewAnalyzerError,
    save_weekly_review_request,
    validate_weekly_review_output,
)
from src.agents.weekly_review_agent import (
    WeeklyReviewAgentError,
    run_weekly_review_agent,
)
from src.agent.vocabulary_sync_agent import (
    VocabularySyncAgentError,
    sync_vocabulary_from_highlight_changes,
)
from src.extractor.pipeline import SourceExtractionError, extract_audio_from_source
from src.extractor.podcast_resolver import PodcastResolverError, resolve_podcast_title
from src.extractor.router import SourceRouterError, SourceType, detect_source
from src.notion.learning_publisher import (
    CompletePodcastLearningPayload,
    LearningPublisherError,
    publish_complete_learning_materials,
)
from src.workflow.highlight_vocabulary_publish_pipeline import (
    HighlightVocabularyPublishResult,
    publish_highlight_vocabulary,
)
from src.workflow.vocabulary_learning_pipeline import build_vocabulary_learning_preview
from src.notion.weekly_review_publisher import (
    WeeklyReviewPublishPayload,
    WeeklyReviewPublisherError,
    publish_weekly_review,
)
from src.notion.comment_vocab_sync import (
    CommentVocabSyncError,
    debug_comment_sync,
    debug_comment_sources,
    debug_page_comments,
    sync_vocab_comments,
)
from src.notion.config import load_notion_config
from src.notion.uploader import (
    NotionUploadError,
    create_notion_client,
    transcript_to_text,
)
from src.pipeline.validators import AudioValidationError, validate_audio_source
from src.transcriber.whisper import TranscriptionError, transcribe_audio
from src.transcriber.whisper import save_transcript_json
from src.workflow.weekly_review_pipeline import (
    WeeklyReviewPipelineError,
    fetch_weekly_learning_data,
)
from src.workflow.weekly_reflection_pipeline import (
    WeeklyReflectionPipelineError,
    run_weekly_reflection_pipeline,
)


LOGGER = logging.getLogger(__name__)


class MainPipelineError(RuntimeError):
    """Raised when the CLI pipeline cannot complete."""


@dataclass(frozen=True)
class MainPipelineResult:
    """Result of one CLI pipeline run."""

    kind: str
    value: str
    expected_output_path: Optional[str] = None
    rerun_command: Optional[str] = None


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Notion Podcast Library page from an audio source."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help=(
            "Apple Podcasts page URL, Podcast RSS URL, or local audio file."
        ),
    )
    parser.add_argument(
        "--title",
        help="Optional Notion page title. Defaults to a simple title inferred from the source.",
    )
    parser.add_argument(
        "--source-type",
        choices=["YouTube", "Podcast", "Local Audio"],
        help=(
            "Optional Notion Source Type. YouTube remains a legacy experimental "
            "value and is not supported in v1."
        ),
    )
    parser.add_argument(
        "--model-size",
        default="base",
        help="faster-whisper model size. Default: base.",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="faster-whisper device. Default: auto.",
    )
    parser.add_argument(
        "--compute-type",
        default="default",
        help="faster-whisper compute type. Default: default.",
    )
    parser.add_argument(
        "--print-config",
        action="store_true",
        help="Print non-secret runtime configuration and exit.",
    )
    parser.add_argument(
        "--analysis-json",
        type=Path,
        help=(
            "Path to Codex-generated Phase 3 AI analysis JSON. Required to "
            "create a complete Notion Podcast Library page."
        ),
    )
    parser.add_argument(
        "--weekly-review",
        nargs="?",
        const="",
        default=None,
        help=(
            "Generate the current week's Weekly Review request when used "
            "without a path, or publish the provided analysis JSON when a "
            "path is supplied."
        ),
    )
    parser.add_argument(
        "--weekly-reflection",
        nargs="?",
        const="",
        default=None,
        help=(
            "Run the full Weekly Reflection pipeline. When used without a path, "
            "it loads output/weekly_learning_context.json."
        ),
    )
    parser.add_argument(
        "--weekly-review-json",
        type=Path,
        help=(
            "Path to Codex-generated Weekly Review JSON. When provided with "
            "--weekly-review, publishes the weekly review to Notion."
        ),
    )
    parser.add_argument(
        "--sync-vocab-comments",
        action="store_true",
        help=(
            "Scan Podcast Library comments for ?vocab triggers and sync "
            "manual vocabulary captures into the Vocabulary Database."
        ),
    )
    parser.add_argument(
        "--run-vocabulary-agent",
        action="store_true",
        help=(
            "Scan changed Podcast Library pages for new pink highlights and "
            "sync them into the Vocabulary Database."
        ),
    )
    parser.add_argument(
        "--publish-highlight-vocab",
        nargs="?",
        const="",
        default=None,
        metavar="PAGE_ID",
        help=(
            "Publish approved pink-highlight vocabulary from a Notion page "
            "into the Vocabulary Database."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview vocabulary publishing without writing to Notion.",
    )
    parser.add_argument(
        "--debug-comments",
        action="store_true",
        help="Print raw Podcast Library comments without filtering.",
    )
    parser.add_argument(
        "--debug-page-comments",
        action="store_true",
        help="Print page_id comment payloads fetched via Notion comments?page_id=...",
    )
    parser.add_argument(
        "--debug-comment-sources",
        action="store_true",
        help=(
            "Print summaries of fetched Podcast Library comments, including "
            "comment text, discussion info, and source structure."
        ),
    )
    parser.add_argument(
        "--publish-weekly-review",
        type=Path,
        help=(
            "Path to Codex-generated Weekly Review JSON. Publishes the weekly "
            "review to Notion."
        ),
    )
    parser.add_argument(
        "--transcript-json",
        type=Path,
        help=(
            "Path to an existing transcript JSON. Skips audio extraction and "
            "Whisper; without --analysis-json, creates a Codex request artifact."
        ),
    )
    return parser.parse_args(argv)


def print_config() -> None:
    settings = load_settings()
    print(f"environment={settings.environment}")
    print(f"log_level={settings.log_level}")
    print(f"data_dir={settings.data_dir}")
    print(f"audio_output_dir={settings.audio_output_dir}")
    print(f"transcript_output_dir={settings.transcript_output_dir}")
    print(f"notion_token_configured={bool(settings.notion_token)}")
    print(f"notion_parent_page_id_configured={bool(settings.notion_parent_page_id)}")
    print(
        "notion_podcast_database_id_configured="
        f"{bool(settings.notion_podcast_database_id)}"
    )


def infer_title(source: str) -> str:
    """Infer a reasonable MVP page title from source."""
    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if parsed.netloc:
            path_name = Path(parsed.path).stem
            return path_name.replace("-", " ").replace("_", " ").strip() or parsed.netloc
    return Path(source).stem or "Untitled Podcast"


def resolve_title(source: str, source_type: SourceType) -> str:
    """Resolve the best available podcast title without requiring AI."""
    if source_type in {SourceType.APPLE_PODCAST, SourceType.PODCAST_RSS}:
        try:
            resolved_title = resolve_podcast_title(source)
        except PodcastResolverError as exc:
            LOGGER.warning("Could not resolve podcast title from metadata: %s", exc)
        else:
            if resolved_title:
                return resolved_title
    return infer_title(source)


def notion_source_type(source_type: SourceType) -> str:
    """Map router source type to Notion Podcast Library Source Type select."""
    if source_type == SourceType.YOUTUBE:
        return "YouTube"
    if source_type == SourceType.LOCAL_AUDIO:
        return "Local Audio"
    return "Podcast"


def slugify(value: str, fallback: str = "podcast") -> str:
    """Create a stable filesystem-safe slug for generated artifacts."""
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:80] or fallback


def transcript_output_path(title: str, output_dir: Path) -> Path:
    """Return the transcript JSON path for a processed podcast."""
    return output_dir / f"{slugify(title)}.json"


def weekly_review_request_output_path(week: str, output_dir: Path) -> Path:
    return output_dir / "weekly_review_requests" / f"{week}.json"


def analysis_request_output_path(title: str, data_dir: Path) -> Path:
    """Return where Codex analysis request JSON should be saved."""
    return data_dir / "analysis_requests" / f"{slugify(title)}.json"


def analysis_output_path_from_request(request_path: Path) -> Path:
    """Return the expected Codex analysis output path for a request artifact."""
    return request_path.parent.parent / "analysis" / request_path.name


def analysis_request_result(
    request_path: Path,
    transcript_path: Path,
    source: str,
    title: str,
    source_type: str,
) -> MainPipelineResult:
    """Build the request result and exact command for the artifact handoff."""
    expected_output_path = analysis_output_path_from_request(request_path)
    rerun_command = shlex.join(
        [
            "./.venv/bin/python",
            "src/main.py",
            source,
            "--title",
            title,
            "--source-type",
            source_type,
            "--transcript-json",
            str(transcript_path),
            "--analysis-json",
            str(expected_output_path),
        ]
    )
    return MainPipelineResult(
        kind="analysis_request",
        value=str(request_path),
        expected_output_path=str(expected_output_path),
        rerun_command=rerun_command,
    )


def save_analysis_request_json(
    analyzer: LearningAnalyzer,
    title: str,
    transcript_text: str,
    output_path: Path,
) -> Path:
    """Save transcript analysis instructions for Codex Skill orchestration."""
    request = analyzer.prepare_analysis_request(
        TranscriptAnalysisInput(title=title, transcript=transcript_text)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(request.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()


def load_transcript_json(path: Path) -> dict:
    """Load an existing transcript JSON file for direct Notion publishing."""
    if not path.exists():
        raise MainPipelineError(f"Transcript JSON does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MainPipelineError(f"Transcript JSON is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise MainPipelineError("Transcript JSON must be a JSON object.")
    return payload


def load_json_object(path: Path, label: str) -> dict:
    """Load a JSON object from disk for publish-only commands."""
    if not path.exists():
        raise MainPipelineError(f"{label} does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise MainPipelineError(f"{label} is invalid: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise MainPipelineError(f"{label} must be a JSON object.")
    return payload


def sync_vocab_comments_from_cli(dry_run: bool = False) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        result = sync_vocab_comments(dry_run=dry_run)
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    if dry_run:
        print("Vocabulary comment sync dry run")
        print()
        print("Scanned pages:")
        print(result.scanned_pages)
        print()
        print("Matched comments:")
        print(result.matched_comments)
        print()
        print("Create:")
        print(result.created)
        print()
        print("Update:")
        print(result.updated)
        print()
        print("Preview:")
        for preview in result.previews or []:
            print(json.dumps(preview, ensure_ascii=False, indent=2))
        return MainPipelineResult(
            kind="vocab_comment_sync_dry_run",
            value=str(result.scanned_pages),
        )

    LOGGER.info(
        "Vocabulary comments synced: created=%s updated=%s skipped=%s",
        result.created,
        result.updated,
        result.skipped,
    )
    return MainPipelineResult(
        kind="vocab_comment_sync",
        value=f"created={result.created}, updated={result.updated}, skipped={result.skipped}",
    )


def publish_highlight_vocab_from_cli(
    page_id: str,
    dry_run: bool = False,
) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    if not page_id.strip():
        raise MainPipelineError("--publish-highlight-vocab requires a page_id.")

    normalized_page_id = page_id.strip()
    try:
        if dry_run:
            preview = build_vocabulary_learning_preview(normalized_page_id)
            approved = preview.get("approved_vocabulary", [])
            rejected = preview.get("rejected_candidates", [])
            print("Highlight vocabulary dry run")
            print(f"Page ID: {normalized_page_id}")
            print(f"Approved: {len(approved)}")
            print(f"Rejected: {len(rejected)}")
            print(json.dumps(preview, ensure_ascii=False, indent=2))
            return MainPipelineResult(
                kind="highlight_vocab_dry_run",
                value=f"approved={len(approved)}, rejected={len(rejected)}",
            )

        result: HighlightVocabularyPublishResult = publish_highlight_vocabulary(
            normalized_page_id
        )
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    LOGGER.info(
        "Highlight vocabulary published: created=%s updated=%s skipped=%s",
        result.created,
        result.updated,
        result.skipped,
    )
    return MainPipelineResult(
        kind="highlight_vocab_page",
        value=f"created={result.created}, updated={result.updated}, skipped={result.skipped}",
    )


def debug_comments_from_cli() -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        result = debug_comment_sync()
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc
    return MainPipelineResult(kind="debug_comments", value=str(result))


def debug_page_comments_from_cli() -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        result = debug_page_comments()
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc
    return MainPipelineResult(kind="debug_page_comments", value=str(result))


def debug_comment_sources_from_cli() -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        result = debug_comment_sources()
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc
    return MainPipelineResult(kind="debug_comment_sources", value=str(result))


def run_vocabulary_agent_from_cli() -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        result = sync_vocabulary_from_highlight_changes()
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    LOGGER.info(
        "Vocabulary sync agent finished: pages=%s new_highlights=%s created=%s updated=%s skipped=%s",
        result.scanned_pages,
        result.new_highlights,
        result.created,
        result.updated,
        result.skipped,
    )
    return MainPipelineResult(
        kind="vocabulary_sync_agent",
        value=(
            f"pages={result.scanned_pages}, new_highlights={result.new_highlights}, "
            f"created={result.created}, updated={result.updated}, skipped={result.skipped}"
        ),
    )


def publish_vocab_from_file(path: Path, dry_run: bool = False) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        expressions = load_analysis_expressions(path)
        if not expressions:
            raise MainPipelineError("Analysis JSON does not contain any expressions.")

        if dry_run:
            plan = build_vocabulary_publish_plan(expressions)
            _print_vocabulary_dry_run(plan)
            return MainPipelineResult(kind="vocabulary_dry_run", value=str(path))

        config = load_notion_config()
        notion = create_notion_client(config.token)

        created = 0
        updated = 0
        for expression in expressions:
            word = str(expression.get("expression", "")).strip()
            if not word:
                continue
            result = upsert_vocabulary_page(
                expression_to_vocabulary_payload(expression),
                notion=notion,
                vocabulary_database_id=config.vocabulary_database_id,
            )
            if result.action == "updated":
                updated += 1
            else:
                created += 1
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    LOGGER.info("Vocabulary pages published: created=%s updated=%s", created, updated)
    return MainPipelineResult(
        kind="vocabulary_page",
        value=f"created={created}, updated={updated}",
    )


def publish_weekly_review_from_file(path: Path) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)
    try:
        config = load_notion_config()
        notion = create_notion_client(config.token)
        weekly_review_json = validate_weekly_review_output(
            load_json_object(path, "Weekly Review JSON")
        )
        result = publish_weekly_review(
            WeeklyReviewPublishPayload(
                week=str(weekly_review_json.get("week", "")),
                executive_summary=weekly_review_json.get("executive_summary", {}),
                knowledge_insights=weekly_review_json.get("knowledge_insights", []),
                expression_upgrade=weekly_review_json.get("expression_upgrade", []),
                vocabulary_memory=weekly_review_json.get("vocabulary_memory", []),
                career_reflection=weekly_review_json.get("career_reflection", {}),
                next_learning_direction=weekly_review_json.get("next_learning_direction", []),
            ),
            notion=notion,
            weekly_database_id=config.weekly_database_id,
            vocabulary_database_id=config.vocabulary_database_id,
        )
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    LOGGER.info("Weekly review page created: %s", result.page_id)
    return MainPipelineResult(kind="weekly_review_page", value=result.page_url or result.page_id)


def publish_from_existing_transcript(
    args: argparse.Namespace,
    title: str,
    source_type: str,
) -> MainPipelineResult:
    """Prepare analysis or publish without rerunning audio extraction/Whisper."""
    transcript_payload = load_transcript_json(args.transcript_json)
    transcript_text = transcript_to_text(transcript_payload)
    analyzer = LearningAnalyzer()
    analyzer.prepare_analysis_request(
        TranscriptAnalysisInput(title=title, transcript=transcript_text)
    )
    if not args.analysis_json:
        request_path = save_analysis_request_json(
            analyzer=analyzer,
            title=title,
            transcript_text=transcript_text,
            output_path=analysis_request_output_path(title, load_settings().data_dir),
        )
        return analysis_request_result(
            request_path=request_path,
            transcript_path=args.transcript_json.resolve(),
            source=args.source,
            title=title,
            source_type=source_type,
        )

    analysis = analyzer.validate_generated_analysis(
        read_generated_analysis_file(args.analysis_json)
    )
    publish_result = publish_complete_learning_materials(
        CompletePodcastLearningPayload(
            title=title,
            source_url=args.source if args.source and urlparse(args.source).scheme else None,
            source_type=source_type,
            transcript=transcript_text,
            analysis=analysis,
        )
    )
    LOGGER.info(
        "Complete Notion learning page created from existing transcript with "
        "%s expression pages: %s",
        len(publish_result.expression_page_ids),
        publish_result.podcast_page_id,
    )
    return MainPipelineResult(
        kind="notion_page",
        value=publish_result.podcast_page_url or publish_result.podcast_page_id,
    )


def run_weekly_review_pipeline(args: argparse.Namespace) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)

    try:
        config = load_notion_config()
        notion = create_notion_client(config.token)
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    weekly_data = fetch_weekly_learning_data(
        notion,
        config.podcast_database_id,
        config.expression_database_id,
    )
    request_path = weekly_review_request_output_path(
        weekly_data.week,
        settings.data_dir,
    )
    save_weekly_review_request(weekly_data, request_path)
    LOGGER.info("Weekly review request saved: %s", request_path)

    if not args.weekly_review_json:
        return MainPipelineResult(kind="weekly_review_request", value=str(request_path))

    weekly_review_json = validate_weekly_review_output(
        read_generated_analysis_file(args.weekly_review_json)
    )
    executive_summary = weekly_review_json.get("executive_summary", {})
    if not isinstance(executive_summary, dict):
        executive_summary = {}
    knowledge_insights = weekly_review_json.get("knowledge_insights", [])
    if not isinstance(knowledge_insights, list):
        knowledge_insights = []
    expression_upgrade = weekly_review_json.get("expression_upgrade", [])
    if not isinstance(expression_upgrade, list):
        expression_upgrade = []
    vocabulary_memory = weekly_review_json.get("vocabulary_memory", [])
    if not isinstance(vocabulary_memory, list):
        vocabulary_memory = []
    career_reflection = weekly_review_json.get("career_reflection", {})
    if not isinstance(career_reflection, dict):
        career_reflection = {}
    next_learning_direction = weekly_review_json.get("next_learning_direction", [])
    if not isinstance(next_learning_direction, list):
        next_learning_direction = []
    publish_result = publish_weekly_review(
        WeeklyReviewPublishPayload(
            week=str(weekly_review_json.get("week", weekly_data.week)),
            executive_summary=executive_summary,
            knowledge_insights=knowledge_insights,
            expression_upgrade=expression_upgrade,
            vocabulary_memory=vocabulary_memory,
            career_reflection=career_reflection,
            next_learning_direction=next_learning_direction,
        ),
        notion=notion,
        weekly_database_id=config.weekly_database_id,
    )
    return MainPipelineResult(
        kind="weekly_review_page",
        value=publish_result.page_url or publish_result.page_id,
    )


def _weekly_reflection_learning_context_path_from_args(args: argparse.Namespace) -> Path:
    weekly_reflection_arg = getattr(args, "weekly_reflection", None)
    if isinstance(weekly_reflection_arg, str) and weekly_reflection_arg:
        return Path(weekly_reflection_arg)
    return Path("output/weekly_learning_context.json")


def run_weekly_reflection_pipeline_from_cli(args: argparse.Namespace) -> MainPipelineResult:
    settings = load_settings()
    configure_logging(settings.log_level)

    weekly_learning_context_path = _weekly_reflection_learning_context_path_from_args(args)
    try:
        result = run_weekly_reflection_pipeline(
            weekly_learning_context_path=weekly_learning_context_path,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        raise MainPipelineError(str(exc)) from exc

    print("================================")
    print("Weekly Reflection Pipeline")
    print("================================")
    print()
    print("Extraction:")
    print("SUCCESS")
    print()
    print("Reflection Analysis:")
    print("SUCCESS")
    print()
    print("ReflectionContext:")
    print("saved")
    print()
    print("Path:")
    print(str(result.reflection_context_path))
    print()
    print("Weekly Review:")
    print("SUCCESS")
    print()
    print("Quality Gate:")
    print("PASSED")
    print(f"Score: {int(result.quality_report.get('score', 0))}/100")
    print()
    is_dry_run = bool(getattr(result, "dry_run", args.dry_run))
    publish_result = getattr(result, "publish_result", None)

    if is_dry_run or publish_result is None:
        print("Notion skipped (dry run)")
    else:
        print("Notion:")
        print("Page created")
        print()
        print("URL:")
        print(publish_result.page_url or publish_result.page_id)

    return MainPipelineResult(
        kind="weekly_reflection_dry_run" if is_dry_run or publish_result is None else "weekly_reflection_page",
        value="dry-run" if is_dry_run or publish_result is None else (publish_result.page_url or publish_result.page_id),
    )


def _weekly_review_analysis_path_from_args(args: argparse.Namespace) -> Optional[Path]:
    weekly_review_arg = getattr(args, "weekly_review", None)
    if isinstance(weekly_review_arg, str) and weekly_review_arg:
        return Path(weekly_review_arg)
    if args.weekly_review_json:
        return args.weekly_review_json
    return None


def run_pipeline(args: argparse.Namespace) -> Optional[MainPipelineResult]:
    """Run the podcast pipeline and return the created Notion page URL/ID."""
    settings = load_settings()
    configure_logging(settings.log_level)

    if args.print_config:
        print_config()
        return None

    if args.publish_highlight_vocab is not None:
        return publish_highlight_vocab_from_cli(
            args.publish_highlight_vocab,
            dry_run=args.dry_run,
        )

    if args.run_vocabulary_agent:
        return run_vocabulary_agent_from_cli()

    if args.sync_vocab_comments:
        return sync_vocab_comments_from_cli(dry_run=args.dry_run)

    if args.debug_comments:
        return debug_comments_from_cli()

    if args.debug_page_comments:
        return debug_page_comments_from_cli()

    if args.debug_comment_sources:
        return debug_comment_sources_from_cli()

    if args.publish_weekly_review:
        return publish_weekly_review_from_file(args.publish_weekly_review)

    if args.weekly_reflection is not None:
        return run_weekly_reflection_pipeline_from_cli(args)

    weekly_review_analysis_path = _weekly_review_analysis_path_from_args(args)
    if args.weekly_review is not None or weekly_review_analysis_path is not None:
        if weekly_review_analysis_path is not None:
            return run_weekly_review_agent(
                weekly_review_analysis_path,
                dry_run=args.dry_run,
            )
        return run_weekly_review_pipeline(args)

    if not args.source:
        raise MainPipelineError("Missing source. Usage: python src/main.py <source>")

    detection = detect_source(args.source)
    title = args.title or resolve_title(args.source, detection.type)
    source_type = args.source_type or notion_source_type(detection.type)

    if args.transcript_json:
        return publish_from_existing_transcript(args, title, source_type)

    LOGGER.info("Starting podcast source pipeline")
    audio_path = extract_audio_from_source(
        args.source,
        output_dir=settings.audio_output_dir,
    )
    LOGGER.info("Audio ready: %s", audio_path)
    audio_validation = validate_audio_source(audio_path)
    if audio_validation.duration_seconds is None:
        LOGGER.info("Audio source validated: duration=skipped")
    else:
        LOGGER.info(
            "Audio source validated: duration=%.1f seconds",
            audio_validation.duration_seconds,
        )

    transcript_result = transcribe_audio(
        audio_validation.path,
        model_size=args.model_size,
        device=args.device,
        compute_type=args.compute_type,
    )
    LOGGER.info("Transcript generated with %s segments", len(transcript_result.segments))
    transcript_path = save_transcript_json(
        transcript_result,
        transcript_output_path(title, settings.transcript_output_dir),
    )
    LOGGER.info("Transcript saved: %s", transcript_path)

    transcript_text = transcript_to_text(transcript_result.to_dict())
    analyzer = LearningAnalyzer()
    analyzer.prepare_analysis_request(
        TranscriptAnalysisInput(title=title, transcript=transcript_text)
    )
    if not args.analysis_json:
        request_path = save_analysis_request_json(
            analyzer=analyzer,
            title=title,
            transcript_text=transcript_text,
            output_path=analysis_request_output_path(title, settings.data_dir),
        )
        LOGGER.info("Codex AI analysis request saved: %s", request_path)
        return analysis_request_result(
            request_path=request_path,
            transcript_path=transcript_path,
            source=args.source,
            title=title,
            source_type=source_type,
        )

    analysis = analyzer.validate_generated_analysis(
        read_generated_analysis_file(args.analysis_json)
    )
    publish_result = publish_complete_learning_materials(
        CompletePodcastLearningPayload(
            title=title,
            source_url=args.source if urlparse(args.source).scheme else None,
            source_type=source_type,
            transcript=transcript_text,
            analysis=analysis,
        )
    )
    LOGGER.info(
        "Complete Notion learning page created with %s expression pages: %s",
        len(publish_result.expression_page_ids),
        publish_result.podcast_page_id,
    )

    return MainPipelineResult(
        kind="notion_page",
        value=publish_result.podcast_page_url or publish_result.podcast_page_id,
    )


def main(argv: Optional[list[str]] = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if argv and argv[0] == "weekly-reflection":
        argv = ["--weekly-reflection", *argv[1:]]
    args = parse_args(argv)

    try:
        result = run_pipeline(args)
    except (
        MainPipelineError,
        WeeklyReviewAnalyzerError,
        WeeklyReviewAgentError,
        WeeklyReviewPipelineError,
        WeeklyReflectionPipelineError,
        SourceRouterError,
        SourceExtractionError,
        AudioValidationError,
        TranscriptionError,
        NotionUploadError,
        LearningAnalyzerError,
        SkillAIWorkflowError,
        AnalysisValidationError,
        LearningPublisherError,
        WeeklyReviewPublisherError,
        VocabularySyncAgentError,
        CommentVocabSyncError,
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result:
        if result.kind == "analysis_request":
            print(f"Codex AI Analysis Request: {result.value}")
            if result.expected_output_path and result.rerun_command:
                print(f"Expected Analysis Output: {result.expected_output_path}")
                print("Next step:")
                print("Use Codex to read the request and generate:")
                print(result.expected_output_path)
                print("Then run:")
                print(result.rerun_command)
        elif result.kind == "weekly_review_request":
            print(f"Weekly Review Request: {result.value}")
        elif result.kind == "weekly_review_page":
            print(f"Created Weekly Review Page: {result.value}")
        elif result.kind == "weekly_review_dry_run":
            print(f"Weekly Review Dry Run: {result.value}")
        elif result.kind == "weekly_reflection_page":
            print(f"Created Weekly Reflection Page: {result.value}")
        elif result.kind == "weekly_reflection_dry_run":
            print(f"Weekly Reflection Dry Run: {result.value}")
        elif result.kind == "vocab_comment_sync":
            print(f"Synced Vocabulary Comments: {result.value}")
        elif result.kind == "debug_comments":
            print(f"Debug Comments: {result.value}")
        elif result.kind == "debug_page_comments":
            print(f"Debug Page Comments: {result.value}")
        elif result.kind == "debug_comment_sources":
            print(f"Debug Comment Sources: {result.value}")
        elif result.kind == "vocabulary_sync_agent":
            print(f"Vocabulary Sync Agent: {result.value}")
        elif result.kind == "highlight_vocab_page":
            print(f"Published Highlight Vocabulary: {result.value}")
        elif result.kind == "highlight_vocab_dry_run":
            print(f"Highlight Vocabulary Dry Run: {result.value}")
        else:
            print(f"Created Notion Podcast Page: {result.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
