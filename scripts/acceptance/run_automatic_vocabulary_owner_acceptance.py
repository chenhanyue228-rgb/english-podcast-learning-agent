#!/usr/bin/env python3
"""Explicit entry point for protected automatic Vocabulary acceptance."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.acceptance.automatic_vocabulary_owner_acceptance import (
    AcceptanceConfigurationError,
    AcceptanceFailure,
    AutomaticVocabularyOwnerAcceptanceRunner,
    GuardViolation,
    LIVE_CONFIRMATION,
    load_acceptance_config,
    render_failure_report,
    render_redacted_report,
)
from src.notion.uploader import create_notion_client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run protected automatic Vocabulary acceptance. Dry-run is "
            "read-only; live mode requires the exact confirmation token."
        )
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirmation", default="")
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
        with tempfile.TemporaryDirectory(
            prefix="epla-automatic-vocabulary-acceptance-"
        ) as temporary:
            root = Path(temporary)
            runner = AutomaticVocabularyOwnerAcceptanceRunner(
                notion,
                config,
                state_path=root / "state.sqlite3",
                artifact_root=root / "artifacts",
                lock_path=root / "worker.lock",
                log_path=root / "runtime.jsonl",
            )
            result = (
                runner.dry_run()
                if args.dry_run
                else runner.run(confirmation=args.confirmation)
            )
    except (
        AcceptanceConfigurationError,
        AcceptanceFailure,
        GuardViolation,
    ) as exc:
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
                result.controlled_podcast_page_id,
                result.vocabulary_page_id,
            ),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
