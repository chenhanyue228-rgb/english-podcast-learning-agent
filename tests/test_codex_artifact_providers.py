from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.enrichment.codex_provider import CodexVocabularyEnrichmentProvider
from src.skill_runtime.artifacts import CodexArtifactPendingError
from src.weekly_review.codex_provider import (
    CodexReflectionProvider,
    CodexWeeklyReviewGenerationProvider,
)


def _write_after_request(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    stat = path.stat()
    os.utime(path, (stat.st_atime + 1, stat.st_mtime + 1))


def test_codex_vocabulary_provider_prepares_request_then_reads_output(tmp_path: Path) -> None:
    provider = CodexVocabularyEnrichmentProvider(
        request_dir=tmp_path / "requests",
        output_dir=tmp_path / "outputs",
    )

    with pytest.raises(CodexArtifactPendingError):
        provider.enrich("leverage", "We can leverage AI to improve the workflow.")

    request_path = tmp_path / "requests" / "leverage.json"
    output_path = tmp_path / "outputs" / "leverage.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    assert request["stage"] == "vocabulary_enrichment"
    assert request["input"]["word"] == "leverage"
    _write_after_request(
        output_path,
        {
            "word": "leverage",
            "original_context": "We can leverage AI to improve the workflow.",
            "meaning": "Use a resource to gain an advantage.",
            "chinese_meaning": "利用",
            "part_of_speech": "verb",
            "professional_category": "Business Strategy",
            "usage_example": "We should leverage customer insights in planning.",
            "common_collocations": ["leverage technology"],
        },
    )

    assert provider.enrich("leverage", "We can leverage AI to improve the workflow.")["meaning"]


def test_codex_reflection_provider_uses_artifact_contract(tmp_path: Path) -> None:
    provider = CodexReflectionProvider(
        request_path=tmp_path / "reflection_request.json",
        output_path=tmp_path / "reflection.json",
    )
    context = {"weekly_learning_context": {"podcasts": []}, "schema": {"type": "object"}}

    with pytest.raises(CodexArtifactPendingError):
        provider.generate("Reflect", context)

    payload = {
        "weekly_theme": {"category": "Communication", "theme": "Listen before influencing"},
        "mindset_shifts": [],
        "cross_content_patterns": [],
        "professional_actions": ["Ask one clarifying question."],
    }
    _write_after_request(tmp_path / "reflection.json", payload)
    assert provider.generate("Reflect", context) == payload


def test_codex_weekly_review_provider_uses_artifact_contract(tmp_path: Path) -> None:
    provider = CodexWeeklyReviewGenerationProvider(
        request_path=tmp_path / "review_request.json",
        output_path=tmp_path / "review.json",
    )
    context = {
        "reflection_context": {"weekly_theme": {"theme": "Negotiation"}},
        "weekly_learning_context": {"podcasts": []},
        "schema": {"type": "object"},
    }

    with pytest.raises(CodexArtifactPendingError):
        provider.generate("Write", context)

    payload = {"period": {}, "core_idea": {}}
    _write_after_request(tmp_path / "review.json", payload)
    assert provider.generate("Write", context) == payload
