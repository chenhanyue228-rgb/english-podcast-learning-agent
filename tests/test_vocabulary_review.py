from __future__ import annotations

from src.workflow.vocabulary_review import approve_vocabulary_items, review_vocabulary_items


def test_review_vocabulary_items_marks_conversation_pending() -> None:
    result = review_vocabulary_items(
        [
            {
                "word": "conversation",
            }
        ]
    )

    assert len(result["pending_vocabulary"]) == 1
    assert result["pending_vocabulary"][0]["word"] == "conversation"
    assert result["pending_vocabulary"][0]["review_status"] == "pending"
    assert result["approved"] == []
    assert result["rejected"] == []


def test_approve_vocabulary_items_promotes_pending_item() -> None:
    result = approve_vocabulary_items(
        [
            {
                "word": "conversation",
            }
        ]
    )

    assert len(result["approved"]) == 1
    assert result["approved"][0]["word"] == "conversation"
    assert result["approved"][0]["review_status"] == "approved"
    assert result["pending_vocabulary"] == []
    assert result["rejected"] == []
