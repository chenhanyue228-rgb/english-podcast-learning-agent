from __future__ import annotations

from src.analyzer.highlight_mapper import map_highlights_to_rich_text


def test_highlighted_expression_is_colored_and_bold() -> None:
    rich_text = map_highlights_to_rich_text(
        "Companies need to take ownership of the project.",
        [
            {
                "text": "take ownership",
                "type": "Business Phrase",
                "color": "blue",
            }
        ],
    )

    highlighted = rich_text[1]

    assert highlighted["text"]["content"] == "take ownership"
    assert highlighted["annotations"]["color"] == "blue_background"
    assert highlighted["annotations"]["bold"] is True
