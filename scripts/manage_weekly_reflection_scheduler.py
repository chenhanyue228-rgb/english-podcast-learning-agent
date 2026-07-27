#!/usr/bin/env python3
"""Manage the bounded Weekly Reflection LaunchAgent."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.weekly_reflection_scheduler import (  # noqa: E402
    WeeklyReflectionSchedulerError,
    apply_scheduler_configuration,
    configured_schedule,
    default_schedule,
    load_schedule,
    scheduler_management_lock,
    scheduler_status,
    uninstall_scheduler,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manage the bounded Weekly Reflection LaunchAgent."
    )
    parser.add_argument(
        "action",
        choices=(
            "install",
            "status",
            "configure",
            "pause",
            "resume",
            "uninstall",
        ),
    )
    parser.add_argument("--weekday")
    parser.add_argument("--hour", type=int)
    parser.add_argument("--minute", type=int)
    parser.add_argument("--confirmation", default="")
    return parser


def _configured_from_args(
    args: argparse.Namespace,
    *,
    current=None,
):
    current = current or load_schedule()
    return configured_schedule(
        weekday=args.weekday if args.weekday is not None else current.weekday,
        hour=args.hour if args.hour is not None else current.hour,
        minute=args.minute if args.minute is not None else current.minute,
        enabled=current.enabled,
    )


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.action == "status":
            result = scheduler_status()
        else:
            with scheduler_management_lock():
                if args.action == "uninstall":
                    result = uninstall_scheduler(
                        confirmation=args.confirmation,
                    )
                else:
                    if args.action == "install":
                        schedule = _configured_from_args(
                            args,
                            current=default_schedule(),
                        )
                    elif args.action == "configure":
                        schedule = _configured_from_args(args)
                    elif args.action == "pause":
                        schedule = replace(
                            load_schedule(),
                            enabled=False,
                            effective_at=default_schedule().effective_at,
                        )
                    else:
                        schedule = replace(
                            load_schedule(),
                            enabled=True,
                            effective_at=default_schedule().effective_at,
                        )
                    result = apply_scheduler_configuration(
                        action=args.action,
                        confirmation=args.confirmation,
                        project_root=PROJECT_ROOT,
                        python_executable=Path(sys.executable),
                        schedule=schedule,
                    )
    except WeeklyReflectionSchedulerError as exc:
        print(
            json.dumps(
                {"status": "SAFE_STOP", "error_code": exc.code},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    except Exception:
        print(
            json.dumps(
                {
                    "status": "SAFE_STOP",
                    "error_code": "weekly_scheduler_operation_failed",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            result.to_dict(),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
