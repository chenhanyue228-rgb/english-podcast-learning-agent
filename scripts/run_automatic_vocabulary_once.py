#!/usr/bin/env python3
"""Run one bounded automatic vocabulary cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.automatic_vocabulary_runtime import (
    run_bounded_automatic_vocabulary_cycle,
)


def main() -> int:
    report = run_bounded_automatic_vocabulary_cycle()
    print(
        json.dumps(
            report.to_dict(),
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 1 if report.status in {"SAFE_STOP", "PARTIAL"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
