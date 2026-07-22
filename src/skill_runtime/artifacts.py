"""Deterministic request/output handoff for Codex reasoning stages."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


class CodexArtifactPendingError(RuntimeError):
    """Raised when Codex must generate or refresh an output artifact."""


def _canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def prepare_codex_request(
    *,
    stage: str,
    instructions: str,
    input_payload: Mapping[str, Any],
    schema: Mapping[str, Any],
    request_path: Path,
    output_path: Path,
) -> Path:
    """Persist a stable Codex request, rewriting it only when its inputs change."""
    digest_source = {
        "stage": stage,
        "instructions": instructions,
        "input": dict(input_payload),
        "schema": dict(schema),
    }
    digest = hashlib.sha256(_canonical_json(digest_source).encode("utf-8")).hexdigest()
    request = {
        **digest_source,
        "input_digest": digest,
        "output_path": str(output_path),
    }

    existing_digest = ""
    if request_path.exists():
        try:
            existing = json.loads(request_path.read_text(encoding="utf-8"))
            if isinstance(existing, Mapping):
                existing_digest = str(existing.get("input_digest", ""))
        except (OSError, json.JSONDecodeError):
            existing_digest = ""

    if existing_digest != digest:
        request_path.parent.mkdir(parents=True, exist_ok=True)
        request_path.write_text(
            json.dumps(request, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return request_path.resolve()


def load_codex_artifact(*, request_path: Path, output_path: Path, stage: str) -> dict[str, Any]:
    """Load a Codex output only when it exists and is current for its request."""
    request_path = request_path.resolve()
    output_path = output_path.resolve()
    if not output_path.exists() or output_path.stat().st_mtime < request_path.stat().st_mtime:
        raise CodexArtifactPendingError(
            f"Codex artifact required for {stage}. Read {request_path}, generate JSON, "
            f"and save it to {output_path}, then rerun the command."
        )
    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CodexArtifactPendingError(
            f"Codex artifact for {stage} is invalid JSON: {output_path}: {exc.msg}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise CodexArtifactPendingError(
            f"Codex artifact for {stage} must be a JSON object: {output_path}"
        )
    return dict(payload)
