"""Skill-based orchestration for Phase 3 AI learning analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from src.analyzer.ai_client import SkillAnalysisRequest, load_analysis_schema
from src.analyzer.models import AIAnalysisResult
from src.analyzer.prompt_loader import AnalyzerPrompts, load_analyzer_prompts
from src.analyzer.validators import validate_ai_analysis


DEFAULT_ANALYSIS_SCHEMA_PATH = Path("skill/schemas/ai_analysis_schema.json")


class LearningAnalyzerError(RuntimeError):
    """Raised when transcript analysis cannot complete."""


@dataclass(frozen=True)
class TranscriptAnalysisInput:
    title: str
    transcript: str

    def to_payload(self) -> dict[str, str]:
        return {"title": self.title, "transcript": self.transcript}


class LearningAnalyzer:
    """Prepare Codex Skill analysis instructions and validate generated JSON."""

    def __init__(
        self,
        prompts: Optional[AnalyzerPrompts] = None,
        schema: Optional[Mapping[str, Any]] = None,
        schema_path: Path = DEFAULT_ANALYSIS_SCHEMA_PATH,
    ) -> None:
        self.prompts = prompts or load_analyzer_prompts()
        self.schema = schema
        self.schema_path = schema_path

    def prepare_analysis_request(
        self,
        transcript_input: TranscriptAnalysisInput,
    ) -> SkillAnalysisRequest:
        """Prepare prompts, schema, and transcript payload for Codex reasoning."""
        if not transcript_input.transcript.strip():
            raise LearningAnalyzerError("Transcript text is required for AI analysis.")

        return SkillAnalysisRequest(
            title=transcript_input.title,
            transcript=transcript_input.transcript,
            prompts=self.prompts,
            schema=self.schema or load_analysis_schema(self.schema_path),
        )

    def validate_generated_analysis(
        self,
        generated_output: Mapping[str, Any],
    ) -> AIAnalysisResult:
        """Validate Codex-generated JSON and return structured analysis data."""
        return validate_ai_analysis(generated_output)

    def analyze_generated_output(
        self,
        transcript_input: TranscriptAnalysisInput,
        generated_output: Mapping[str, Any],
    ) -> AIAnalysisResult:
        """Validate transcript input and Codex-generated analysis JSON."""
        if not transcript_input.transcript.strip():
            raise LearningAnalyzerError("Transcript text is required for AI analysis.")
        return self.validate_generated_analysis(generated_output)


def merge_analysis_outputs(
    summary_output: Mapping[str, Any],
    metadata_output: Mapping[str, Any],
    expression_output: Mapping[str, Any],
) -> dict[str, Any]:
    """Merge separate Codex-generated prompt outputs into one analysis payload."""
    return {
        "summary": summary_output.get("summary", {}),
        "podcast_metadata": metadata_output.get("podcast_metadata", {}),
        "learning_items": list(expression_output.get("learning_items", [])),
        "sentence_patterns": list(expression_output.get("sentence_patterns", [])),
        "learning_notes": list(expression_output.get("learning_notes", [])),
    }
