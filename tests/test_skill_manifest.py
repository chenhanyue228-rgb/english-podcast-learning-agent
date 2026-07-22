from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = PROJECT_ROOT / "skill" / "SKILL.md"


def _frontmatter_fields() -> dict[str, str]:
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert text.startswith("---\n")

    closing_marker = text.find("\n---\n", 4)
    assert closing_marker != -1

    fields: dict[str, str] = {}
    for line in text[4:closing_marker].splitlines():
        key, separator, value = line.partition(":")
        assert separator == ":"
        fields[key.strip()] = value.strip()
    return fields


def test_skill_manifest_has_exact_activation_frontmatter() -> None:
    fields = _frontmatter_fields()

    assert set(fields) == {"name", "description"}
    assert fields["name"] == "english-audio-learning-agent"
    description = fields["description"].lower()
    assert description
    assert "english audio" in description
    assert "vocabulary" in description
    assert "weekly reflection" in description


def test_skill_prompt_resources_are_present() -> None:
    prompt_names = {
        path.name for path in (PROJECT_ROOT / "skill" / "prompts").glob("*.md")
    }

    assert {
        "expression_prompt.md",
        "metadata_prompt.md",
        "summary_prompt.md",
        "vocabulary_prompt.md",
        "weekly_reflection_prompt.md",
        "weekly_review_generator_prompt.md",
        "weekly_review_prompt.md",
    } <= prompt_names


def test_skill_schema_resources_are_present() -> None:
    schema_names = {
        path.name for path in (PROJECT_ROOT / "skill" / "schemas").glob("*.json")
    }

    assert {
        "ai_analysis_schema.json",
        "reflection_context_schema.json",
        "vocabulary_memory_schema.json",
        "weekly_review_generator_schema.json",
        "weekly_review_schema.json",
        "weekly_review_v2_analysis_schema.json",
    } <= schema_names
