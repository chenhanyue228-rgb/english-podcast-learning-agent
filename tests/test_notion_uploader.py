from __future__ import annotations

import pytest

from src.notion.uploader import (
    MAX_RICH_TEXT_LENGTH,
    NotionUploadError,
    PodcastUploadPayload,
    chunk_text,
    create_podcast_page,
    load_notion_upload_config,
    podcast_page_children,
    podcast_page_properties,
    transcript_to_text,
)


class FakePages:
    def __init__(self):
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": "page_123", "url": "https://notion.so/page_123"}


class FakeNotion:
    def __init__(self):
        self.pages = FakePages()


def test_load_notion_upload_config_prefers_podcast_database_id() -> None:
    token, database_id = load_notion_upload_config(
        {
            "NOTION_TOKEN": "secret",
            "PODCAST_DATABASE_ID": "podcast_db",
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "legacy_db",
        }
    )

    assert token == "secret"
    assert database_id == "podcast_db"


def test_load_notion_upload_config_accepts_legacy_database_id() -> None:
    token, database_id = load_notion_upload_config(
        {
            "NOTION_TOKEN": "secret",
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "legacy_db",
        }
    )

    assert token == "secret"
    assert database_id == "legacy_db"


def test_load_notion_upload_config_requires_token() -> None:
    with pytest.raises(NotionUploadError, match="NOTION_TOKEN"):
        load_notion_upload_config({"PODCAST_DATABASE_ID": "db"})


def test_load_notion_upload_config_requires_database_id() -> None:
    with pytest.raises(NotionUploadError, match="PODCAST_DATABASE_ID"):
        load_notion_upload_config({"NOTION_TOKEN": "secret"})


def test_podcast_page_properties() -> None:
    payload = PodcastUploadPayload(
        title="World Today",
        source_url="https://example.com",
        source_type="Podcast",
        transcript="Hello",
        processed_date="2026-07-16",
    )

    properties = podcast_page_properties(payload)

    assert properties["Title"]["title"][0]["text"]["content"] == "World Today"
    assert properties["URL"] == {"url": "https://example.com"}
    assert properties["Source Type"] == {"select": {"name": "Podcast"}}
    assert properties["Date"] == {"date": {"start": "2026-07-16"}}


def test_transcript_to_text_accepts_segments() -> None:
    assert (
        transcript_to_text(
            {
                "segments": [
                    {"start": 0, "end": 1, "text": "Hello"},
                    {"start": 1, "end": 2, "text": "world"},
                ]
            }
        )
        == "Hello world"
    )


def test_transcript_to_text_rejects_invalid_payload() -> None:
    with pytest.raises(NotionUploadError, match="Transcript"):
        transcript_to_text({"segments": "bad"})


def test_chunk_text_splits_long_transcript() -> None:
    text = "a" * (MAX_RICH_TEXT_LENGTH + 10)

    chunks = chunk_text(text)

    assert len(chunks) == 2
    assert all(len(chunk) <= MAX_RICH_TEXT_LENGTH for chunk in chunks)


def test_podcast_page_children_contains_transcript_heading_and_chunks() -> None:
    children = podcast_page_children("Hello transcript")

    assert children[0]["type"] == "heading_2"
    assert children[0]["heading_2"]["rich_text"][0]["text"]["content"] == "Transcript"
    assert children[1]["type"] == "paragraph"
    assert (
        children[1]["paragraph"]["rich_text"][0]["text"]["content"]
        == "Hello transcript"
    )


def test_create_podcast_page_calls_notion_sdk() -> None:
    notion = FakeNotion()
    payload = PodcastUploadPayload(
        title="World Today",
        source_url="https://podcasts.apple.com/example",
        source_type="Podcast",
        transcript="Hello transcript",
        processed_date="2026-07-16",
    )

    result = create_podcast_page(
        payload,
        notion=notion,
        podcast_database_id="podcast_db",
    )

    assert result.page_id == "page_123"
    assert result.url == "https://notion.so/page_123"
    call = notion.pages.calls[0]
    assert call["parent"] == {"data_source_id": "podcast_db"}
    assert call["properties"]["Title"]["title"][0]["text"]["content"] == "World Today"
    assert call["children"][0]["heading_2"]["rich_text"][0]["text"]["content"] == "Transcript"


def test_create_podcast_page_requires_title() -> None:
    with pytest.raises(NotionUploadError, match="title"):
        create_podcast_page(
            PodcastUploadPayload(
                title=" ",
                source_url=None,
                source_type="Podcast",
                transcript="Hello",
            ),
            notion=FakeNotion(),
            podcast_database_id="podcast_db",
        )


def test_create_podcast_page_requires_notion_page_id() -> None:
    class BrokenPages:
        def create(self, **kwargs):
            return {}

    class BrokenNotion:
        pages = BrokenPages()

    with pytest.raises(NotionUploadError, match="page ID"):
        create_podcast_page(
            PodcastUploadPayload(
                title="World Today",
                source_url=None,
                source_type="Podcast",
                transcript="Hello",
            ),
            notion=BrokenNotion(),
            podcast_database_id="podcast_db",
        )
