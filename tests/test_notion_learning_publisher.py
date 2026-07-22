from __future__ import annotations

import pytest

from notion_client import APIResponseError
from src.analyzer.models import (
    AIAnalysisResult,
    LearningItem,
    PodcastMetadata,
    SentencePattern,
    Summary,
)
from src.notion.learning_publisher import (
    CompletePodcastLearningPayload,
    LearningPublishPayload,
    LearningPublisherError,
    analysis_summary_text,
    complete_podcast_page_properties,
    create_complete_podcast_learning_page,
    expression_page_properties,
    learning_item_payload,
    podcast_update_properties,
    publish_complete_learning_materials,
    publish_learning_materials,
    update_podcast_learning_page,
)
from src.notion.renderers import highlight_legend_blocks
from src.notion.renderers import expression_body_blocks, expression_table_block


class FakePages:
    def __init__(self):
        self.update_calls = []
        self.create_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        return {"id": kwargs["page_id"]}

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        if kwargs["parent"] == {"data_source_id": "podcast_db"}:
            return {
                "id": "podcast_page",
                "url": "https://notion.so/podcast_page",
            }
        return {"id": f"expression_{len(self.create_calls)}"}


class FakeBlocksChildren:
    def __init__(self):
        self.append_calls = []

    def append(self, **kwargs):
        self.append_calls.append(kwargs)
        return {}


class FakeBlocks:
    def __init__(self):
        self.children = FakeBlocksChildren()


class FakeDataSources:
    def __init__(
        self,
        properties: dict[str, object] = None,
        query_results: list[dict[str, object]] = None,
    ):
        self.properties = properties or {
            "Expression": {"type": "title"},
            "Category": {"type": "select"},
            "Commonness": {"type": "select"},
            "Source Podcast": {"type": "relation"},
            "Review Status": {"type": "select"},
        }
        self.retrieve_calls = []
        self.update_calls = []
        self.query_calls = []
        self.query_results = query_results or []

    def retrieve(self, **kwargs):
        self.retrieve_calls.append(kwargs)
        return {"properties": self.properties}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        self.properties.update({"Commonness": {"type": "select"}})
        return {"id": kwargs.get("data_source_id")}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {"results": self.query_results}


class FakeNotion:
    def __init__(
        self,
        properties: dict[str, object] = None,
        query_results: list[dict[str, object]] = None,
    ):
        self.pages = FakePages()
        self.blocks = FakeBlocks()
        self.data_sources = FakeDataSources(
            properties=properties,
            query_results=query_results,
        )


class ErrorWithoutMessage:
    code = "bad_request"

    def __str__(self) -> str:
        return "fallback detail"


def analysis_result() -> AIAnalysisResult:
    return AIAnalysisResult(
        summary=Summary(
            english="English summary",
            chinese="中文解释",
            key_points=["Point one", "Point two"],
        ),
        podcast_metadata=PodcastMetadata(
            title="Better Episode Title",
            topic="AI",
            difficulty="Intermediate",
            short_summary="Short AI summary.",
        ),
        learning_items=[
            LearningItem(
                text="take ownership",
                category="Business Phrase",
                meaning="Accept responsibility.",
                chinese_meaning="承担责任",
                usage_context="Use it when discussing accountability.",
                context_sentence="Companies need to take ownership.",
                example_sentence="The team took ownership of the launch.",
                highlight_color="blue",
                commonness="High",
            )
        ],
        sentence_patterns=[
            SentencePattern(
                text="What we're seeing is...",
                meaning="Introduce an observed trend.",
                usage_context="Use it in analysis or meetings.",
                context_sentence="What we're seeing is a leadership gap.",
                example_sentence="What we're seeing is a change in user behavior.",
                highlight_color="orange",
                commonness="Medium",
            )
        ],
    )


def test_podcast_update_properties_maps_metadata() -> None:
    properties = podcast_update_properties(analysis_result())

    assert properties["Topic"] == {"select": {"name": "AI"}}
    assert properties["Title"]["title"][0]["text"]["content"] == "Better Episode Title"
    assert properties["Difficulty"] == {"select": {"name": "Intermediate"}}
    assert (
        properties["Short Summary"]["rich_text"][0]["text"]["content"]
        == "Short AI summary."
    )


def test_complete_podcast_page_properties_are_full() -> None:
    properties = complete_podcast_page_properties(
        CompletePodcastLearningPayload(
            title="Original Title",
            source_url="https://example.com/episode",
            source_type="Podcast",
            transcript="Companies need to take ownership.",
            analysis=analysis_result(),
            processed_date="2026-07-17",
        )
    )

    assert properties["Title"]["title"][0]["text"]["content"] == "Better Episode Title"
    assert properties["URL"] == {"url": "https://example.com/episode"}
    assert properties["Source Type"] == {"select": {"name": "Podcast"}}
    assert properties["Date"] == {"date": {"start": "2026-07-17"}}
    assert properties["Topic"] == {"select": {"name": "AI"}}
    assert properties["Difficulty"] == {"select": {"name": "Intermediate"}}
    assert (
        properties["Short Summary"]["rich_text"][0]["text"]["content"]
        == "Short AI summary."
    )


