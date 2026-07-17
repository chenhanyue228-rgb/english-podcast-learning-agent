import pytest

from src.analyzer.expression_analyzer import (
    ExpressionAnalysisInput,
    ExpressionAnalyzer,
    ExpressionAnalyzerError,
    validate_expression_output,
)
from src.analyzer.prompt_loader import load_expression_prompt


class FakeAIClient:
    def __init__(self, output):
        self.output = output
        self.calls = []

    def analyze_json(self, prompt, payload):
        self.calls.append((prompt, payload))
        return self.output


def expression_output():
    return {
        "learning_items": [
            {
                "text": "move the needle",
                "category": "Native Expression",
                "meaning": "Create meaningful impact.",
                "chinese_meaning": "产生实质性影响",
                "usage_context": "Use it when describing visible results.",
                "context_sentence": "We need to move the needle.",
                "example_sentence": "This campaign moved the needle on signups.",
                "commonness": "High",
                "highlight_color": "green",
            },
            {
                "text": "take ownership",
                "category": "Business Phrase",
                "meaning": "Accept responsibility.",
                "chinese_meaning": "承担责任",
                "usage_context": "Use it for accountability at work.",
                "context_sentence": "Teams must take ownership.",
                "example_sentence": "She took ownership of the launch.",
                "commonness": "High",
                "highlight_color": "blue",
            },
            {
                "text": "operational leverage",
                "category": "Industry Term",
                "meaning": "Efficiency that increases output.",
                "commonness": "Medium",
                "highlight_color": "yellow",
            },
            {
                "text": "leadership gap",
                "category": "Collocation",
                "meaning": "A lack of effective leadership.",
                "commonness": "Medium",
                "highlight_color": "purple",
            },
            {
                "text": "What we're seeing is...",
                "category": "Sentence Pattern",
                "meaning": "Introduce an observed trend.",
                "commonness": "High",
                "highlight_color": "orange",
            },
        ]
    }


def test_expression_analysis_input_builds_payload() -> None:
    payload = ExpressionAnalysisInput(
        title="Podcast",
        transcript="Transcript text",
    ).to_payload()

    assert payload == {"title": "Podcast", "transcript": "Transcript text"}


def test_expression_analyzer_calls_ai_client_with_prompt() -> None:
    client = FakeAIClient(expression_output())
    analyzer = ExpressionAnalyzer(ai_client=client, prompt="expression prompt")

    result = analyzer.analyze("Transcript text", title="Podcast")

    assert [item.category for item in result] == [
        "Native Expression",
        "Business Phrase",
        "Industry Term",
        "Collocation",
        "Sentence Pattern",
    ]
    assert result[0].text == "move the needle"
    assert result[1].usage_context == "Use it for accountability at work."
    assert client.calls == [
        (
            "expression prompt",
            {"title": "Podcast", "transcript": "Transcript text"},
        )
    ]


def test_validate_expression_output_normalizes_color_and_deduplicates() -> None:
    payload = expression_output()
    payload["learning_items"].append(
        {
            "text": "move the needle",
            "category": "Native Expression",
            "meaning": "Duplicate item.",
        }
    )
    payload["learning_items"][0]["highlight_color"] = ""
    payload["learning_items"][0]["commonness"] = "Common"

    result = validate_expression_output(payload)

    assert len(result) == 5
    assert result[0].highlight_color == "green"
    assert result[0].commonness == "High"
    assert result[0].quality_score >= 90


def test_expression_analyzer_requires_transcript() -> None:
    analyzer = ExpressionAnalyzer(
        ai_client=FakeAIClient(expression_output()),
        prompt="expression prompt",
    )

    with pytest.raises(ExpressionAnalyzerError, match="Transcript text"):
        analyzer.analyze(" ")


def test_validate_expression_output_requires_learning_items_list() -> None:
    with pytest.raises(ExpressionAnalyzerError, match="learning_items"):
        validate_expression_output({"learning_items": "wrong"})


def test_validate_expression_output_rejects_simple_invalid_items() -> None:
    with pytest.raises(ExpressionAnalyzerError, match="meaning"):
        validate_expression_output(
            {
                "learning_items": [
                    {
                        "text": "the",
                        "category": "Native Expression",
                        "meaning": "",
                    }
                ]
            }
        )


def test_load_expression_prompt_reads_prompt_file() -> None:
    prompt = load_expression_prompt()

    assert "Expression Prompt" in prompt
    assert "Business Phrase" in prompt
