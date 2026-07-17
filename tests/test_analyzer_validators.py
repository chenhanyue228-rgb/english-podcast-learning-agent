import pytest

from src.analyzer.validators import (
    AnalysisValidationError,
    normalize_category,
    validate_ai_analysis,
)


def valid_payload():
    return {
        "summary": {
            "english": "English summary",
            "chinese": "中文总结",
            "key_points": ["Point 1"],
        },
        "podcast_metadata": {
            "title": "AI Transformation in Business",
            "topic": "AI",
            "difficulty": "Intermediate",
            "short_summary": "Short",
        },
        "learning_items": [
            {
                "text": "take ownership",
                "category": "Business Expression",
                "meaning": "Accept responsibility",
                "commonness": "High",
                "confidence": 1.5,
            },
            {
                "text": "take ownership",
                "category": "Business Phrase",
                "meaning": "Duplicate",
                "commonness": "Medium",
            },
        ],
        "sentence_patterns": [
            {
                "text": "What we're seeing is...",
                "meaning": "Describe an observed trend.",
                "commonness": "High",
            }
        ],
        "learning_notes": [
            {
                "title": "Business language",
                "note": "Notice accountability language.",
                "chinese_note": "注意责任相关表达。",
            }
        ],
    }


def test_normalize_category_maps_business_expression_to_business_phrase() -> None:
    assert normalize_category("Business Expression") == "Business Phrase"


def test_validate_ai_analysis_normalizes_and_deduplicates() -> None:
    result = validate_ai_analysis(valid_payload())

    assert result.summary.english == "English summary"
    assert result.podcast_metadata.title == "AI Transformation in Business"
    assert result.podcast_metadata.topic == "AI"
    assert len(result.learning_items) == 1
    assert result.learning_items[0].category == "Business Phrase"
    assert result.learning_items[0].highlight_color == "blue"
    assert result.learning_items[0].commonness == "High"
    assert result.learning_items[0].confidence == 1.0
    assert result.learning_items[0].quality_score >= 90
    assert result.sentence_patterns[0].category == "Sentence Pattern"
    assert result.learning_notes[0].title == "Business language"


def test_validate_ai_analysis_requires_summary_english() -> None:
    payload = valid_payload()
    payload["summary"]["english"] = ""

    with pytest.raises(AnalysisValidationError, match="summary.english"):
        validate_ai_analysis(payload)


def test_validate_ai_analysis_rejects_unknown_category() -> None:
    payload = valid_payload()
    payload["learning_items"][0]["category"] = "Random"

    with pytest.raises(AnalysisValidationError, match="Unsupported"):
        validate_ai_analysis(payload)


def test_validate_ai_analysis_rejects_weak_learning_item_quality() -> None:
    payload = valid_payload()
    payload["learning_items"][0]["commonness"] = "Low"
    payload["learning_items"][0]["confidence"] = 0.0

    with pytest.raises(AnalysisValidationError, match="quality score"):
        validate_ai_analysis(payload)


def test_validate_ai_analysis_rejects_unknown_difficulty() -> None:
    payload = valid_payload()
    payload["podcast_metadata"]["difficulty"] = "Expert"

    with pytest.raises(AnalysisValidationError, match="difficulty"):
        validate_ai_analysis(payload)
