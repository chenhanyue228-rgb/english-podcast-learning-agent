"""Prompt loading for weekly review generation."""

from __future__ import annotations

from pathlib import Path

from src.analyzer.prompt_loader import load_prompt


DEFAULT_WEEKLY_REVIEW_GENERATOR_PROMPT_PATH = Path("skill/prompts/weekly_review_generator_prompt.md")


def load_weekly_review_generator_prompt(
    prompt_path: Path = DEFAULT_WEEKLY_REVIEW_GENERATOR_PROMPT_PATH,
) -> str:
    return load_prompt(prompt_path.name, prompt_path.parent)
