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
from src.extractor.pipeline import SourceExtractionError, extract_audio_from_source
from src.extractor.podcast_resolver import PodcastResolverError, resolve_podcast_title
from src.extractor.router import SourceRouterError, SourceType, detect_source
from src.notion.learning_publisher import (
    CompletePodcastLearningPayload,
    LearningPublisherError,
    publish_complete_learning_materials,
)
from src.notion.weekly_review_publisher import (
    WeeklyReviewPublishPayload,
    WeeklyReviewPublisherError,
    publish_weekly_review,
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


LOGGER = logging.getLogger(__name__)


class MainPipelineError(RuntimeError):
    """Raised when the CLI pipeline cannot complete."""


@dataclass(frozen=True)
class MainPipelineResult:
    """Result of one CLI pipeline run."""

    kind: str
    value: str


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Notion Podcast Library page from an audio source."
    )
    parser.add_argument(
        "source",
        nargs="?",
        help=(
            "YouTube URL, Apple Podcasts page URL, Podcast RSS URL, direct "
            "audio URL, or local audio file."
        ),
    )
    parser.add_argument(
        "--title",
        help="Optional Notion page title. Defaults to a simple title inferred from the source.",
    )
    parser.add_argument(
        "--source-type",
        choices=["YouTube", "Podcast", "Local Audio"],
        help="Optional Notion Source Type. Defaults based on detected source.",
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
        action="store_true",
        help="Generate or publish the current week's Weekly Review workflow.",
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
        "--transcript-json",
        type=Path,
        help=(
            "Path to an existing transcript JSON. When provided with "
            "--analysis-json, skips audio extraction and Whisper."
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


def publish_from_existing_transcript(
    args: argparse.Namespace,
    title: str,
    source_type: str,
) -> MainPipelineResult:
    """Create a complete Notion page without rerunning audio extraction/Whisper."""
    if not args.analysis_json:
        raise MainPipelineError("--transcript-json requires --analysis-json.")

    transcript_payload = load_transcript_json(args.transcript_json)
    transcript_text = transcript_to_text(transcript_payload)
    analyzer = LearningAnalyzer()
    analyzer.prepare_analysis_request(
        TranscriptAnalysisInput(title=title, transcript=transcript_text)
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
    publish_result = publish_weekly_review(
        WeeklyReviewPublishPayload(
            week=str(weekly_review_json.get("week", weekly_data.week)),
            date=str(weekly_review_json.get("date", weekly_data.date)),
            statistics=weekly_review_json.get("statistics", {}),
            summary=weekly_review_json.get("summary", {}),
            key_learning_points=list(weekly_review_json.get("key_learning_points", [])),
            recommended_review=list(weekly_review_json.get("recommended_review", [])),
            podcast_page_ids=[podcast.page_id for podcast in weekly_data.podcasts if podcast.page_id],
        ),
        notion=notion,
        weekly_database_id=config.weekly_database_id,
    )
    return MainPipelineResult(
        kind="weekly_review_page",
        value=publish_result.page_url or publish_result.page_id,
    )


def run_pipeline(args: argparse.Namespace) -> Optional[MainPipelineResult]:
    """Run the podcast pipeline and return the created Notion page URL/ID."""
    settings = load_settings()
    configure_logging(settings.log_level)

    if args.print_config:
        print_config()
        return None

    if args.weekly_review:
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
        return MainPipelineResult(
            kind="analysis_request",
            value=str(request_path),
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
    args = parse_args(argv)

    try:
        result = run_pipeline(args)
    except (
        MainPipelineError,
        WeeklyReviewAnalyzerError,
        WeeklyReviewPipelineError,
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
    ) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if result:
        if result.kind == "analysis_request":
            print(f"Codex AI Analysis Request: {result.value}")
        elif result.kind == "weekly_review_request":
            print(f"Weekly Review Request: {result.value}")
        elif result.kind == "weekly_review_page":
            print(f"Created Weekly Review Page: {result.value}")
        else:
            print(f"Created Notion Podcast Page: {result.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
