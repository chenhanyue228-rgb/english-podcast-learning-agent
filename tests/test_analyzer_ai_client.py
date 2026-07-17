from pathlib import Path

import pytest

from src.analyzer.ai_client import (
    SkillAIWorkflowError,
    load_analysis_schema,
    parse_generated_analysis_json,
    read_generated_analysis_file,
)


def test_load_analysis_schema_reads_json_schema(tmp_path: Path) -> None:
    schema_file = tmp_path / "schema.json"
    schema_file.write_text('{"type":"object"}', encoding="utf-8")

    assert load_analysis_schema(schema_file) == {"type": "object"}


def test_load_analysis_schema_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(SkillAIWorkflowError, match="does not exist"):
        load_analysis_schema(tmp_path / "missing.json")


def test_parse_generated_analysis_json_reads_object() -> None:
    parsed = parse_generated_analysis_json('{"summary":{"english":"Hello"}}')

    assert parsed == {"summary": {"english": "Hello"}}


def test_parse_generated_analysis_json_rejects_invalid_json() -> None:
    with pytest.raises(SkillAIWorkflowError, match="invalid JSON"):
        parse_generated_analysis_json("not json")


def test_parse_generated_analysis_json_requires_object() -> None:
    with pytest.raises(SkillAIWorkflowError, match="must be a JSON object"):
        parse_generated_analysis_json("[1, 2]")


def test_read_generated_analysis_file(tmp_path: Path) -> None:
    output_file = tmp_path / "analysis.json"
    output_file.write_text('{"learning_items":[]}', encoding="utf-8")

    assert read_generated_analysis_file(output_file) == {"learning_items": []}
