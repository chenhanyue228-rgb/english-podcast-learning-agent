"""Legacy CLI publisher for precomputed podcast learning JSON.

The canonical user-facing entrypoint is ``python3 src/main.py``. This module is
kept as a small development tool for publishing already prepared transcript and
learning-analysis JSON fixtures.

Current CLI usage expects precomputed transcript and analysis JSON files:

    python -m src.workflow.podcast_pipeline \
        --source-url https://example.com/podcast \
        --title "AI Transformation in Business" \
        --source-type Podcast \
        --transcript-file transcript.json \
        --analysis-file learning.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Optional, Protocol, Sequence, TYPE_CHECKING

from src.notion.config import NotionConfigError, load_notion_config
from src.notion.renderers import (
    expression_body_blocks as render_expression_body_blocks,
    podcast_body_blocks,
)
from src.notion.schema import EXPRESSION_DATABASE, PODCAST_LIBRARY
from src.notion.target_binding import ensure_notion_target_binding_for_write

if TYPE_CHECKING:
    from notion_client import Client


class PipelineError(RuntimeError):
    """Raised when the podcast pipeline cannot complete."""


@dataclass(frozen=True)
class PodcastMetadata:
    title: str
    source_url: Optional[str]
    source_type: str
    topic: Optional[str] = None
    difficulty: Optional[str] = None
    processed_date: str = field(default_factory=lambda: date.today().isoformat())


@dataclass(frozen=True)
class Transcript:
    text: str
    segments: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class LearningExpression:
    text: str
    category: str
    meaning: str
    color: str
    usage_context: str = ""
    context: str = ""
    example: str = ""


@dataclass(frozen=True)
class LearningAnalysis:
    summary: str
    expressions: list[LearningExpression]
    short_summary: Optional[str] = None
    ai_summary: Optional[str] = None


@dataclass(frozen=True)
class PipelineResult:
    podcast_page_id: str
    expression_page_ids: list[str]


class AudioExtractor(Protocol):
    def extract(self, metadata: PodcastMetadata) -> Path:
        """Extract audio and return a local audio path."""


class Transcriber(Protocol):
    def transcribe(self, audio_path: Path) -> Transcript:
        """Generate a transcript from an audio file."""


class LearningAnalyzer(Protocol):
    def analyze(self, transcript: Transcript) -> LearningAnalysis:
        """Analyze a transcript into English learning content."""


class NotImplementedAudioExtractor:
    def extract(self, metadata: PodcastMetadata) -> Path:
        raise PipelineError(
            "Audio extraction is not implemented yet. Provide --transcript-file and "
            "--analysis-file for the current CLI workflow."
        )


class NotImplementedTranscriber:
    def transcribe(self, audio_path: Path) -> Transcript:
        raise PipelineError(
            "Transcription is not implemented yet. Provide --transcript-file."
        )


class NotImplementedLearningAnalyzer:
    def analyze(self, transcript: Transcript) -> LearningAnalysis:
        raise PipelineError(
            "AI learning analysis is not implemented yet. Provide --analysis-file."
        )


class PodcastPipeline:
    """Coordinate the complete podcast-to-Notion learning workflow."""

    def __init__(
        self,
        extractor: AudioExtractor,
        transcriber: Transcriber,
        analyzer: LearningAnalyzer,
        publisher: "NotionPodcastPublisher",
    ) -> None:
        self.extractor = extractor
        self.transcriber = transcriber
        self.analyzer = analyzer
        self.publisher = publisher

    def process(self, metadata: PodcastMetadata) -> PipelineResult:
        """Run extraction, transcription, analysis, publishing, and reporting."""
        audio_path = self.extractor.extract(metadata)
        transcript = self.transcriber.transcribe(audio_path)
        analysis = self.analyzer.analyze(transcript)
        return publish_learning_result(
            metadata=metadata,
            transcript=transcript,
            analysis=analysis,
            publisher=self.publisher,
        )


def title_value(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def rich_text_value(text: str) -> dict[str, Any]:
    if not text:
        return {"rich_text": []}
    return {"rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}


def select_value(name: Optional[str]) -> dict[str, Any]:
    return {"select": {"name": name}} if name else {"select": None}


def date_value(value: str) -> dict[str, Any]:
    return {"date": {"start": value}}


def url_value(value: Optional[str]) -> dict[str, Any]:
    return {"url": value}


def relation_value(page_ids: Sequence[str]) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(f"Could not read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PipelineError(f"Invalid JSON in {path}: {exc}") from exc


def load_transcript(path: Path) -> Transcript:
    payload = load_json_file(path)
    if isinstance(payload.get("text"), str):
        return Transcript(text=payload["text"], segments=payload.get("segments", []))

    segments = payload.get("segments")
    if isinstance(segments, list):
        text = " ".join(str(segment.get("text", "")).strip() for segment in segments)
        text = " ".join(text.split())
        return Transcript(text=text, segments=segments)

    raise PipelineError(
        "Transcript JSON must contain either a string 'text' field or a "
        "'segments' list."
    )


def parse_expression(payload: dict[str, Any], transcript_text: str) -> LearningExpression:
    text = payload.get("text") or payload.get("expression")
    category = payload.get("type") or payload.get("category")
    meaning = payload.get("meaning")
    color = payload.get("color") or payload.get("color_type")

    missing = [
        name
        for name, value in {
            "text": text,
            "category/type": category,
            "meaning": meaning,
            "color": color,
        }.items()
        if not value
    ]
    if missing:
        raise PipelineError(f"Expression is missing required fields: {', '.join(missing)}")

    return LearningExpression(
        text=str(text),
        category=str(category),
        meaning=str(meaning),
        color=str(color).title(),
        usage_context=str(payload.get("usage_context") or payload.get("usage") or ""),
        context=str(payload.get("context") or transcript_text),
        example=str(payload.get("example") or ""),
    )


def load_learning_analysis(path: Path, transcript: Transcript) -> LearningAnalysis:
    payload = load_json_file(path)
    raw_expressions = payload.get("expressions")
    if not isinstance(raw_expressions, list):
        raise PipelineError("Analysis JSON must contain an 'expressions' list.")

    return LearningAnalysis(
        summary=str(payload.get("summary") or ""),
        short_summary=str(payload.get("short_summary") or ""),
        ai_summary=str(payload.get("ai_summary") or payload.get("summary") or ""),
        expressions=[
            parse_expression(expression, transcript.text)
            for expression in raw_expressions
            if isinstance(expression, dict)
        ],
    )


def expression_payload(expression: LearningExpression) -> dict[str, str]:
    return {
        "text": expression.text,
        "expression": expression.text,
        "category": expression.category,
        "type": expression.category,
        "meaning": expression.meaning,
        "color": expression.color,
        "usage_context": expression.usage_context,
        "context": expression.context,
        "example": expression.example,
    }


class NotionPodcastPublisher:
    """Publish precomputed podcast learning output to Notion."""

    def __init__(self, notion: "Client", podcast_db_id: str, expression_db_id: str):
        self.notion = notion
        self.podcast_db_id = podcast_db_id
        self.expression_db_id = expression_db_id

    def create_podcast_page(
        self,
        metadata: PodcastMetadata,
        transcript: Transcript,
        analysis: LearningAnalysis,
    ) -> str:
        ensure_notion_target_binding_for_write(
            self.notion,
            configured_role_ids={
                PODCAST_LIBRARY: self.podcast_db_id,
                EXPRESSION_DATABASE: self.expression_db_id,
            },
        )
        response = self.notion.pages.create(
            parent={"data_source_id": self.podcast_db_id},
            properties={
                "Title": title_value(metadata.title),
                "URL": url_value(metadata.source_url),
                "Source Type": select_value(metadata.source_type),
                "Date": date_value(metadata.processed_date),
                "Topic": select_value(metadata.topic),
                "Difficulty": select_value(metadata.difficulty),
                "Short Summary": rich_text_value(
                    analysis.short_summary or analysis.summary
                ),
            },
        )
        page_id = response.get("id")
        if not page_id:
            raise PipelineError("Notion did not return an ID for the podcast page.")
        return page_id

    def create_expression_pages(
        self,
        podcast_page_id: str,
        transcript: Transcript,
        expressions: Sequence[LearningExpression],
    ) -> list[str]:
        ensure_notion_target_binding_for_write(
            self.notion,
            configured_role_ids={
                PODCAST_LIBRARY: self.podcast_db_id,
                EXPRESSION_DATABASE: self.expression_db_id,
            },
        )
        page_ids: list[str] = []
        for expression in expressions:
            response = self.notion.pages.create(
                parent={"data_source_id": self.expression_db_id},
                properties={
                    "Expression": title_value(expression.text),
                    "Category": select_value(expression.category),
                    "Source Podcast": relation_value([podcast_page_id]),
                    "Review Status": select_value("New"),
                },
                children=render_expression_body_blocks(
                    expression_payload(expression),
                    fallback_context_sentence=transcript.text,
                ),
            )
            page_id = response.get("id")
            if not page_id:
                raise PipelineError(
                    f"Notion did not return an ID for expression '{expression.text}'."
                )
            page_ids.append(page_id)
        return page_ids

    def insert_highlighted_transcript(
        self,
        podcast_page_id: str,
        transcript: Transcript,
        analysis: LearningAnalysis,
        expressions: Sequence[LearningExpression],
    ) -> None:
        ensure_notion_target_binding_for_write(
            self.notion,
            configured_role_ids={
                PODCAST_LIBRARY: self.podcast_db_id,
                EXPRESSION_DATABASE: self.expression_db_id,
            },
        )
        self.notion.blocks.children.append(
            block_id=podcast_page_id,
            children=podcast_body_blocks(
                summary=analysis.summary,
                transcript=transcript.text,
                expressions=[expression_payload(expression) for expression in expressions],
            ),
        )

    def get_relation_page_ids(self, page_id: str, property_name: str) -> list[str]:
        page = self.notion.pages.retrieve(page_id=page_id)
        relation = (
            page.get("properties", {})
            .get(property_name, {})
            .get("relation", [])
        )
        return [item["id"] for item in relation if "id" in item]

def create_notion_publisher() -> NotionPodcastPublisher:
    try:
        from notion_client import Client
    except ModuleNotFoundError as exc:
        raise NotionConfigError(
            "Missing dependency notion-client. Install dependencies with "
            "pip install -r requirements.txt."
        ) from exc

    config = load_notion_config()
    notion = Client(auth=config.token)
    ensure_notion_target_binding_for_write(notion, config=config)
    return NotionPodcastPublisher(
        notion=notion,
        podcast_db_id=config.podcast_database_id,
        expression_db_id=config.expression_database_id,
    )


def publish_learning_result(
    metadata: PodcastMetadata,
    transcript: Transcript,
    analysis: LearningAnalysis,
    publisher: NotionPodcastPublisher,
) -> PipelineResult:
    podcast_page_id = publisher.create_podcast_page(metadata, transcript, analysis)
    expression_page_ids = publisher.create_expression_pages(
        podcast_page_id, transcript, analysis.expressions
    )
    publisher.insert_highlighted_transcript(
        podcast_page_id, transcript, analysis, analysis.expressions
    )
    return PipelineResult(
        podcast_page_id=podcast_page_id,
        expression_page_ids=expression_page_ids,
    )


def run_pipeline(
    metadata: PodcastMetadata,
    transcript: Transcript,
    analysis: LearningAnalysis,
    publisher: NotionPodcastPublisher,
) -> PipelineResult:
    """Backward-compatible helper for publishing precomputed learning output."""
    return publish_learning_result(metadata, transcript, analysis, publisher)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Process podcast learning data and publish it to Notion."
    )
    parser.add_argument("--title", required=True, help="Podcast title.")
    parser.add_argument("--source-url", help="Original podcast or audio source URL.")
    parser.add_argument(
        "--source-type",
        required=True,
        choices=["YouTube", "Podcast", "Local Audio"],
        help=(
            "Source type stored in Notion. YouTube is retained only for legacy "
            "compatibility and is outside v1."
        ),
    )
    parser.add_argument("--topic", help="Podcast topic.")
    parser.add_argument("--difficulty", help="Learning difficulty.")
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Processing date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--transcript-file",
        required=True,
        type=Path,
        help="Transcript JSON with 'text' or 'segments'.",
    )
    parser.add_argument(
        "--analysis-file",
        required=True,
        type=Path,
        help="Learning analysis JSON with 'summary' and 'expressions'.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        metadata = PodcastMetadata(
            title=args.title,
            source_url=args.source_url,
            source_type=args.source_type,
            topic=args.topic,
            difficulty=args.difficulty,
            processed_date=args.date,
        )
        transcript = load_transcript(args.transcript_file)
        analysis = load_learning_analysis(args.analysis_file, transcript)
        publisher = create_notion_publisher()
        result = run_pipeline(metadata, transcript, analysis, publisher)
    except (PipelineError, NotionConfigError) as exc:
        print(f"Podcast pipeline failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Podcast pipeline failed unexpectedly: {exc}", file=sys.stderr)
        return 1

    print("Podcast pipeline completed:")
    print(f"Podcast page: {result.podcast_page_id}")
    print("Expression pages:")
    for page_id in result.expression_page_ids:
        print(f"- {page_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
