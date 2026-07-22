"""Factory for selecting a weekly review generation provider."""

from __future__ import annotations

import os
import warnings

from src.weekly_review.codex_provider import CodexWeeklyReviewGenerationProvider
from src.weekly_review.llm_provider import OpenAIWeeklyReviewGenerationProvider
from src.weekly_review.placeholder_provider import PlaceholderWeeklyReviewGenerationProvider


def create_weekly_review_generation_provider() -> object:
    provider_name = os.environ.get("WEEKLY_REVIEW_PROVIDER", "codex").strip().lower()
    if provider_name == "openai":
        warnings.warn(
            "WEEKLY_REVIEW_PROVIDER=openai is deprecated; use the Codex artifact runtime.",
            DeprecationWarning,
            stacklevel=2,
        )
        return OpenAIWeeklyReviewGenerationProvider()
    if provider_name == "placeholder":
        return PlaceholderWeeklyReviewGenerationProvider()
    if provider_name == "codex":
        return CodexWeeklyReviewGenerationProvider()
    raise ValueError(f"Unsupported WEEKLY_REVIEW_PROVIDER: {provider_name}")
