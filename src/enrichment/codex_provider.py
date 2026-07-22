"""Codex artifact provider for vocabulary enrichment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.enrichment.provider import VocabularyEnrichmentProvider
from src.skill_runtime.artifacts import (
    CodexArtifactPendingError,
    load_codex_artifact,
    prepare_codex_request,
)


VOCABULARY_ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "word",
        "original_context",
        "meaning",
        "chinese_meaning",
        "part_of_speech",
        "professional_category",
        "usage_example",
        "common_collocations",
    ],
    "properties": {
        "word": {"type": "string"},
        "original_context": {"type": "string"},
        "meaning": {"type": "string"},
        "chinese_meaning": {"type": "string"},
        "part_of_speech": {"type": "string"},
        "professional_category": {"type": "string"},
        "usage_example": {"type": "string"},
        "common_collocations": {"type": "array", "items": {"type": "string"}},
    },
}

VOCABULARY_INSTRUCTIONS = """Enrich the exact user-selected vocabulary target for Business English learning.
Do not expand or replace the highlighted word or phrase. Use the supplied context for meaning,
Chinese explanation, part of speech, professional category, a natural professional example, and
common collocations. Return only one JSON object matching the supplied schema."""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "vocabulary"


@dataclass(frozen=True)
class CodexVocabularyEnrichmentProvider(VocabularyEnrichmentProvider):
    request_dir: Path = Path("data/vocabulary_enrichment_requests")
    output_dir: Path = Path("data/vocabulary_enrichment")

    def _paths(self, word: str) -> tuple[Path, Path]:
        name = _slug(word)
        return self.request_dir / f"{name}.json", self.output_dir / f"{name}.json"

    def _prepare(self, word: str, context: str) -> tuple[Path, Path]:
        request_path, output_path = self._paths(word)
        prepare_codex_request(
            stage="vocabulary_enrichment",
            instructions=VOCABULARY_INSTRUCTIONS,
            input_payload={"word": word, "context": context},
            schema=VOCABULARY_ENRICHMENT_SCHEMA,
            request_path=request_path,
            output_path=output_path,
        )
        return request_path, output_path

    def enrich(self, word: str, context: str) -> dict[str, Any]:
        request_path, output_path = self._prepare(word, context)
        return load_codex_artifact(
            request_path=request_path,
            output_path=output_path,
            stage=f"vocabulary enrichment ({word})",
        )

    def enrich_many(self, items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        prepared = [
            (str(item.get("word", "")).strip(), *self._prepare(
                str(item.get("word", "")).strip(),
                str(item.get("context", "")).strip(),
            ))
            for item in items
        ]
        outputs: list[dict[str, Any]] = []
        pending: list[str] = []
        for word, request_path, output_path in prepared:
            try:
                outputs.append(
                    load_codex_artifact(
                        request_path=request_path,
                        output_path=output_path,
                        stage=f"vocabulary enrichment ({word})",
                    )
                )
            except CodexArtifactPendingError:
                pending.append(f"{request_path.resolve()} -> {output_path.resolve()}")
        if pending:
            raise CodexArtifactPendingError(
                "Codex vocabulary artifacts required:\n" + "\n".join(pending)
            )
        return outputs
