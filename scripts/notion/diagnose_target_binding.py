#!/usr/bin/env python3
"""Read-only diagnosis for the configured Notion target database group."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.notion.config import NotionConfigError, load_notion_config
from src.notion.target_binding import (
    CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP,
    TARGET_BINDING_RETRIEVE_FAILED,
    TARGET_DATABASE_AMBIGUOUS,
    TARGET_DATABASE_MISSING,
    TARGET_DATABASE_ROLE_MISMATCH,
    TARGET_PARENT_MISMATCH,
    TARGET_PARENT_NOT_CONFIGURED,
    TARGET_RELATION_OUTSIDE_GROUP,
    NotionTargetBindingError,
    validate_notion_target_binding,
)
from src.notion.uploader import create_notion_client


EXIT_CONFIGURATION_INCOMPLETE = 2
EXIT_TARGET_MISMATCH = 3
EXIT_TARGET_ACCESS_UNAVAILABLE = 4
EXIT_TARGET_AMBIGUOUS = 5

_MISMATCH_CODES = {
    TARGET_PARENT_MISMATCH,
    CONFIGURED_DATA_SOURCES_NOT_SAME_GROUP,
    TARGET_DATABASE_ROLE_MISMATCH,
    TARGET_RELATION_OUTSIDE_GROUP,
}
_AMBIGUOUS_CODES = {
    TARGET_DATABASE_AMBIGUOUS,
    TARGET_DATABASE_MISSING,
}


def _report(
    *,
    status: str,
    failure: str = "",
    result: Any = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "failure": failure,
        "target_binding_verified": bool(
            result is not None and result.valid
        ),
        "configured_parent_matches_expected": bool(
            result is not None
            and result.configured_parent_matches_expected
        ),
        "all_data_sources_same_group": bool(
            result is not None and result.all_data_sources_same_group
        ),
        "internal_relations_verified": bool(
            result is not None and result.internal_relations_verified
        ),
        "target_parent_fingerprint": (
            result.target_parent_fingerprint if result is not None else ""
        ),
        "target_group_fingerprint": (
            result.target_group_fingerprint if result is not None else ""
        ),
        "read_only": True,
    }


def diagnose() -> tuple[dict[str, Any], int]:
    try:
        config = load_notion_config()
    except NotionConfigError as exc:
        failure = (
            TARGET_PARENT_NOT_CONFIGURED
            if "NOTION_TARGET_PARENT_PAGE_ID" in str(exc)
            else "configuration_incomplete"
        )
        return (
            _report(status="failed", failure=failure),
            EXIT_CONFIGURATION_INCOMPLETE,
        )

    if not config.target_parent_page_id:
        return (
            _report(
                status="failed",
                failure=TARGET_PARENT_NOT_CONFIGURED,
            ),
            EXIT_CONFIGURATION_INCOMPLETE,
        )

    try:
        notion = create_notion_client(config.token)
        result = validate_notion_target_binding(notion, config)
    except NotionTargetBindingError as exc:
        if exc.code == TARGET_BINDING_RETRIEVE_FAILED:
            exit_code = EXIT_TARGET_ACCESS_UNAVAILABLE
        elif exc.code in _AMBIGUOUS_CODES:
            exit_code = EXIT_TARGET_AMBIGUOUS
        elif exc.code in _MISMATCH_CODES:
            exit_code = EXIT_TARGET_MISMATCH
        else:
            exit_code = 1
        return _report(status="failed", failure=exc.code), exit_code
    except Exception:
        return _report(status="failed", failure="diagnosis_failed"), 1

    return _report(status="valid", result=result), 0


def main() -> int:
    report, exit_code = diagnose()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
