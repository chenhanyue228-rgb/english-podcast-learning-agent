"""Synthetic feasibility check for unattended Codex vocabulary enrichment.

This experiment is intentionally isolated from the production runtime. It does
not read Notion configuration, call Notion, publish vocabulary, or install a
scheduler.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Mapping, Sequence

from src.enrichment.codex_provider import (
    VOCABULARY_ENRICHMENT_SCHEMA,
    VOCABULARY_INSTRUCTIONS,
)
from src.skill_runtime.artifacts import (
    CodexArtifactPendingError,
    load_codex_artifact,
    prepare_codex_request,
)


DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_SYNTHETIC_WORD = "challenge assumptions"
DEFAULT_SYNTHETIC_CONTEXT = (
    "Strong negotiators challenge assumptions before proposing a solution."
)
MACOS_CODEX_PATH = Path("/Applications/ChatGPT.app/Contents/Resources/codex")

SAFE_CHILD_ENV_KEYS = frozenset(
    {
        "ALL_PROXY",
        "CODEX_HOME",
        "HOME",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "LOGNAME",
        "NO_PROXY",
        "PATH",
        "SHELL",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TERM",
        "TMPDIR",
        "USER",
    }
)


class CodexFeasibilityError(RuntimeError):
    """A stable, redacted failure from the synthetic feasibility check."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CodexFeasibilityResult:
    status: str
    executable_resolved: bool
    non_interactive_invocation: bool
    schema_validation: bool
    exact_word_preserved: bool
    exact_context_preserved: bool
    finite_timeout_seconds: int
    child_environment_sanitized: bool
    notion_environment_exposed: bool
    openai_api_key_exposed: bool
    exit_code: int

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def resolve_codex_executable(
    env: Mapping[str, str] | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    macos_path: Path = MACOS_CODEX_PATH,
) -> Path:
    """Resolve an executable without invoking a shell."""
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
    raise CodexFeasibilityError(
        "codex_executable_not_found",
        "Codex executable could not be resolved.",
    )


