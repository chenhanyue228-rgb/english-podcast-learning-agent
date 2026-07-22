from __future__ import annotations

import pytest

import src.memory.vocabulary_capture as vocabulary_capture
from src.memory.vocabulary_capture import (
    VocabularyCaptureError,
    build_vocabulary_record,
    is_vocab_trigger,
    prepare_vocabulary_memory,
    parse_vocabulary_annotation,
)


def test_is_vocab_trigger_matches_manual_comment() -> None:
    assert is_vocab_trigger("?vocab")
    assert is_vocab_trigger("  ?vocab  ")
    assert is_vocab_trigger("Please capture this ?vocab")


def test_build_vocabulary_record_uses_manual_trigger_only() -> None:
    record = build_vocabulary_record(
        highlighted_text="leverage",
        comment_text="?vocab",
        context="Companies can leverage AI to move faster.",
        source="Podcast Library",
        page_id="page_123",
    )

    assert record == {
        "type": "vocabulary",
        "word": "leverage",
        "original_context": "Companies can leverage AI to move faster.",
        "meaning": "",
        "professional_category": "",
        "source": "Podcast Library",
        "source_page_id": "page_123",
        "first_seen": record["first_seen"],
        "review_status": "New",
        "last_review": "",
        "usage_example": "",
        "personal_note": "",
    }


def test_build_vocabulary_record_rejects_missing_trigger() -> None:
    with pytest.raises(VocabularyCaptureError, match="trigger"):
        build_vocabulary_record(
            highlighted_text="leverage",
            comment_text="capture this",
            context="Companies can leverage AI to move faster.",
            source="Podcast Library",
            page_id="page_123",
        )


def test_parse_vocabulary_annotation_returns_none_without_trigger() -> None:
    assert (
        parse_vocabulary_annotation(
            {
                "text": "leverage",
                "comment": "nice phrase",
                "context": "Companies can leverage AI to move faster.",
                "source": "Podcast Library",
                "page_id": "page_123",
            }
        )
        is None
    )


def test_prepare_vocabulary_memory_includes_review_fields(monkeypatch) -> None:
    class FixedDate:
        @staticmethod
        def today() -> object:
            class _Day:
                @staticmethod
                def isoformat() -> str:
                    return "2026-07-17"

            return _Day()

    monkeypatch.setattr(vocabulary_capture, "date", FixedDate)

    record = prepare_vocabulary_memory(
        highlighted_text="leverage",
        comment_text="?vocab",
        context="Companies can leverage AI to move faster.",
        source="Podcast Library",
        page_id="page_123",
        meaning="Use resources effectively.",
        professional_category="Word",
        usage_example="We can leverage AI tools to save time.",
        personal_note="A reusable business verb.",
        last_review="2026-07-17",
    )

    assert record == {
        "type": "vocabulary",
        "word": "leverage",
        "original_context": "Companies can leverage AI to move faster.",
        "meaning": "Use resources effectively.",
        "professional_category": "Word",
        "source": "Podcast Library",
        "source_page_id": "page_123",
        "first_seen": "2026-07-17",
        "review_status": "New",
        "last_review": "2026-07-17",
        "usage_example": "We can leverage AI tools to save time.",
        "personal_note": "A reusable business verb.",
    }


def test_parse_vocabulary_annotation_builds_record_with_trigger() -> None:
    record = parse_vocabulary_annotation(
        {
            "text": "leverage",
            "comment": "?vocab",
            "context": "Companies can leverage AI to move faster.",
            "source": "Podcast Library",
            "page_id": "page_123",
        }
    )

    assert record == {
        "type": "vocabulary",
        "word": "leverage",
        "original_context": "Companies can leverage AI to move faster.",
        "meaning": "",
        "professional_category": "",
        "source": "Podcast Library",
        "source_page_id": "page_123",
        "review_status": "New",
        "last_review": "",
        "usage_example": "",
        "personal_note": "",
        "first_seen": record["first_seen"],
    }
