from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.notion.comment_vocab_sync import (
    _extract_context_from_comment,
    _extract_highlighted_text_from_comment,
    _is_trigger_comment,
    _normalize_vocab_candidate,
    _normalize_comment_text,
    debug_comment_sources,
    _iter_vocab_comment_records,
    fetch_page_comments_raw,
    debug_comment_sync,
    debug_page_comments,
    sync_vocab_comments,
)
from src.notion import comment_sync_state


@pytest.fixture(autouse=True)
def isolated_comment_state(tmp_path, monkeypatch):
    monkeypatch.setattr(
        comment_sync_state,
        "COMMENT_SYNC_STATE_PATH",
        tmp_path / "comment_sync_state.json",
    )
    yield


class FakeDataSources:
    def __init__(self, results=None):
        self.results = results or []
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {"results": self.results}


class FakePages:
    def __init__(self):
        self.update_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"], "url": "https://notion.so/vocab_page"}

    def create(self, **kwargs):
        return {"id": "created_page", "url": "https://notion.so/created_page"}


class FakeBlockChildren:
    def __init__(self, results=None):
        self.results = results or []
        self.list_calls = []

    def list(self, **kwargs):
        self.list_calls.append(kwargs)
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
        self.get_calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, headers=None, params=None):
        call = {"url": url, "headers": headers, "params": params}
        self.get_calls.append(call)
        return self.handler(url, headers=headers, params=params)


def test_comment_trigger_three() -> None:
    assert _is_trigger_comment("3") is True
    assert _is_trigger_comment("3 ") is True
    assert _is_trigger_comment(" 3") is True
    assert _is_trigger_comment("33") is False
    assert _is_trigger_comment("3 vocab") is False
    assert _is_trigger_comment("?vocab") is False
    assert _is_trigger_comment("hello") is False


def test_extract_highlighted_text_from_comment_prefers_anchor_fields() -> None:
    comment = {
        "anchor_text": "reframes",
        "context": "This episode reframes negotiation as relationship management.",
    }
    assert _extract_highlighted_text_from_comment(comment) == "reframes"
    assert _extract_context_from_comment(comment) == "This episode reframes negotiation as relationship management."


def test_normalize_vocab_candidate_handles_basic_inflection() -> None:
    assert _normalize_vocab_candidate("reframes") == "reframe"
    assert _normalize_vocab_candidate("leverages") == "leverage"


def test_normalize_comment_text_handles_rich_text() -> None:
    comment = {
        "rich_text": [
            {"plain_text": "3", "text": {"content": "3"}},
        ]
    }
    assert _normalize_comment_text(comment) == "3"


def test_sync_vocab_comments_uses_block_comments(monkeypatch) -> None:
    notion = FakeNotion(
        pages=[{"id": "podcast_1", "properties": {}}],
        block_children={
            "podcast_1": [{"id": "block_1", "type": "paragraph", "has_children": False}],
            "block_1": [],
        },
    )

    calls = {}

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.load_notion_config",
        lambda: SimpleNamespace(token="secret", podcast_database_id="podcast_db", vocabulary_database_id="vocab_db"),
    )
    monkeypatch.setattr("src.notion.comment_vocab_sync.create_notion_client", lambda token: notion)

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["request"] = {
            "url": url,
            "headers": headers,
            "params": params,
        }
        assert params == {"block_id": "block_1"}
        return FakeResponse(
            [
                {
                    "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                    "highlighted_text": "reframes",
                    "context": "This episode reframes negotiation as relationship management.",
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
        )

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.httpx.Client",
        lambda timeout=None: FakeHttpxClient(fake_get, timeout=timeout),
    )

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

    assert result.scanned_pages == 1
    assert result.scanned_comments == 1
    assert result.matched_comments == 1
    assert result.created == 1
    assert calls["request"]["params"] == {"block_id": "block_1"}
    assert calls["payload"]["word"] == "reframe"
    assert calls["payload"]["original_context"] == "This episode reframes negotiation as relationship management."
    assert calls["payload"]["source_page_id"] == "podcast_1"
    assert notion.blocks.children.list_calls == [{"block_id": "podcast_1", "page_size": 100}]


def test_sync_vocab_comments_skips_without_highlight(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )
    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.upsert_vocabulary_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Should not upsert without highlighted text")),
    )

    result = sync_vocab_comments()
    captured = capsys.readouterr().out

    assert result.scanned_pages == 1
    assert result.scanned_comments == 1
    assert result.matched_comments == 0
    assert result.created == 0
    assert "SKIPPED VOCAB COMMENT" in captured
    assert "reason: highlight unavailable" in captured


