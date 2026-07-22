from __future__ import annotations

from src.workflow.vocabulary_learning_pipeline import preview_vocabulary_learning


class FakeBlockChildren:
    def __init__(self, results):
        self.results = results

    def list(self, **kwargs):
        return {"results": self.results}


class FakeNotion:
    def __init__(self, results):
        self.blocks = type("Blocks", (), {"children": FakeBlockChildren(results)})()


def test_preview_vocabulary_learning_approves_conversation(monkeypatch) -> None:
    monkeypatch.setenv("ENRICHMENT_PROVIDER", "placeholder")

    notion = FakeNotion(
        [
            {
                "id": "block_1",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "Christensen",
                            "text": {"content": "Christensen"},
                            "annotations": {"color": "pink_background"},
                        },
                        {
                            "plain_text": " explains the idea.",
                            "text": {"content": " explains the idea."},
                            "annotations": {"color": "default"},
                        },
                    ]
                },
            },
            {
                "id": "block_2",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "conversation",
                            "text": {"content": "conversation"},
                            "annotations": {"color": "pink_background"},
                        },
                        {
                            "plain_text": " also shows how to negotiate with investors.",
                            "text": {"content": " also shows how to negotiate with investors."},
                            "annotations": {"color": "default"},
                        },
                    ]
                },
            },
        ]
    )

    payload = preview_vocabulary_learning("11111111111111111111111111111111", notion=notion)

    assert payload["page_id"] == "11111111111111111111111111111111"
    assert payload["total_highlights"] == 2
    assert len(payload["rejected_candidates"]) == 1
    assert payload["rejected_candidates"][0]["word"] == "Christensen"
    assert payload["rejected_candidates"][0]["reason"] == "person name"
    assert payload["pending_vocabulary"] == []
    assert len(payload["approved_vocabulary"]) == 1
    item = payload["approved_vocabulary"][0]
    assert item["word"] == "conversation"
    assert item["original_context"] == "conversation also shows how to negotiate with investors."
    assert item["review_status"] == "New"
    assert item["source_page_id"] == "11111111111111111111111111111111"


def test_preview_vocabulary_learning_emits_stage_logs(monkeypatch, capsys) -> None:
    monkeypatch.setenv("ENRICHMENT_PROVIDER", "placeholder")

    notion = FakeNotion(
        [
            {
                "id": "block_1",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "plain_text": "conversation",
                            "text": {"content": "conversation"},
                            "annotations": {"color": "pink_background"},
                        },
                    ]
                },
            }
        ]
    )

    preview_vocabulary_learning("11111111111111111111111111111111", notion=notion)
    output = capsys.readouterr().out

    assert "highlight preview started" in output
    assert "highlight preview completed" in output
    assert "candidate filter completed" in output
    assert "enrichment started" in output
    assert "enrichment completed" in output
