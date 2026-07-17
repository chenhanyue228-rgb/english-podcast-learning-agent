"""Expression analyzer for Phase 3 English learning materials."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from src.analyzer.ai_client import AIClient
from src.analyzer.models import LearningItem, ensure_mapping
from src.analyzer.prompt_loader import DEFAULT_PROMPT_DIR, load_expression_prompt
from src.analyzer.validators import (
    AnalysisValidationError,
    deduplicate_learning_items,
    validate_learning_item,
)


class ExpressionAnalyzerError(RuntimeError):
    """Raised when expression analysis cannot complete."""


@dataclass(frozen=True)
class ExpressionAnalysisInput:
    transcript: str
    title: str = ""

    def to_payload(self) -> dict[str, str]:
        return {
            "title": self.title,
            "transcript": self.transcript,
        }


class ExpressionAnalyzer:
    """Extract reusable English learning items from transcript text."""

    def __init__(
        self,
        ai_client: AIClient,
        prompt: Optional[str] = None,
        prompt_dir: Optional[Path] = None,
    ) -> None:
        self.ai_client = ai_client
        self.prompt = prompt or load_expression_prompt(
            prompt_dir if prompt_dir is not None else DEFAULT_PROMPT_DIR
        )

    def analyze(self, transcript: str, title: str = "") -> list[LearningItem]:
        if not transcript.strip():
            raise ExpressionAnalyzerError(
                "Transcript text is required for expression analysis."
            )

        analysis_input = ExpressionAnalysisInput(transcript=transcript, title=title)
        output = self.ai_client.analyze_json(self.prompt, analysis_input.to_payload())
        return validate_expression_output(output)


def validate_expression_output(output: object) -> list[LearningItem]:
    if not isinstance(output, Mapping):
        raise ExpressionAnalyzerError("Expression analysis output must be a JSON object.")

    learning_items = output.get("learning_items", [])
    if not isinstance(learning_items, list):
        raise ExpressionAnalyzerError("learning_items must be a list.")

    try:
        validated_items = [
            validate_learning_item(ensure_mapping(item, "learning item"))
            for item in learning_items
        ]
    except (AnalysisValidationError, ValueError) as exc:
        raise ExpressionAnalyzerError(str(exc)) from exc

    return deduplicate_learning_items(validated_items)