def test_sync_vocab_comments_logs_existing_vocabulary(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                    "highlighted_text": "reframes",
                    "context": "This episode reframes negotiation as relationship management.",
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.upsert_vocabulary_page",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "action": "updated",
                "page_id": "vocab_1",
                "page_url": "https://notion.so/vocab_1",
            },
        )(),
    )

    result = sync_vocab_comments()
    captured = capsys.readouterr().out

    assert result.updated == 1
    assert "SKIPPED VOCAB COMMENT" in captured
    assert "reason: existing vocabulary entry" in captured


def test_sync_vocab_comments_logs_empty_word(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                    "highlighted_text": "!!!",
                    "context": "This episode reframes negotiation as relationship management.",
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )
    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.upsert_vocabulary_page",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Should not upsert empty words")),
    )

    result = sync_vocab_comments()
    captured = capsys.readouterr().out

    assert result.created == 0
    assert "SKIPPED VOCAB COMMENT" in captured
    assert "reason: empty extracted word" in captured


def test_sync_vocab_comments_logs_unsupported_format(capsys) -> None:
    result = _iter_vocab_comment_records(
        page_id="podcast_1",
        block_id="",
        comments=[
            {
                "id": "c1",
                "parent": {},
                "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                "created_time": "2026-07-17T20:00:00.000Z",
            }
        ],
    )
    captured = capsys.readouterr().out

    assert result == []
    assert "SKIPPED VOCAB COMMENT" in captured
    assert "reason: highlight unavailable" in captured


def test_sync_vocab_comments_prints_timing(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                    "highlighted_text": "reframes",
                    "context": "This episode reframes negotiation as relationship management.",
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )
    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.upsert_vocabulary_page",
        lambda *args, **kwargs: type(
            "Result",
            (),
            {
                "action": "created",
                "page_id": "vocab_1",
                "page_url": "https://notion.so/vocab_1",
            },
        )(),
    )

    sync_vocab_comments()
    captured = capsys.readouterr().out

    assert "[SYNCH START]" in captured
    assert "1. query podcast pages:" in captured
    assert "2. fetch comments:" in captured
    assert "3. matched trigger comments:" in captured
    assert "Highlighted words extracted:" in captured
    assert "4. vocabulary upsert:" in captured
    assert "Vocabulary created:" in captured
    assert "Vocabulary updated:" in captured
    assert "TOTAL TIME:" in captured


def test_debug_comment_sync_prints_raw_comments(monkeypatch, capsys) -> None:
    notion = FakeNotion(
        pages=[{"id": "podcast_1", "properties": {}}],
        block_children={
            "podcast_1": [{"id": "block_1", "type": "paragraph"}, {"id": "block_2", "type": "paragraph"}],
            "block_1": [],
            "block_2": [],
        },
    )

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.load_notion_config",
        lambda: SimpleNamespace(token="secret", podcast_database_id="podcast_db", vocabulary_database_id="vocab_db"),
    )
    monkeypatch.setattr("src.notion.comment_vocab_sync.create_notion_client", lambda token: notion)
    def fake_get(url, headers=None, params=None, timeout=None):
        block_id = (params or {}).get("block_id")
        if block_id == "block_1":
            return FakeResponse(
                [
                    {
                        "id": "c1",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "hello", "text": {"content": "hello"}}],
                        "created_time": "2026-07-17T20:00:00.000Z",
                    }
                ]
            )
        return FakeResponse([])

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.httpx.Client",
        lambda timeout=None: FakeHttpxClient(fake_get, timeout=timeout),
    )

    count = debug_comment_sync()
    captured = capsys.readouterr().out

    assert count == 1
    assert "Scanning pages: 1/1" in captured
    assert "Scanning blocks: 1/20" in captured
    assert "Page: podcast_1" in captured
    assert "Block: block_1" in captured
    assert "Comment ID: c1" in captured
    assert "Comment text: hello" in captured
    assert "Parent type: block_id" in captured
    assert "Highlighted text:" in captured


