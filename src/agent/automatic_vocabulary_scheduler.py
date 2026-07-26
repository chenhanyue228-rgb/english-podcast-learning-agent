"""Safe macOS LaunchAgent lifecycle for the bounded vocabulary worker."""

from __future__ import annotations

import os
import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


LAUNCH_AGENT_LABEL = (
    "com.english-audio-learning-agent.automatic-vocabulary"
)
DEFAULT_INTERVAL_SECONDS = 60
MINIMUM_INTERVAL_SECONDS = 30
MAXIMUM_INTERVAL_SECONDS = 3600
INSTALL_CONFIRMATION = "INSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT"
UNINSTALL_CONFIRMATION = "UNINSTALL_AUTOMATIC_VOCABULARY_LAUNCH_AGENT"


class AutomaticVocabularySchedulerError(RuntimeError):
    """A stable scheduler failure that does not expose local paths."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class LaunchAgentStatus:
    action: str
    installed: bool
    loaded: bool
    interval_seconds: int
    label: str = LAUNCH_AGENT_LABEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "installed": self.installed,
            "loaded": self.loaded,
            "interval_seconds": self.interval_seconds,
            "label": self.label,
        }


Runner = Callable[..., subprocess.CompletedProcess[str]]


def default_launch_agents_directory() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def launch_agent_path(
    launch_agents_directory: Optional[Path] = None,
) -> Path:
    directory = (
        launch_agents_directory
        if launch_agents_directory is not None
        else default_launch_agents_directory()
    )
    return Path(directory) / f"{LAUNCH_AGENT_LABEL}.plist"


def _validate_interval(interval_seconds: int) -> None:
    if (
        isinstance(interval_seconds, bool)
        or not isinstance(interval_seconds, int)
        or interval_seconds < MINIMUM_INTERVAL_SECONDS
        or interval_seconds > MAXIMUM_INTERVAL_SECONDS
    ):
        raise AutomaticVocabularySchedulerError(
            "launch_agent_interval_invalid"
        )


def build_launch_agent_payload(
    *,
    project_root: Path,
    python_executable: Path,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
) -> dict[str, Any]:
    """Return a secret-free plist payload for one bounded invocation."""
    _validate_interval(interval_seconds)
    root = Path(project_root).resolve()
    python = Path(python_executable).resolve()
    worker = root / "scripts" / "run_automatic_vocabulary_once.py"
    if not root.is_dir() or not python.is_file() or not worker.is_file():
        raise AutomaticVocabularySchedulerError(
            "launch_agent_runtime_missing"
        )
    log_directory = root / "logs" / "automatic_vocabulary"
    return {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [str(python), str(worker)],
        "WorkingDirectory": str(root),
        "StartInterval": interval_seconds,
        "RunAtLoad": True,
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
        raise AutomaticVocabularySchedulerError(
            "launchctl_unavailable"
        ) from None


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _is_loaded(*, runner: Runner) -> bool:
    result = _launchctl(
        ["print", f"{_domain()}/{LAUNCH_AGENT_LABEL}"],
        runner=runner,
    )
    return result.returncode == 0


def scheduler_status(
    *,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> LaunchAgentStatus:
    _validate_interval(interval_seconds)
    return LaunchAgentStatus(
        action="status",
        installed=launch_agent_path(
            launch_agents_directory
        ).is_file(),
        loaded=_is_loaded(runner=runner),
        interval_seconds=interval_seconds,
    )


def install_launch_agent(
    *,
    project_root: Path,
    python_executable: Path,
    confirmation: str,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> LaunchAgentStatus:
    """Install once; refuse to replace an already-loaded agent."""
    if confirmation != INSTALL_CONFIRMATION:
        raise AutomaticVocabularySchedulerError(
            "launch_agent_install_confirmation_missing"
        )
    payload = build_launch_agent_payload(
        project_root=project_root,
        python_executable=python_executable,
        interval_seconds=interval_seconds,
    )
    path = launch_agent_path(launch_agents_directory)
    loaded = _is_loaded(runner=runner)
    serialized = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    if loaded:
        if path.is_file() and path.read_bytes() == serialized:
            return LaunchAgentStatus(
                action="already-installed",
                installed=True,
                loaded=True,
                interval_seconds=interval_seconds,
            )
        raise AutomaticVocabularySchedulerError(
            "launch_agent_loaded_configuration_mismatch"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    log_directory = (
        Path(payload["StandardOutPath"]).parent
    )
    log_directory.mkdir(parents=True, exist_ok=True)
    os.chmod(log_directory, 0o700)
    previous = path.read_bytes() if path.is_file() else None
    temporary = path.with_suffix(".plist.tmp")
    try:
        temporary.write_bytes(serialized)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
        result = _launchctl(
            ["bootstrap", _domain(), str(path)],
            runner=runner,
        )
        if result.returncode != 0:
            raise AutomaticVocabularySchedulerError(
                "launch_agent_install_failed"
            )
    except Exception:
        temporary.unlink(missing_ok=True)
        if previous is None:
            path.unlink(missing_ok=True)
        else:
            path.write_bytes(previous)
            os.chmod(path, 0o600)
        raise
    os.chmod(path, 0o600)
    return LaunchAgentStatus(
        action="installed",
        installed=True,
        loaded=True,
        interval_seconds=interval_seconds,
    )


def uninstall_launch_agent(
    *,
    confirmation: str,
    interval_seconds: int = DEFAULT_INTERVAL_SECONDS,
    launch_agents_directory: Optional[Path] = None,
    runner: Runner = subprocess.run,
) -> LaunchAgentStatus:
    """Unload the agent and keep all state, artifacts, and learning data."""
    if confirmation != UNINSTALL_CONFIRMATION:
        raise AutomaticVocabularySchedulerError(
            "launch_agent_uninstall_confirmation_missing"
        )
    _validate_interval(interval_seconds)
    path = launch_agent_path(launch_agents_directory)
    if _is_loaded(runner=runner):
        result = _launchctl(
            ["bootout", _domain(), str(path)],
            runner=runner,
        )
        if result.returncode != 0:
            raise AutomaticVocabularySchedulerError(
                "launch_agent_uninstall_failed"
            )
    path.unlink(missing_ok=True)
    return LaunchAgentStatus(
        action="uninstalled",
        installed=False,
        loaded=False,
        interval_seconds=interval_seconds,
    )


__all__ = [
    "AutomaticVocabularySchedulerError",
    "DEFAULT_INTERVAL_SECONDS",
    "INSTALL_CONFIRMATION",
    "LAUNCH_AGENT_LABEL",
    "LaunchAgentStatus",
    "UNINSTALL_CONFIRMATION",
    "build_launch_agent_payload",
    "install_launch_agent",
    "launch_agent_path",
    "scheduler_status",
    "uninstall_launch_agent",
]
