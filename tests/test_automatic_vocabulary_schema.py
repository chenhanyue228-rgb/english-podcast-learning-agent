from __future__ import annotations

from typing import Any

import pytest

from src.enrichment.automatic_vocabulary_schema import (
    AutomaticVocabularyArtifactError,
    validate_automatic_vocabulary_artifact,
)


WORD = "challenge assumptions"
CONTEXT = (
    "Strong negotiators challenge assumptions before proposing a solution."
)


def payload(**overrides: Any) -> dict[str, Any]:
    result = {
        "word": WORD,
        "original_context": CONTEXT,
        "meaning": "Question beliefs before deciding.",
        "chinese_meaning": "在决策前质疑既有假设。",
        "part_of_speech": "phrase",
        "professional_category": "Negotiation",
        "usage_example": (
            "The team should challenge assumptions before committing."
        ),
        "common_collocations": [
            "challenge existing assumptions",
            "challenge strategic assumptions",
        ],
    }
    result.update(overrides)
    return result


def test_strict_artifact_accepts_complete_exact_payload() -> None:
    result = validate_automatic_vocabulary_artifact(
        payload(),
        exact_word=WORD,
        exact_context=CONTEXT,
    )

    assert result["word"] == WORD
    assert result["original_context"] == CONTEXT


@pytest.mark.parametrize(
    "invalid",
    [
        {"unexpected": "value"},
        {"meaning": "   "},
        {"common_collocations": [" "]},
        {"part_of_speech": "verb phrase"},
        {"professional_category": "Generic Communication"},
        {"common_collocations": []},
    ],
)
def test_strict_artifact_rejects_invalid_schema(
    invalid: dict[str, Any],
) -> None:
    with pytest.raises(AutomaticVocabularyArtifactError) as raised:
        validate_automatic_vocabulary_artifact(
            payload(**invalid),
            exact_word=WORD,
            exact_context=CONTEXT,
        )

    assert raised.value.code == "schema_validation_failed"


def test_strict_artifact_rejects_word_expansion() -> None:
    with pytest.raises(AutomaticVocabularyArtifactError) as raised:
        validate_automatic_vocabulary_artifact(
            payload(word="expanded challenge assumptions"),
            exact_word=WORD,
            exact_context=CONTEXT,
        )

    assert raised.value.code == "exact_word_mismatch"


def test_strict_artifact_rejects_context_rewrite() -> None:
    with pytest.raises(AutomaticVocabularyArtifactError) as raised:
        validate_automatic_vocabulary_artifact(
            payload(original_context="A rewritten context."),
            exact_word=WORD,
            exact_context=CONTEXT,
        )

    assert raised.value.code == "exact_context_mismatch"
