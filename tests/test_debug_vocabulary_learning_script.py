from __future__ import annotations

from pathlib import Path


def test_debug_vocabulary_learning_script_calls_pipeline(monkeypatch, capsys) -> None:
    import scripts.debug_vocabulary_learning as script

    called = {}

    def fake_preview_vocabulary_learning(page_id: str):
        called["page_id"] = page_id
        return {"page_id": page_id, "total_highlights": 0, "rejected_candidates": [], "approved_vocabulary": []}

    monkeypatch.setattr(script, "preview_vocabulary_learning", fake_preview_vocabulary_learning)

    exit_code = script.main(["11111111111111111111111111111111"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["page_id"] == "11111111111111111111111111111111"
    assert '"page_id": "11111111111111111111111111111111"' in output
