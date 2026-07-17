"""Podcast metadata analyzer for Phase 3."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from src.analyzer.ai_client import AIClient
from src.analyzer.models import PodcastMetadata
from src.analyzer.prompt_loader import DEFAULT_PROMPT_DIR, load_metadata_prompt
from src.analyzer.validators import AnalysisValidationError, validate_podcast_metadata


class MetadataAnalyzerError(RuntimeError):
    """Raised when podcast metadata analysis cannot complete."""


ALLOWED_DIFFICULTIES = {"Beginner", "Intermediate", "Advanced"}


@dataclass(frozen=True)
class MetadataAnalysisInput:
    transcript: str
    title: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "transcript": self.transcript,
        }


class PodcastMetadataAnalyzer:
    """Analyze transcript text and return normalized Podcast Library metadata."""

    def __init__(
        self,
        ai_client: AIClient,
        prompt: Optional[str] = None,
        prompt_dir: Optional[Path] = None,
    ) -> None:
        self.ai_client = ai_client
        self.prompt = prompt or load_metadata_prompt(
            prompt_dir if prompt_dir is not None else DEFAULT_PROMPT_DIR
        )

    def analyze(self, transcript: str, title: str = "") -> PodcastMetadata:
        if not transcript.strip():
            raise MetadataAnalyzerError("Transcript text is required for metadata analysis.")

        analysis_input = MetadataAnalysisInput(transcript=transcript, title=title)
        output = self.ai_client.analyze_json(self.prompt, analysis_input.to_payload())
        return validate_metadata_output(output)


def validate_metadata_output(output: object) -> PodcastMetadata:
    if not isinstance(output, Mapping):
        raise MetadataAnalyzerError("Metadata analysis output must be a JSON object.")

    try:
        metadata = validate_podcast_metadata(output)
    except AnalysisValidationError as exc:
        raise MetadataAnalyzerError(str(exc)) from exc
    missing_fields = [
        field_name
        for field_name, value in {
            "topic": metadata.topic,
            "title": metadata.title,
            "difficulty": metadata.difficulty,
            "short_summary": metadata.short_summary,
        }.items()
        if not value
    ]
    if missing_fields:
        raise MetadataAnalyzerError(
            "Missing metadata fields: " + ", ".join(missing_fields)
        )
    if metadata.difficulty not in ALLOWED_DIFFICULTIES:
        raise MetadataAnalyzerError(
            "Unsupported difficulty. Expected one of: "
            + ", ".join(sorted(ALLOWED_DIFFICULTIES))
        )
    return metadata
