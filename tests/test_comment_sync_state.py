from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.notion import comment_sync_state
from src.notion.comment_vocab_sync import sync_vocab_comments


class FakeDataSources:
    def __init__(self, results=None):
        self.results = results or []

    def query(self, **kwargs):
        return {"results": self.results}


class FakePages:
    def update(self, **kwargs):
        return {"id": kwargs["page_id"], "url": "https://notion.so/vocab_page"}


class FakeBlockChildren:
    def __init__(self, results=None):
        self.results = results or []

    def list(self, **kwargs):
        block_id = kwargs.get("block_id")
        if isinstance(self.results, dict):
            return {"results": self.results.get(block_id, [])}
        return {"results": self.results}


class FakeBlocks:
    def __init__(self, children=None):
        self.children = FakeBlockChildren(children)


class FakeNotion:
    def __init__(self, pages, block_children=None):
        self.data_sources = FakeDataSources(pages)
        self.pages = FakePages()
        self.blocks = FakeBlocks(block_children)


class FakeResponse:
    def __init__(self, results):
        self._results = results
        self.status_code = 200
        self.text = "{}"

    def json(self):
        return {"results": self._results}


class FakeHttpxClient:
    def __init__(self, handler, timeout=None):
        self.handler = handler
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        return self.handler(url, headers=headers, params=params)


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    state_path = tmp_path / "comment_sync_state.json"
    monkeypatch.setattr(comment_sync_state, "COMMENT_SYNC_STATE_PATH", state_path)
    yield


def test_comment_state_save_and_load() -> None:
    comment_sync_state.save_comment_state(
        {
            "processed_comment_ids": ["c1", "c2"],
            "processed_discussion_ids": ["d1"],
            "last_scan_time": "2026-07-18T00:00:00Z",
        }
    )

    loaded = comment_sync_state.load_comment_state()

    assert loaded["processed_comment_ids"] == ["c1", "c2"]
    assert loaded["processed_discussion_ids"] == ["d1"]
    assert loaded["last_scan_time"] == "2026-07-18T00:00:00Z"


def test_sync_vocab_comments_skips_processed_comment(monkeypatch) -> None:
    notion = FakeNotion(
        pages=[{"id": "podcast_1", "properties": {}}],
        block_children={
            "podcast_1": [{"id": "block_1", "type": "paragraph"}],
            "block_1": [],
        },
    )

    comment_sync_state.save_comment_state(
        {
            "processed_comment_ids": ["c1"],
            "processed_discussion_ids": [],
            "last_scan_time": "",
        }
    )

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.load_notion_config",
        lambda: SimpleNamespace(token="secret", podcast_database_id="podcast_db", vocabulary_database_id="vocab_db"),
    )
    monkeypatch.setattr("src.notion.comment_vocab_sync.create_notion_client", lambda token: notion)
    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.httpx.Client",
        lambda timeout=None: FakeHttpxClient(
            lambda *args, **kwargs: FakeResponse(
                [
                    {
                        "id": "c1",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                        "highlighted_text": "reframes",
                        "context": "This episode reframes negotiation as relationship management.",
                        "created_time": "2026-07-18T20:00:00.000Z",
                    },
                    {
                        "id": "c2",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                        "highlighted_text": "assumptions",
                        "context": "Question assumptions when surprises appear.",
                        "created_time": "2026-07-18T21:00:00.000Z",
                    },
                ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )

    calls = {}

    def fake_upsert_vocabulary_page(payload, notion, vocabulary_database_id):
        calls["payload"] = payload
        return type(
            "Result",
            (),
            {
                "action": "created",
                "page_id": "vocab_1",
                "page_url": "https://notion.so/vocab_1",
            },
        )()

    monkeypatch.setattr("src.notion.comment_vocab_sync.upsert_vocabulary_page", fake_upsert_vocabulary_page)

    result = sync_vocab_comments()

    assert result.created == 1
    assert calls["payload"]["word"] == "assumption"


def test_sync_vocab_comments_new_trigger_three_enters_flow(monkeypatch) -> None:
    notion = FakeNotion(
        pages=[{"id": "podcast_1", "properties": {}}],
        block_children={
            "podcast_1": [{"id": "block_1", "type": "paragraph"}],
            "block_1": [],
        },
    )

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.load_notion_config",
        lambda: SimpleNamespace(token="secret", podcast_database_id="podcast_db", vocabulary_database_id="vocab_db"),
    )
    monkeypatch.setattr("src.notion.comment_vocab_sync.create_notion_client", lambda token: notion)
    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.httpx.Client",
        lambda timeout=None: FakeHttpxClient(
            lambda *args, **kwargs: FakeResponse(
                [
                    {
                        "id": "c3",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                        "highlighted_text": "reframes",
                        "context": "This episode reframes negotiation as relationship management.",
                        "created_time": "2026-07-18T22:00:00.000Z",
                    }
                ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )

    calls = {}

    def fake_upsert_vocabulary_page(payload, notion, vocabulary_database_id):
        calls["payload"] = payload
        return type(
            "Result",
            (),
            {
                "action": "created",
                "page_id": "vocab_2",
                "page_url": "https://notion.so/vocab_2",
            },
        )()

    monkeypatch.setattr("src.notion.comment_vocab_sync.upsert_vocabulary_page", fake_upsert_vocabulary_page)

    result = sync_vocab_comments()

    assert result.created == 1
    assert calls["payload"]["word"] == "reframe"
