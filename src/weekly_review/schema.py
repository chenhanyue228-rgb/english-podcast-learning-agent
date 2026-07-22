"""Schema helpers for weekly review generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


DEFAULT_WEEKLY_REVIEW_GENERATOR_SCHEMA_PATH = Path(
    "skill/schemas/weekly_review_generator_schema.json"
)


class WeeklyReviewSchemaError(RuntimeError):
    """Raised when the weekly review generator schema cannot be loaded."""


def load_weekly_review_generator_schema(
    schema_path: Path = DEFAULT_WEEKLY_REVIEW_GENERATOR_SCHEMA_PATH,
) -> Mapping[str, Any]:
    if not schema_path.exists():
        raise WeeklyReviewSchemaError(f"Weekly review generator schema does not exist: {schema_path}")
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise WeeklyReviewSchemaError(
            f"Weekly review generator schema is invalid JSON: {exc.msg}"
        ) from exc
    if not isinstance(schema, Mapping):
        raise WeeklyReviewSchemaError("Weekly review generator schema must be a JSON object.")
    return schema
