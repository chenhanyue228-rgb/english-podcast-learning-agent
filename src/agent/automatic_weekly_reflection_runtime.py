"""One-shot unattended Weekly Reflection runtime with strict safety gates."""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence

from src.agent.automatic_vocabulary_detector import (
    target_namespace,
)
from src.agent.weekly_reflection_scheduler import (
    DEFAULT_RUNTIME_STATUS_PATH,
    DEFAULT_SCHEDULE_PATH,
    WEEKDAYS,
    WeeklyReflectionSchedule,
    WeeklyReflectionSchedulerError,
    load_schedule,
)
from src.notion.config import NotionConfig, load_notion_config
from src.notion.pagination import next_notion_cursor
from src.notion.target_binding import (
    NotionTargetBindingError,
    validate_notion_target_binding,
)
from src.notion.uploader import create_notion_client
from src.notion.weekly_reflection_writer import (
    WeeklyReflectionPublishPayload,
    weekly_reflection_body_blocks,
)
from src.skill_runtime.artifacts import (
    CodexArtifactPendingError,
    load_codex_artifact,
    prepare_codex_request,
)
from src.skill_runtime.codex_cli import (
    DEFAULT_CODEX_TIMEOUT_SECONDS,
    CodexRuntimeError,
    generate_codex_json_artifact,
)
from src.weekly_review.generator import _validate_output
from src.weekly_review.prompt import load_weekly_review_generator_prompt
from src.weekly_review.quality_checker import check_weekly_review_quality
from src.weekly_review.reflection_analyzer import (
    ReflectionGenerationError,
    _validate_reflection_payload,
    load_reflection_schema,
)
from src.weekly_review.schema import load_weekly_review_generator_schema
from src.workflow.schema_validator import (
    WeeklyLearningContextValidationError,
    validate_weekly_learning_context,
)
from src.workflow.weekly_learning_context_pipeline import (
    run_weekly_learning_extraction,
)
from src.workflow.weekly_reflection_pipeline import (
    WeeklyReflectionPipelineError,
    run_weekly_reflection_pipeline,
)


DEFAULT_STATE_DIRECTORY = Path("data/weekly_reflection")
DEFAULT_ARTIFACT_DIRECTORY = DEFAULT_STATE_DIRECTORY / "artifacts"
DEFAULT_RUNTIME_LOG_PATH = Path("logs/weekly_reflection/runtime.jsonl")
DEFAULT_PROCESS_LOCK_SUFFIX = ".worker.lock"
STATE_SCHEMA_VERSION = 1
PRODUCTION_QUALITY_THRESHOLD = 85


