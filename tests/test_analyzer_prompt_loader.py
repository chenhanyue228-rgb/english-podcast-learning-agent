from pathlib import Path

import pytest

from src.analyzer.prompt_loader import (
    PromptLoaderError,
    load_analyzer_prompts,
    load_prompt,
)


def test_load_prompt_reads_file(tmp_path: Path) -> None:
    prompt_file = tmp_path / "summary_prompt.md"
    prompt_file.write_text("Prompt body", encoding="utf-8")

    assert load_prompt("summary_prompt.md", tmp_path) == "Prompt body"


def test_load_prompt_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PromptLoaderError, match="does not exist"):
        load_prompt("missing.md", tmp_path)


def test_load_analyzer_prompts_reads_three_prompt_files(tmp_path: Path) -> None:
    (tmp_path / "summary_prompt.md").write_text("summary", encoding="utf-8")
    (tmp_path / "metadata_prompt.md").write_text("metadata", encoding="utf-8")
    (tmp_path / "expression_prompt.md").write_text("expression", encoding="utf-8")

    prompts = load_analyzer_prompts(tmp_path)

    assert prompts.summary == "summary"
    assert prompts.metadata == "metadata"
    assert prompts.expression == "expression"
