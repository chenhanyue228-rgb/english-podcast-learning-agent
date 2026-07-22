from __future__ import annotations


def test_publish_highlight_vocabulary_upserts_approved_items(monkeypatch) -> None:
    import src.workflow.highlight_vocabulary_publish_pipeline as pipeline

    calls = {}

    def fake_build_vocabulary_learning_preview(page_id: str, notion=None):
        calls["preview_page_id"] = page_id
        return {
            "page_id": page_id,
            "total_highlights": 2,
            "rejected_candidates": [{"word": "Christensen", "reason": "person name"}],
            "pending_vocabulary": [],
            "approved_vocabulary": [
                {
                    "word": "conversation",
                    "original_context": "The conversation also shows how to negotiate with investors.",
                    "meaning": "A discussion between parties",
                    "chinese_meaning": "对话",
                    "part_of_speech": "noun",
                    "professional_category": "Business Communication",
                    "usage_example": "The conversation with stakeholders was productive.",
                    "source_page_id": page_id,
                    "review_status": "New",
                }
            ],
        }

    def fake_upsert_vocabulary_page(payload, notion=None, vocabulary_database_id=None):
        calls["upsert_payload"] = payload
        calls["vocabulary_database_id"] = vocabulary_database_id
        return type("Result", (), {"action": "created", "page_id": "vocab_1", "page_url": None})()

    monkeypatch.setattr(pipeline, "build_vocabulary_learning_preview", fake_build_vocabulary_learning_preview)
    monkeypatch.setattr(pipeline, "upsert_vocabulary_page", fake_upsert_vocabulary_page)
    monkeypatch.setattr(
        pipeline,
        "create_notion_client",
        lambda token: type("Notion", (), {})(),
    )
    monkeypatch.setattr(
        pipeline,
        "load_notion_config",
        lambda: type(
            "Config",
            (),
            {"token": "secret", "vocabulary_database_id": "vocabulary_db"},
        )(),
    )

    result = pipeline.publish_highlight_vocabulary("11111111111111111111111111111111")

    assert result.page_id == "11111111111111111111111111111111"
    assert result.created == 1
    assert result.updated == 0
    assert result.skipped == 1
    assert calls["preview_page_id"] == "11111111111111111111111111111111"
    assert calls["vocabulary_database_id"] == "vocabulary_db"
    assert calls["upsert_payload"].word == "conversation"
    assert calls["upsert_payload"].review_status == "New"
    assert calls["upsert_payload"].source_page_id == "11111111111111111111111111111111"


def test_publish_highlight_vocabulary_updates_existing_record(monkeypatch) -> None:
    import src.workflow.highlight_vocabulary_publish_pipeline as pipeline

    class FakePages:
        def __init__(self):
            self.create_calls = []
            self.update_calls = []

        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return {"id": "created_page", "url": "https://notion.so/created_page"}

        def update(self, **kwargs):
            self.update_calls.append(kwargs)
            return {"id": kwargs["page_id"], "url": f"https://notion.so/{kwargs['page_id']}"}

    class FakeDataSources:
        def __init__(self):
            self.query_calls = []
            self.results = []

        def query(self, **kwargs):
            self.query_calls.append(kwargs)
            return {"results": self.results}

    class FakeNotion:
        def __init__(self):
            self.data_sources = FakeDataSources()
            self.pages = FakePages()

    fake_notion = FakeNotion()

    def fake_build_vocabulary_learning_preview(page_id: str, notion=None):
        return {
            "page_id": page_id,
            "total_highlights": 1,
            "rejected_candidates": [],
            "pending_vocabulary": [],
            "approved_vocabulary": [
                {
                    "word": "conversation",
                    "original_context": "The conversation also shows how to negotiate with investors.",
                    "meaning": "A discussion between parties",
                    "chinese_meaning": "对话",
                    "part_of_speech": "noun",
                    "professional_category": "Business Communication",
                    "usage_example": "The conversation with stakeholders was productive.",
                    "source_page_id": page_id,
                    "review_status": "New",
                }
            ],
        }

    monkeypatch.setattr(pipeline, "build_vocabulary_learning_preview", fake_build_vocabulary_learning_preview)

    result_first = pipeline.publish_highlight_vocabulary(
        "11111111111111111111111111111111",
        notion=fake_notion,
        vocabulary_database_id="vocabulary_db",
    )
    fake_notion.data_sources.results = [{"id": "existing_page"}]
    result_second = pipeline.publish_highlight_vocabulary(
        "11111111111111111111111111111111",
        notion=fake_notion,
        vocabulary_database_id="vocabulary_db",
    )

    assert result_first.created == 1
    assert result_first.updated == 0
    assert result_second.created == 0
    assert result_second.updated == 1
    assert len(fake_notion.pages.create_calls) == 1
    assert len(fake_notion.pages.update_calls) == 1
