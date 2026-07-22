from __future__ import annotations

from src.workflow.vocabulary_candidate_filter import filter_vocabulary_candidates


def test_filter_vocabulary_candidates_separates_person_name_and_english_word() -> None:
    result = filter_vocabulary_candidates(
        [
            {"word": "Christensen", "context": "Stan Christensen explains the idea."},
            {"word": "conversation", "context": "The conversation also shows how to negotiate with investors."},
        ]
    )

    assert len(result.approved) == 1
    assert len(result.rejected) == 1
    assert result.rejected[0]["word"] == "Christensen"
    assert result.rejected[0]["reason"] == "person name"
    assert result.approved[0]["word"] == "conversation"
