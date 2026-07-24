#!/usr/bin/env python3
"""Explicit entry point for protected Vocabulary owner acceptance."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.acceptance.vocabulary_owner_acceptance import (
    AcceptanceConfigurationError,
    AcceptanceFailure,
    GuardViolation,
    LIVE_CONFIRMATION,
    VocabularyOwnerAcceptanceRunner,
    load_acceptance_config,
    render_failure_report,
    render_redacted_report,
)
from src.notion.uploader import create_notion_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run protected pink-highlight Vocabulary acceptance. Dry-run is "
            "read-only; live mode requires an exact confirmation token."
        )
    )
    parser.add_argument("--page-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirmation")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.dry_run and args.confirmation != LIVE_CONFIRMATION:
        print(render_failure_report("live_confirmation_missing"))
        return 2

    previous_logging_disable = logging.root.manager.disable
    logging.disable(logging.INFO)
    try:
        config = load_acceptance_config()
        notion = create_notion_client(config.token)
        runner = VocabularyOwnerAcceptanceRunner(notion, config)
        result = (
            runner.dry_run(args.page_id)
            if args.dry_run
            else runner.run(args.page_id)
        )
    except (AcceptanceConfigurationError, AcceptanceFailure, GuardViolation) as exc:
        print(render_failure_report(getattr(exc, "code", str(exc))))
        return 1
    except Exception:
        print(render_failure_report("acceptance_execution_failed"))
        return 1
    finally:
        logging.disable(previous_logging_disable)

    print(
        render_redacted_report(
            result.report,
            secrets=(
                config.token,
                config.target_parent_page_id,
                *config.data_source_ids.values(),
                args.page_id,
            ),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
