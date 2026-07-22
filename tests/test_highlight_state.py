from __future__ import annotations

from src.agent import highlight_state


def test_highlight_state_save_and_load_round_trip(tmp_path) -> None:
    state_path = tmp_path / "highlight_sync_state.json"
    state = {
        "last_scan_time": "2026-07-20T00:00:00Z",
        "processed_highlights_by_page": {
            "page_1": ["assumption", "fundraising"],
        },
    }

    highlight_state.save_highlight_state(state, path=state_path)
    loaded = highlight_state.load_highlight_state(path=state_path)

    assert loaded["last_scan_time"] == "2026-07-20T00:00:00Z"
    assert loaded["processed_highlights_by_page"]["page_1"] == ["assumption", "fundraising"]


def test_highlight_state_loads_default_when_missing(tmp_path) -> None:
    state_path = tmp_path / "missing.json"

    loaded = highlight_state.load_highlight_state(path=state_path)

    assert loaded["last_scan_time"] == ""
    assert loaded["processed_highlights_by_page"] == {}
