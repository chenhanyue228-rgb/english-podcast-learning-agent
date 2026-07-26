from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from src.skill_runtime.artifacts import prepare_codex_request
from src.skill_runtime.codex_cli import (
    CodexRuntimeError,
    build_codex_json_command,
    generate_codex_json_artifact,
    sanitized_codex_environment,
)


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["word"],
    "properties": {"word": {"type": "string"}},
}


def _request(tmp_path: Path) -> tuple[Path, Path]:
    request_path = tmp_path / "requests" / "request.json"
    output_path = tmp_path / "outputs" / "output.json"
    prepare_codex_request(
        stage="test",
        instructions="Return JSON.",
        input_payload={"word": "assumption"},
        schema=SCHEMA,
        request_path=request_path,
        output_path=output_path,
    )
    return request_path, output_path


def test_sanitized_environment_excludes_credentials_and_proxies() -> None:
    child = sanitized_codex_environment(
        {
            "HOME": "/safe/home",
            "PATH": "/safe/bin",
            "CODEX_HOME": "/safe/codex",
            "NOTION_TOKEN": "secret",
            "NOTION_TARGET_PARENT_PAGE_ID": "secret",
            "OPENAI_API_KEY": "secret",
            "HTTP_PROXY": "http://secret",
            "HTTPS_PROXY": "http://secret",
            "ALL_PROXY": "http://secret",
            "CUSTOM_TOKEN": "secret",
        }
    )

    assert child == {
        "HOME": "/safe/home",
        "PATH": "/safe/bin",
        "CODEX_HOME": "/safe/codex",
    }


def test_command_disables_tools_and_uses_read_only_sandbox(
    tmp_path: Path,
) -> None:
    command = build_codex_json_command(
        tmp_path / "codex",
        schema_path=tmp_path / "schema.json",
        output_path=tmp_path / "output.json",
        work_dir=tmp_path,
    )

    assert command[1:4] == ["-a", "never", "exec"]
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("-c") + 1] == 'web_search="disabled"'
    disabled = {
        command[index + 1]
        for index, value in enumerate(command)
        if value == "--disable"
    }
    assert {
        "shell_tool",
        "unified_exec",
        "code_mode",
        "web_search_request",
    }.issubset(disabled)


def test_generate_codex_artifact_is_finite_private_and_sanitized(
    tmp_path: Path,
) -> None:
    request_path, output_path = _request(tmp_path)
    captured: dict[str, Any] = {}

    def runner(
        command: list[str],
        **kwargs: Any,
    ) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        output = Path(
            command[command.index("--output-last-message") + 1]
        )
        output.write_text(
            json.dumps({"word": "assumption"}),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"agent_message"}',
            stderr="",
        )

    result = generate_codex_json_artifact(
        request_path=request_path,
        output_path=output_path,
        schema=SCHEMA,
        prompt="Return JSON.",
        executable=tmp_path / "codex",
        timeout_seconds=7,
        env={
            "HOME": str(tmp_path),
            "PATH": "/safe/bin",
            "NOTION_TOKEN": "secret",
            "OPENAI_API_KEY": "secret",
        },
        runner=runner,
    )

    assert result == {"word": "assumption"}
    assert captured["timeout"] == 7
    assert captured["check"] is False
    assert "NOTION_TOKEN" not in captured["env"]
    assert "OPENAI_API_KEY" not in captured["env"]
    assert os.stat(output_path).st_mode & 0o777 == 0o600
    schema_path = request_path.with_suffix(".schema.json")
    assert os.stat(schema_path).st_mode & 0o777 == 0o600


def test_generate_codex_artifact_rejects_observed_tool_use(
    tmp_path: Path,
) -> None:
    request_path, output_path = _request(tmp_path)

    def runner(
        command: list[str],
        **_: Any,
    ) -> subprocess.CompletedProcess[str]:
        output = Path(
            command[command.index("--output-last-message") + 1]
        )
        output.write_text('{"word":"assumption"}', encoding="utf-8")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout='{"type":"command_execution","command":"redacted"}',
            stderr="",
        )

    with pytest.raises(CodexRuntimeError) as raised:
        generate_codex_json_artifact(
            request_path=request_path,
            output_path=output_path,
            schema=SCHEMA,
            prompt="Return JSON.",
            executable=tmp_path / "codex",
            runner=runner,
        )

    assert raised.value.code == "codex_tool_use_blocked"


def test_generate_codex_artifact_timeout_is_redacted(
    tmp_path: Path,
) -> None:
    request_path, output_path = _request(tmp_path)

    def runner(command: list[str], **kwargs: Any) -> Any:
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    with pytest.raises(CodexRuntimeError) as raised:
        generate_codex_json_artifact(
            request_path=request_path,
            output_path=output_path,
            schema=SCHEMA,
            prompt="Return JSON.",
            executable=tmp_path / "codex",
            timeout_seconds=1,
            runner=runner,
        )

    assert raised.value.code == "codex_timeout"
