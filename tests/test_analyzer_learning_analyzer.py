import pytest

from src.analyzer.learning_analyzer import (
    LearningAnalyzer,
    LearningAnalyzerError,
    TranscriptAnalysisInput,
    merge_analysis_outputs,
)
from src.analyzer.prompt_loader import AnalyzerPrompts


def valid_generated_output():
    return {
        "summary": {
            "english": "English summary",
            "chinese": "中文总结",
            "key_points": ["Point"],
        },
        "podcast_metadata": {
            "topic": "AI",
            "difficulty": "Intermediate",
            "short_summary": "Short",
        },
        "learning_items": [
            {
                "text": "take ownership",
                "category": "Business Phrase",
                "meaning": "Accept responsibility",
                "commonness": "High",
            }
        ],
        "learning_notes": [
            {"title": "Note", "note": "Learning note"}
        ],
    }


def test_merge_analysis_outputs_combines_prompt_results() -> None:
    merged = merge_analysis_outputs(
        summary_output={"summary": {"english": "A"}},
        metadata_output={"podcast_metadata": {"topic": "AI"}},
        expression_output={"learning_items": [{"text": "a"}]},
    )

    assert merged["summary"] == {"english": "A"}
    assert merged["podcast_metadata"] == {"topic": "AI"}
    assert [item["text"] for item in merged["learning_items"]] == ["a"]


def test_learning_analyzer_prepares_skill_analysis_request() -> None:
    analyzer = LearningAnalyzer(
        prompts=AnalyzerPrompts(
            summary="summary prompt",
            metadata="metadata prompt",
            expression="expression prompt",
        ),
        schema={"type": "object"},
    )

    request = analyzer.prepare_analysis_request(
        TranscriptAnalysisInput(title="Podcast", transcript="Transcript text")
    )

    assert request.title == "Podcast"
    assert request.transcript == "Transcript text"
    assert request.prompts.summary == "summary prompt"
    assert request.schema == {"type": "object"}
    assert request.to_dict()["prompts"]["expression"] == "expression prompt"


def test_learning_analyzer_validates_generated_json() -> None:
    analyzer = LearningAnalyzer(
        prompts=AnalyzerPrompts("summary", "metadata", "expression"),
        schema={"type": "object"},
    )

    result = analyzer.validate_generated_analysis(valid_generated_output())

    assert result.summary.english == "English summary"
    assert result.podcast_metadata.topic == "AI"
    assert result.learning_items[0].category == "Business Phrase"
    assert result.learning_notes[0].title == "Note"


def test_learning_analyzer_requires_transcript_text() -> None:
    analyzer = LearningAnalyzer(
        prompts=AnalyzerPrompts("summary", "metadata", "expression"),
        schema={"type": "object"},
    )

    with pytest.raises(LearningAnalyzerError, match="Transcript text"):
        analyzer.prepare_analysis_request(
            TranscriptAnalysisInput(title="Podcast", transcript=" ")
        )
