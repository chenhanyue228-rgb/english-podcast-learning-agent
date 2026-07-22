from __future__ import annotations

from src.notion.vocabulary_publisher import (
    VocabularyPublishPayload,
    VocabularyPublisherError,
    create_vocabulary_page,
    publish_vocabulary_memory,
    vocabulary_page_properties,
)


class FakePages:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "vocab_page_1", "url": "https://notion.so/vocab_page_1"}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"], "url": f"https://notion.so/{kwargs['page_id']}"}


class FakeDataSources:
    def __init__(self, results=None):
        self.query_calls = []
        self.results = results or []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {"results": self.results}


class FakeNotion:
    def __init__(self, query_results=None):
        self.data_sources = FakeDataSources(query_results)
        self.pages = FakePages()


def sample_payload() -> VocabularyPublishPayload:
    return VocabularyPublishPayload(
        word="leverage",
        original_context="Companies can leverage AI to move faster.",
        meaning="Use resources effectively",
        professional_category="Word",
        source="Podcast Library",
        source_page_id="podcast_page_1",
        first_seen="2026-07-17",
        review_status="New",
        last_review="",
        usage_example="We can leverage AI tools to save time.",
        personal_note="A reusable business verb.",
    )


def test_vocabulary_page_properties_include_source_relation() -> None:
    properties = vocabulary_page_properties(sample_payload())

    assert properties["Name"]["title"][0]["text"]["content"] == "leverage"
    assert properties["Source"] == {"relation": [{"id": "podcast_page_1"}]}
    assert properties["Source Page ID"]["rich_text"][0]["text"]["content"] == "podcast_page_1"
    assert properties["Review Status"] == {"select": {"name": "New"}}


def test_create_vocabulary_page_calls_notion_sdk() -> None:
    notion = FakeNotion()

    result = create_vocabulary_page(
        sample_payload(),
        notion=notion,
        vocabulary_database_id="vocabulary_db",
    )

    assert result.page_id == "vocab_page_1"
    call = notion.pages.create_calls[0]
    assert call["parent"] == {"data_source_id": "vocabulary_db"}
    assert call["properties"]["Source"] == {"relation": [{"id": "podcast_page_1"}]}
    assert call["children"][0]["heading_1"]["rich_text"][0]["text"]["content"] == "leverage"


def test_create_vocabulary_page_allows_empty_optional_fields() -> None:
    notion = FakeNotion()
    payload = VocabularyPublishPayload(
        word="leverage",
        source_page_id="podcast_page_1",
    )

    result = create_vocabulary_page(
        payload,
        notion=notion,
        vocabulary_database_id="vocabulary_db",
    )

    assert result.page_id == "vocab_page_1"
    call = notion.pages.create_calls[0]
    assert call["properties"]["Original Context"] == {"rich_text": []}
    assert call["properties"]["Meaning"] == {"rich_text": []}
    assert call["properties"]["Usage Example"] == {"rich_text": []}
    assert call["properties"]["Personal Note"] == {"rich_text": []}


def test_upsert_vocabulary_page_updates_existing_record() -> None:
    notion = FakeNotion(query_results=[{"id": "existing_page"}])
    payload = VocabularyPublishPayload(
        word="leverage",
        source_page_id="podcast_page_1",
        professional_category="Business Strategy",
    )

    from src.notion.vocabulary_publisher import upsert_vocabulary_page

    result = upsert_vocabulary_page(
        payload,
        notion=notion,
        vocabulary_database_id="vocabulary_db",
    )

    assert result.action == "updated"
    assert notion.data_sources.query_calls[0]["data_source_id"] == "vocabulary_db"
    assert notion.pages.update_calls[0]["page_id"] == "existing_page"
    assert notion.pages.create_calls == []


def test_publish_vocabulary_memory_requires_word() -> None:
    try:
        publish_vocabulary_memory(
            {
                "word": " ",
                "source_page_id": "podcast_page_1",
            },
            notion=FakeNotion(),
            vocabulary_database_id="vocabulary_db",
        )
    except VocabularyPublisherError as exc:
        assert "word" in str(exc)
    else:
        raise AssertionError("Expected VocabularyPublisherError")
