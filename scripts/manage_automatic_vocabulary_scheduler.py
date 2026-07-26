#!/usr/bin/env python3
"""Install, inspect, or uninstall the bounded macOS LaunchAgent."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.automatic_vocabulary_scheduler import (
    AutomaticVocabularySchedulerError,
    DEFAULT_INTERVAL_SECONDS,
    install_launch_agent,
    scheduler_status,
    uninstall_launch_agent,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Manage the bounded automatic vocabulary LaunchAgent. "
            "No command changes Notion data directly."
        )
    )
    parser.add_argument("action", choices=("install", "status", "uninstall"))
    parser.add_argument(
        "--interval",
        type=int,
        default=DEFAULT_INTERVAL_SECONDS,
    )
    parser.add_argument("--confirmation", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.action == "install":
            status = install_launch_agent(
                project_root=PROJECT_ROOT,
                python_executable=Path(sys.executable),
                confirmation=args.confirmation,
                interval_seconds=args.interval,
            )
        elif args.action == "uninstall":
            status = uninstall_launch_agent(
                confirmation=args.confirmation,
                interval_seconds=args.interval,
            )
        else:
            status = scheduler_status(
                interval_seconds=args.interval,
            )
    except AutomaticVocabularySchedulerError as exc:
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
                    "error_code": "launch_agent_operation_failed",
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    print(
        json.dumps(
            status.to_dict(),
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
