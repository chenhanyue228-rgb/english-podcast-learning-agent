"""Persistent runtime metadata for long-running workflow commands."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DEFAULT_PIPELINE_RUN_PATH = Path("output/pipeline_run.json")
DEFAULT_LOGS_DIR = Path("logs")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_steps() -> dict[str, str]:
    return {
        "extraction": "",
        "reflection": "",
        "generation": "",
        "quality_gate": "",
        "notion": "",
    }


@dataclass
class PipelineRunRecord:
    run_id: str
    period: str
    started_at: str
    completed_at: str
    status: str
    steps: dict[str, str] = field(default_factory=_default_steps)

    def set_step(self, step: str, status: str) -> None:
        self.steps[step] = status

    def finalize(self, status: str, completed_at: str | None = None) -> None:
        self.status = status
        self.completed_at = completed_at or _utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "period": self.period,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "steps": dict(self.steps),
        }


def create_pipeline_run_record(period: str = "") -> PipelineRunRecord:
    return PipelineRunRecord(
        run_id=uuid4().hex,
        period=period,
        started_at=_utc_now(),
        completed_at="",
        status="running",
        steps=_default_steps(),
    )


def save_pipeline_run_record(record: PipelineRunRecord, output_path: Path = DEFAULT_PIPELINE_RUN_PATH) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_path.resolve()


def create_pipeline_logger(run_id: str, logs_dir: Path = DEFAULT_LOGS_DIR) -> tuple[logging.Logger, Path, logging.Handler]:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"weekly_reflection_{run_id}.log"
    logger = logging.getLogger(f"{__name__}.{run_id}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.handlers = [handler]
    return logger, log_path, handler


def log_pipeline_step(
    logger: logging.Logger,
    run_id: str,
    step: str,
    status: str,
    duration_seconds: float | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "run_id": run_id,
        "step": step,
        "status": status,
    }
    if duration_seconds is not None:
        payload["duration_seconds"] = round(duration_seconds, 3)
    if error:
        payload["error"] = error
    logger.info(json.dumps(payload, ensure_ascii=False))
