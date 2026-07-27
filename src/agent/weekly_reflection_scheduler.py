"""Safe local schedule and macOS LaunchAgent lifecycle for Weekly Reflection."""

from __future__ import annotations

import fcntl
import json
import os
import plistlib
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional


LAUNCH_AGENT_LABEL = "com.english-audio-learning-agent.weekly-reflection"
INSTALL_CONFIRMATION = "INSTALL_WEEKLY_REFLECTION_LAUNCH_AGENT"
CONFIGURE_CONFIRMATION = "CONFIGURE_WEEKLY_REFLECTION_LAUNCH_AGENT"
PAUSE_CONFIRMATION = "PAUSE_WEEKLY_REFLECTION_LAUNCH_AGENT"
RESUME_CONFIRMATION = "RESUME_WEEKLY_REFLECTION_LAUNCH_AGENT"
UNINSTALL_CONFIRMATION = "UNINSTALL_WEEKLY_REFLECTION_LAUNCH_AGENT"

DEFAULT_SCHEDULE_PATH = Path("data/weekly_reflection/schedule.json")
DEFAULT_RUNTIME_STATUS_PATH = Path(
    "data/weekly_reflection/runtime_status.json"
)
DEFAULT_MANAGEMENT_LOCK_PATH = Path(
    "data/weekly_reflection/scheduler.manager.lock"
)
SCHEDULE_SCHEMA_VERSION = 1
RECOVERY_INTERVAL_SECONDS = 15 * 60
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
CALENDAR_WEEKDAYS = {
    "sunday": 1,
    "monday": 2,
    "tuesday": 3,
    "wednesday": 4,
    "thursday": 5,
    "friday": 6,
    "saturday": 7,
}


