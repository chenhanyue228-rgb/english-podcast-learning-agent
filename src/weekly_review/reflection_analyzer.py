"""Reflection context generation for weekly review."""

from __future__ import annotations

import json
import os
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

import httpx

from src.config.settings import load_env_file


DEFAULT_REFLECTION_PROMPT_PATH = Path("skill/prompts/weekly_reflection_prompt.md")
DEFAULT_REFLECTION_SCHEMA_PATH = Path("skill/schemas/reflection_context_schema.json")
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


class ReflectionGenerationError(RuntimeError):
    """Raised when reflection context generation cannot complete."""


class ReflectionProvider(Protocol):
    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        """Generate a reflection context JSON object."""


def load_reflection_prompt(path: Path = DEFAULT_REFLECTION_PROMPT_PATH) -> str:
    if not path.exists():
        raise ReflectionGenerationError(f"Reflection prompt does not exist: {path}")
    return path.read_text(encoding="utf-8")


def load_reflection_schema(path: Path = DEFAULT_REFLECTION_SCHEMA_PATH) -> Mapping[str, Any]:
    if not path.exists():
        raise ReflectionGenerationError(f"Reflection schema does not exist: {path}")
    try:
        schema = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReflectionGenerationError(f"Reflection schema is invalid JSON: {exc.msg}") from exc
    if not isinstance(schema, Mapping):
        raise ReflectionGenerationError("Reflection schema must be a JSON object.")
    return schema


