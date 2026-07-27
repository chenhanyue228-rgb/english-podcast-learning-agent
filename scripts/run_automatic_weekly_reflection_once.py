#!/usr/bin/env python3
"""Run one bounded automatic Weekly Reflection cycle and exit."""

from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.automatic_weekly_reflection_runtime import (  # noqa: E402
    run_bounded_automatic_weekly_reflection,
)


def main() -> int:
    report = run_bounded_automatic_weekly_reflection()
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if report.status not in {"SAFE_STOP", "RETRYABLE_FAILURE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