class AutomaticWeeklyReflectionError(RuntimeError):
    """A stable, redacted failure from the bounded Weekly runtime."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class AutomaticWeeklyReflectionBusy(AutomaticWeeklyReflectionError):
    """Another local one-shot runtime owns the non-blocking lock."""


class RetryableAutomaticWeeklyReflectionError(
    AutomaticWeeklyReflectionError
):
    """A transient failure that a later bounded invocation may retry."""


@dataclass(frozen=True)
class ScheduledPeriod:
    key: str
    scheduled_at: datetime
    extraction_date: date


@dataclass(frozen=True)
class AutomaticWeeklyReflectionReport:
    status: str
    enabled: bool
    weekday: str
    hour: int
    minute: int
    timezone_mode: str
    period: str
    target_binding_valid: bool
    podcasts: int
    learning_assets: int
    reflection_codex_calls: int
    weekly_review_codex_calls: int
    quality_score: int
    weekly_created: int
    weekly_updated: int
    podcast_writes: int
    expression_writes: int
    vocabulary_writes: int
    schema_writes: int
    deletes_or_archives: int
    historical_group_reads: int
    historical_group_writes: int
    process_lock_acquired: bool
    last_success_period: str
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, repr=False)
class WeeklyIdentityInspection:
    same_period_count: int
    exact_identity_count: int
    generated_identity_count: int = 0
    exact_page_id: str = ""


Runner = Callable[..., subprocess.CompletedProcess[str]]
CodexGenerator = Callable[..., dict[str, Any]]


class _UnavailableEndpoint:
    def __getattr__(self, _name: str) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_notion_endpoint_unavailable"
        )


class _WeeklyPagesProxy:
    def __init__(self, endpoint: Any, weekly_data_source_id: str) -> None:
        self._endpoint = endpoint
        self._weekly_data_source_id = weekly_data_source_id
        self.create_count = 0

    def create(self, **kwargs: Any) -> Any:
        parent = kwargs.get("parent")
        if (
            not isinstance(parent, Mapping)
            or parent.get("data_source_id") != self._weekly_data_source_id
            or self.create_count != 0
        ):
            raise AutomaticWeeklyReflectionError(
                "weekly_unattended_write_blocked"
            )
        self.create_count += 1
        return self._endpoint.create(**kwargs)

    def update(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_update_blocked"
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._endpoint, name)


class _ReadOnlyChildrenProxy:
    def __init__(self, endpoint: Any) -> None:
        self._endpoint = endpoint

    def list(self, **kwargs: Any) -> Any:
        return self._endpoint.list(**kwargs)

    def append(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_block_write_blocked"
        )


class _ReadOnlyBlocksProxy:
    def __init__(self, endpoint: Any) -> None:
        self._endpoint = endpoint
        self.children = _ReadOnlyChildrenProxy(
            getattr(endpoint, "children", _UnavailableEndpoint())
        )

    def delete(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_delete_blocked"
        )

    def update(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_block_write_blocked"
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._endpoint, name)


class _ReadOnlyEndpointProxy:
    def __init__(self, endpoint: Any) -> None:
        self._endpoint = endpoint

    def create(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_nonweekly_write_blocked"
        )

    def update(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_nonweekly_write_blocked"
        )

    def delete(self, **_kwargs: Any) -> Any:
        raise AutomaticWeeklyReflectionError(
            "weekly_unattended_nonweekly_write_blocked"
        )

    def __getattr__(self, name: str) -> Any:
        return getattr(self._endpoint, name)


class _WeeklyOnlyNotionProxy:
    def __init__(self, notion: Any, weekly_data_source_id: str) -> None:
        self.pages = _WeeklyPagesProxy(
            getattr(notion, "pages", _UnavailableEndpoint()),
            weekly_data_source_id,
        )
        self.blocks = _ReadOnlyBlocksProxy(
            getattr(notion, "blocks", _UnavailableEndpoint())
        )
        self.data_sources = _ReadOnlyEndpointProxy(
            getattr(notion, "data_sources", _UnavailableEndpoint())
        )
        self.databases = _ReadOnlyEndpointProxy(
            getattr(notion, "databases", _UnavailableEndpoint())
        )


def _private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    _private_parent(path)
    temporary: Optional[Path] = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=str(path.parent),
            text=True,
        )
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                dict(payload),
                handle,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise AutomaticWeeklyReflectionError(
            "weekly_runtime_state_write_failed"
        ) from exc


def _load_json_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AutomaticWeeklyReflectionError(
            "weekly_runtime_state_invalid"
        ) from exc
    if not isinstance(payload, Mapping):
        raise AutomaticWeeklyReflectionError(
            "weekly_runtime_state_invalid"
        )
    return dict(payload)


def default_state_path(target_group_fingerprint: str) -> Path:
    return DEFAULT_STATE_DIRECTORY / (
        f"runtime_state_{target_group_fingerprint[:12]}.json"
    )


def default_process_lock_path(target_group_fingerprint: str) -> Path:
    return Path(
        f"{default_state_path(target_group_fingerprint)}"
        f"{DEFAULT_PROCESS_LOCK_SUFFIX}"
    )


def _artifact_paths(
    artifact_root: Path,
    target_group_fingerprint: str,
    period: str,
) -> dict[str, Path]:
    root = artifact_root / target_group_fingerprint[:12] / period
    root.mkdir(parents=True, exist_ok=True)
    os.chmod(root, 0o700)
    return {
        "root": root,
        "weekly_context": root / "weekly_learning_context.json",
        "reflection_request": root / "reflection_context_request.json",
        "reflection_output": root / "reflection_context.json",
        "weekly_request": root / "weekly_review_request.json",
        "weekly_codex_output": root / "weekly_review_codex.json",
        "weekly_output": root / "weekly_review.json",
        "pipeline_run": root / "pipeline_run.json",
        "logs": root / "logs",
    }


@contextmanager
def automatic_weekly_process_lock(path: Path) -> Iterator[None]:
    _private_parent(path)
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(path, 0o600)
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            raise AutomaticWeeklyReflectionBusy(
                "weekly_runtime_overlap"
            ) from None
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _parse_effective_at(
    value: str,
    local_timezone: Any,
) -> Optional[datetime]:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(local_timezone)


def scheduled_period_if_due(
    now: datetime,
    schedule: WeeklyReflectionSchedule,
) -> Optional[ScheduledPeriod]:
    if not schedule.enabled:
        return None
    local_now = now if now.tzinfo is not None else now.astimezone()
    local_now = local_now.astimezone()
    target_weekday = WEEKDAYS.index(schedule.weekday)
    days_since = (local_now.weekday() - target_weekday) % 7
    candidate_date = local_now.date() - timedelta(days=days_since)
    candidate = datetime.combine(
        candidate_date,
        time(schedule.hour, schedule.minute),
        tzinfo=local_now.tzinfo,
    )
    if candidate > local_now:
        return None
    if local_now - candidate >= timedelta(days=7):
        return None
    effective_at = _parse_effective_at(
        schedule.effective_at,
        local_now.tzinfo,
    )
    if effective_at is not None and candidate < effective_at:
        return None
    iso = candidate_date.isocalendar()
    return ScheduledPeriod(
        key=f"{iso.year}-W{iso.week:02d}",
        scheduled_at=candidate,
        extraction_date=candidate_date,
    )


def _state_for_group(path: Path, group_fingerprint: str) -> dict[str, Any]:
    state = _load_json_mapping(path)
    if not state:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "target_group_fingerprint": group_fingerprint,
            "last_run_status": "",
            "last_success_period": "",
            "completed_periods": {},
            "publish_intents": {},
        }
    if (
        state.get("schema_version") != STATE_SCHEMA_VERSION
        or state.get("target_group_fingerprint") != group_fingerprint
        or not isinstance(state.get("completed_periods"), Mapping)
        or not isinstance(state.get("publish_intents", {}), Mapping)
    ):
        raise AutomaticWeeklyReflectionError(
            "weekly_runtime_state_namespace_mismatch"
        )
    return state


def _publish_artifact_fingerprint(paths: Mapping[str, Path]) -> str:
    digest = hashlib.sha256()
    for key in ("reflection_output", "weekly_codex_output"):
        path = paths[key]
        try:
            content = path.read_bytes()
        except OSError:
            raise AutomaticWeeklyReflectionError(
                "weekly_publish_artifact_missing"
            ) from None
        digest.update(key.encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _canonical_block(
    block: Mapping[str, Any],
    children: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    block_type = str(block.get("type", "")).strip()
    payload = block.get(block_type, {})
    if not block_type or not isinstance(payload, Mapping):
        raise AutomaticWeeklyReflectionError(
            "weekly_body_read_failed"
        )
    canonical: dict[str, Any] = {"type": block_type}
    rich_text = payload.get("rich_text")
    if isinstance(rich_text, list):
        canonical["text"] = _plain_text(rich_text)
    cells = payload.get("cells")
    if isinstance(cells, list):
        canonical["cells"] = [
            _plain_text(cell) if isinstance(cell, list) else ""
            for cell in cells
        ]
    if block_type == "to_do":
        canonical["checked"] = bool(payload.get("checked", False))
    if block_type == "table":
        canonical.update(
            {
                "table_width": int(payload.get("table_width", 0) or 0),
                "has_column_header": bool(
                    payload.get("has_column_header", False)
                ),
                "has_row_header": bool(
                    payload.get("has_row_header", False)
                ),
            }
        )
    canonical["children"] = [
        _canonical_block(
            child,
            _embedded_block_children(child),
        )
        for child in children
    ]
    return canonical


def _embedded_block_children(
    block: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    block_type = str(block.get("type", "")).strip()
    payload = block.get(block_type, {})
    if not isinstance(payload, Mapping):
        return []
    children = payload.get("children", [])
    if not isinstance(children, list):
        return []
    return [
        child for child in children if isinstance(child, Mapping)
    ]


def _block_tree_fingerprint(
    blocks: Sequence[Mapping[str, Any]],
) -> str:
    canonical = [
        _canonical_block(block, _embedded_block_children(block))
        for block in blocks
    ]
    return _canonical_tree_fingerprint(canonical)


def _canonical_tree_fingerprint(
    canonical: Sequence[Mapping[str, Any]],
) -> str:
    serialized = json.dumps(
        list(canonical),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _expected_weekly_body_fingerprint(
    paths: Mapping[str, Path],
) -> str:
    try:
        reflection = json.loads(
            paths["reflection_output"].read_text(encoding="utf-8")
        )
        weekly_review = json.loads(
            paths["weekly_codex_output"].read_text(encoding="utf-8")
        )
        weekly_context = json.loads(
            paths["weekly_context"].read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        raise AutomaticWeeklyReflectionError(
            "weekly_publish_artifact_missing"
        ) from None
    if (
        not isinstance(reflection, Mapping)
        or not isinstance(weekly_review, Mapping)
        or not isinstance(weekly_context, Mapping)
    ):
        raise AutomaticWeeklyReflectionError(
            "weekly_publish_artifact_invalid"
        )
    validated_reflection = validate_strict_reflection_artifact(
        reflection,
        require_cross_content_patterns=(
            sum(
                1
                for item in weekly_context.get("podcasts", [])
                if isinstance(item, Mapping)
            )
            > 1
        ),
    )
    validated_weekly = validate_strict_weekly_artifact(
        weekly_review,
        weekly_context,
    )
    payload = WeeklyReflectionPublishPayload(
        weekly_review=validated_weekly,
        reflection_context=validated_reflection,
    )
    return _block_tree_fingerprint(
        weekly_reflection_body_blocks(payload)
    )


def _has_matching_publish_intent(
    state: Mapping[str, Any],
    period: str,
    paths: Mapping[str, Path],
) -> bool:
    intents = state.get("publish_intents", {})
    if not isinstance(intents, Mapping):
        return False
    intent = intents.get(period, {})
    if not isinstance(intent, Mapping):
        return False
    expected = str(intent.get("artifact_fingerprint", "")).strip()
    if not expected:
        return False
    try:
        actual = _publish_artifact_fingerprint(paths)
    except AutomaticWeeklyReflectionError:
        return False
    body_fingerprint = str(
        intent.get("body_fingerprint", "")
    ).strip()
    if not body_fingerprint:
        return False
    try:
        expected_body = _expected_weekly_body_fingerprint(paths)
    except AutomaticWeeklyReflectionError:
        return False
    return actual == expected and expected_body == body_fingerprint


def _matching_publish_intent_body_fingerprint(
    state: Mapping[str, Any],
    period: str,
    paths: Mapping[str, Path],
) -> str:
    if not _has_matching_publish_intent(state, period, paths):
        return ""
    intents = state.get("publish_intents", {})
    intent = intents.get(period, {}) if isinstance(intents, Mapping) else {}
    if not isinstance(intent, Mapping):
        return ""
    return str(intent.get("body_fingerprint", "")).strip()


def _record_publish_intent(
    state: dict[str, Any],
    period: str,
    paths: Mapping[str, Path],
    *,
    started_at: str,
) -> None:
    intents = dict(state.get("publish_intents", {}))
    intents[period] = {
        "artifact_fingerprint": _publish_artifact_fingerprint(paths),
        "body_fingerprint": _expected_weekly_body_fingerprint(paths),
        "started_at": started_at,
    }
    state["publish_intents"] = intents


def _clear_publish_intent(
    state: dict[str, Any],
    period: str,
) -> None:
    intents = dict(state.get("publish_intents", {}))
    intents.pop(period, None)
    state["publish_intents"] = intents


def _save_runtime_status(
    report: AutomaticWeeklyReflectionReport,
    path: Path,
) -> None:
    _atomic_json_write(
        path,
        {
            "last_run_status": report.status,
            "last_success_period": report.last_success_period,
        },
    )


def append_redacted_runtime_log(
    report: AutomaticWeeklyReflectionReport,
    path: Path = DEFAULT_RUNTIME_LOG_PATH,
) -> None:
    _private_parent(path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                report.to_dict(),
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        handle.write("\n")
    os.chmod(path, 0o600)


def _strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    strict = copy.deepcopy(dict(schema))

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object" and isinstance(
                node.get("properties"), dict
            ):
                node["additionalProperties"] = False
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(strict)
    return strict


def _schema_matches_type(value: Any, expected: str) -> bool:
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
    return False


def _validate_schema_value(
    value: Any,
    schema: Mapping[str, Any],
    *,
    code: str,
) -> None:
    choices = schema.get("oneOf")
    if isinstance(choices, list):
        matches = 0
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            try:
                _validate_schema_value(value, choice, code=code)
            except AutomaticWeeklyReflectionError:
                continue
            matches += 1
        if matches != 1:
            raise AutomaticWeeklyReflectionError(code)
        return

    expected = schema.get("type")
    if isinstance(expected, str) and not _schema_matches_type(value, expected):
        raise AutomaticWeeklyReflectionError(code)

    allowed = schema.get("enum")
    if isinstance(allowed, list) and value not in allowed:
        raise AutomaticWeeklyReflectionError(code)

    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if isinstance(minimum, int) and len(value) < minimum:
            raise AutomaticWeeklyReflectionError(code)
        if isinstance(maximum, int) and len(value) > maximum:
            raise AutomaticWeeklyReflectionError(code)

    if isinstance(value, list):
        minimum = schema.get("minItems")
        maximum = schema.get("maxItems")
        if isinstance(minimum, int) and len(value) < minimum:
            raise AutomaticWeeklyReflectionError(code)
        if isinstance(maximum, int) and len(value) > maximum:
            raise AutomaticWeeklyReflectionError(code)
        item_schema = schema.get("items")
        if isinstance(item_schema, Mapping):
            for item in value:
                _validate_schema_value(item, item_schema, code=code)

    if isinstance(value, Mapping):
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise AutomaticWeeklyReflectionError(code)
        required = schema.get("required", [])
        if isinstance(required, list) and any(
            key not in value for key in required
        ):
            raise AutomaticWeeklyReflectionError(code)
        if schema.get("additionalProperties") is False and (
            set(value) - set(properties)
        ):
            raise AutomaticWeeklyReflectionError(code)
        for key, item in value.items():
            definition = properties.get(key)
            if isinstance(definition, Mapping):
                _validate_schema_value(item, definition, code=code)


def _strict_weekly_schema() -> dict[str, Any]:
    schema = copy.deepcopy(dict(load_weekly_review_generator_schema()))
    string_fields = {
        "period": ("start_date", "end_date", "generated_at", "source"),
        "core_idea": (
            "idea",
            "why_it_matters",
            "refined_understanding",
        ),
        "mindset_shift": ("before", "now"),
        "ideas_worth_compounding": (
            "idea",
            "why_it_matters",
            "application",
            "source_reference",
        ),
        "expressions_worth_reusing": (
            "expression",
            "contextual_meaning",
            "reusable_example",
            "communication_function",
        ),
        "next_week_application": (
            "scenario",
            "behavior",
            "phrase_to_use",
            "completion_condition",
        ),
        "sources": ("page_id", "title", "url"),
    }
    properties = schema["properties"]
    for name, fields in string_fields.items():
        prop = properties[name]
        target = prop
        if name in {"ideas_worth_compounding", "expressions_worth_reusing", "sources"}:
            target = prop["items"]
        elif name == "mindset_shift":
            target = prop["oneOf"][1]
        target["properties"] = {
            field: {"type": "string"} for field in fields
        }
    return _strict_schema(schema)


def _exact_keys(
    value: Mapping[str, Any],
    expected: Sequence[str],
    code: str,
) -> None:
    if set(value) != set(expected):
        raise AutomaticWeeklyReflectionError(code)


def validate_strict_reflection_artifact(
    payload: Mapping[str, Any],
    *,
    require_cross_content_patterns: bool = True,
) -> dict[str, Any]:
    _validate_schema_value(
        payload,
        _strict_schema(load_reflection_schema()),
        code="reflection_artifact_schema_invalid",
    )
    try:
        validated = _validate_reflection_payload(payload)
    except ReflectionGenerationError:
        raise AutomaticWeeklyReflectionError(
            "reflection_artifact_incomplete"
        ) from None
    _exact_keys(
        validated,
        (
            "weekly_theme",
            "mindset_shifts",
            "cross_content_patterns",
            "professional_actions",
        ),
        "reflection_artifact_extra_or_missing_fields",
    )
    theme = validated["weekly_theme"]
    _exact_keys(
        theme,
        ("category", "theme"),
        "reflection_artifact_extra_or_missing_fields",
    )
    if not str(theme["category"]).strip() or not str(theme["theme"]).strip():
        raise AutomaticWeeklyReflectionError(
            "reflection_artifact_incomplete"
        )
    for shift in validated["mindset_shifts"]:
        _exact_keys(
            shift,
            ("before", "after", "evidence", "confidence"),
            "reflection_artifact_extra_or_missing_fields",
        )
        if not shift["evidence"]:
            raise AutomaticWeeklyReflectionError(
                "reflection_artifact_incomplete"
            )
        for evidence in shift["evidence"]:
            _exact_keys(
                evidence,
                ("source", "supporting_concept"),
                "reflection_artifact_extra_or_missing_fields",
            )
            if (
                not str(evidence["source"]).strip()
                or not str(evidence["supporting_concept"]).strip()
            ):
                raise AutomaticWeeklyReflectionError(
                    "reflection_artifact_incomplete"
                )
        if not shift["before"].strip() or not shift["after"].strip():
            raise AutomaticWeeklyReflectionError(
                "reflection_artifact_incomplete"
            )
        if shift["confidence"] < 0 or shift["confidence"] > 1:
            raise AutomaticWeeklyReflectionError(
                "reflection_artifact_incomplete"
            )
    if (
        require_cross_content_patterns
        and not validated["cross_content_patterns"]
    ):
        raise AutomaticWeeklyReflectionError(
            "reflection_artifact_incomplete"
        )
    if not validated["professional_actions"]:
        raise AutomaticWeeklyReflectionError(
            "reflection_artifact_incomplete"
        )
    if any(
        not isinstance(item, str) or not item.strip()
        for item in (
            list(validated["cross_content_patterns"])
            + list(validated["professional_actions"])
        )
    ):
        raise AutomaticWeeklyReflectionError(
            "reflection_artifact_incomplete"
        )
    return validated


def validate_strict_weekly_artifact(
    payload: Mapping[str, Any],
    weekly_context: Mapping[str, Any],
) -> dict[str, Any]:
    _validate_schema_value(
        payload,
        _strict_weekly_schema(),
        code="weekly_artifact_schema_invalid",
    )
    validated = _validate_output(payload)
    root_fields = (
        "period",
        "core_idea",
        "mindset_shift",
        "ideas_worth_compounding",
        "expressions_worth_reusing",
        "language_thinking_connection",
        "next_week_application",
        "sources",
    )
    _exact_keys(
        validated,
        root_fields,
        "weekly_artifact_extra_or_missing_fields",
    )
    object_fields = {
        "period": ("start_date", "end_date", "generated_at", "source"),
        "core_idea": (
            "idea",
            "why_it_matters",
            "refined_understanding",
        ),
        "next_week_application": (
            "scenario",
            "behavior",
            "phrase_to_use",
            "completion_condition",
        ),
    }
    for name, fields in object_fields.items():
        _exact_keys(
            validated[name],
            fields,
            "weekly_artifact_extra_or_missing_fields",
        )
    if validated["mindset_shift"] is not None:
        _exact_keys(
            validated["mindset_shift"],
            ("before", "now"),
            "weekly_artifact_extra_or_missing_fields",
        )
    for item in validated["ideas_worth_compounding"]:
        _exact_keys(
            item,
            ("idea", "why_it_matters", "application", "source_reference"),
            "weekly_artifact_extra_or_missing_fields",
        )
    for item in validated["expressions_worth_reusing"]:
        _exact_keys(
            item,
            (
                "expression",
                "contextual_meaning",
                "reusable_example",
                "communication_function",
            ),
            "weekly_artifact_extra_or_missing_fields",
        )
    for item in validated["sources"]:
        _exact_keys(
            item,
            ("page_id", "title", "url"),
            "weekly_artifact_extra_or_missing_fields",
        )

    required_objects = {
        "period": (
            "start_date",
            "end_date",
            "generated_at",
            "source",
        ),
        "core_idea": (
            "idea",
            "why_it_matters",
            "refined_understanding",
        ),
        "next_week_application": (
            "scenario",
            "behavior",
            "phrase_to_use",
            "completion_condition",
        ),
    }
    for object_name, fields in required_objects.items():
        if any(
            not str(validated[object_name][field]).strip()
            for field in fields
        ):
            raise AutomaticWeeklyReflectionError(
                "weekly_artifact_incomplete"
            )
    if validated["mindset_shift"] is not None and any(
        not str(validated["mindset_shift"][field]).strip()
        for field in ("before", "now")
    ):
        raise AutomaticWeeklyReflectionError(
            "weekly_artifact_incomplete"
        )
    for item in validated["ideas_worth_compounding"]:
        if any(
            not str(item[field]).strip()
            for field in (
                "idea",
                "why_it_matters",
                "application",
                "source_reference",
            )
        ):
            raise AutomaticWeeklyReflectionError(
                "weekly_artifact_incomplete"
            )
    for item in validated["expressions_worth_reusing"]:
        if any(
            not str(item[field]).strip()
            for field in (
                "expression",
                "contextual_meaning",
                "reusable_example",
                "communication_function",
            )
        ):
            raise AutomaticWeeklyReflectionError(
                "weekly_artifact_incomplete"
            )
    if not validated["language_thinking_connection"].strip():
        raise AutomaticWeeklyReflectionError(
            "weekly_artifact_incomplete"
        )
    if not validated["sources"] or any(
        not str(item["page_id"]).strip()
        or not str(item["title"]).strip()
        for item in validated["sources"]
    ):
        raise AutomaticWeeklyReflectionError(
            "weekly_artifact_incomplete"
        )

    metadata = weekly_context.get("metadata", {})
    expected_period = {
        "start_date": str(metadata.get("period_start", "")),
        "end_date": str(metadata.get("period_end", "")),
        "generated_at": str(metadata.get("generated_at", "")),
        "source": str(metadata.get("source", "")),
    }
    if dict(validated["period"]) != expected_period:
        raise AutomaticWeeklyReflectionError(
            "weekly_artifact_period_mismatch"
        )
    expected_sources = {
        str(item.get("page_id", "")).strip()
        for item in weekly_context.get("podcasts", [])
        if isinstance(item, Mapping)
        and str(item.get("page_id", "")).strip()
    }
    artifact_sources = {
        str(item.get("page_id", "")).strip()
        for item in validated["sources"]
        if isinstance(item, Mapping)
        and str(item.get("page_id", "")).strip()
    }
    if artifact_sources != expected_sources:
        raise AutomaticWeeklyReflectionError(
            "weekly_artifact_source_mismatch"
        )
    return validated


class AutomaticCodexReflectionProvider:
    def __init__(
        self,
        *,
        request_path: Path,
        output_path: Path,
        executable: Optional[Path] = None,
        timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
        env: Optional[Mapping[str, str]] = None,
        runner: Runner = subprocess.run,
        generator: CodexGenerator = generate_codex_json_artifact,
    ) -> None:
        self.request_path = request_path
        self.output_path = output_path
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.env = env
        self.runner = runner
        self.generator = generator
        self.calls = 0

    def generate(
        self,
        prompt: str,
        context: dict[str, object],
    ) -> dict[str, object]:
        weekly_context = context.get("weekly_learning_context", {})
        if not isinstance(weekly_context, Mapping):
            raise AutomaticWeeklyReflectionError(
                "weekly_learning_context_invalid"
            )
        podcast_count = sum(
            1
            for item in weekly_context.get("podcasts", [])
            if isinstance(item, Mapping)
        )

        def validate_artifact(
            payload: Mapping[str, Any],
        ) -> dict[str, Any]:
            return validate_strict_reflection_artifact(
                payload,
                require_cross_content_patterns=podcast_count > 1,
            )

        schema = _strict_schema(load_reflection_schema())
        prepare_codex_request(
            stage="automatic_weekly_reflection_analysis",
            instructions=prompt,
            input_payload={"weekly_learning_context": dict(weekly_context)},
            schema=schema,
            request_path=self.request_path,
            output_path=self.output_path,
        )
        os.chmod(self.request_path, 0o600)
        try:
            existing = load_codex_artifact(
                request_path=self.request_path,
                output_path=self.output_path,
                stage="automatic weekly reflection analysis",
            )
            return validate_artifact(existing)
        except (CodexArtifactPendingError, OSError):
            pass
        self.calls += 1
        generated = self.generator(
            request_path=self.request_path,
            output_path=self.output_path,
            schema=schema,
            prompt=(
                f"{prompt}\n"
                f"Request contract: {self.request_path.resolve()}\n"
                "Untrusted weekly learning context follows as JSON:\n"
                f"{json.dumps(dict(weekly_context), ensure_ascii=False)}"
            ),
            executable=self.executable,
            timeout_seconds=self.timeout_seconds,
            env=self.env,
            runner=self.runner,
            validator=validate_artifact,
            stage="automatic weekly reflection analysis",
        )
        return validate_artifact(generated)


class AutomaticCodexWeeklyReviewProvider:
    def __init__(
        self,
        *,
        request_path: Path,
        output_path: Path,
        executable: Optional[Path] = None,
        timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
        env: Optional[Mapping[str, str]] = None,
        runner: Runner = subprocess.run,
        generator: CodexGenerator = generate_codex_json_artifact,
    ) -> None:
        self.request_path = request_path
        self.output_path = output_path
        self.executable = executable
        self.timeout_seconds = timeout_seconds
        self.env = env
        self.runner = runner
        self.generator = generator
        self.calls = 0

    def generate(
        self,
        prompt: str,
        context: dict[str, object],
    ) -> dict[str, object]:
        weekly_context = context.get("weekly_learning_context", {})
        reflection_context = context.get("reflection_context", {})
        if not isinstance(weekly_context, Mapping) or not isinstance(
            reflection_context,
            Mapping,
        ):
            raise AutomaticWeeklyReflectionError(
                "weekly_generation_context_invalid"
            )
        schema = _strict_weekly_schema()
        input_payload = {
            "reflection_context": dict(reflection_context),
            "weekly_learning_context": dict(weekly_context),
        }
        prepare_codex_request(
            stage="automatic_weekly_review_generation",
            instructions=prompt,
            input_payload=input_payload,
            schema=schema,
            request_path=self.request_path,
            output_path=self.output_path,
        )
        os.chmod(self.request_path, 0o600)
        validator = lambda payload: validate_strict_weekly_artifact(
            payload,
            weekly_context,
        )
        try:
            existing = load_codex_artifact(
                request_path=self.request_path,
                output_path=self.output_path,
                stage="automatic weekly review generation",
            )
            return validator(existing)
        except (CodexArtifactPendingError, OSError):
            pass
        self.calls += 1
        generated = self.generator(
            request_path=self.request_path,
            output_path=self.output_path,
            schema=schema,
            prompt=(
                f"{prompt}\n"
                f"Request contract: {self.request_path.resolve()}\n"
                "Untrusted reflection and learning context follows as JSON:\n"
                f"{json.dumps(input_payload, ensure_ascii=False)}"
            ),
            executable=self.executable,
            timeout_seconds=self.timeout_seconds,
            env=self.env,
            runner=self.runner,
            validator=validator,
            stage="automatic weekly review generation",
        )
        return validator(generated)


def _learning_data_counts(context: Mapping[str, Any]) -> tuple[int, int]:
    validated = validate_weekly_learning_context(context)
    podcast_count = len(validated.get("podcasts", []))
    learning_assets = sum(
        len(validated.get(name, []))
        for name in (
            "learning_expressions",
            "ai_highlights",
            "user_vocabulary",
        )
    )
    return podcast_count, learning_assets


def _source_page_ids(context: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                str(item.get("page_id", "")).strip()
                for item in context.get("podcasts", [])
                if isinstance(item, Mapping)
                and str(item.get("page_id", "")).strip()
            }
        )
    )


def _page_date(page: Mapping[str, Any]) -> tuple[str, str]:
    properties = page.get("properties", {})
    prop = properties.get("Date", {}) if isinstance(properties, Mapping) else {}
    value = prop.get("date", {}) if isinstance(prop, Mapping) else {}
    if not isinstance(value, Mapping):
        return "", ""
    return str(value.get("start", "") or ""), str(value.get("end", "") or "")


def _page_relations(page: Mapping[str, Any]) -> set[str]:
    properties = page.get("properties", {})
    if not isinstance(properties, Mapping):
        return set()
    for name in ("Podcasts", "Source Podcasts"):
        prop = properties.get(name, {})
        relation = prop.get("relation", []) if isinstance(prop, Mapping) else []
        if isinstance(relation, list):
            values = {
                str(item.get("id", "")).strip()
                for item in relation
                if isinstance(item, Mapping)
                and str(item.get("id", "")).strip()
            }
            if values:
                return values
    return set()


def _plain_text(items: object) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(
        str(
            item.get("plain_text")
            or (
                item.get("text", {}).get("content", "")
                if isinstance(item.get("text"), Mapping)
                else ""
            )
        )
        for item in items
        if isinstance(item, Mapping)
    )


def _block_text(block: Mapping[str, Any]) -> str:
    block_type = str(block.get("type", ""))
    payload = block.get(block_type, {})
    if not isinstance(payload, Mapping):
        return ""
    return _plain_text(payload.get("rich_text")).strip()


def _list_page_blocks(notion: Any, page_id: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    cursor: Optional[str] = None
    visited: set[str] = set()
    while True:
        kwargs: dict[str, Any] = {
            "block_id": page_id,
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            response = notion.blocks.children.list(**kwargs)
        except Exception:
            raise RetryableAutomaticWeeklyReflectionError(
                "weekly_body_read_failed"
            ) from None
        results = response.get("results", [])
        if not isinstance(results, list):
            raise RetryableAutomaticWeeklyReflectionError(
                "weekly_body_read_failed"
            )
        for block in results:
            if not isinstance(block, Mapping):
                raise RetryableAutomaticWeeklyReflectionError(
                    "weekly_body_read_failed"
                )
            blocks.append(dict(block))
        cursor = next_notion_cursor(
            response,
            current_cursor=cursor,
            visited_cursors=visited,
        )
        if cursor is None:
            return blocks


def _canonical_actual_block(
    notion: Any,
    block: Mapping[str, Any],
    *,
    visited: set[str],
    depth: int,
) -> dict[str, Any]:
    if depth > 16:
        raise AutomaticWeeklyReflectionError(
            "weekly_body_read_failed"
        )
    canonical = _canonical_block(
        block,
        [] if bool(block.get("has_children", False)) else (
            _embedded_block_children(block)
        ),
    )
    block_id = str(block.get("id", "")).strip()
    if bool(block.get("has_children", False)):
        if not block_id or block_id in visited:
            raise AutomaticWeeklyReflectionError(
                "weekly_body_read_failed"
            )
        visited.add(block_id)
        children = _list_page_blocks(notion, block_id)
        canonical["children"] = [
            _canonical_actual_block(
                notion,
                child,
                visited=visited,
                depth=depth + 1,
            )
            for child in children
        ]
    return canonical


def _actual_weekly_body_fingerprint(
    notion: Any,
    page_id: str,
) -> str:
    canonical = [
        _canonical_actual_block(
            notion,
            block,
            visited=set(),
            depth=0,
        )
        for block in _list_page_blocks(notion, page_id)
    ]
    return _canonical_tree_fingerprint(canonical)


def verify_weekly_page_integrity(notion: Any, page_id: str) -> None:
    blocks = _list_page_blocks(notion, page_id)
    toc_indexes = [
        index
        for index, block in enumerate(blocks)
        if block.get("type") == "table_of_contents"
    ]
    required_headings = {
        "1. This Week's Core Idea",
        "3. Ideas Worth Compounding",
        "4. Expressions Worth Reusing",
        "5. Language-Thinking Connection",
        "6. One Application for Next Week",
        "7. Sources",
    }
    headings = [
        _block_text(block)
        for block in blocks
        if block.get("type") in {"heading_1", "heading_2"}
    ]
    if (
        toc_indexes != [0]
        or not required_headings.issubset(set(headings))
        or any(headings.count(item) != 1 for item in required_headings)
    ):
        raise AutomaticWeeklyReflectionError(
            "weekly_existing_page_incomplete"
        )


def inspect_weekly_identity(
    notion: Any,
    weekly_data_source_id: str,
    *,
    start_date: str,
    end_date: str,
    source_page_ids: Sequence[str],
    expected_body_fingerprint: str = "",
) -> WeeklyIdentityInspection:
    cursor: Optional[str] = None
    visited: set[str] = set()
    same_period_count = 0
    exact_pages: list[str] = []
    generated_pages = 0
    while True:
        kwargs: dict[str, Any] = {
            "data_source_id": weekly_data_source_id,
            "filter": {
                "property": "Date",
                "date": {"equals": start_date},
            },
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            response = notion.data_sources.query(**kwargs)
        except Exception:
            raise RetryableAutomaticWeeklyReflectionError(
                "weekly_identity_query_failed"
            ) from None
        results = response.get("results", [])
        if not isinstance(results, list):
            raise AutomaticWeeklyReflectionError(
                "weekly_identity_query_invalid"
            )
        for page in results:
            if not isinstance(page, Mapping):
                raise AutomaticWeeklyReflectionError(
                    "weekly_identity_query_invalid"
                )
            page_start, page_end = _page_date(page)
            if page_start != start_date:
                continue
            if page_end and page_end != end_date:
                continue
            same_period_count += 1
            if set(source_page_ids) != _page_relations(page):
                continue
            page_id = str(page.get("id", "")).strip()
            if not page_id:
                raise AutomaticWeeklyReflectionError(
                    "weekly_identity_query_invalid"
                )
            exact_pages.append(page_id)
            if (
                expected_body_fingerprint
                and _actual_weekly_body_fingerprint(
                    notion,
                    page_id,
                )
                == expected_body_fingerprint
            ):
                generated_pages += 1
        cursor = next_notion_cursor(
            response,
            current_cursor=cursor,
            visited_cursors=visited,
        )
        if cursor is None:
            return WeeklyIdentityInspection(
                same_period_count=same_period_count,
                exact_identity_count=len(exact_pages),
                generated_identity_count=generated_pages,
                exact_page_id=(
                    exact_pages[0] if len(exact_pages) == 1 else ""
                ),
            )


def count_existing_weekly_identity(
    notion: Any,
    weekly_data_source_id: str,
    *,
    start_date: str,
    end_date: str,
    source_page_ids: Sequence[str],
) -> int:
    """Compatibility helper returning only the exact identity count."""
    return inspect_weekly_identity(
        notion,
        weekly_data_source_id,
        start_date=start_date,
        end_date=end_date,
        source_page_ids=source_page_ids,
    ).exact_identity_count


def _coerce_identity_inspection(
    value: object,
) -> WeeklyIdentityInspection:
    if isinstance(value, WeeklyIdentityInspection):
        return value
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return WeeklyIdentityInspection(
            same_period_count=value,
            exact_identity_count=value,
            generated_identity_count=value,
        )
    raise AutomaticWeeklyReflectionError(
        "weekly_identity_query_invalid"
    )


def _remove_unattended_pipeline_logs(path: Path) -> None:
    try:
        if path.exists():
            shutil.rmtree(path)
    except OSError:
        raise AutomaticWeeklyReflectionError(
            "weekly_pipeline_log_cleanup_failed"
        ) from None


def _empty_report(
    schedule: WeeklyReflectionSchedule,
    *,
    status: str,
    period: str = "",
    process_lock_acquired: bool = False,
    last_success_period: str = "",
    error_code: str = "",
) -> AutomaticWeeklyReflectionReport:
    return AutomaticWeeklyReflectionReport(
        status=status,
        enabled=schedule.enabled,
        weekday=schedule.weekday,
        hour=schedule.hour,
        minute=schedule.minute,
        timezone_mode=schedule.timezone_mode,
        period=period,
        target_binding_valid=False,
        podcasts=0,
        learning_assets=0,
        reflection_codex_calls=0,
        weekly_review_codex_calls=0,
        quality_score=0,
        weekly_created=0,
        weekly_updated=0,
        podcast_writes=0,
        expression_writes=0,
        vocabulary_writes=0,
        schema_writes=0,
        deletes_or_archives=0,
        historical_group_reads=0,
        historical_group_writes=0,
        process_lock_acquired=process_lock_acquired,
        last_success_period=last_success_period,
        error_code=error_code,
    )


def _error_code(exc: BaseException) -> str:
    current: Optional[BaseException] = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        code = getattr(current, "code", "")
        if isinstance(code, str) and code:
            return code
        current = current.__cause__ or current.__context__
    if isinstance(exc, WeeklyReflectionPipelineError):
        return "weekly_pipeline_failed"
    if isinstance(exc, WeeklyLearningContextValidationError):
        return "weekly_learning_context_invalid"
    return "automatic_weekly_reflection_failed"


def _persist_report(
    report: AutomaticWeeklyReflectionReport,
    *,
    runtime_status_path: Optional[Path],
    log_path: Optional[Path],
) -> AutomaticWeeklyReflectionReport:
    try:
        if runtime_status_path is not None:
            _save_runtime_status(report, runtime_status_path)
        if log_path is not None:
            append_redacted_runtime_log(report, log_path)
    except Exception:
        return AutomaticWeeklyReflectionReport(
            **{
                **report.to_dict(),
                "status": "SAFE_STOP",
                "error_code": "weekly_runtime_log_write_failed",
            }
        )
    return report


def run_bounded_automatic_weekly_reflection(
    *,
    now: Optional[datetime] = None,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
    state_path: Optional[Path] = None,
    artifact_root: Path = DEFAULT_ARTIFACT_DIRECTORY,
    lock_path: Optional[Path] = None,
    runtime_status_path: Optional[Path] = DEFAULT_RUNTIME_STATUS_PATH,
    log_path: Optional[Path] = DEFAULT_RUNTIME_LOG_PATH,
    notion: Any = None,
    config: Optional[NotionConfig] = None,
    config_loader: Callable[[], NotionConfig] = load_notion_config,
    notion_factory: Callable[[str], Any] = create_notion_client,
    binding_validator: Callable[..., Any] = validate_notion_target_binding,
    context_extractor: Callable[..., Any] = run_weekly_learning_extraction,
    pipeline_runner: Callable[..., Any] = run_weekly_reflection_pipeline,
    identity_counter: Callable[..., object] = inspect_weekly_identity,
    codex_executable: Optional[Path] = None,
    codex_timeout_seconds: int = DEFAULT_CODEX_TIMEOUT_SECONDS,
    codex_env: Optional[Mapping[str, str]] = None,
    codex_runner: Runner = subprocess.run,
    codex_generator: CodexGenerator = generate_codex_json_artifact,
) -> AutomaticWeeklyReflectionReport:
    """Run at most one due Weekly Reflection period and exit."""
    try:
        schedule = load_schedule(schedule_path)
    except WeeklyReflectionSchedulerError as exc:
        schedule = WeeklyReflectionSchedule()
        return _persist_report(
            _empty_report(
                schedule,
                status="SAFE_STOP",
                error_code=exc.code,
            ),
            runtime_status_path=runtime_status_path,
            log_path=log_path,
        )
    if not schedule.enabled:
        return _persist_report(
            _empty_report(schedule, status="PAUSED"),
            runtime_status_path=runtime_status_path,
            log_path=log_path,
        )

    cycle_now = now or datetime.now().astimezone()
    due = scheduled_period_if_due(cycle_now, schedule)
    if due is None:
        return _persist_report(
            _empty_report(schedule, status="NOT_DUE"),
            runtime_status_path=runtime_status_path,
            log_path=log_path,
        )

    try:
        active_config = config or config_loader()
        namespace = target_namespace(active_config)
        resolved_state_path = state_path or default_state_path(
            namespace.target_group_fingerprint
        )
        resolved_lock_path = lock_path or default_process_lock_path(
            namespace.target_group_fingerprint
        )
        state = _state_for_group(
            resolved_state_path,
            namespace.target_group_fingerprint,
        )
    except Exception as exc:
        return _persist_report(
            _empty_report(
                schedule,
                status="SAFE_STOP",
                period=due.key,
                error_code=_error_code(exc),
            ),
            runtime_status_path=runtime_status_path,
            log_path=log_path,
        )

    last_success = str(state.get("last_success_period", ""))
    if due.key in state.get("completed_periods", {}):
        return _persist_report(
            _empty_report(
                schedule,
                status="ALREADY_COMPLETED",
                period=due.key,
                last_success_period=last_success,
            ),
            runtime_status_path=runtime_status_path,
            log_path=log_path,
        )

    reflection_provider: Optional[AutomaticCodexReflectionProvider] = None
    weekly_provider: Optional[AutomaticCodexWeeklyReviewProvider] = None
    guarded_notion: Optional[_WeeklyOnlyNotionProxy] = None
    podcasts = 0
    learning_assets = 0
    quality_score = 0
    pipeline_logs_path: Optional[Path] = None
    try:
        with automatic_weekly_process_lock(resolved_lock_path):
            active_notion = notion or notion_factory(active_config.token)
            binding = binding_validator(active_notion, active_config)
            if not getattr(binding, "valid", False):
                raise AutomaticWeeklyReflectionError(
                    "target_binding_invalid"
                )
            paths = _artifact_paths(
                artifact_root,
                namespace.target_group_fingerprint,
                due.key,
            )
            generated_at = due.scheduled_at.astimezone(
                timezone.utc
            ).isoformat()
            context, extraction_report, _saved_path = context_extractor(
                notion=active_notion,
                output_path=paths["weekly_context"],
                today=due.extraction_date,
                generated_at=generated_at,
            )
            os.chmod(paths["weekly_context"], 0o600)
            if int(getattr(extraction_report, "failures", 0) or 0) > 0:
                raise RetryableAutomaticWeeklyReflectionError(
                    "weekly_learning_extraction_incomplete"
                )
            podcasts, learning_assets = _learning_data_counts(context)
            if podcasts == 0 or learning_assets == 0:
                report = _empty_report(
                    schedule,
                    status="SKIPPED_INSUFFICIENT_DATA",
                    period=due.key,
                    process_lock_acquired=True,
                    last_success_period=last_success,
                )
                report = AutomaticWeeklyReflectionReport(
                    **{
                        **report.to_dict(),
                        "target_binding_valid": True,
                        "podcasts": podcasts,
                        "learning_assets": learning_assets,
                    }
                )
                return _persist_report(
                    report,
                    runtime_status_path=runtime_status_path,
                    log_path=log_path,
                )

            metadata = context["metadata"]
            source_ids = _source_page_ids(context)
            expected_body_fingerprint = (
                _matching_publish_intent_body_fingerprint(
                    state,
                    due.key,
                    paths,
                )
            )
            existing = _coerce_identity_inspection(
                identity_counter(
                    active_notion,
                    active_config.weekly_database_id,
                    start_date=str(metadata["period_start"]),
                    end_date=str(metadata["period_end"]),
                    source_page_ids=source_ids,
                    expected_body_fingerprint=(
                        expected_body_fingerprint
                    ),
                )
            )
            if (
                existing.same_period_count > 1
                or existing.exact_identity_count > 1
            ):
                raise AutomaticWeeklyReflectionError(
                    "weekly_identity_not_unique"
                )
            if (
                existing.same_period_count == 1
                and existing.exact_identity_count == 0
            ):
                raise AutomaticWeeklyReflectionError(
                    "weekly_identity_conflict"
                )
            if existing.exact_identity_count == 1:
                if (
                    not expected_body_fingerprint
                    or existing.generated_identity_count != 1
                ):
                    raise AutomaticWeeklyReflectionError(
                        "weekly_existing_page_unmanaged"
                    )
                if existing.exact_page_id:
                    verify_weekly_page_integrity(
                        active_notion,
                        existing.exact_page_id,
                    )
                completed = dict(state.get("completed_periods", {}))
                completed[due.key] = {
                    "completed_at": cycle_now.astimezone(
                        timezone.utc
                    ).isoformat(),
                    "reconciled": True,
                }
                _clear_publish_intent(state, due.key)
                state.update(
                    {
                        "last_run_status": "ALREADY_COMPLETED",
                        "last_success_period": due.key,
                        "completed_periods": completed,
                    }
                )
                _atomic_json_write(resolved_state_path, state)
                report = _empty_report(
                    schedule,
                    status="ALREADY_COMPLETED",
                    period=due.key,
                    process_lock_acquired=True,
                    last_success_period=due.key,
                )
                report = AutomaticWeeklyReflectionReport(
                    **{
                        **report.to_dict(),
                        "target_binding_valid": True,
                        "podcasts": podcasts,
                        "learning_assets": learning_assets,
                    }
                )
                return _persist_report(
                    report,
                    runtime_status_path=runtime_status_path,
                    log_path=log_path,
                )

            reflection_provider = AutomaticCodexReflectionProvider(
                request_path=paths["reflection_request"],
                output_path=paths["reflection_output"],
                executable=codex_executable,
                timeout_seconds=codex_timeout_seconds,
                env=codex_env,
                runner=codex_runner,
                generator=codex_generator,
            )
            weekly_provider = AutomaticCodexWeeklyReviewProvider(
                request_path=paths["weekly_request"],
                output_path=paths["weekly_codex_output"],
                executable=codex_executable,
                timeout_seconds=codex_timeout_seconds,
                env=codex_env,
                runner=codex_runner,
                generator=codex_generator,
            )
            pipeline_logs_path = paths["logs"]
            guarded_notion = _WeeklyOnlyNotionProxy(
                active_notion,
                active_config.weekly_database_id,
            )
            pipeline_kwargs = {
                "weekly_learning_context_path": paths["weekly_context"],
                "weekly_review_output_path": paths["weekly_output"],
                "reflection_context_output_path": paths["reflection_output"],
                "notion": guarded_notion,
                "weekly_reflection_database_id": (
                    active_config.weekly_database_id
                ),
                "podcast_database_id": active_config.podcast_database_id,
                "pipeline_run_output_path": paths["pipeline_run"],
                "logs_dir": paths["logs"],
                "reflection_provider": reflection_provider,
                "weekly_review_provider": weekly_provider,
            }
            preview_result = pipeline_runner(
                **pipeline_kwargs,
                dry_run=True,
            )
            preview_quality = check_weekly_review_quality(
                preview_result.weekly_review
            )
            quality_score = preview_quality.score
            if (
                not preview_quality.passed
                or quality_score < PRODUCTION_QUALITY_THRESHOLD
            ):
                raise AutomaticWeeklyReflectionError(
                    "weekly_quality_gate_failed"
                )
            _record_publish_intent(
                state,
                due.key,
                paths,
                started_at=cycle_now.astimezone(
                    timezone.utc
                ).isoformat(),
            )
            _atomic_json_write(resolved_state_path, state)
            expected_body_fingerprint = (
                _matching_publish_intent_body_fingerprint(
                    state,
                    due.key,
                    paths,
                )
            )
            if not expected_body_fingerprint:
                raise AutomaticWeeklyReflectionError(
                    "weekly_publish_intent_invalid"
                )
            pipeline_result = pipeline_runner(
                **pipeline_kwargs,
                dry_run=False,
            )
            quality = check_weekly_review_quality(
                pipeline_result.weekly_review
            )
            quality_score = quality.score
            if (
                not quality.passed
                or quality_score < PRODUCTION_QUALITY_THRESHOLD
            ):
                raise AutomaticWeeklyReflectionError(
                    "weekly_quality_gate_failed"
                )
            verified = _coerce_identity_inspection(
                identity_counter(
                    active_notion,
                    active_config.weekly_database_id,
                    start_date=str(metadata["period_start"]),
                    end_date=str(metadata["period_end"]),
                    source_page_ids=source_ids,
                    expected_body_fingerprint=(
                        expected_body_fingerprint
                    ),
                )
            )
            if (
                verified.same_period_count != 1
                or verified.exact_identity_count != 1
                or verified.generated_identity_count != 1
            ):
                raise AutomaticWeeklyReflectionError(
                    "weekly_publish_reconciliation_failed"
                )
            if verified.exact_page_id:
                verify_weekly_page_integrity(
                    active_notion,
                    verified.exact_page_id,
                )
            completed = dict(state.get("completed_periods", {}))
            completed[due.key] = {
                "completed_at": cycle_now.astimezone(
                    timezone.utc
                ).isoformat(),
                "reconciled": False,
            }
            _clear_publish_intent(state, due.key)
            state.update(
                {
                    "last_run_status": "PASS",
                    "last_success_period": due.key,
                    "completed_periods": completed,
                }
            )
            _atomic_json_write(resolved_state_path, state)
            report = AutomaticWeeklyReflectionReport(
                status="PASS",
                enabled=True,
                weekday=schedule.weekday,
                hour=schedule.hour,
                minute=schedule.minute,
                timezone_mode=schedule.timezone_mode,
                period=due.key,
                target_binding_valid=True,
                podcasts=podcasts,
                learning_assets=learning_assets,
                reflection_codex_calls=reflection_provider.calls,
                weekly_review_codex_calls=weekly_provider.calls,
                quality_score=quality_score,
                weekly_created=guarded_notion.pages.create_count,
                weekly_updated=0,
                podcast_writes=0,
                expression_writes=0,
                vocabulary_writes=0,
                schema_writes=0,
                deletes_or_archives=0,
                historical_group_reads=0,
                historical_group_writes=0,
                process_lock_acquired=True,
                last_success_period=due.key,
            )
    except AutomaticWeeklyReflectionBusy as exc:
        report = _empty_report(
            schedule,
            status="OVERLAP_SKIPPED",
            period=due.key,
            error_code=exc.code,
            last_success_period=last_success,
        )
    except (
        AutomaticWeeklyReflectionError,
        CodexRuntimeError,
        NotionTargetBindingError,
    ) as exc:
        if pipeline_logs_path is not None:
            _remove_unattended_pipeline_logs(pipeline_logs_path)
        report = _empty_report(
            schedule,
            status=(
                "RETRYABLE_FAILURE"
                if isinstance(
                    exc,
                    (
                        CodexRuntimeError,
                        RetryableAutomaticWeeklyReflectionError,
                    ),
                )
                else "SAFE_STOP"
            ),
            period=due.key,
            process_lock_acquired=True,
            last_success_period=last_success,
            error_code=_error_code(exc),
        )
        report = AutomaticWeeklyReflectionReport(
            **{
                **report.to_dict(),
                "podcasts": podcasts,
                "learning_assets": learning_assets,
                "reflection_codex_calls": (
                    reflection_provider.calls
                    if reflection_provider is not None
                    else 0
                ),
                "weekly_review_codex_calls": (
                    weekly_provider.calls
                    if weekly_provider is not None
                    else 0
                ),
                "quality_score": quality_score,
                "weekly_created": (
                    guarded_notion.pages.create_count
                    if guarded_notion is not None
                    else 0
                ),
            }
        )
    except WeeklyReflectionPipelineError as exc:
        if pipeline_logs_path is not None:
            _remove_unattended_pipeline_logs(pipeline_logs_path)
        report = _empty_report(
            schedule,
            status="RETRYABLE_FAILURE",
            period=due.key,
            process_lock_acquired=True,
            last_success_period=last_success,
            error_code=_error_code(exc),
        )
        report = AutomaticWeeklyReflectionReport(
            **{
                **report.to_dict(),
                "podcasts": podcasts,
                "learning_assets": learning_assets,
                "reflection_codex_calls": (
                    reflection_provider.calls
                    if reflection_provider is not None
                    else 0
                ),
                "weekly_review_codex_calls": (
                    weekly_provider.calls
                    if weekly_provider is not None
                    else 0
                ),
                "weekly_created": (
                    guarded_notion.pages.create_count
                    if guarded_notion is not None
                    else 0
                ),
            }
        )
    except Exception as exc:
        if pipeline_logs_path is not None:
            _remove_unattended_pipeline_logs(pipeline_logs_path)
        report = _empty_report(
            schedule,
            status="SAFE_STOP",
            period=due.key,
            process_lock_acquired=True,
            last_success_period=last_success,
            error_code=_error_code(exc),
        )
        report = AutomaticWeeklyReflectionReport(
            **{
                **report.to_dict(),
                "podcasts": podcasts,
                "learning_assets": learning_assets,
                "reflection_codex_calls": (
                    reflection_provider.calls
                    if reflection_provider is not None
                    else 0
                ),
                "weekly_review_codex_calls": (
                    weekly_provider.calls
                    if weekly_provider is not None
                    else 0
                ),
                "quality_score": quality_score,
                "weekly_created": (
                    guarded_notion.pages.create_count
                    if guarded_notion is not None
                    else 0
                ),
            }
        )

    return _persist_report(
        report,
        runtime_status_path=runtime_status_path,
        log_path=log_path,
    )


__all__ = [
    "AutomaticCodexReflectionProvider",
    "AutomaticCodexWeeklyReviewProvider",
    "AutomaticWeeklyReflectionError",
    "AutomaticWeeklyReflectionReport",
    "PRODUCTION_QUALITY_THRESHOLD",
    "ScheduledPeriod",
    "append_redacted_runtime_log",
    "automatic_weekly_process_lock",
    "count_existing_weekly_identity",
    "default_process_lock_path",
    "default_state_path",
    "run_bounded_automatic_weekly_reflection",
    "scheduled_period_if_due",
    "validate_strict_reflection_artifact",
    "validate_strict_weekly_artifact",
]