def load_weekly_learning_context(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        raise ReflectionGenerationError(f"Weekly learning context does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReflectionGenerationError(f"Weekly learning context is invalid JSON: {exc.msg}") from exc
    if not isinstance(payload, Mapping):
        raise ReflectionGenerationError("Weekly learning context must be a JSON object.")
    return payload


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _shorten_text(value: object, limit: int = 140) -> str:
    text = _normalize_text(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _select_theme(podcasts: list[Mapping[str, Any]]) -> str:
    topics = [str(item.get("topic", "")).strip() for item in podcasts if str(item.get("topic", "")).strip()]
    if not topics:
        return "Professional learning reflection"
    counts = Counter(topics)
    return counts.most_common(1)[0][0]


def _make_evidence(source: str, supporting_concept: str) -> dict[str, str]:
    return {
        "source": source,
        "supporting_concept": supporting_concept,
    }


def _pick_summary_text(summary: Any) -> str:
    if not isinstance(summary, Mapping):
        return ""
    english = _normalize_text(summary.get("english", ""))
    if english:
        return english
    chinese = _normalize_text(summary.get("chinese", ""))
    return chinese


def _estimate_confidence(podcast_count: int, evidence_count: int) -> float:
    if podcast_count >= 3 and evidence_count >= 2:
        return 0.95
    if podcast_count >= 2 and evidence_count >= 1:
        return 0.85
    if podcast_count >= 1 and evidence_count >= 1:
        return 0.65
    return 0.4


def _build_reflection_payload(weekly_context: Mapping[str, Any]) -> dict[str, Any]:
    podcasts = [item for item in weekly_context.get("podcasts", []) if isinstance(item, Mapping)]
    expressions = [item for item in weekly_context.get("learning_expressions", []) if isinstance(item, Mapping)]
    vocab = [item for item in weekly_context.get("user_vocabulary", []) if isinstance(item, Mapping)]

    theme = _select_theme(podcasts)
    first_topic = _normalize_text(podcasts[0].get("topic", "")) if podcasts else ""
    second_topic = _normalize_text(podcasts[1].get("topic", "")) if len(podcasts) > 1 else first_topic

    first_evidence = []
    if podcasts:
        summary = podcasts[0].get("summary", {})
        summary_text = _pick_summary_text(summary)
        if summary_text:
            first_evidence.append(_make_evidence("Podcast summary", _shorten_text(summary_text, 160)))
        takeaways = podcasts[0].get("key_takeaways", [])
        if isinstance(takeaways, list):
            for item in takeaways[:2]:
                text = str(item).strip()
                if text:
                    first_evidence.append(_make_evidence("Key takeaway", _shorten_text(text, 120)))
        if not first_evidence:
            title = _normalize_text(podcasts[0].get("title", ""))
            topic = _normalize_text(podcasts[0].get("topic", ""))
            fallback = " / ".join(part for part in [topic, title] if part)
            if fallback:
                first_evidence.append(_make_evidence("Podcast metadata", _shorten_text(fallback, 120)))

    mindset_shifts = []
    if first_evidence:
        if "negotiat" in theme.lower():
            before = "I used to treat negotiation mainly as a contest over positions and immediate outcomes."
            after = "I now see negotiation as relationship management: uncover interests, frame the problem collaboratively, and protect implementation after agreement."
        else:
            before = f"I used to treat {first_topic or 'this topic'} as a set of separate ideas."
            after = f"I now see {theme.lower()} as a transferable professional principle that changes how I communicate and decide."
        mindset_shifts.append(
            {
                "before": before,
                "after": after,
                "evidence": first_evidence[:3],
                "confidence": _estimate_confidence(len(podcasts), len(first_evidence)),
            }
        )

    cross_content_patterns = []
    if len(podcasts) > 1:
        cross_content_patterns.append(
            f"{theme} shows up as a repeated pattern across the week's learning rather than a one-off topic."
        )
        top_expression = (
            str(expressions[0].get("expression", "")).strip()
            if expressions
            else ""
        )
        if top_expression:
            cross_content_patterns.append(
                f"Expressions like '{top_expression}' turn learning ideas into reusable language for work conversations."
            )
        else:
            cross_content_patterns.append(
                f"{first_topic or theme} and {second_topic or theme} both "
                "reinforce a transferable professional learning pattern."
            )
    professional_actions = [
        "In one stakeholder conversation, restate the shared outcome before discussing constraints and note whether the exchange moves from positions to options."
    ]

    return {
        "weekly_theme": {
            "category": first_topic or theme,
            "theme": theme,
        },
        "mindset_shifts": mindset_shifts,
        "cross_content_patterns": cross_content_patterns[:3],
        "professional_actions": professional_actions,
    }


class PlaceholderReflectionProvider(ReflectionProvider):
    """Build a deterministic reflection context without external services."""

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        weekly_context = context.get("weekly_learning_context", {})
        if not isinstance(weekly_context, Mapping):
            weekly_context = {}
        return _build_reflection_payload(weekly_context)


@dataclass(frozen=True)
class OpenAIReflectionProvider(ReflectionProvider):
    api_key: Optional[str] = None
    model: str = DEFAULT_OPENAI_MODEL
    base_url: str = DEFAULT_OPENAI_BASE_URL
    timeout: httpx.Timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)

    def _resolve_api_key(self) -> str:
        key = self.api_key or os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            raise ReflectionGenerationError("Missing OPENAI_API_KEY for reflection provider.")
        return key

    def _parse_json_object(self, content: str) -> Mapping[str, Any]:
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ReflectionGenerationError(f"Reflection LLM response is invalid JSON: {exc.msg}") from exc
        if not isinstance(parsed, Mapping):
            raise ReflectionGenerationError("Reflection LLM response must be a JSON object.")
        return parsed

    def generate(self, prompt: str, context: dict[str, object]) -> dict[str, object]:
        api_key = self._resolve_api_key()
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        prompt_text = f"{prompt}\n\nWeekly learning context:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You generate structured reflection JSON."},
                {"role": "user", "content": prompt_text},
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
            raise ReflectionGenerationError(f"Failed to reach OpenAI API: {exc}") from exc
        except Exception as exc:
            raise ReflectionGenerationError(f"Failed to call OpenAI API: {exc}") from exc

        if response.status_code >= 400:
            raise ReflectionGenerationError(
                f"OpenAI API request failed: HTTP {response.status_code} {response.text[:200]}"
            )

        body = response.json()
        choices = body.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise ReflectionGenerationError("OpenAI API response did not contain any choices.")
        message = choices[0].get("message", {}) if isinstance(choices[0], Mapping) else {}
        content = ""
        if isinstance(message, Mapping):
            content = str(message.get("content", "")).strip()
        if not content:
            raise ReflectionGenerationError("OpenAI API response did not contain message content.")
        return dict(self._parse_json_object(content))


def create_reflection_provider() -> ReflectionProvider:
    provider_name = os.environ.get("WEEKLY_REFLECTION_PROVIDER", "codex").strip().lower()
    if provider_name == "openai":
        warnings.warn(
            "WEEKLY_REFLECTION_PROVIDER=openai is deprecated; use the Codex artifact runtime.",
            DeprecationWarning,
            stacklevel=2,
        )
        return OpenAIReflectionProvider()
    if provider_name == "placeholder":
        return PlaceholderReflectionProvider()
    if provider_name == "codex":
        from src.weekly_review.codex_provider import CodexReflectionProvider

        return CodexReflectionProvider()
    raise ReflectionGenerationError(f"Unsupported WEEKLY_REFLECTION_PROVIDER: {provider_name}")


def _validate_reflection_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    required_keys = ["weekly_theme", "mindset_shifts", "cross_content_patterns", "professional_actions"]
    missing = [key for key in required_keys if key not in payload]
    if missing:
        raise ReflectionGenerationError(
            f"Reflection context is missing required fields: {', '.join(missing)}"
        )
    if set(payload) != set(required_keys):
        raise ReflectionGenerationError(
            "Reflection context contains unsupported fields."
        )
    weekly_theme = payload.get("weekly_theme")
    if not isinstance(weekly_theme, Mapping):
        raise ReflectionGenerationError("Reflection weekly_theme must be an object.")
    if set(weekly_theme) != {"category", "theme"}:
        raise ReflectionGenerationError(
            "Reflection weekly_theme contains unsupported fields."
        )
    if (
        not isinstance(weekly_theme.get("category"), str)
        or not weekly_theme.get("category", "").strip()
        or not isinstance(weekly_theme.get("theme"), str)
        or not weekly_theme.get("theme", "").strip()
    ):
        raise ReflectionGenerationError("Reflection weekly_theme must contain category and theme strings.")
    if not isinstance(payload.get("mindset_shifts"), list):
        raise ReflectionGenerationError("Reflection mindset_shifts must be an array.")
    if len(payload.get("mindset_shifts", [])) > 1:
        raise ReflectionGenerationError(
            "Reflection mindset_shifts must contain at most one item."
        )
    for shift in payload.get("mindset_shifts", []):
        if not isinstance(shift, Mapping):
            raise ReflectionGenerationError("Each mindset_shift must be an object.")
        if set(shift) != {"before", "after", "evidence", "confidence"}:
            raise ReflectionGenerationError(
                "Each mindset_shift contains unsupported fields."
            )
        if (
            not isinstance(shift.get("before"), str)
            or not shift.get("before", "").strip()
            or not isinstance(shift.get("after"), str)
            or not shift.get("after", "").strip()
        ):
            raise ReflectionGenerationError("Each mindset_shift must contain before and after strings.")
        if not isinstance(shift.get("evidence"), list) or not shift.get("evidence"):
            raise ReflectionGenerationError("Each mindset_shift must include non-empty evidence references.")
        for evidence in shift.get("evidence", []):
            if not isinstance(evidence, Mapping):
                raise ReflectionGenerationError(
                    "Each mindset_shift evidence item must be an object."
                )
            if set(evidence) != {"source", "supporting_concept"}:
                raise ReflectionGenerationError(
                    "Each mindset_shift evidence item contains unsupported fields."
                )
            if (
                not isinstance(evidence.get("source"), str)
                or not evidence.get("source", "").strip()
                or not isinstance(evidence.get("supporting_concept"), str)
                or not evidence.get("supporting_concept", "").strip()
            ):
                raise ReflectionGenerationError(
                    "Each mindset_shift evidence item must contain non-empty source and supporting_concept strings."
                )
        if isinstance(shift.get("confidence"), bool) or not isinstance(
            shift.get("confidence"),
            (int, float),
        ):
            raise ReflectionGenerationError("Each mindset_shift must include a confidence score.")
        confidence = float(shift.get("confidence"))
        if confidence < 0 or confidence > 1:
            raise ReflectionGenerationError("Each mindset_shift confidence must be between 0 and 1.")
    if not isinstance(payload.get("cross_content_patterns"), list):
        raise ReflectionGenerationError("Reflection cross_content_patterns must be an array.")
    if len(payload.get("cross_content_patterns", [])) > 4 or any(
        not isinstance(item, str) or not item.strip()
        for item in payload.get("cross_content_patterns", [])
    ):
        raise ReflectionGenerationError(
            "Reflection cross_content_patterns must contain at most four non-empty strings."
        )
    professional_actions = payload.get("professional_actions")
    if (
        not isinstance(professional_actions, list)
        or len(professional_actions) != 1
        or any(
            not isinstance(item, str) or not item.strip()
            for item in professional_actions
        )
    ):
        raise ReflectionGenerationError(
            "Reflection professional_actions must contain exactly one non-empty string."
        )
    return dict(payload)


class ReflectionAnalyzer:
    """Generate a reflection context from weekly learning data."""

    def __init__(
        self,
        provider: Optional[ReflectionProvider] = None,
        prompt_path: Path = DEFAULT_REFLECTION_PROMPT_PATH,
        schema_path: Path = DEFAULT_REFLECTION_SCHEMA_PATH,
    ) -> None:
        self.provider = provider or create_reflection_provider()
        self.prompt = load_reflection_prompt(prompt_path)
        self.schema = load_reflection_schema(schema_path)

    def generate(self, weekly_learning_context: Mapping[str, Any]) -> dict[str, Any]:
        context = {"weekly_learning_context": weekly_learning_context, "schema": self.schema}
        generated = self.provider.generate(self.prompt, context)
        validated = _validate_reflection_payload(generated)
        podcasts = [item for item in weekly_learning_context.get("podcasts", []) if isinstance(item, Mapping)]
        patterns = validated.get("cross_content_patterns", [])
        if len(podcasts) <= 1 and patterns:
            raise ReflectionGenerationError(
                "Reflection cross_content_patterns must be empty for "
                "single-podcast weeks."
            )
        if len(podcasts) > 1 and len(patterns) < 2:
            raise ReflectionGenerationError(
                "Reflection cross_content_patterns must contain 2-4 items "
                "for multi-podcast weeks."
            )
        return validated


@dataclass(frozen=True)
class ReflectionGenerationResult:
    input_path: Path
    output_path: Path
    payload: dict[str, Any]


def save_reflection_context(output: Mapping[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(dict(output), ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path.resolve()


def run_reflection_analysis(
    input_path: Path,
    output_path: Path = Path("output/reflection_context.json"),
    provider: Optional[ReflectionProvider] = None,
) -> ReflectionGenerationResult:
    load_env_file()
    weekly_learning_context = load_weekly_learning_context(input_path)
    analyzer = ReflectionAnalyzer(provider=provider)
    payload = analyzer.generate(weekly_learning_context)
    saved_path = save_reflection_context(payload, output_path)
    return ReflectionGenerationResult(
        input_path=input_path.resolve(),
        output_path=saved_path,
        payload=payload,
    )
