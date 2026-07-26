"""Strict validation for unattended vocabulary-enrichment artifacts."""

from __future__ import annotations

from typing import Any, Mapping


PARTS_OF_SPEECH = (
    "noun",
    "verb",
    "adjective",
    "adverb",
    "phrase",
    "phrasal verb",
    "idiom",
    "term",
    "other",
)

PROFESSIONAL_CATEGORIES = (
    "Negotiation",
    "Business Communication",
    "Leadership",
    "Management",
    "Technology",
    "Business Strategy",
    "Decision Making",
    "Finance",
    "Marketing",
    "Operations",
    "Career Growth",
    "Other",
)

AUTOMATIC_VOCABULARY_ENRICHMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
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
        "word": {"type": "string", "minLength": 1, "maxLength": 500},
        "original_context": {
            "type": "string",
            "minLength": 1,
            "maxLength": 5000,
        },
        "meaning": {"type": "string", "minLength": 1, "maxLength": 2000},
        "chinese_meaning": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
        },
        "part_of_speech": {
            "type": "string",
            "enum": list(PARTS_OF_SPEECH),
        },
        "professional_category": {
            "type": "string",
            "enum": list(PROFESSIONAL_CATEGORIES),
        },
        "usage_example": {
            "type": "string",
            "minLength": 1,
            "maxLength": 3000,
        },
        "common_collocations": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 300,
            },
        },
    },
}


class AutomaticVocabularyArtifactError(RuntimeError):
    """A stable, redacted validation failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _validate_string(value: Any, definition: Mapping[str, Any]) -> bool:
    if not isinstance(value, str):
        return False
    if not value.strip():
        return False
    length = len(value)
    minimum = definition.get("minLength")
    maximum = definition.get("maxLength")
    if isinstance(minimum, int) and length < minimum:
        return False
    if isinstance(maximum, int) and length > maximum:
        return False
    allowed = definition.get("enum")
    return not isinstance(allowed, list) or value in allowed


def _validate_value(value: Any, definition: Mapping[str, Any]) -> bool:
    expected = definition.get("type")
    if expected == "string":
        return _validate_string(value, definition)
    if expected == "array":
        if not isinstance(value, list):
            return False
        minimum = definition.get("minItems")
        maximum = definition.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            return False
        if isinstance(maximum, int) and len(value) > maximum:
            return False
        item_definition = definition.get("items")
        return not isinstance(item_definition, Mapping) or all(
            _validate_value(item, item_definition) for item in value
        )
    if expected == "object":
        return isinstance(value, Mapping)
    return False


def validate_automatic_vocabulary_artifact(
    payload: Mapping[str, Any],
    *,
    exact_word: str,
    exact_context: str,
) -> dict[str, Any]:
    """Validate the complete strict schema and preserve exact user intent."""
    schema = AUTOMATIC_VOCABULARY_ENRICHMENT_SCHEMA
    properties = schema["properties"]
    required = schema["required"]

    if any(key not in payload for key in required):
        raise AutomaticVocabularyArtifactError("schema_validation_failed")
    if schema.get("additionalProperties") is False and (
        set(payload) - set(properties)
    ):
        raise AutomaticVocabularyArtifactError("schema_validation_failed")
    for key, value in payload.items():
        definition = properties.get(key)
        if not isinstance(definition, Mapping) or not _validate_value(
            value,
            definition,
        ):
            raise AutomaticVocabularyArtifactError("schema_validation_failed")

    if payload.get("word") != exact_word:
        raise AutomaticVocabularyArtifactError("exact_word_mismatch")
    if payload.get("original_context") != exact_context:
        raise AutomaticVocabularyArtifactError("exact_context_mismatch")
    return dict(payload)
