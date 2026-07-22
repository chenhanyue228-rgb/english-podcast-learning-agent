"""Codex artifact providers for reflection and weekly review reasoning."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.skill_runtime.artifacts import load_codex_artifact, prepare_codex_request
from src.weekly_review.provider import WeeklyReviewGenerationProvider
from src.weekly_review.reflection_analyzer import ReflectionProvider


@dataclass(frozen=True)
class CodexReflectionProvider(ReflectionProvider):
    request_path: Path = Path("output/reflection_context_request.json")
    output_path: Path = Path("output/reflection_context.json")

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        schema = context.get("schema", {})
        input_payload = {"weekly_learning_context": context.get("weekly_learning_context", {})}
        prepare_codex_request(
            stage="reflection_analysis",
            instructions=prompt,
            input_payload=input_payload,
            schema=schema if isinstance(schema, dict) else {},
            request_path=self.request_path,
            output_path=self.output_path,
        )
        return load_codex_artifact(
            request_path=self.request_path,
            output_path=self.output_path,
            stage="reflection analysis",
        )


@dataclass(frozen=True)
class CodexWeeklyReviewGenerationProvider(WeeklyReviewGenerationProvider):
    request_path: Path = Path("output/weekly_review_request.json")
    output_path: Path = Path("output/weekly_review.json")

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        schema = context.get("schema", {})
        input_payload = {
            "reflection_context": context.get("reflection_context", {}),
            "weekly_learning_context": context.get("weekly_learning_context", {}),
        }
        prepare_codex_request(
            stage="weekly_review_generation",
            instructions=prompt,
            input_payload=input_payload,
            schema=schema if isinstance(schema, dict) else {},
            request_path=self.request_path,
            output_path=self.output_path,
        )
        return load_codex_artifact(
            request_path=self.request_path,
            output_path=self.output_path,
            stage="weekly review generation",
        )
