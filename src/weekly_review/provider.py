"""Provider interface for weekly review generation."""

from __future__ import annotations

from typing import Protocol, Sequence


class WeeklyReviewGenerationProvider(Protocol):
    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        """Generate a structured weekly review JSON object."""
        raise NotImplementedError
