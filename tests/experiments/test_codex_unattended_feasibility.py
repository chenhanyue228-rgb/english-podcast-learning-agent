from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from experiments.automatic_vocabulary_sync.codex_unattended_feasibility import (
    CodexFeasibilityError,
    build_codex_command,
    resolve_codex_executable,
    run_synthetic_feasibility,
    sanitized_child_environment,
    validate_against_existing_schema,
    validate_exact_intent,
)


WORD = "challenge assumptions"
CONTEXT = "Strong negotiators challenge assumptions before proposing a solution."


def _payload(**overrides: Any) -> dict[str, Any]:
    payload = {
        "word": WORD,
        "original_context": CONTEXT,
        "meaning": "Question beliefs before deciding.",
        "chinese_meaning": "在决策前质疑既有假设。",
        "part_of_speech": "verb phrase",
        "professional_category": "Negotiation",
        "usage_example": "The team should challenge assumptions before committing.",
        "common_collocations": [
            "challenge existing assumptions",
            "challenge strategic assumptions",
        ],
    }
    payload.update(overrides)
    return payload


def _successful_runner(payload: dict[str, Any]):
    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        assert command[:4] == [command[0], "-a", "never", "exec"]
        assert "--ephemeral" in command
        assert "--ignore-user-config" in command
        assert "--ignore-rules" in command
        assert command[command.index("--sandbox") + 1] == "read-only"
        assert kwargs["timeout"] == 9
        assert kwargs["check"] is False
        assert not any("NOTION" in key.upper() for key in kwargs["env"])
        assert "OPENAI_API_KEY" not in kwargs["env"]
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    return runner


def test_resolve_codex_executable_prefers_explicit_path(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)

    resolved = resolve_codex_executable(
        {"CODEX_EXECUTABLE": str(executable)},
        which=lambda _: None,
        macos_path=tmp_path / "missing",
    )

    assert resolved == executable.resolve()


def test_resolve_codex_executable_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(CodexFeasibilityError) as exc_info:
        resolve_codex_executable(
            {},
            which=lambda _: None,
            macos_path=tmp_path / "missing",
        )

    assert exc_info.value.code == "codex_executable_not_found"


def test_sanitized_child_environment_excludes_credentials() -> None:
    child = sanitized_child_environment(
        {
            "PATH": "/safe/bin",
            "HOME": "/safe/home",
            "CODEX_HOME": "/safe/codex",
            "NOTION_TOKEN": "do-not-pass",
            "NOTION_TARGET_PARENT_PAGE_ID": "do-not-pass",
            "EPLA_NOTION_SETUP_STATE": "complete",
            "OPENAI_API_KEY": "do-not-pass",
            "CUSTOM_SECRET": "do-not-pass",
        }
    )

    assert child == {
        "PATH": "/safe/bin",
        "HOME": "/safe/home",
        "CODEX_HOME": "/safe/codex",
    }


def test_build_codex_command_is_non_interactive_and_read_only(tmp_path: Path) -> None:
    command = build_codex_command(
        tmp_path / "codex",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        work_dir=tmp_path,
    )

    assert command[1:4] == ["-a", "never", "exec"]
    assert "--ephemeral" in command
    assert "--ignore-rules" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[-1] == "-"


def test_successful_synthetic_run_preserves_exact_intent(tmp_path: Path) -> None:
    executable = tmp_path / "codex"
    executable.touch()
    executable.chmod(0o755)

    result = run_synthetic_feasibility(
        executable=executable,
        timeout_seconds=9,
        word=WORD,
        context=CONTEXT,
        env={
            "PATH": "/safe/bin",
            "HOME": "/safe/home",
            "NOTION_TOKEN": "must-not-pass",
            "OPENAI_API_KEY": "must-not-pass",
        },
        work_dir=tmp_path / "run",
        runner=_successful_runner(_payload()),
    )

    assert result.status == "PASS"
    assert result.schema_validation is True
    assert result.exact_word_preserved is True
    assert result.exact_context_preserved is True
    assert result.child_environment_sanitized is True
    assert result.notion_environment_exposed is False
    assert result.openai_api_key_exposed is False


def test_real_child_process_receives_no_notion_or_openai_environment(
    tmp_path: Path,
) -> None:
    executable = tmp_path / "fake-codex"
    payload = json.dumps(_payload(), ensure_ascii=False)
    executable.write_text(
        "#!/bin/sh\n"
        "if env | grep -qi notion; then exit 23; fi\n"
        "if env | grep -q '^OPENAI_API_KEY='; then exit 24; fi\n"
        "output=''\n"
        "previous=''\n"
        "for argument in \"$@\"; do\n"
        "  if [ \"$previous\" = '--output-last-message' ]; then output=\"$argument\"; fi\n"
        "  previous=\"$argument\"\n"
        "done\n"
        f"printf '%s' '{payload}' > \"$output\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)

    result = run_synthetic_feasibility(
        executable=executable,
        timeout_seconds=9,
        word=WORD,
        context=CONTEXT,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path),
            "NOTION_TOKEN": "must-not-pass",
            "NOTION_TARGET_PARENT_PAGE_ID": "must-not-pass",
            "OPENAI_API_KEY": "must-not-pass",
        },
        work_dir=tmp_path / "real-child-run",
    )

    assert result.status == "PASS"
    assert result.notion_environment_exposed is False
    assert result.openai_api_key_exposed is False


def test_nonzero_exit_fails_closed(tmp_path: Path) -> None:
    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 7, stdout="", stderr="failure")

    with pytest.raises(CodexFeasibilityError) as exc_info:
        run_synthetic_feasibility(
            executable=tmp_path / "codex",
            timeout_seconds=9,
            work_dir=tmp_path / "run",
            runner=runner,
        )

    assert exc_info.value.code == "codex_nonzero_exit"


def test_timeout_fails_closed(tmp_path: Path) -> None:
    def runner(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(CodexFeasibilityError) as exc_info:
        run_synthetic_feasibility(
            executable=tmp_path / "codex",
            timeout_seconds=9,
            work_dir=tmp_path / "run",
            runner=runner,
        )

    assert exc_info.value.code == "codex_timeout"


def test_malformed_output_fails_closed(tmp_path: Path) -> None:
    def runner(command: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        output_index = command.index("--output-last-message") + 1
        Path(command[output_index]).write_text("not json", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(CodexFeasibilityError) as exc_info:
        run_synthetic_feasibility(
            executable=tmp_path / "codex",
            timeout_seconds=9,
            work_dir=tmp_path / "run",
            runner=runner,
        )

    assert exc_info.value.code == "malformed_or_missing_output"


def test_schema_validation_rejects_missing_or_invalid_fields() -> None:
    incomplete = _payload()
    del incomplete["meaning"]
    with pytest.raises(CodexFeasibilityError) as missing:
        validate_against_existing_schema(incomplete)
    assert missing.value.code == "schema_validation_failed"

    with pytest.raises(CodexFeasibilityError) as invalid:
        validate_against_existing_schema(_payload(common_collocations="not-a-list"))
    assert invalid.value.code == "schema_validation_failed"


def test_exact_word_and_context_mismatches_fail_closed() -> None:
    with pytest.raises(CodexFeasibilityError) as word_error:
        validate_exact_intent(
            _payload(word="expanded challenge assumptions"),
            word=WORD,
            context=CONTEXT,
        )
    assert word_error.value.code == "exact_word_mismatch"

    with pytest.raises(CodexFeasibilityError) as context_error:
        validate_exact_intent(
            _payload(original_context="rewritten context"),
            word=WORD,
            context=CONTEXT,
        )
    assert context_error.value.code == "exact_context_mismatch"