def test_highlight_legend_contains_all_expression_categories() -> None:
    blocks = highlight_legend_blocks()
    legend_text = " ".join(
        rich_text["text"]["content"]
        for block in blocks
        for rich_text in block[block["type"]]["rich_text"]
        if rich_text.get("text")
    )

    assert "Green" in legend_text
    assert "Native expressions" in legend_text
    assert "Blue" in legend_text
    assert "Business phrases" in legend_text
    assert "Yellow" in legend_text
    assert "Industry terms" in legend_text
    assert "Purple" in legend_text
    assert "Collocations" in legend_text
    assert "Orange" in legend_text
    assert "Sentence patterns" in legend_text


def test_analysis_summary_text_combines_english_chinese_and_points() -> None:
    text = analysis_summary_text(analysis_result())

    assert "English summary" in text
    assert "中文解释" in text
    assert "- Point one" in text


def test_learning_item_payload_matches_renderer_shape() -> None:
    item = analysis_result().learning_items[0]

    payload = learning_item_payload(item)

    assert payload["expression"] == "take ownership"
    assert payload["category"] == "Business Phrase"
    assert payload["usage_context"] == "Use it when discussing accountability."
    assert payload["color"] == "blue"
    assert payload["commonness"] == "High"


def test_expression_table_includes_chinese_meaning_and_example() -> None:
    table = expression_table_block([learning_item_payload(analysis_result().learning_items[0])])

    assert table["table"]["table_width"] == 6
    header_cells = table["table"]["children"][0]["table_row"]["cells"]
    headers = [cell[0]["text"]["content"] for cell in header_cells]
    assert headers == [
        "Expression",
        "Meaning",
        "Chinese Meaning",
        "Usage Context",
        "Commonness",
        "Example",
    ]
    data_cells = table["table"]["children"][1]["table_row"]["cells"]
    values = [cell[0]["text"]["content"] for cell in data_cells]
    assert data_cells[0][0]["annotations"]["bold"] is True
    assert "承担责任" in values
    assert "High" in values
    assert "The team took ownership of the launch." in values


def test_expression_body_includes_chinese_meaning() -> None:
    blocks = expression_body_blocks(
        learning_item_payload(analysis_result().learning_items[0]),
        fallback_context_sentence="Fallback",
    )
    block_text = " ".join(
        rich_text["text"]["content"]
        for block in blocks
        for rich_text in block[block["type"]]["rich_text"]
        if rich_text.get("text")
    )

    assert "Chinese Meaning" in block_text
    assert "承担责任" in block_text
    assert "Commonness" in block_text


def test_expression_page_properties_create_relation_and_status() -> None:
    item = analysis_result().learning_items[0]

    properties = expression_page_properties(item, "podcast_page")

    assert properties["Expression"]["title"][0]["text"]["content"] == "take ownership"
    assert properties["Category"] == {"select": {"name": "Business Phrase"}}
    assert properties["Commonness"] == {"select": {"name": "High"}}
    assert properties["Review Status"] == {"select": {"name": "New"}}
    assert properties["Source Podcast"] == {"relation": [{"id": "podcast_page"}]}