class WeeklyReflectionSchedulerError(RuntimeError):
    """A stable scheduler/configuration failure without private values."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class WeeklyReflectionSchedule:
    enabled: bool = True
    weekday: str = "saturday"
    hour: int = 10
    minute: int = 0
    timezone_mode: str = "local"
    schema_version: int = SCHEDULE_SCHEMA_VERSION
    effective_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WeeklyReflectionSchedulerStatus:
    action: str
    installed: bool
    loaded: bool
    enabled: bool
    weekday: str
    hour: int
    minute: int
    timezone_mode: str
    last_run_status: str = ""
    last_success_period: str = ""
    next_due_summary: str = ""
    error_code: str = ""
    label: str = LAUNCH_AGENT_LABEL

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_integer(value: object, minimum: int, maximum: int, code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WeeklyReflectionSchedulerError(code)
    if value < minimum or value > maximum:
        raise WeeklyReflectionSchedulerError(code)
    return value


def validate_schedule(
    payload: Mapping[str, Any] | WeeklyReflectionSchedule,
) -> WeeklyReflectionSchedule:
    raw = payload.to_dict() if isinstance(payload, WeeklyReflectionSchedule) else dict(payload)
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise WeeklyReflectionSchedulerError("weekly_schedule_enabled_invalid")
    weekday = str(raw.get("weekday", "")).strip().casefold()
    if weekday not in WEEKDAYS:
        raise WeeklyReflectionSchedulerError("weekly_schedule_weekday_invalid")
    hour = _validate_integer(
        raw.get("hour"),
        0,
        23,
        "weekly_schedule_hour_invalid",
    )
    minute = _validate_integer(
        raw.get("minute"),
        0,
        59,
        "weekly_schedule_minute_invalid",
    )
    timezone_mode = str(raw.get("timezone_mode", "")).strip().casefold()
    if timezone_mode != "local":
        raise WeeklyReflectionSchedulerError(
            "weekly_schedule_timezone_mode_invalid"
        )
    schema_version = _validate_integer(
        raw.get("schema_version", SCHEDULE_SCHEMA_VERSION),
        SCHEDULE_SCHEMA_VERSION,
        SCHEDULE_SCHEMA_VERSION,
        "weekly_schedule_schema_version_invalid",
    )
    effective_at = str(raw.get("effective_at", "")).strip()
    if effective_at:
        try:
            datetime.fromisoformat(effective_at.replace("Z", "+00:00"))
        except ValueError:
            raise WeeklyReflectionSchedulerError(
                "weekly_schedule_effective_at_invalid"
            ) from None
    return WeeklyReflectionSchedule(
        enabled=enabled,
        weekday=weekday,
        hour=hour,
        minute=minute,
        timezone_mode=timezone_mode,
        schema_version=schema_version,
        effective_at=effective_at,
    )


def default_schedule(
    *,
    effective_at: str = "",
) -> WeeklyReflectionSchedule:
    return WeeklyReflectionSchedule(
        effective_at=effective_at or _utc_now_text(),
    )


def configured_schedule(
    *,
    weekday: str,
    hour: int,
    minute: int,
    enabled: bool = True,
    effective_at: str = "",
) -> WeeklyReflectionSchedule:
    return validate_schedule(
        {
            "enabled": enabled,
            "weekday": weekday,
            "hour": hour,
            "minute": minute,
            "timezone_mode": "local",
            "schema_version": SCHEDULE_SCHEMA_VERSION,
            "effective_at": effective_at or _utc_now_text(),
        }
    )


def _private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)


@contextmanager
def scheduler_management_lock(
    path: Path = DEFAULT_MANAGEMENT_LOCK_PATH,
) -> Iterator[None]:
    """Prevent concurrent persistent scheduler mutations."""
    resolved = Path(path)
    _private_parent(resolved)
    descriptor = os.open(resolved, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        os.chmod(resolved, 0o600)
        try:
            fcntl.flock(
                descriptor,
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_management_overlap"
            ) from None
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def save_schedule(
    schedule: WeeklyReflectionSchedule,
    path: Path = DEFAULT_SCHEDULE_PATH,
) -> Path:
    validated = validate_schedule(schedule)
    resolved = Path(path)
    _private_parent(resolved)
    temporary: Optional[Path] = None
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{resolved.name}.",
            dir=str(resolved.parent),
            text=True,
        )
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                validated.to_dict(),
                handle,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, resolved)
        os.chmod(resolved, 0o600)
    except OSError as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise WeeklyReflectionSchedulerError(
            "weekly_schedule_write_failed"
        ) from exc
    return resolved


def load_schedule(
    path: Path = DEFAULT_SCHEDULE_PATH,
) -> WeeklyReflectionSchedule:
    resolved = Path(path)
    if not resolved.is_file():
        raise WeeklyReflectionSchedulerError("weekly_schedule_not_configured")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WeeklyReflectionSchedulerError(
            "weekly_schedule_read_failed"
        ) from exc
    if not isinstance(payload, Mapping):
        raise WeeklyReflectionSchedulerError("weekly_schedule_invalid")
    return validate_schedule(payload)


def default_launch_agents_directory() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def launch_agent_path(
    launch_agents_directory: Optional[Path] = None,
) -> Path:
    directory = (
        Path(launch_agents_directory)
        if launch_agents_directory is not None
        else default_launch_agents_directory()
    )
    return directory / f"{LAUNCH_AGENT_LABEL}.plist"


def _validate_project_root(project_root: Path) -> Path:
    root = Path(project_root).expanduser().resolve()
    protected = {"Documents", "Desktop", "Downloads"}
    if protected.intersection(root.parts):
        raise WeeklyReflectionSchedulerError(
            "weekly_scheduler_protected_project_root"
        )
    return root


def build_launch_agent_payload(
    *,
    project_root: Path,
    python_executable: Path,
    schedule: WeeklyReflectionSchedule,
) -> dict[str, Any]:
    validated = validate_schedule(schedule)
    root = _validate_project_root(project_root)
    python = Path(python_executable).expanduser().absolute()
    worker = root / "scripts" / "run_automatic_weekly_reflection_once.py"
    if not root.is_dir() or not python.is_file() or not worker.is_file():
        raise WeeklyReflectionSchedulerError(
            "weekly_scheduler_runtime_missing"
        )
    log_directory = root / "logs" / "weekly_reflection"
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(python), str(worker)],
        "WorkingDirectory": str(root),
        "StartCalendarInterval": {
            "Weekday": CALENDAR_WEEKDAYS[validated.weekday],
            "Hour": validated.hour,
            "Minute": validated.minute,
        },
        "StartInterval": RECOVERY_INTERVAL_SECONDS,
        "ProcessType": "Background",
        "StandardOutPath": str(log_directory / "launchd.stdout.log"),
        "StandardErrorPath": str(log_directory / "launchd.stderr.log"),
    }


def _launchctl(
    arguments: list[str],
    *,
    runner: Runner,
) -> subprocess.CompletedProcess[str]:
    try:
        return runner(
            ["/bin/launchctl", *arguments],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception:
        raise WeeklyReflectionSchedulerError(
            "weekly_scheduler_launchctl_unavailable"
        ) from None


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _is_loaded(*, runner: Runner) -> bool:
    result = _launchctl(
        ["print", f"{_domain()}/{LAUNCH_AGENT_LABEL}"],
        runner=runner,
    )
    return result.returncode == 0


def _load_runtime_status(path: Path) -> tuple[str, str]:
    if not path.is_file():
        return "", ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(payload, Mapping):
        return "", ""
    return (
        str(payload.get("last_run_status", "")).strip(),
        str(payload.get("last_success_period", "")).strip(),
    )


def scheduler_status(
    *,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
    runtime_status_path: Path = DEFAULT_RUNTIME_STATUS_PATH,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> WeeklyReflectionSchedulerStatus:
    path = launch_agent_path(launch_agents_directory)
    installed = path.is_file()
    try:
        schedule = load_schedule(schedule_path)
    except WeeklyReflectionSchedulerError as exc:
        if exc.code != "weekly_schedule_not_configured":
            raise
        schedule = default_schedule(effective_at="")
    if installed:
        try:
            payload = plistlib.loads(path.read_bytes())
            calendar = payload.get("StartCalendarInterval", {})
            expected_calendar = {
                "Weekday": CALENDAR_WEEKDAYS[schedule.weekday],
                "Hour": schedule.hour,
                "Minute": schedule.minute,
            }
            if (
                not isinstance(payload, Mapping)
                or payload.get("Label") != LAUNCH_AGENT_LABEL
                or not isinstance(calendar, Mapping)
                or dict(calendar) != expected_calendar
                or payload.get("StartInterval")
                != RECOVERY_INTERVAL_SECONDS
            ):
                raise ValueError
            arguments = payload.get("ProgramArguments")
            working_directory = payload.get("WorkingDirectory")
            if (
                not isinstance(arguments, list)
                or len(arguments) != 2
                or not all(isinstance(item, str) for item in arguments)
                or not isinstance(working_directory, str)
            ):
                raise ValueError
            root = _validate_project_root(Path(working_directory))
            python = Path(arguments[0]).expanduser().resolve()
            worker = Path(arguments[1]).expanduser().resolve()
            if (
                root != Path(working_directory).expanduser().resolve()
                or worker
                != root
                / "scripts"
                / "run_automatic_weekly_reflection_once.py"
                or not python.is_file()
                or not worker.is_file()
            ):
                raise ValueError
        except (
            KeyError,
            OSError,
            ValueError,
            plistlib.InvalidFileException,
        ):
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_plist_invalid"
            ) from None
    last_run, last_success = _load_runtime_status(runtime_status_path)
    return WeeklyReflectionSchedulerStatus(
        action="status",
        installed=installed,
        loaded=_is_loaded(runner=runner),
        enabled=schedule.enabled,
        weekday=schedule.weekday,
        hour=schedule.hour,
        minute=schedule.minute,
        timezone_mode=schedule.timezone_mode,
        last_run_status=last_run,
        last_success_period=last_success,
        next_due_summary=(
            f"{schedule.weekday} {schedule.hour:02d}:{schedule.minute:02d} local"
        ),
    )


def _write_plist(path: Path, payload: Mapping[str, Any]) -> None:
    _private_parent(path)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_bytes(plistlib.dumps(dict(payload), fmt=plistlib.FMT_XML))
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except OSError as exc:
        temporary.unlink(missing_ok=True)
        raise WeeklyReflectionSchedulerError(
            "weekly_scheduler_plist_write_failed"
        ) from exc


def _replace_loaded_agent(
    *,
    path: Path,
    payload: Mapping[str, Any],
    enabled: bool,
    runner: Runner,
) -> bool:
    loaded = _is_loaded(runner=runner)
    if loaded:
        result = _launchctl(["bootout", _domain(), str(path)], runner=runner)
        if result.returncode != 0:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_unload_failed"
            )
    _write_plist(path, payload)
    if enabled:
        result = _launchctl(["bootstrap", _domain(), str(path)], runner=runner)
        if result.returncode != 0:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_load_failed"
            )
        return True
    return False


def _restore_file(path: Path, previous: Optional[bytes]) -> None:
    if previous is None:
        path.unlink(missing_ok=True)
        return
    _private_parent(path)
    path.write_bytes(previous)
    os.chmod(path, 0o600)


def _rollback_scheduler_configuration(
    *,
    path: Path,
    schedule_path: Path,
    previous_plist: Optional[bytes],
    previous_schedule: Optional[bytes],
    was_loaded: bool,
    runner: Runner,
) -> None:
    if _is_loaded(runner=runner):
        result = _launchctl(
            ["bootout", _domain(), str(path)],
            runner=runner,
        )
        if result.returncode != 0:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_rollback_failed"
            )
    _restore_file(path, previous_plist)
    _restore_file(schedule_path, previous_schedule)
    if was_loaded:
        if previous_plist is None:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_rollback_failed"
            )
        result = _launchctl(
            ["bootstrap", _domain(), str(path)],
            runner=runner,
        )
        if result.returncode != 0:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_rollback_failed"
            )


def apply_scheduler_configuration(
    *,
    action: str,
    confirmation: str,
    project_root: Path,
    python_executable: Path,
    schedule: WeeklyReflectionSchedule,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> WeeklyReflectionSchedulerStatus:
    confirmations = {
        "install": INSTALL_CONFIRMATION,
        "configure": CONFIGURE_CONFIRMATION,
        "pause": PAUSE_CONFIRMATION,
        "resume": RESUME_CONFIRMATION,
    }
    if confirmation != confirmations.get(action):
        raise WeeklyReflectionSchedulerError(
            f"weekly_scheduler_{action}_confirmation_missing"
        )
    validated = validate_schedule(schedule)
    path = launch_agent_path(launch_agents_directory)
    payload = build_launch_agent_payload(
        project_root=project_root,
        python_executable=python_executable,
        schedule=validated,
    )
    log_directory = Path(payload["StandardOutPath"]).parent
    log_directory.mkdir(parents=True, exist_ok=True)
    os.chmod(log_directory, 0o700)
    previous_schedule = (
        schedule_path.read_bytes() if schedule_path.is_file() else None
    )
    previous_plist = path.read_bytes() if path.is_file() else None
    was_loaded = _is_loaded(runner=runner)
    try:
        save_schedule(validated, schedule_path)
        loaded = _replace_loaded_agent(
            path=path,
            payload=payload,
            enabled=validated.enabled,
            runner=runner,
        )
    except Exception:
        try:
            _rollback_scheduler_configuration(
                path=path,
                schedule_path=schedule_path,
                previous_plist=previous_plist,
                previous_schedule=previous_schedule,
                was_loaded=was_loaded,
                runner=runner,
            )
        except WeeklyReflectionSchedulerError:
            raise
        raise
    return WeeklyReflectionSchedulerStatus(
        action=action,
        installed=True,
        loaded=loaded,
        enabled=validated.enabled,
        weekday=validated.weekday,
        hour=validated.hour,
        minute=validated.minute,
        timezone_mode=validated.timezone_mode,
        next_due_summary=(
            f"{validated.weekday} {validated.hour:02d}:{validated.minute:02d} local"
        ),
    )


def uninstall_scheduler(
    *,
    confirmation: str,
    schedule_path: Path = DEFAULT_SCHEDULE_PATH,
    runtime_status_path: Path = DEFAULT_RUNTIME_STATUS_PATH,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> WeeklyReflectionSchedulerStatus:
    if confirmation != UNINSTALL_CONFIRMATION:
        raise WeeklyReflectionSchedulerError(
            "weekly_scheduler_uninstall_confirmation_missing"
        )
    path = launch_agent_path(launch_agents_directory)
    if _is_loaded(runner=runner):
        result = _launchctl(["bootout", _domain(), str(path)], runner=runner)
        if result.returncode != 0:
            raise WeeklyReflectionSchedulerError(
                "weekly_scheduler_unload_failed"
            )
    path.unlink(missing_ok=True)
    try:
        schedule = load_schedule(schedule_path)
    except WeeklyReflectionSchedulerError:
        schedule = default_schedule(effective_at="")
    last_run, last_success = _load_runtime_status(runtime_status_path)
    return WeeklyReflectionSchedulerStatus(
        action="uninstall",
        installed=False,
        loaded=False,
        enabled=schedule.enabled,
        weekday=schedule.weekday,
        hour=schedule.hour,
        minute=schedule.minute,
        timezone_mode=schedule.timezone_mode,
        last_run_status=last_run,
        last_success_period=last_success,
        next_due_summary="",
    )


__all__ = [
    "CALENDAR_WEEKDAYS",
    "CONFIGURE_CONFIRMATION",
    "DEFAULT_RUNTIME_STATUS_PATH",
    "DEFAULT_MANAGEMENT_LOCK_PATH",
    "DEFAULT_SCHEDULE_PATH",
    "INSTALL_CONFIRMATION",
    "LAUNCH_AGENT_LABEL",
    "PAUSE_CONFIRMATION",
    "RECOVERY_INTERVAL_SECONDS",
    "RESUME_CONFIRMATION",
    "UNINSTALL_CONFIRMATION",
    "WEEKDAYS",
    "WeeklyReflectionSchedule",
    "WeeklyReflectionSchedulerError",
    "WeeklyReflectionSchedulerStatus",
    "apply_scheduler_configuration",
    "build_launch_agent_payload",
    "configured_schedule",
    "default_schedule",
    "launch_agent_path",
    "load_schedule",
    "save_schedule",
    "scheduler_status",
    "scheduler_management_lock",
    "uninstall_scheduler",
    "validate_schedule",
]
