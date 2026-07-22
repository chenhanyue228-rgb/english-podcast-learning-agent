from __future__ import annotations

from src.notion.weekly_review_publisher import (
    WeeklyReviewPublishPayload,
    publish_weekly_review,
    weekly_review_body_blocks,
    weekly_review_page_properties,
)


class FakePages:
    def __init__(self):
        self.create_calls = []
        self.update_calls = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return {"id": "weekly_page", "url": "https://notion.so/weekly_page"}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"], "url": "https://notion.so/weekly_page"}


class FakeDataSources:
    def __init__(self, existing=False):
        self.existing = existing
        self.query_calls = []

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if self.existing:
            return {"results": [{"id": "existing_page"}]}
        return {"results": []}


class FakeNotion:
    def __init__(self, existing=False):
        self.data_sources = FakeDataSources(existing=existing)
        self.pages = FakePages()


def sample_payload() -> WeeklyReviewPublishPayload:
    return WeeklyReviewPublishPayload(
        week="2026-W29",
        executive_summary={
            "overview": "Overview",
            "takeaway": "Takeaway",
            "highlights": ["AI Leadership"],
        },
        knowledge_insights=[
            {
                "what_happened": "Something happened",
                "why_it_matters": "It matters",
                "my_interpretation": "My view",
                "application": "Apply it",
            }
        ],
        expression_upgrade=[
            {
                "expression": "take ownership",
                "meaning": "Accept responsibility",
                "context": "Leadership context",
                "example": "We need to take ownership.",
            }
        ],
        vocabulary_memory=[],
        career_reflection={
            "questions": ["What changed?"],
            "possible_applications": ["Use it in meetings."],
        },
        next_learning_direction=["Review the strongest expressions."],
    )


def test_weekly_review_body_blocks_starts_with_toc() -> None:
    blocks = weekly_review_body_blocks(sample_payload(), vocabulary_database_id="vocab_db")

    assert blocks[0]["type"] == "table_of_contents"
    assert blocks[1]["type"] == "bulleted_list_item"
    assert blocks[1]["bulleted_list_item"]["rich_text"][0]["text"]["content"].startswith("1. ")
    assert blocks[2]["bulleted_list_item"]["rich_text"][0]["text"]["content"].startswith("2. ")
    assert blocks[3]["bulleted_list_item"]["rich_text"][0]["text"]["content"].startswith("3. ")
    assert any(block["type"] == "table" and block["table"]["table_width"] == 2 for block in blocks)
    assert any(block["type"] == "table" and block["table"]["table_width"] == 3 for block in blocks)


def test_weekly_review_page_properties_use_v2_schema() -> None:
    properties = weekly_review_page_properties(sample_payload())

    assert properties["Week"]["title"][0]["text"]["content"] == "2026-W29"
    assert properties["Status"] == {"select": {"name": "Draft"}}
    assert properties["Quality Score"]["number"] >= 60


def test_publish_weekly_review_creates_page_with_v2_blocks() -> None:
    notion = FakeNotion(existing=False)

    result = publish_weekly_review(
        sample_payload(),
        notion=notion,
        weekly_database_id="weekly_db",
        vocabulary_database_id="vocab_db",
    )

    assert result.page_id == "weekly_page"
    assert notion.pages.create_calls
    assert notion.pages.create_calls[0]["parent"] == {"data_source_id": "weekly_db"}
    assert notion.pages.create_calls[0]["children"][0]["type"] == "table_of_contents"
    assert any(
        block["type"] == "paragraph"
        and "Source podcasts are linked" in block["paragraph"]["rich_text"][0]["text"]["content"]
        for block in notion.pages.create_calls[0]["children"]
    )
    assert notion.pages.create_calls[0]["properties"]["Status"] == {"select": {"name": "Draft"}}


def test_publish_weekly_review_updates_existing_page() -> None:
    notion = FakeNotion(existing=True)

    result = publish_weekly_review(
        sample_payload(),
        notion=notion,
        weekly_database_id="weekly_db",
        vocabulary_database_id="vocab_db",
    )

    assert result.page_id == "existing_page"
    assert notion.pages.update_calls


def test_weekly_review_body_blocks_does_not_copy_vocabulary_records() -> None:
    blocks = weekly_review_body_blocks(sample_payload(), vocabulary_database_id="vocab_db")

    block_texts = []
    for block in blocks:
        block_type = block["type"]
        value = block.get(block_type, {})
        rich_text = value.get("rich_text")
        if isinstance(rich_text, list):
            block_texts.extend(
                item.get("text", {}).get("content", "")
                for item in rich_text
                if isinstance(item, dict)
            )
        if block_type == "table":
            for row in value.get("children", []):
                cells = row["table_row"]["cells"]
                for cell in cells:
                    block_texts.extend(item.get("text", {}).get("content", "") for item in cell if isinstance(item, dict))

    assert "Vocabulary memory will be synced" not in " ".join(block_texts)


def test_career_reflection_and_next_direction_are_tables() -> None:
    blocks = weekly_review_body_blocks(sample_payload(), vocabulary_database_id="vocab_db")
    tables = [block for block in blocks if block["type"] == "table"]

    career_table = next(table for table in tables if table["table"]["table_width"] == 2)
    next_direction_table = next(table for table in tables if table["table"]["table_width"] == 3)

    career_headers = [
        cell[0]["text"]["content"]
        for cell in career_table["table"]["children"][0]["table_row"]["cells"]
    ]
    assert career_headers == ["Insight", "Action"]
    career_values = [
        cell[0]["text"]["content"]
        for cell in career_table["table"]["children"][1]["table_row"]["cells"]
    ]
    assert career_values == ["What changed?", "Use it in meetings."]

    next_headers = [
        cell[0]["text"]["content"]
        for cell in next_direction_table["table"]["children"][0]["table_row"]["cells"]
    ]
    assert next_headers == ["Priority", "Learning Goal", "Reason"]
    next_values = [
        cell[0]["text"]["content"]
        for cell in next_direction_table["table"]["children"][1]["table_row"]["cells"]
    ]
    assert next_values[0] == "1"
    assert next_values[1] == "Review the strongest expressions."
    assert next_values[2]