def test_publish_learning_materials_updates_podcast_and_creates_expressions() -> None:
    notion = FakeNotion()

    result = publish_learning_materials(
        LearningPublishPayload(
            podcast_page_id="podcast_page",
            analysis=analysis_result(),
            transcript="Companies need to take ownership.",
        ),
        notion=notion,
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "podcast_page"
    assert result.expression_page_ids == ["expression_1", "expression_2"]

    update_call = notion.pages.update_calls[0]
    assert update_call["page_id"] == "podcast_page"
    assert update_call["properties"]["Topic"] == {"select": {"name": "AI"}}
    assert update_call["properties"]["Difficulty"] == {"select": {"name": "Intermediate"}}

    append_call = notion.blocks.children.append_calls[0]
    assert append_call["block_id"] == "podcast_page"
    headings = [
        block[block["type"]]["rich_text"][0]["text"]["content"]
        for block in append_call["children"]
        if block["type"].startswith("heading_")
        and block[block["type"]]["rich_text"][0].get("text")
    ]
    assert "Summary" in headings
    assert "Expressions" in headings
    assert "Highlight Legend" in headings
    assert "Highlighted Transcript" in headings
    first_create = notion.pages.create_calls[0]
    assert first_create["parent"] == {"data_source_id": "expression_db"}
    assert first_create["properties"]["Commonness"] == {"select": {"name": "High"}}
    assert first_create["properties"]["Source Podcast"] == {
        "relation": [{"id": "podcast_page"}]
    }


def test_publish_learning_materials_skips_commonness_when_database_missing_field() -> None:
    notion = FakeNotion(
        properties={
            "Expression": {"type": "title"},
            "Category": {"type": "select"},
            "Source Podcast": {"type": "relation"},
            "Review Status": {"type": "select"},
        }
    )

    result = publish_learning_materials(
        LearningPublishPayload(
            podcast_page_id="podcast_page",
            analysis=analysis_result(),
            transcript="Companies need to take ownership.",
        ),
        notion=notion,
        expression_database_id="expression_db",
    )

    assert result.expression_page_ids == ["expression_1", "expression_2"]
    assert notion.data_sources.update_calls
    first_create = notion.pages.create_calls[0]
    assert first_create["properties"]["Commonness"] == {"select": {"name": "High"}}


def test_create_complete_podcast_learning_page_creates_full_body() -> None:
    notion = FakeNotion()

    page_id, page_url = create_complete_podcast_learning_page(
        notion=notion,
        podcast_database_id="podcast_db",
        payload=CompletePodcastLearningPayload(
            title="Original Title",
            source_url="https://example.com/episode",
            source_type="Podcast",
            transcript="Companies need to take ownership.",
            analysis=analysis_result(),
        ),
    )

    assert page_id == "podcast_page"
    assert page_url == "https://notion.so/podcast_page"
    create_call = notion.pages.create_calls[0]
    assert create_call["parent"] == {"data_source_id": "podcast_db"}
    assert create_call["properties"]["Topic"] == {"select": {"name": "AI"}}
    assert create_call["properties"]["Difficulty"] == {
        "select": {"name": "Intermediate"}
    }
    headings = [
        block[block["type"]]["rich_text"][0]["text"]["content"]
        for block in create_call["children"]
        if block["type"].startswith("heading_")
        and block[block["type"]]["rich_text"][0].get("text")
    ]
    assert headings[:4] == [
        "Summary",
        "Expressions",
        "Business Phrase",
        "Sentence Pattern",
    ]
    assert "Highlight Legend" in headings
    assert "Highlighted Transcript" in headings


def test_publish_complete_learning_materials_creates_podcast_then_expressions() -> None:
    notion = FakeNotion()

    result = publish_complete_learning_materials(
        CompletePodcastLearningPayload(
            title="Original Title",
            source_url="https://example.com/episode",
            source_type="Podcast",
            transcript="Companies need to take ownership.",
            analysis=analysis_result(),
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "podcast_page"
    assert result.podcast_page_url == "https://notion.so/podcast_page"
    assert result.expression_page_ids == ["expression_2", "expression_3"]
    expression_create = notion.pages.create_calls[1]
    assert expression_create["parent"] == {"data_source_id": "expression_db"}
    assert expression_create["properties"]["Source Podcast"] == {
        "relation": [{"id": "podcast_page"}]
    }


def test_publish_complete_learning_materials_updates_exact_repeat_without_duplicates() -> None:
    notion = FakeNotion(
        query_results=[
            {
                "id": "existing_podcast_page",
                "url": "https://notion.so/existing_podcast_page",
            }
        ]
    )

    result = publish_complete_learning_materials(
        CompletePodcastLearningPayload(
            title="Original Title",
            source_url="https://podcasts.apple.com/podcast/id123?i=456",
            source_type="Podcast",
            transcript="Companies need to take ownership.",
            analysis=analysis_result(),
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "existing_podcast_page"
    assert result.podcast_page_url == "https://notion.so/existing_podcast_page"
    assert result.expression_page_ids == []
    assert notion.pages.create_calls == []
    assert notion.blocks.children.append_calls == []
    assert notion.pages.update_calls[0]["page_id"] == "existing_podcast_page"
    query_call = notion.data_sources.query_calls[0]
    assert query_call["data_source_id"] == "podcast_db"
    assert query_call["filter"] == {
        "property": "URL",
        "url": {"equals": "https://podcasts.apple.com/podcast/id123?i=456"},
    }


def test_update_podcast_learning_page_requires_transcript() -> None:
    with pytest.raises(LearningPublisherError, match="Transcript"):
        update_podcast_learning_page(
            notion=FakeNotion(),
            podcast_page_id="podcast_page",
            analysis=analysis_result(),
            transcript=" ",
        )


def test_publish_learning_materials_requires_expression_page_id() -> None:
    class BrokenPages(FakePages):
        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return {}

    class BrokenNotion(FakeNotion):
        def __init__(self):
            self.pages = BrokenPages()
            self.blocks = FakeBlocks()

    with pytest.raises(LearningPublisherError, match="page ID"):
        publish_learning_materials(
            LearningPublishPayload(
                podcast_page_id="podcast_page",
                analysis=analysis_result(),
                transcript="Companies need to take ownership.",
            ),
            notion=BrokenNotion(),
            expression_database_id="expression_db",
        )


def test_api_error_message_handles_missing_message_attribute() -> None:
    from src.notion.learning_publisher import api_error_message

    err = ErrorWithoutMessage()
    assert api_error_message(err) == "bad_request fallback detail"
