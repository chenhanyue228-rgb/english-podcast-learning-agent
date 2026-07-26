from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path

import pytest

from src.agent.automatic_vocabulary_scheduler import (
    INSTALL_CONFIRMATION,
    LAUNCH_AGENT_LABEL,
    UNINSTALL_CONFIRMATION,
    AutomaticVocabularySchedulerError,
    build_launch_agent_payload,
    install_launch_agent,
    launch_agent_path,
    scheduler_status,
    uninstall_launch_agent,
)


class LaunchctlRunner:
    def __init__(self) -> None:
        self.loaded = False
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs):
        self.calls.append(command)
        action = command[1]
        if action == "print":
            code = 0 if self.loaded else 113
        elif action == "bootstrap":
            self.loaded = True
            code = 0
        elif action == "bootout":
            self.loaded = False
            code = 0
        else:
            code = 1
        return subprocess.CompletedProcess(command, code, "", "")


def _runtime(tmp_path: Path) -> tuple[Path, Path]:
    project = tmp_path / "project"
    script = project / "scripts" / "run_automatic_vocabulary_once.py"
    script.parent.mkdir(parents=True)
    script.write_text("# test worker\n", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")
    return project, python


def test_launch_agent_payload_runs_one_bounded_worker_every_60_seconds(
    tmp_path: Path,
) -> None:
    project, python = _runtime(tmp_path)

    payload = build_launch_agent_payload(
        project_root=project,
        python_executable=python,
    )

    assert payload["Label"] == LAUNCH_AGENT_LABEL
    assert payload["StartInterval"] == 60
    assert payload["RunAtLoad"] is True
    assert payload["ProgramArguments"] == [
        str(python.resolve()),
        str(
            (
                project
                / "scripts"
                / "run_automatic_vocabulary_once.py"
            ).resolve()
        ),
    ]
    assert "while" not in " ".join(payload["ProgramArguments"])
    assert "EnvironmentVariables" not in payload


def test_install_status_uninstall_preserves_runtime_data(
    tmp_path: Path,
) -> None:
    project, python = _runtime(tmp_path)
    launch_agents = tmp_path / "LaunchAgents"
    state = project / "data" / "automatic_vocabulary" / "state.sqlite3"
    state.parent.mkdir(parents=True)
    state.write_text("persistent-state", encoding="utf-8")
    runner = LaunchctlRunner()

    installed = install_launch_agent(
        project_root=project,
        python_executable=python,
        confirmation=INSTALL_CONFIRMATION,
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    status = scheduler_status(
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    removed = uninstall_launch_agent(
        confirmation=UNINSTALL_CONFIRMATION,
        launch_agents_directory=launch_agents,
        runner=runner,
    )

    assert installed.installed and installed.loaded
    assert status.installed and status.loaded
    assert not removed.installed and not removed.loaded
    assert state.read_text(encoding="utf-8") == "persistent-state"
    assert not launch_agent_path(launch_agents).exists()


def test_installed_plist_is_valid_and_private(tmp_path: Path) -> None:
    project, python = _runtime(tmp_path)
    launch_agents = tmp_path / "LaunchAgents"

    install_launch_agent(
        project_root=project,
        python_executable=python,
        confirmation=INSTALL_CONFIRMATION,
        launch_agents_directory=launch_agents,
        runner=LaunchctlRunner(),
    )

    path = launch_agent_path(launch_agents)
    payload = plistlib.loads(path.read_bytes())
    assert payload["StartInterval"] == 60
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (
        project / "logs" / "automatic_vocabulary"
    ).is_dir()


def test_status_reads_installed_plist_interval(tmp_path: Path) -> None:
    project, python = _runtime(tmp_path)
    launch_agents = tmp_path / "LaunchAgents"
    runner = LaunchctlRunner()
    install_launch_agent(
        project_root=project,
        python_executable=python,
        confirmation=INSTALL_CONFIRMATION,
        interval_seconds=120,
        launch_agents_directory=launch_agents,
        runner=runner,
    )

    status = scheduler_status(
        launch_agents_directory=launch_agents,
        runner=runner,
    )

    assert status.interval_seconds == 120


def test_install_and_uninstall_require_exact_confirmation(
    tmp_path: Path,
) -> None:
    project, python = _runtime(tmp_path)
    runner = LaunchctlRunner()

    with pytest.raises(AutomaticVocabularySchedulerError) as install:
        install_launch_agent(
            project_root=project,
            python_executable=python,
            confirmation="",
            launch_agents_directory=tmp_path / "LaunchAgents",
            runner=runner,
        )
    with pytest.raises(AutomaticVocabularySchedulerError) as uninstall:
        uninstall_launch_agent(
            confirmation="",
            launch_agents_directory=tmp_path / "LaunchAgents",
            runner=runner,
        )

    assert install.value.code == (
        "launch_agent_install_confirmation_missing"
    )
    assert uninstall.value.code == (
        "launch_agent_uninstall_confirmation_missing"
    )
    assert runner.calls == []


@pytest.mark.parametrize("interval", [0, 29, 3601, True])
def test_invalid_interval_fails_closed(
    tmp_path: Path,
    interval,
) -> None:
    project, python = _runtime(tmp_path)

    with pytest.raises(
        AutomaticVocabularySchedulerError,
        match="launch_agent_interval_invalid",
    ):
        build_launch_agent_payload(
            project_root=project,
            python_executable=python,
            interval_seconds=interval,
        )