def sanitized_child_environment(
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Build a minimal environment that excludes Notion and API credentials."""
    source = env if env is not None else os.environ
    child = {
        key: str(value)
        for key, value in source.items()
        if key in SAFE_CHILD_ENV_KEYS and str(value)
    }
    child.setdefault("PATH", os.defpath)

    exposed_notion_keys = [key for key in child if "NOTION" in key.upper()]
    if exposed_notion_keys:
        raise CodexFeasibilityError(
            "notion_environment_exposed",
            "A Notion-related variable reached the Codex child environment.",
        )
    if "OPENAI_API_KEY" in child:
        raise CodexFeasibilityError(
            "openai_api_key_exposed",
            "OPENAI_API_KEY reached the Codex child environment.",
        )
    return child


def strict_output_schema() -> dict[str, Any]:
    """Use the existing enrichment schema with strict output-key enforcement."""
    schema = copy.deepcopy(VOCABULARY_ENRICHMENT_SCHEMA)
    schema["additionalProperties"] = False
    return schema


def _matches_schema_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_against_existing_schema(
    payload: Mapping[str, Any],
    schema: Mapping[str, Any] = VOCABULARY_ENRICHMENT_SCHEMA,
) -> None:
    """Validate the subset of JSON Schema used by vocabulary enrichment."""
    required = schema.get("required", [])
    if isinstance(required, list):
        missing = [key for key in required if key not in payload]
        if missing:
            raise CodexFeasibilityError(
                "schema_validation_failed",
                "Codex output is missing required vocabulary fields.",
            )

    properties = schema.get("properties", {})
    if not isinstance(properties, Mapping):
        raise CodexFeasibilityError(
            "schema_configuration_invalid",
            "Vocabulary enrichment schema properties are invalid.",
        )

    for key, value in payload.items():
        definition = properties.get(key)
        if not isinstance(definition, Mapping):
            continue
        expected = definition.get("type")
        if isinstance(expected, str) and not _matches_schema_type(value, expected):
            raise CodexFeasibilityError(
                "schema_validation_failed",
                "Codex output contains an invalid vocabulary field type.",
            )
        if expected == "array":
            item_schema = definition.get("items", {})
            item_type = (
                item_schema.get("type")
                if isinstance(item_schema, Mapping)
                else None
            )
            if isinstance(item_type, str) and any(
                not _matches_schema_type(item, item_type) for item in value
            ):
                raise CodexFeasibilityError(
                    "schema_validation_failed",
                    "Codex output contains an invalid vocabulary list item.",
                )


def validate_exact_intent(
    payload: Mapping[str, Any],
    *,
    word: str,
    context: str,
) -> None:
    """Reject any AI expansion, replacement, or context rewriting."""
    if payload.get("word") != word:
        raise CodexFeasibilityError(
            "exact_word_mismatch",
            "Codex did not preserve the exact highlighted text.",
        )
    if payload.get("original_context") != context:
        raise CodexFeasibilityError(
            "exact_context_mismatch",
            "Codex did not preserve the exact highlight context.",
        )


def build_codex_command(
    executable: Path,
    *,
    schema_path: Path,
    output_path: Path,
    work_dir: Path,
) -> list[str]:
    """Build a finite, non-interactive, read-only Codex invocation."""
    return [
        str(executable),
        "-a",
        "never",
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--ignore-rules",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "--cd",
        str(work_dir),
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]


def _prompt(request_path: Path, *, word: str, context: str) -> str:
    return (
        "Perform a synthetic vocabulary-enrichment feasibility check. "
        f"The corresponding request artifact is {request_path}. "
        "For this no-tool experiment, use this exact input JSON: "
        f"{json.dumps({'word': word, 'context': context}, ensure_ascii=False)}. "
        "Return only the JSON object required by its schema. "
        "Preserve input.word exactly as word and input.context exactly as "
        "original_context. Do not expand, replace, normalize, or infer the "
        "vocabulary target. Do not call tools or access unrelated files."
    )


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def run_synthetic_feasibility(
    *,
    executable: Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    word: str = DEFAULT_SYNTHETIC_WORD,
    context: str = DEFAULT_SYNTHETIC_CONTEXT,
    env: Mapping[str, str] | None = None,
    work_dir: Path | None = None,
    runner: Runner = subprocess.run,
) -> CodexFeasibilityResult:
    """Run one isolated synthetic check without production side effects."""
    if timeout_seconds <= 0:
        raise CodexFeasibilityError(
            "invalid_timeout",
            "The feasibility timeout must be positive.",
        )
    codex_executable = executable or resolve_codex_executable(env)
    child_env = sanitized_child_environment(env)

    def execute(directory: Path) -> CodexFeasibilityResult:
        directory.mkdir(parents=True, exist_ok=True)
        request_path = directory / "vocabulary_enrichment_request.json"
        output_path = directory / "vocabulary_enrichment_output.json"
        schema_path = directory / "vocabulary_enrichment_output_schema.json"

        prepare_codex_request(
            stage="synthetic_vocabulary_enrichment_feasibility",
            instructions=VOCABULARY_INSTRUCTIONS,
            input_payload={"word": word, "context": context},
            schema=VOCABULARY_ENRICHMENT_SCHEMA,
            request_path=request_path,
            output_path=output_path,
        )
        schema_path.write_text(
            json.dumps(strict_output_schema(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        command = build_codex_command(
            codex_executable,
            schema_path=schema_path.resolve(),
            output_path=output_path.resolve(),
            work_dir=directory.resolve(),
        )

        try:
            completed = runner(
                command,
                input=_prompt(request_path.resolve(), word=word, context=context),
                text=True,
                capture_output=True,
                cwd=directory,
                env=child_env,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise CodexFeasibilityError(
                "codex_timeout",
                f"Codex exceeded the finite timeout ({timeout_seconds}s).",
            ) from exc
        except OSError as exc:
            raise CodexFeasibilityError(
                "codex_process_start_failed",
                "Codex child process could not start.",
            ) from exc

        if completed.returncode != 0:
            stderr = completed.stderr or ""
            raise CodexFeasibilityError(
                "codex_nonzero_exit",
                "Codex exited unsuccessfully "
                f"(code={completed.returncode}, diagnostic={_fingerprint(stderr)}).",
            )

        try:
            payload = load_codex_artifact(
                request_path=request_path,
                output_path=output_path,
                stage="synthetic vocabulary enrichment feasibility",
            )
        except (CodexArtifactPendingError, OSError) as exc:
            raise CodexFeasibilityError(
                "malformed_or_missing_output",
                "Codex did not produce a current JSON object artifact.",
            ) from exc

        validate_against_existing_schema(payload)
        validate_exact_intent(payload, word=word, context=context)

        return CodexFeasibilityResult(
            status="PASS",
            executable_resolved=True,
            non_interactive_invocation=True,
            schema_validation=True,
            exact_word_preserved=True,
            exact_context_preserved=True,
            finite_timeout_seconds=timeout_seconds,
            child_environment_sanitized=True,
            notion_environment_exposed=False,
            openai_api_key_exposed=False,
            exit_code=completed.returncode,
        )

    if work_dir is not None:
        return execute(work_dir.resolve())
    with TemporaryDirectory(prefix="epla-codex-feasibility-") as temp_dir:
        return execute(Path(temp_dir))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the isolated unattended Codex vocabulary feasibility check."
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help="Finite child-process timeout.",
    )
    parser.add_argument(
        "--codex-executable",
        type=Path,
        help="Optional explicit Codex executable used only by this experiment.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = run_synthetic_feasibility(
            executable=args.codex_executable,
            timeout_seconds=args.timeout_seconds,
        )
    except CodexFeasibilityError as exc:
        print(
            json.dumps(
                {
                    "status": "FAIL",
                    "failure_code": exc.code,
                    "real_notion_calls": 0,
                    "real_notion_writes": 0,
                },
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            {
                **result.to_json(),
                "real_notion_calls": 0,
                "real_notion_writes": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
