"""Create sample Notion learning data for English Audio Learning Agent.

Usage:
    python -m src.notion.create_example_data

The sample mirrors the canonical Notion model:
- Podcast properties store metadata only.
- Podcast page body stores summary, expression tables, legend, and transcript.
- Expression page body stores meaning, usage context, source sentence, example,
  and highlight color.
"""

from __future__ import annotations

import sys
from typing import Any, TYPE_CHECKING

from src.notion.config import NotionConfigError, load_notion_config
from src.notion.renderers import expression_body_blocks, podcast_body_blocks

if TYPE_CHECKING:
    from notion_client import Client


SAMPLE_SHORT_SUMMARY = "A short sample about business ownership of AI adoption."
SAMPLE_SUMMARY = (
    "This sample discusses how companies need to take responsibility for AI "
    "adoption and use AI to create meaningful business impact. The key learning "
    "focus is business English around ownership, impact, and operational efficiency."
)
SAMPLE_TRANSCRIPT = (
    "Companies need to take ownership of AI adoption and move the needle "
    "through operational leverage."
)
SAMPLE_EXPRESSIONS = [
    {
        "expression": "take ownership",
        "category": "Business Phrase",
        "meaning": "Accept responsibility",
        "usage_context": "Used when someone or a team accepts accountability for a task, project, or business outcome.",
        "context": SAMPLE_TRANSCRIPT,
        "example": SAMPLE_TRANSCRIPT,
        "color": "Blue",
        "commonness": "High",
    },
    {
        "expression": "move the needle",
        "category": "Native Expression",
        "meaning": "Create meaningful impact",
        "usage_context": "Used when describing work, strategy, or decisions that produce a noticeable result.",
        "context": SAMPLE_TRANSCRIPT,
        "example": SAMPLE_TRANSCRIPT,
        "color": "Green",
        "commonness": "High",
    },
    {
        "expression": "operational leverage",
        "category": "Industry Term",
        "meaning": "Improve business efficiency",
        "usage_context": "Used in business, finance, and operations when discussing how fixed resources can create greater output.",
        "context": SAMPLE_TRANSCRIPT,
        "example": SAMPLE_TRANSCRIPT,
        "color": "Yellow",
        "commonness": "Medium",
    },
]


class ExampleDataError(RuntimeError):
    """Raised when sample Notion data cannot be created."""


def title_value(text: str) -> dict[str, Any]:
    return {"title": [{"type": "text", "text": {"content": text}}]}


def rich_text_value(text: str) -> dict[str, Any]:
    return {"rich_text": [{"type": "text", "text": {"content": text}}]}


def select_value(name: str) -> dict[str, Any]:
    return {"select": {"name": name}}


def relation_value(page_ids: list[str]) -> dict[str, Any]:
    return {"relation": [{"id": page_id} for page_id in page_ids]}


def create_notion_client() -> tuple["Client", Any]:
    try:
        from notion_client import Client
    except ModuleNotFoundError as exc:
        raise NotionConfigError(
            "Missing dependency notion-client. Install dependencies with "
            "pip install -r requirements.txt."
        ) from exc

    config = load_notion_config()
    return Client(auth=config.token), config


def create_podcast_page(notion: "Client", podcast_database_id: str) -> str:
    try:
        response = notion.pages.create(
            parent={"data_source_id": podcast_database_id},
            properties={
                "Title": title_value("AI Transformation in Business"),
                "Source Type": select_value("Podcast"),
                "Topic": select_value("AI Transformation"),
                "Difficulty": select_value("Intermediate"),
                "Short Summary": rich_text_value(SAMPLE_SHORT_SUMMARY),
            },
            children=podcast_body_blocks(
                summary=SAMPLE_SUMMARY,
                transcript=SAMPLE_TRANSCRIPT,
                expressions=SAMPLE_EXPRESSIONS,
            ),
        )
    except Exception as exc:
        raise ExampleDataError(f"Failed to create sample podcast: {exc}") from exc

    page_id = response.get("id")
    if not page_id:
        raise ExampleDataError("Notion did not return an ID for the sample podcast.")

    return page_id


def create_expression_page(
    notion: "Client",
    expression_database_id: str,
    podcast_page_id: str,
    expression_data: dict[str, str],
) -> str:
    try:
        response = notion.pages.create(
            parent={"data_source_id": expression_database_id},
            properties={
                "Expression": title_value(expression_data["expression"]),
                "Category": select_value(expression_data["category"]),
                "Source Podcast": relation_value([podcast_page_id]),
                "Review Status": select_value("New"),
            },
            children=expression_body_blocks(
                expression_data,
                fallback_context_sentence=SAMPLE_TRANSCRIPT,
            ),
        )
    except Exception as exc:
        expression = expression_data["expression"]
        raise ExampleDataError(
            f"Failed to create sample expression '{expression}': {exc}"
        ) from exc

    page_id = response.get("id")
    if not page_id:
        expression = expression_data["expression"]
        raise ExampleDataError(
            f"Notion did not return an ID for sample expression '{expression}'."
        )

    return page_id


def create_example_data() -> dict[str, Any]:
    notion, config = create_notion_client()

    podcast_page_id = create_podcast_page(notion, config.podcast_database_id)
    expression_page_ids = [
        create_expression_page(
            notion=notion,
            expression_database_id=config.expression_database_id,
            podcast_page_id=podcast_page_id,
            expression_data=expression_data,
        )
        for expression_data in SAMPLE_EXPRESSIONS
    ]
    return {
        "podcast_page_id": podcast_page_id,
        "expression_page_ids": expression_page_ids,
    }


def main() -> int:
    try:
        created = create_example_data()
    except (ExampleDataError, NotionConfigError) as exc:
        print(f"Example data creation failed: {exc}", file=sys.stderr)
        return 1

    print("Created sample Notion data:")
    print(f"Podcast: {created['podcast_page_id']}")
    print("Expressions:")
    for page_id in created["expression_page_ids"]:
        print(f"- {page_id}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
