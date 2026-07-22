"""Persistent state for comment-triggered vocabulary synchronization."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


DEFAULT_COMMENT_STATE: dict[str, Any] = {
    "processed_comment_ids": [],
    "processed_discussion_ids": [],
    "last_scan_time": "",
}

COMMENT_SYNC_STATE_PATH = Path("data/comment_sync_state.json")


def _normalize_state(raw_state: Any) -> dict[str, Any]:
    state = dict(DEFAULT_COMMENT_STATE)
    if isinstance(raw_state, dict):
        processed_comment_ids = raw_state.get("processed_comment_ids", [])
        processed_discussion_ids = raw_state.get("processed_discussion_ids", [])
        last_scan_time = raw_state.get("last_scan_time", "")

        if isinstance(processed_comment_ids, list):
            state["processed_comment_ids"] = [
                str(item).strip() for item in processed_comment_ids if str(item).strip()
            ]
        if isinstance(processed_discussion_ids, list):
            state["processed_discussion_ids"] = [
                str(item).strip() for item in processed_discussion_ids if str(item).strip()
            ]
        if isinstance(last_scan_time, str):
            state["last_scan_time"] = last_scan_time.strip()
    return state


def load_comment_state() -> dict[str, Any]:
    if not COMMENT_SYNC_STATE_PATH.exists():
        return dict(DEFAULT_COMMENT_STATE)

    try:
        with COMMENT_SYNC_STATE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_COMMENT_STATE)

    return _normalize_state(payload)


def save_comment_state(state: dict[str, Any]) -> None:
    COMMENT_SYNC_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    normalized_state = _normalize_state(state)

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(COMMENT_SYNC_STATE_PATH.parent),
        prefix=COMMENT_SYNC_STATE_PATH.name + ".",
        suffix=".tmp",
    ) as handle:
        json.dump(normalized_state, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)

    os.replace(temp_path, COMMENT_SYNC_STATE_PATH)
