from __future__ import annotations

import json
import plistlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from scripts import manage_weekly_reflection_scheduler as scheduler_manager
from src.agent.automatic_vocabulary_scheduler import (
    LAUNCH_AGENT_LABEL as VOCABULARY_LAUNCH_AGENT_LABEL,
)
from src.agent.weekly_reflection_scheduler import (
    CALENDAR_WEEKDAYS,
    CONFIGURE_CONFIRMATION,
    INSTALL_CONFIRMATION,
    LAUNCH_AGENT_LABEL,
    PAUSE_CONFIRMATION,
    RECOVERY_INTERVAL_SECONDS,
    RESUME_CONFIRMATION,
    UNINSTALL_CONFIRMATION,
    WeeklyReflectionSchedulerError,
    apply_scheduler_configuration,
    build_launch_agent_payload,
    configured_schedule,
    default_schedule,
    launch_agent_path,
    load_schedule,
    save_schedule,
    scheduler_management_lock,
    scheduler_status,
    uninstall_scheduler,
    validate_schedule,
)


class LaunchctlRunner:
    def __init__(self, *, fail_action: str = "") -> None:
        self.loaded = False
        self.fail_action = fail_action
        self.calls: list[list[str]] = []

    def __call__(self, command: list[str], **_kwargs):
        self.calls.append(command)
        action = command[1]
        if action == "print":
            code = 0 if self.loaded else 113
        elif action == self.fail_action:
            self.fail_action = ""
            code = 1
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
    project = tmp_path / "EnglishAudioLearningAgent"
    worker = (
        project
        / "scripts"
        / "run_automatic_weekly_reflection_once.py"
    )
    worker.parent.mkdir(parents=True)
    worker.write_text("# bounded worker\n", encoding="utf-8")
    python = project / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    return project, python


def _install(
    tmp_path: Path,
    runner: LaunchctlRunner,
    *,
    schedule=None,
):
    project, python = _runtime(tmp_path)
    schedule_path = tmp_path / "data" / "schedule.json"
    launch_agents = tmp_path / "LaunchAgents"
    result = apply_scheduler_configuration(
        action="install",
        confirmation=INSTALL_CONFIRMATION,
        project_root=project,
        python_executable=python,
        schedule=schedule or default_schedule(
            effective_at="2026-07-25T00:00:00+00:00"
        ),
        schedule_path=schedule_path,
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    return result, project, python, schedule_path, launch_agents


def test_default_schedule_is_saturday_at_ten_local() -> None:
    schedule = default_schedule(
        effective_at="2026-07-25T00:00:00+00:00"
    )

    assert schedule.enabled is True
    assert schedule.weekday == "saturday"
    assert schedule.hour == 10
    assert schedule.minute == 0
    assert schedule.timezone_mode == "local"


def test_first_install_can_use_a_custom_schedule() -> None:
    args = type(
        "Args",
        (),
        {"weekday": "sunday", "hour": 20, "minute": 30},
    )()

    schedule = scheduler_manager._configured_from_args(
        args,
        current=default_schedule(
            effective_at="2026-07-25T00:00:00+00:00"
        ),
    )

    assert (schedule.weekday, schedule.hour, schedule.minute) == (
        "sunday",
        20,
        30,
    )


def test_scheduler_management_lock_is_non_blocking(tmp_path: Path) -> None:
    lock_path = tmp_path / "scheduler.manager.lock"

    with scheduler_management_lock(lock_path):
        with pytest.raises(WeeklyReflectionSchedulerError) as error:
            with scheduler_management_lock(lock_path):
                pass

    assert error.value.code == "weekly_scheduler_management_overlap"


def test_custom_schedule_round_trips_with_private_atomic_file(
    tmp_path: Path,
) -> None:
    path = tmp_path / "data" / "weekly_reflection" / "schedule.json"
    schedule = configured_schedule(
        weekday="sunday",
        hour=20,
        minute=30,
        effective_at="2026-07-25T00:00:00+00:00",
    )

    save_schedule(schedule, path)
    loaded = load_schedule(path)

    assert loaded == schedule
    assert (path.stat().st_mode & 0o777) == 0o600
    assert (path.parent.stat().st_mode & 0o777) == 0o700
    assert not list(path.parent.glob(f".{path.name}.*"))


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (
            {
                "enabled": True,
                "weekday": "funday",
                "hour": 10,
                "minute": 0,
                "timezone_mode": "local",
                "schema_version": 1,
            },
            "weekly_schedule_weekday_invalid",
        ),
        (
            {
                "enabled": True,
                "weekday": "saturday",
                "hour": True,
                "minute": 0,
                "timezone_mode": "local",
                "schema_version": 1,
            },
            "weekly_schedule_hour_invalid",
        ),
        (
            {
                "enabled": True,
                "weekday": "saturday",
                "hour": 24,
                "minute": 0,
                "timezone_mode": "local",
                "schema_version": 1,
            },
            "weekly_schedule_hour_invalid",
        ),
        (
            {
                "enabled": True,
                "weekday": "saturday",
                "hour": 10,
                "minute": 60,
                "timezone_mode": "local",
                "schema_version": 1,
            },
            "weekly_schedule_minute_invalid",
        ),
    ],
)
def test_invalid_schedule_fails_closed(payload: dict, code: str) -> None:
    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        validate_schedule(payload)

    assert error.value.code == code


