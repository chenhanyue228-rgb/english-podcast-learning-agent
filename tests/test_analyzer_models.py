from src.analyzer.models import (
    AIAnalysisResult,
    LearningItem,
    LearningNote,
    PodcastMetadata,
    SentencePattern,
    Summary,
)


def test_ai_analysis_result_serializes_all_sections() -> None:
    result = AIAnalysisResult(
        summary=Summary("English", "中文", ["point"]),
        podcast_metadata=PodcastMetadata(
            topic="AI",
            difficulty="Intermediate",
            short_summary="Short",
        ),
        learning_items=[
            LearningItem(
                text="take ownership",
                category="Business Phrase",
                meaning="Accept responsibility",
                commonness="High",
            )
        ],
        sentence_patterns=[
            SentencePattern(
                text="What we're seeing is...",
                meaning="Describe an observed trend.",
                commonness="Medium",
            )
        ],
        learning_notes=[LearningNote("Note", "English note", "中文说明")],
    )

    payload = result.to_dict()

    assert payload["summary"]["english"] == "English"
    assert payload["podcast_metadata"]["topic"] == "AI"
    assert payload["learning_items"][0]["text"] == "take ownership"
    assert payload["learning_items"][0]["commonness"] == "High"
    assert payload["sentence_patterns"][0]["category"] == "Sentence Pattern"
    assert payload["learning_notes"][0]["title"] == "Note"
    assert len(result.all_learning_items()) == 2
