from __future__ import annotations

from pathlib import Path

from src.agent import highlight_state
from src.agent.vocabulary_sync_agent import sync_vocabulary_from_highlight_changes


def test_sync_vocabulary_from_highlight_changes_processes_only_new_highlights(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "highlight_sync_state.json"
    highlight_state.save_highlight_state(
        {
            "last_scan_time": "2026-07-18T10:00:00Z",
            "processed_highlights_by_page": {"page_1": ["assumption"]},
        },
        path=state_path,
    )

    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.scan_changed_podcast_pages",
        lambda notion=None, podcast_database_id=None, last_scan_time="": [
            type("ChangedPage", (), {"page_id": "page_1", "last_edited_time": "2026-07-19T12:00:00Z"})()
        ],
    )
    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.read_pink_highlights",
        lambda page_id, notion=None: [
            {"text": "assumption", "context": "assumption context", "color": "pink_background"},
            {"text": "fundraising", "context": "fundraising context", "color": "pink_background"},
        ],
    )
    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.enrich_vocabulary_candidates",
        lambda items, provider=None: [
            {
                "word": item["word"],
                "original_context": item["context"],
                "meaning": f"Meaning for {item['word']}",
                "chinese_meaning": "中文",
                "part_of_speech": "noun",
                "professional_category": "Business Phrase",
                "usage_example": f"Use {item['word']} in context.",
                "common_collocations": ["one", "two"],
                "source_page_id": item["source_page_id"],
            }
            for item in items
        ],
    )

    calls = []

    def fake_upsert(payload, notion=None, vocabulary_database_id=None):
        calls.append((payload.word, vocabulary_database_id))
        return type(
            "Result",
            (),
            {"action": "created", "page_id": "vocab_1", "page_url": None},
        )()

    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.upsert_vocabulary_page",
        fake_upsert,
    )

    result = sync_vocabulary_from_highlight_changes(
        notion=object(),
        podcast_database_id="podcast_db",
        vocabulary_database_id="vocab_db",
        state_path=state_path,
    )

    assert result.new_highlights == 1
    assert result.created == 1
    assert calls == [("fundraising", "vocab_db")]

    saved = highlight_state.load_highlight_state(path=state_path)
    assert saved["processed_highlights_by_page"]["page_1"] == ["assumption", "fundraising"]


def test_sync_vocabulary_from_highlight_changes_is_idempotent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "highlight_sync_state.json"
    highlight_state.save_highlight_state(
        {
            "last_scan_time": "2026-07-18T10:00:00Z",
            "processed_highlights_by_page": {"page_1": ["assumption", "fundraising"]},
        },
        path=state_path,
    )

    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.scan_changed_podcast_pages",
        lambda notion=None, podcast_database_id=None, last_scan_time="": [
            type("ChangedPage", (), {"page_id": "page_1", "last_edited_time": "2026-07-19T12:00:00Z"})()
        ],
    )
    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.read_pink_highlights",
        lambda page_id, notion=None: [
            {"text": "assumption", "context": "assumption context", "color": "pink_background"},
            {"text": "fundraising", "context": "fundraising context", "color": "pink_background"},
        ],
    )

    def fail_enrich(items, provider=None):  # pragma: no cover - should not be called
        raise AssertionError("enrichment should not be called for already processed highlights")

    monkeypatch.setattr("src.agent.vocabulary_sync_agent.enrich_vocabulary_candidates", fail_enrich)

    calls = []

    def fake_upsert(payload, notion=None, vocabulary_database_id=None):  # pragma: no cover
        calls.append(payload.word)
        return type(
            "Result",
            (),
            {"action": "created", "page_id": "vocab_1", "page_url": None},
        )()

    monkeypatch.setattr("src.agent.vocabulary_sync_agent.upsert_vocabulary_page", fake_upsert)

    result = sync_vocabulary_from_highlight_changes(
        notion=object(),
        podcast_database_id="podcast_db",
        vocabulary_database_id="vocab_db",
        state_path=state_path,
    )

    assert result.new_highlights == 0
    assert result.created == 0
    assert calls == []


def test_sync_vocabulary_from_highlight_changes_normalizes_case_and_plural(
    monkeypatch,
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "highlight_sync_state.json"
    highlight_state.save_highlight_state(
        {
            "last_scan_time": "2026-07-18T10:00:00Z",
            "processed_highlights_by_page": {"page_1": ["Fundraising"]},
        },
        path=state_path,
    )

    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.scan_changed_podcast_pages",
        lambda notion=None, podcast_database_id=None, last_scan_time="": [
            type("ChangedPage", (), {"page_id": "page_1", "last_edited_time": "2026-07-19T12:00:00Z"})()
        ],
    )
    monkeypatch.setattr(
        "src.agent.vocabulary_sync_agent.read_pink_highlights",
        lambda page_id, notion=None: [
            {"text": "fundraisings", "context": "fundraisings context", "color": "pink_background"},
        ],
    )

    def fail_enrich(items, provider=None):  # pragma: no cover - should not be called
        raise AssertionError("normalized duplicate should be skipped")

    monkeypatch.setattr("src.agent.vocabulary_sync_agent.enrich_vocabulary_candidates", fail_enrich)

    result = sync_vocabulary_from_highlight_changes(
        notion=object(),
        podcast_database_id="podcast_db",
        vocabulary_database_id="vocab_db",
        state_path=state_path,
    )

    assert result.new_highlights == 0
    assert result.created == 0