def test_launch_agent_payload_is_independent_and_secret_free(
    tmp_path: Path,
) -> None:
    project, python = _runtime(tmp_path)
    schedule = configured_schedule(
        weekday="friday",
        hour=9,
        minute=30,
        effective_at="2026-07-25T00:00:00+00:00",
    )

    payload = build_launch_agent_payload(
        project_root=project,
        python_executable=python,
        schedule=schedule,
    )
    rendered = json.dumps(payload)

    assert payload["Label"] == LAUNCH_AGENT_LABEL
    assert LAUNCH_AGENT_LABEL != VOCABULARY_LAUNCH_AGENT_LABEL
    assert payload["StartCalendarInterval"] == {
        "Weekday": CALENDAR_WEEKDAYS["friday"],
        "Hour": 9,
        "Minute": 30,
    }
    assert payload["StartInterval"] == RECOVERY_INTERVAL_SECONDS
    assert payload["ProgramArguments"] == [
        str(python.absolute()),
        str(
            (
                project
                / "scripts"
                / "run_automatic_weekly_reflection_once.py"
            ).absolute()
        ),
    ]
    assert "EnvironmentVariables" not in payload
    assert "NOTION" not in rendered.upper()
    assert "DATABASE_ID" not in rendered.upper()


def test_scheduler_lifecycle_preserves_state_and_reports_real_config(
    tmp_path: Path,
) -> None:
    runner = LaunchctlRunner()
    (
        installed,
        project,
        python,
        schedule_path,
        launch_agents,
    ) = _install(tmp_path, runner)
    runtime_status = tmp_path / "runtime_status.json"
    runtime_status.write_text(
        json.dumps(
            {
                "last_run_status": "PASS",
                "last_success_period": "2026-W30",
            }
        ),
        encoding="utf-8",
    )

    configured = configured_schedule(
        weekday="sunday",
        hour=8,
        minute=15,
        effective_at="2026-07-26T00:00:00+00:00",
    )
    updated = apply_scheduler_configuration(
        action="configure",
        confirmation=CONFIGURE_CONFIRMATION,
        project_root=project,
        python_executable=python,
        schedule=configured,
        schedule_path=schedule_path,
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    status = scheduler_status(
        schedule_path=schedule_path,
        runtime_status_path=runtime_status,
        launch_agents_directory=launch_agents,
        runner=runner,
    )

    assert installed.installed and installed.loaded
    assert updated.loaded and updated.weekday == "sunday"
    assert status.loaded and status.enabled
    assert (status.weekday, status.hour, status.minute) == (
        "sunday",
        8,
        15,
    )
    assert status.last_run_status == "PASS"
    assert status.last_success_period == "2026-W30"


def test_pause_resume_and_uninstall_keep_schedule_and_learning_data(
    tmp_path: Path,
) -> None:
    runner = LaunchctlRunner()
    _, project, python, schedule_path, launch_agents = _install(
        tmp_path,
        runner,
    )
    learning_data = project / "data" / "weekly_reflection" / "artifact.json"
    learning_data.parent.mkdir(parents=True)
    learning_data.write_text("persistent", encoding="utf-8")

    paused_schedule = replace(
        load_schedule(schedule_path),
        enabled=False,
        effective_at="2026-07-26T00:00:00+00:00",
    )
    paused = apply_scheduler_configuration(
        action="pause",
        confirmation=PAUSE_CONFIRMATION,
        project_root=project,
        python_executable=python,
        schedule=paused_schedule,
        schedule_path=schedule_path,
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    resumed = apply_scheduler_configuration(
        action="resume",
        confirmation=RESUME_CONFIRMATION,
        project_root=project,
        python_executable=python,
        schedule=replace(
            paused_schedule,
            enabled=True,
            effective_at="2026-07-27T00:00:00+00:00",
        ),
        schedule_path=schedule_path,
        launch_agents_directory=launch_agents,
        runner=runner,
    )
    removed = uninstall_scheduler(
        confirmation=UNINSTALL_CONFIRMATION,
        schedule_path=schedule_path,
        launch_agents_directory=launch_agents,
        runner=runner,
    )

    assert paused.enabled is False and paused.loaded is False
    assert resumed.enabled is True and resumed.loaded is True
    assert removed.installed is False and removed.loaded is False
    assert schedule_path.is_file()
    assert learning_data.read_text(encoding="utf-8") == "persistent"


@pytest.mark.parametrize(
    ("action", "confirmation"),
    [
        ("install", INSTALL_CONFIRMATION),
        ("configure", CONFIGURE_CONFIRMATION),
        ("pause", PAUSE_CONFIRMATION),
        ("resume", RESUME_CONFIRMATION),
    ],
)
def test_mutating_actions_require_exact_confirmation(
    tmp_path: Path,
    action: str,
    confirmation: str,
) -> None:
    project, python = _runtime(tmp_path)
    runner = LaunchctlRunner()

    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        apply_scheduler_configuration(
            action=action,
            confirmation=f"{confirmation}-wrong",
            project_root=project,
            python_executable=python,
            schedule=default_schedule(
                effective_at="2026-07-25T00:00:00+00:00"
            ),
            schedule_path=tmp_path / "schedule.json",
            launch_agents_directory=tmp_path / "LaunchAgents",
            runner=runner,
        )

    assert error.value.code == (
        f"weekly_scheduler_{action}_confirmation_missing"
    )
    assert runner.calls == []


def test_failed_reconfigure_rolls_back_schedule_plist_and_loaded_state(
    tmp_path: Path,
) -> None:
    runner = LaunchctlRunner()
    _, project, python, schedule_path, launch_agents = _install(
        tmp_path,
        runner,
    )
    plist_path = launch_agent_path(launch_agents)
    previous_schedule = schedule_path.read_bytes()
    previous_plist = plist_path.read_bytes()
    runner.fail_action = "bootstrap"

    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        apply_scheduler_configuration(
            action="configure",
            confirmation=CONFIGURE_CONFIRMATION,
            project_root=project,
            python_executable=python,
            schedule=configured_schedule(
                weekday="monday",
                hour=7,
                minute=45,
                effective_at="2026-07-27T00:00:00+00:00",
            ),
            schedule_path=schedule_path,
            launch_agents_directory=launch_agents,
            runner=runner,
        )

    assert error.value.code == "weekly_scheduler_load_failed"
    assert schedule_path.read_bytes() == previous_schedule
    assert plist_path.read_bytes() == previous_plist
    assert runner.loaded is True


def test_status_rejects_plist_schedule_drift(tmp_path: Path) -> None:
    runner = LaunchctlRunner()
    _, _, _, schedule_path, launch_agents = _install(tmp_path, runner)
    path = launch_agent_path(launch_agents)
    payload = plistlib.loads(path.read_bytes())
    payload["StartCalendarInterval"]["Hour"] = 22
    path.write_bytes(plistlib.dumps(payload))

    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        scheduler_status(
            schedule_path=schedule_path,
            launch_agents_directory=launch_agents,
            runner=runner,
        )

    assert error.value.code == "weekly_scheduler_plist_invalid"


def test_status_rejects_python_outside_installed_project_venv(
    tmp_path: Path,
) -> None:
    runner = LaunchctlRunner()
    _, _, _, schedule_path, launch_agents = _install(tmp_path, runner)
    path = launch_agent_path(launch_agents)
    payload = plistlib.loads(path.read_bytes())
    other_python = tmp_path / "other-python"
    other_python.write_text("", encoding="utf-8")
    payload["ProgramArguments"][0] = str(other_python)
    path.write_bytes(plistlib.dumps(payload))

    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        scheduler_status(
            schedule_path=schedule_path,
            launch_agents_directory=launch_agents,
            runner=runner,
        )

    assert error.value.code == "weekly_scheduler_plist_invalid"


def test_documents_project_root_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "Documents" / "EnglishAudioLearningAgent"
    worker = (
        project
        / "scripts"
        / "run_automatic_weekly_reflection_once.py"
    )
    worker.parent.mkdir(parents=True)
    worker.write_text("", encoding="utf-8")
    python = tmp_path / "python"
    python.write_text("", encoding="utf-8")

    with pytest.raises(WeeklyReflectionSchedulerError) as error:
        build_launch_agent_payload(
            project_root=project,
            python_executable=python,
            schedule=default_schedule(
                effective_at="2026-07-25T00:00:00+00:00"
            ),
        )

    assert error.value.code == "weekly_scheduler_protected_project_root"
