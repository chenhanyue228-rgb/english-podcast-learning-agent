from __future__ import annotations


def test_debug_vocabulary_review_script_calls_pipeline(monkeypatch, capsys) -> None:
    import scripts.debug_vocabulary_review as script

    called = {}

    def fake_build_vocabulary_learning_preview(page_id: str):
        called["page_id"] = page_id
        return {
            "page_id": page_id,
            "total_highlights": 1,
            "rejected_candidates": [{"word": "Christensen", "reason": "person name"}],
            "pending_vocabulary": [{"word": "conversation", "review_status": "pending"}],
        }

    def fake_approve_vocabulary_items(items):
        called["approved_items"] = items
        return {
            "pending_vocabulary": [],
            "approved": [{"word": "conversation", "review_status": "approved"}],
            "rejected": [],
        }

    monkeypatch.setattr(script, "build_vocabulary_learning_preview", fake_build_vocabulary_learning_preview)
    monkeypatch.setattr(script, "approve_vocabulary_items", fake_approve_vocabulary_items)

    exit_code = script.main(["11111111111111111111111111111111"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert called["page_id"] == "11111111111111111111111111111111"
    assert called["approved_items"] == [{"word": "conversation", "review_status": "pending"}]
    assert '"pending_vocabulary"' in output
    assert '"approved_vocabulary"' in output
    assert '"rejected_vocabulary"' in output
