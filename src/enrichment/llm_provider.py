"""OpenAI-backed vocabulary enrichment provider."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping, Optional

import httpx

from src.enrichment.provider import VocabularyEnrichmentProvider


DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class VocabularyEnrichmentProviderError(RuntimeError):
    """Raised when the LLM enrichment provider cannot complete."""


@dataclass(frozen=True)
class OpenAIVocabularyEnrichmentProvider(VocabularyEnrichmentProvider):
    api_key: Optional[str] = None
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout: httpx.Timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

    def _resolve_api_key(self) -> str:
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise VocabularyEnrichmentProviderError(
                "Missing OPENAI_API_KEY for LLM vocabulary enrichment provider."
            )
        return key

    def _build_prompt(self, word: str, context: str) -> str:
        return (
            "You are enriching vocabulary for a Business English Podcast Learning app.\n"
            "Return ONLY valid JSON with the following keys:\n"
            "word, original_context, meaning, chinese_meaning, part_of_speech, "
            "professional_category, usage_example, common_collocations.\n"
            "Rules:\n"
            "- Meaning must be grounded in the original_context, not a generic dictionary definition.\n"
            "- Chinese meaning must be concise and accurate.\n"
            "- professional_category should prefer podcast learning categories such as Negotiation, "
            "Business Communication, Leadership, Management, Technology, Strategy, or similar.\n"
            "- Avoid generic categories like Communication unless nothing more specific fits.\n"
            "- usage_example must be a natural business-English sentence that fits the podcast context.\n"
            "- Do not generate casual daily-chat examples.\n"
            "- common_collocations should be a short list of 2-5 relevant collocations or phrases.\n"
            "- Keep the output compact and practical for professional learning.\n"
            "Do not include markdown or commentary.\n\n"
            f"Word: {word}\n"
            f"Context: {context}\n"
        )

    def _parse_json_object(self, content: str) -> Mapping[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise VocabularyEnrichmentProviderError(
                f"LLM enrichment response is not valid JSON: {exc.msg}"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise VocabularyEnrichmentProviderError(
                "LLM enrichment response must be a JSON object."
            )
        return parsed

    def enrich(self, word: str, context: str) -> dict[str, str]:
        api_key = self._resolve_api_key()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You generate structured vocabulary enrichment JSON.",
                },
                {
                    "role": "user",
                    "content": self._build_prompt(word.strip(), context.strip()),
                },
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}/chat/completions"

        try:
            print("calling OpenAI")
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, headers=headers, json=payload)
        except (httpx.ConnectTimeout, httpx.ConnectError, httpx.ReadTimeout) as exc:
            raise VocabularyEnrichmentProviderError(
                f"Failed to reach OpenAI API: {exc}"
            ) from exc
        except Exception as exc:
            raise VocabularyEnrichmentProviderError(
                f"Failed to call OpenAI API: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise VocabularyEnrichmentProviderError(
                f"OpenAI API request failed: HTTP {response.status_code} {response.text[:200]}"
            )

        print("OpenAI response received")

        body = response.json()
        choices = body.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise VocabularyEnrichmentProviderError(
                "OpenAI API response did not contain any choices."
            )

        message = choices[0].get("message", {}) if isinstance(choices[0], Mapping) else {}
        content = ""
        if isinstance(message, Mapping):
            content = str(message.get("content", "")).strip()
        if not content:
            raise VocabularyEnrichmentProviderError(
                "OpenAI API response did not contain message content."
            )

        parsed = self._parse_json_object(content)
        common_collocations_value = parsed.get("common_collocations", [])
        if isinstance(common_collocations_value, list):
            common_collocations = [
                str(item).strip()
                for item in common_collocations_value
                if str(item).strip()
            ]
        else:
            common_collocations = []
        return {
            "word": str(parsed.get("word", word)).strip(),
            "original_context": str(parsed.get("original_context", context)).strip(),
            "meaning": str(parsed.get("meaning", "")).strip(),
            "chinese_meaning": str(parsed.get("chinese_meaning", "")).strip(),
            "part_of_speech": str(parsed.get("part_of_speech", "")).strip(),
            "professional_category": str(parsed.get("professional_category", "")).strip(),
            "usage_example": str(parsed.get("usage_example", "")).strip(),
            "common_collocations": common_collocations,
        }