def test_debug_page_comments_uses_block_id(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                    "parent": {"type": "block_id", "block_id": "block_1"},
                    "rich_text": [{"plain_text": "hello", "text": {"content": "hello"}}],
                    "created_time": "2026-07-17T20:00:00.000Z",
                }
            ]
            ),
            timeout=timeout,
        ),
    )

    count = debug_page_comments()
    captured = capsys.readouterr().out

    assert count == 1
    assert "Scanning pages: 1/1" in captured
    assert "Scanning blocks: 1/20" in captured
    assert "page_id=podcast_1" in captured
    assert "block_id=block_1" in captured
    assert "comment_id=c1" in captured
    assert "created_time=2026-07-17T20:00:00.000Z" in captured


def test_fetch_page_comments_raw_uses_block_id(monkeypatch) -> None:
    calls = {}

    class RawResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {
                "results": [
                    {
                        "id": "c1",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "hello", "text": {"content": "hello"}}],
                        "created_time": "2026-07-17T20:00:00.000Z",
                    }
                ]
            }

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.load_notion_config",
        lambda: SimpleNamespace(token="secret", podcast_database_id="podcast_db", vocabulary_database_id="vocab_db"),
    )

    def fake_get(url, headers=None, params=None, timeout=None):
        calls["request"] = {
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
        }
        return RawResponse()

    monkeypatch.setattr(
        "src.notion.comment_vocab_sync.httpx.Client",
        lambda timeout=None: FakeHttpxClient(fake_get, timeout=timeout),
    )

    results = fetch_page_comments_raw("block_1")

    assert calls["request"]["url"] == "https://api.notion.com/v1/comments"
    assert calls["request"]["params"] == {"block_id": "block_1"}
    assert calls["request"]["headers"]["Authorization"] == "Bearer secret"
    assert results[0]["id"] == "c1"


def test_debug_comment_sources_prints_summaries(monkeypatch, capsys) -> None:
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
                        "id": "c1",
                        "parent": {"type": "block_id", "block_id": "block_1"},
                        "rich_text": [{"plain_text": "3", "text": {"content": "3"}}],
                        "discussion": {
                            "id": "discussion_1",
                            "rangeText": "assumptions",
                            "comments": [{"id": "c1", "text": "3"}],
                        },
                        "created_time": "2026-07-18T20:00:00.000Z",
                    }
                ]
            )
            if (kwargs or {}).get("params") == {"block_id": "block_1"}
            else FakeResponse([]),
            timeout=timeout,
        ),
    )

    count = debug_comment_sources()
    captured = capsys.readouterr().out

    assert count == 1
    assert "DEBUG COMMENT SUMMARY" in captured
    assert "page_id: podcast_1" in captured
    assert "block_id: block_1" in captured
    assert "comment_id: c1" in captured
    assert "comment_text: 3" in captured
    assert "discussion_id: discussion_1" in captured
    assert "rangeText: assumptions" in captured
    assert "source_structure: discussion" in captured


def test_iter_vocab_comment_records_supports_discussion_shape() -> None:
    records = _iter_vocab_comment_records(
        page_id="podcast_1",
        block_id="block_1",
        comments=[
            {
                "id": "discussion_1",
                "discussion": {
                    "rangeText": "assumptions",
                    "comments": [
                        {
                            "id": "comment_1",
                            "text": "3",
                        }
                    ],
                },
            }
        ],
    )

    assert len(records) == 1
    assert records[0].highlighted_text == "assumptions"
    assert records[0].comment_text == "3"


def test_sync_vocab_comments_supports_discussion_reader_adapter(monkeypatch) -> None:
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

    def fake_fetch_page_comments_raw(block_id):
        assert block_id == "block_1"
        return [
            {
                "id": "discussion_1",
                "discussion": {
                    "id": "discussion_1",
                    "rangeText": "assumptions",
                    "comments": [
                        {
                            "id": "comment_1",
                            "text": "3",
                        }
                    ],
                },
            }
        ]

    monkeypatch.setattr("src.notion.comment_vocab_sync.fetch_page_comments_raw", fake_fetch_page_comments_raw)

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
