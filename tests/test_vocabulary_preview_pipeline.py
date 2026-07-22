from __future__ import annotations

from src.workflow.vocabulary_preview_pipeline import preview_vocabulary


class FakeBlockChildren:
    def __init__(self, results):
        self.results = results

    def list(self, **kwargs):
        return {"results": self.results}


class FakeNotion:
    def __init__(self, results):
        self.blocks = type("Blocks", (), {"children": FakeBlockChildren(results)})()


def test_preview_vocabulary_filters_and_enriches_candidates(monkeypatch) -> None:
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

    payload = preview_vocabulary("11111111111111111111111111111111", notion=notion)

    assert payload["page_id"] == "11111111111111111111111111111111"
    assert payload["total_highlights"] == 2
    assert len(payload["rejected"]) == 1
    assert payload["rejected"][0]["word"] == "Christensen"
    assert payload["rejected"][0]["reason"] == "person name"
    assert len(payload["vocabulary_preview"]) == 1
    item = payload["vocabulary_preview"][0]
    assert item["word"] == "conversation"
    assert item["original_context"] == "conversation also shows how to negotiate with investors."
    assert item["source_page_id"] == "11111111111111111111111111111111"
