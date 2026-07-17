import pytest

from src.analyzer.metadata_analyzer import (
    MetadataAnalysisInput,
    MetadataAnalyzerError,
    PodcastMetadataAnalyzer,
    validate_metadata_output,
)
from src.analyzer.prompt_loader import load_metadata_prompt


class FakeAIClient:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def analyze_json(self, prompt, payload):
        self.calls.append((prompt, payload))
        return self.output


def metadata_output():
    return {
        "podcast_metadata": {
            "title": "AI Transformation in Business",
            "topic": "AI",
            "difficulty": "Intermediate",
            "short_summary": "A short discussion about AI adoption.",
        }
    }


def test_metadata_analysis_input_builds_payload() -> None:
    payload = MetadataAnalysisInput(
        title="Podcast",
        transcript="Transcript text",
    ).to_payload()

    assert payload == {"title": "Podcast", "transcript": "Transcript text"}


def test_podcast_metadata_analyzer_calls_ai_client_with_prompt() -> None:
    client = FakeAIClient(metadata_output())
    analyzer = PodcastMetadataAnalyzer(ai_client=client, prompt="metadata prompt")

    result = analyzer.analyze("Transcript text", title="Podcast")

    assert result.topic == "AI"
    assert result.difficulty == "Intermediate"
    assert result.short_summary == "A short discussion about AI adoption."
    assert client.calls == [
        (
            "metadata prompt",
            {"title": "Podcast", "transcript": "Transcript text"},
        )
    ]


def test_podcast_metadata_analyzer_requires_transcript() -> None:
    analyzer = PodcastMetadataAnalyzer(
        ai_client=FakeAIClient(metadata_output()),
        prompt="metadata prompt",
    )

    with pytest.raises(MetadataAnalyzerError, match="Transcript text"):
        analyzer.analyze(" ")


def test_validate_metadata_output_requires_all_fields() -> None:
    payload = metadata_output()
    payload["podcast_metadata"]["short_summary"] = ""

    with pytest.raises(MetadataAnalyzerError, match="short_summary"):
        validate_metadata_output(payload)


def test_validate_metadata_output_rejects_invalid_difficulty() -> None:
    payload = metadata_output()
    payload["podcast_metadata"]["difficulty"] = "Expert"

    with pytest.raises(MetadataAnalyzerError, match="difficulty"):
        validate_metadata_output(payload)


def test_load_metadata_prompt_reads_prompt_file() -> None:
    prompt = load_metadata_prompt()

    assert "Metadata Prompt" in prompt
    assert "podcast_metadata" in prompt
