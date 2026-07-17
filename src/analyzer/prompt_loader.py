"""Prompt loading utilities for Phase 3 AI analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROMPT_DIR = Path("skill/prompts")


class PromptLoaderError(RuntimeError):
    """Raised when an analyzer prompt cannot be loaded."""


@dataclass(frozen=True)
class AnalyzerPrompts:
    summary: str
    metadata: str
    expression: str


def load_prompt(filename: str, prompt_dir: Path = DEFAULT_PROMPT_DIR) -> str:
    path = prompt_dir / filename
    if not path.exists():
        raise PromptLoaderError(f"Prompt file does not exist: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise PromptLoaderError(f"Prompt file is empty: {path}")
    return content


def load_analyzer_prompts(prompt_dir: Path = DEFAULT_PROMPT_DIR) -> AnalyzerPrompts:
    return AnalyzerPrompts(
        summary=load_prompt("summary_prompt.md", prompt_dir),
        metadata=load_prompt("metadata_prompt.md", prompt_dir),
        expression=load_prompt("expression_prompt.md", prompt_dir),
    )


def load_metadata_prompt(prompt_dir: Path = DEFAULT_PROMPT_DIR) -> str:
    """Load the prompt used for Podcast Library metadata analysis."""
    return load_prompt("metadata_prompt.md", prompt_dir)


def load_expression_prompt(prompt_dir: Path = DEFAULT_PROMPT_DIR) -> str:
    """Load the prompt used for expression and learning item extraction."""
    return load_prompt("expression_prompt.md", prompt_dir)
