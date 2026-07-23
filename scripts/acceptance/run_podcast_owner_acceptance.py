#!/usr/bin/env python3
"""Explicit live entry point for the podcast owner-acceptance harness."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.analyzer.ai_client import read_generated_analysis_file
from src.analyzer.validators import validate_ai_analysis
from src.extractor.router import SourceType, detect_source
from src.notion.learning_publisher import CompletePodcastLearningPayload
from src.notion.uploader import create_notion_client, transcript_to_text

from scripts.acceptance.podcast_owner_acceptance import (
    AcceptanceConfigurationError,
    AcceptanceFailure,
    GuardViolation,
    OwnerAcceptanceRunner,
    load_acceptance_config,
    render_failure_report,
    render_redacted_report,
)


LIVE_CONFIRMATION = "OWNER_ACCEPTANCE_WRITES_TO_NOTION"
SUPPORTED_ACCEPTANCE_SOURCE_TYPES = {
    SourceType.APPLE_PODCAST,
    SourceType.PODCAST_RSS,
    SourceType.LOCAL_AUDIO,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run one guarded podcast publish and one exact idempotency retry. "
            "This command never downloads or transcribes audio."
        )
    )
    parser.add_argument("--source", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--transcript-json", required=True, type=Path)
    parser.add_argument("--analysis-json", required=True, type=Path)
    parser.add_argument("--processed-date")
    parser.add_argument("--allow-partial-recovery", action="store_true")
    parser.add_argument(
        "--confirmation",
        required=True,
        help=f"Must be exactly {LIVE_CONFIRMATION}.",
    )
    return parser


def _load_transcript(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("transcript_artifact_invalid")
    return transcript_to_text(payload)


def _build_payload(args: argparse.Namespace) -> CompletePodcastLearningPayload:
    detection = detect_source(args.source)
    if detection.type not in SUPPORTED_ACCEPTANCE_SOURCE_TYPES:
        raise ValueError("unsupported_acceptance_source")
    analysis = validate_ai_analysis(
        read_generated_analysis_file(args.analysis_json)
    )
    transcript = _load_transcript(args.transcript_json)
    source_type = (
        "Local Audio"
        if detection.type == SourceType.LOCAL_AUDIO
        else "Podcast"
    )
    kwargs = {
        "title": args.title,
        "source_url": (
            None if detection.type == SourceType.LOCAL_AUDIO else detection.source
        ),
        "source_type": source_type,
        "transcript": transcript,
        "analysis": analysis,
    }
    if args.processed_date:
        kwargs["processed_date"] = args.processed_date
    return CompletePodcastLearningPayload(**kwargs)


def main() -> int:
    args = build_parser().parse_args()
    logging.disable(logging.INFO)
    if args.confirmation != LIVE_CONFIRMATION:
        print(render_failure_report("live_confirmation_missing"))
        return 2

    try:
        payload = _build_payload(args)
        config = load_acceptance_config()
        notion = create_notion_client(config.token)
        result = OwnerAcceptanceRunner(notion, config).run(
            payload,
            allow_partial_recovery=args.allow_partial_recovery,
        )
    except (AcceptanceConfigurationError, AcceptanceFailure, GuardViolation) as exc:
        code = getattr(exc, "code", str(exc))
        print(render_failure_report(code))
        return 1
    except Exception:
        print(render_failure_report("acceptance_input_or_execution_failed"))
        return 1

    print(
        render_redacted_report(
            result.report,
            secrets=(
                config.token,
                *config.data_source_ids.values(),
            ),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
