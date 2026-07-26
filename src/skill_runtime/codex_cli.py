"""Finite, isolated Codex execution for production artifact generation."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping

from src.skill_runtime.artifacts import (
    CodexArtifactPendingError,
    load_codex_artifact,
)


DEFAULT_CODEX_TIMEOUT_SECONDS = 60
MACOS_CODEX_PATH = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
SAFE_CHILD_ENV_KEYS = frozenset(
    {
        "CODEX_HOME",
        "HOME",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "PATH",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "USER",
    }
)


class CodexRuntimeError(RuntimeError):
    """A stable, redacted Codex child-process failure."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _make_private_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, 0o700)


def resolve_codex_executable(
    env: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    macos_path: Path = MACOS_CODEX_PATH,
) -> Path:
    """Resolve Codex without invoking a shell."""
    source = env if env is not None else os.environ
    configured = str(source.get("CODEX_EXECUTABLE", "")).strip()
    candidates = [Path(configured).expanduser()] if configured else []
    discovered = which("codex")
    if discovered:
        candidates.append(Path(discovered))
    candidates.append(macos_path)
    for candidate in candidates:
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return candidate.resolve()
    raise CodexRuntimeError("codex_executable_not_found")


def sanitized_codex_environment(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Keep runtime essentials while excluding credentials and Notion config."""
    source = env if env is not None else os.environ
    child = {
        key: str(value)
        for key, value in source.items()
        if key in SAFE_CHILD_ENV_KEYS and str(value)
    }
    child.setdefault("PATH", os.defpath)
    if any("NOTION" in key.upper() for key in child):
        raise CodexRuntimeError("notion_environment_exposed")
    if "OPENAI_API_KEY" in child:
        raise CodexRuntimeError("openai_api_key_exposed")
    return child


def _diagnostic_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def build_codex_json_command(
    executable: Path,
    *,
    schema_path: Path,
    output_path: Path,
    work_dir: Path,
) -> list[str]:
    """Build one non-interactive, read-only Codex command."""
    return [
        str(executable),
        "-a",
        "never",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--disable",
        "shell_tool",
        "--disable",
        "shell_zsh_fork",
        "--disable",
        "unified_exec",
        "--disable",
        "unified_exec_zsh_fork",
        "--disable",
        "code_mode",
        "--disable",
        "web_search_request",
        "--disable",
        "web_search_cached",
        "-c",
        'web_search="disabled"',
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--json",
        "--cd",
        str(work_dir),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]


def generate_codex_json_artifact(
    *,
    request_path: Path,
    output_path: Path,
    schema: Mapping[str, Any],
    prompt: str,
    executable: Path | None = None,
    timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
    env: Mapping[str, str] | None = None,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    """Run Codex once and load the current JSON object it generated."""
    if timeout_seconds <= 0:
        raise CodexRuntimeError("invalid_codex_timeout")
    request_path = request_path.resolve()
    output_path = output_path.resolve()
    work_dir = request_path.parent.resolve()
    _make_private_directory(work_dir)
    _make_private_directory(output_path.parent)
    schema_path = request_path.with_suffix(".schema.json")
    schema_path.write_text(
        json.dumps(dict(schema), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.chmod(schema_path, 0o600)
    codex = executable or resolve_codex_executable(env)
    command = build_codex_json_command(
        codex,
        schema_path=schema_path.resolve(),
        output_path=output_path,
        work_dir=work_dir,
    )
    try:
        completed = runner(
            command,
            input=prompt,
            text=True,
            capture_output=True,
            cwd=work_dir,
            env=sanitized_codex_environment(env),
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexRuntimeError("codex_timeout") from exc
    except OSError as exc:
        raise CodexRuntimeError("codex_process_start_failed") from exc
    if completed.returncode != 0:
        diagnostic = _diagnostic_fingerprint(completed.stderr or "")
        raise CodexRuntimeError(
            f"codex_nonzero_exit_{completed.returncode}_{diagnostic}"
        )
    forbidden_events = (
        '"type":"command_execution"',
        '"type":"mcp_tool_call"',
        '"type":"web_search"',
        '"type":"dynamic_tool_call"',
    )
    compact_stdout = (completed.stdout or "").replace(" ", "")
    if any(marker in compact_stdout for marker in forbidden_events):
        raise CodexRuntimeError("codex_tool_use_blocked")
    try:
        payload = load_codex_artifact(
            request_path=request_path,
            output_path=output_path,
            stage="automatic vocabulary enrichment",
        )
    except (CodexArtifactPendingError, OSError) as exc:
        raise CodexRuntimeError("codex_output_invalid") from exc
    os.chmod(output_path, 0o600)
    return payload
