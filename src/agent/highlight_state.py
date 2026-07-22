"""Persistent state for pink-highlight vocabulary synchronization."""

from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping


DEFAULT_HIGHLIGHT_STATE: dict[str, Any] = {
    "last_scan_time": "",
    "processed_highlights_by_page": {},
}

HIGHLIGHT_SYNC_STATE_PATH = Path("data/highlight_sync_state.json")


def _normalize_state(raw_state: Any) -> dict[str, Any]:
    state = dict(DEFAULT_HIGHLIGHT_STATE)
    processed: dict[str, list[str]] = {}

    if isinstance(raw_state, Mapping):
        last_scan_time = raw_state.get("last_scan_time", "")
        if isinstance(last_scan_time, str):
            state["last_scan_time"] = last_scan_time.strip()

        raw_processed = raw_state.get("processed_highlights_by_page", {})
        if isinstance(raw_processed, Mapping):
            for page_id, items in raw_processed.items():
                if not isinstance(items, list):
                    continue
                normalized_items = [
                    str(item).strip()
                    for item in items
                    if str(item).strip()
                ]
                if normalized_items:
                    processed[str(page_id).strip()] = list(dict.fromkeys(normalized_items))

    state["processed_highlights_by_page"] = processed
    return state


def load_highlight_state(path: Path = HIGHLIGHT_SYNC_STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        return dict(DEFAULT_HIGHLIGHT_STATE)

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_HIGHLIGHT_STATE)

    return _normalize_state(payload)


def save_highlight_state(state: Mapping[str, Any], path: Path = HIGHLIGHT_SYNC_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_state(state)

    with NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        dir=str(path.parent),
        prefix=path.name + ".",
        suffix=".tmp",
    ) as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)

    os.replace(temp_path, path)
