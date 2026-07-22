"""OpenAI-backed weekly review generation provider."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx

from src.weekly_review.provider import WeeklyReviewGenerationProvider


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class WeeklyReviewGenerationProviderError(RuntimeError):
    """Raised when the weekly review provider cannot complete."""


@dataclass(frozen=True)
class OpenAIWeeklyReviewGenerationProvider(WeeklyReviewGenerationProvider):
    api_key: Optional[str] = None
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout: httpx.Timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

    def _resolve_api_key(self) -> str:
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise WeeklyReviewGenerationProviderError(
                "Missing OPENAI_API_KEY for weekly review generation provider."
            )
        return key

    def _parse_json_object(self, content: str) -> Mapping[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise WeeklyReviewGenerationProviderError(
                f"Weekly review LLM response is not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise WeeklyReviewGenerationProviderError(
                "Weekly review LLM response must be a JSON object."
            )
        return parsed

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        api_key = self._resolve_api_key()
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        prompt_text = (
            f"{prompt}\n\n"
            "Weekly learning context:\n"
            f"{json.dumps(context, ensure_ascii=False, indent=2)}\n"
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate structured weekly review JSON.",
                },
                {
                    "role": "user",
                    "content": prompt_text,
                },
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
            raise WeeklyReviewGenerationProviderError(f"Failed to reach OpenAI API: {exc}") from exc
        except Exception as exc:
            raise WeeklyReviewGenerationProviderError(f"Failed to call OpenAI API: {exc}") from exc

        if response.status_code >= 400:
            raise WeeklyReviewGenerationProviderError(
                f"OpenAI API request failed: HTTP {response.status_code} {response.text[:200]}"
            )

        body = response.json()
        choices = body.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise WeeklyReviewGenerationProviderError(
                "OpenAI API response did not contain any choices."
            )
        message = choices[0].get("message", {}) if isinstance(choices[0], Mapping) else {}
        content = ""
        if isinstance(message, Mapping):
            content = str(message.get("content", "")).strip()
        if not content:
            raise WeeklyReviewGenerationProviderError(
                "OpenAI API response did not contain message content."
            )
        parsed = self._parse_json_object(content)
        return dict(parsed)
