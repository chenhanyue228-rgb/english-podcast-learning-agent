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


class StatefulPages:
    def __init__(self, state):
        self.state = state
        self.update_calls = []
        self.create_calls = []

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        self.state.events.append(("pages.update", kwargs["page_id"]))
        return {"id": kwargs["page_id"]}

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        parent_id = kwargs["parent"]["data_source_id"]
        if parent_id == "podcast_db":
            self.state.events.append(("pages.create", "podcast"))
            page_id = f"podcast_page_{self.state.next_podcast_number}"
            self.state.next_podcast_number += 1
            properties = kwargs["properties"]
            page = {
                "id": page_id,
                "url": f"https://notion.test/{page_id}",
            }
            source_url = properties["URL"]["url"]
            if source_url:
                self.state.podcasts_by_url[source_url] = page
            title = properties["Title"]["title"][0]["text"]["content"]
            source_type = properties["Source Type"]["select"]["name"]
            self.state.podcasts_by_local_identity[(title, source_type)] = page
            return page

        self.state.expression_create_attempts += 1
        self.state.events.append(
            ("pages.create", f"expression:{self.state.expression_create_attempts}")
        )
        if (
            self.state.fail_expression_create_at
            == self.state.expression_create_attempts
        ):
            raise RuntimeError("simulated expression create failure")

        properties = kwargs["properties"]
        text = properties["Expression"]["title"][0]["text"]["content"]
        category = properties["Category"]["select"]["name"]
        podcast_page_id = properties["Source Podcast"]["relation"][0]["id"]
        page_id = f"expression_page_{self.state.next_expression_number}"
        self.state.next_expression_number += 1
        key = (text, category, podcast_page_id)
        self.state.expressions.setdefault(key, []).append(page_id)
        return {"id": page_id}


class StatefulDataSources:
    def __init__(self, state, properties=None, retrieve_error=None):
        self.state = state
        self.properties = properties or {
            "Expression": {"type": "title"},
            "Category": {"type": "select"},
            "Commonness": {"type": "select"},
            "Source Podcast": {"type": "relation"},
            "Review Status": {"type": "select"},
        }
        self.retrieve_error = retrieve_error
        self.retrieve_calls = []
        self.update_calls = []
        self.query_calls = []

    def retrieve(self, **kwargs):
        self.retrieve_calls.append(kwargs)
        self.state.events.append(("data_sources.retrieve", "expression"))
        if self.retrieve_error:
            raise self.retrieve_error
        return {"properties": self.properties}

    def update(self, **kwargs):
        self.update_calls.append(kwargs)
        self.state.events.append(("data_sources.update", "expression"))
        self.properties["Commonness"] = {"type": "select"}
        return {"id": "expression_db"}

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        if kwargs["data_source_id"] == "podcast_db":
            self.state.events.append(("data_sources.query", "podcast"))
            query_filter = kwargs["filter"]
            if "url" in query_filter:
                page = self.state.podcasts_by_url.get(
                    query_filter["url"]["equals"]
                )
            else:
                title = query_filter["and"][0]["title"]["equals"]
                source_type = query_filter["and"][1]["select"]["equals"]
                page = self.state.podcasts_by_local_identity.get(
                    (title, source_type)
                )
            return {"results": [page] if page else []}

        self.state.events.append(("data_sources.query", "expression"))
        query_filter = kwargs["filter"]["and"]
        text = query_filter[0]["title"]["equals"]
        category = query_filter[1]["select"]["equals"]
        podcast_page_id = query_filter[2]["relation"]["contains"]
        page_ids = self.state.expressions.get(
            (text, category, podcast_page_id),
            [],
        )
        return {"results": [{"id": page_id} for page_id in page_ids[:2]]}


class StatefulCompletePublishNotion:
    def __init__(self, properties=None, retrieve_error=None):
        self.events = []
        self.podcasts_by_url = {}
        self.podcasts_by_local_identity = {}
        self.expressions = {}
        self.next_podcast_number = 1
        self.next_expression_number = 1
        self.expression_create_attempts = 0
        self.fail_expression_create_at = None
        self.pages = StatefulPages(self)
        self.blocks = FakeBlocks()
        self.data_sources = StatefulDataSources(
            self,
            properties=properties,
            retrieve_error=retrieve_error,
        )

    def add_podcast(
        self,
        page_id,
        source_url=None,
        title="Better Episode Title",
        source_type="Podcast",
    ):
        page = {"id": page_id, "url": f"https://notion.test/{page_id}"}
        if source_url:
            self.podcasts_by_url[source_url] = page
        self.podcasts_by_local_identity[(title, source_type)] = page

    def add_expression(self, text, category, podcast_page_id, page_id):
        self.expressions.setdefault(
            (text, category, podcast_page_id),
            [],
        ).append(page_id)


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


def learning_item(text: str, category: str = "Business Phrase") -> LearningItem:
    return LearningItem(
        text=text,
        category=category,
        meaning=f"Meaning of {text}.",
        chinese_meaning=f"{text} 的中文解释",
        usage_context="Use it in a professional context.",
        context_sentence=f"Teams use {text} at work.",
        example_sentence=f"We should use {text} in the next meeting.",
        highlight_color="blue",
        commonness="High",
    )


def analysis_with_items(*items: LearningItem) -> AIAnalysisResult:
    return AIAnalysisResult(
        summary=Summary(
            english="English summary",
            chinese="中文解释",
            key_points=["Point one"],
        ),
        podcast_metadata=PodcastMetadata(
            title="Better Episode Title",
            topic="AI",
            difficulty="Intermediate",
            short_summary="Short AI summary.",
        ),
        learning_items=list(items),
    )


def complete_payload(
    analysis: AIAnalysisResult = None,
    source_url: str = "https://example.com/episode",
    source_type: str = "Podcast",
    title: str = "Original Title",
) -> CompletePodcastLearningPayload:
    return CompletePodcastLearningPayload(
        title=title,
        source_url=source_url,
        source_type=source_type,
        transcript="Companies need to take ownership.",
        analysis=analysis or analysis_result(),
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
    source_url = "https://podcasts.apple.com/podcast/id123?i=456"
    notion = StatefulCompletePublishNotion()
    notion.add_podcast(
        "existing_podcast_page",
        source_url=source_url,
    )
    notion.add_expression(
        "take ownership",
        "Business Phrase",
        "existing_podcast_page",
        "existing_expression_1",
    )
    notion.add_expression(
        "What we're seeing is...",
        "Sentence Pattern",
        "existing_podcast_page",
        "existing_expression_2",
    )

    result = publish_complete_learning_materials(
        CompletePodcastLearningPayload(
            title="Original Title",
            source_url=source_url,
            source_type="Podcast",
            transcript="Companies need to take ownership.",
            analysis=analysis_result(),
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "existing_podcast_page"
    assert result.podcast_page_url == "https://notion.test/existing_podcast_page"
    assert result.expression_page_ids == [
        "existing_expression_1",
        "existing_expression_2",
    ]
    assert notion.pages.create_calls == []
    assert notion.blocks.children.append_calls == []
    assert len(notion.pages.update_calls) == 1
    assert notion.pages.update_calls[0]["page_id"] == "existing_podcast_page"
    query_call = notion.data_sources.query_calls[0]
    assert query_call["data_source_id"] == "podcast_db"
    assert query_call["filter"] == {
        "property": "URL",
        "url": {"equals": source_url},
    }
    assert all(
        call["page_size"] == 2
        for call in notion.data_sources.query_calls[1:]
    )


def test_publish_complete_learning_materials_recovers_missing_expression_for_existing_podcast() -> None:
    class PartialPublishDataSources(FakeDataSources):
        def query(self, **kwargs):
            self.query_calls.append(kwargs)
            if kwargs["data_source_id"] == "podcast_db":
                return {
                    "results": [
                        {
                            "id": "existing_podcast_page",
                            "url": "https://notion.so/existing_podcast_page",
                        }
                    ]
                }
            expression = kwargs["filter"]["and"][0]["title"]["equals"]
            if expression == "take ownership":
                return {"results": [{"id": "existing_expression_page"}]}
            return {"results": []}

    notion = FakeNotion()
    notion.data_sources = PartialPublishDataSources()

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

    assert result.expression_page_ids == [
        "existing_expression_page",
        "expression_1",
    ]
    assert len(notion.pages.create_calls) == 1
    assert notion.pages.create_calls[0]["parent"] == {
        "data_source_id": "expression_db"
    }


def test_complete_publish_checks_schema_before_any_page_write() -> None:
    notion = StatefulCompletePublishNotion()

    result = publish_complete_learning_materials(
        complete_payload(),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "podcast_page_1"
    assert len(result.expression_page_ids) == 2
    assert notion.events[0] == ("data_sources.retrieve", "expression")
    first_page_write = next(
        index
        for index, event in enumerate(notion.events)
        if event[0] in {"pages.create", "pages.update"}
    )
    assert notion.events.index(("data_sources.retrieve", "expression")) < first_page_write
    podcast_creates = [
        call
        for call in notion.pages.create_calls
        if call["parent"] == {"data_source_id": "podcast_db"}
    ]
    expression_creates = [
        call
        for call in notion.pages.create_calls
        if call["parent"] == {"data_source_id": "expression_db"}
    ]
    assert len(podcast_creates) == 1
    assert len(expression_creates) == 2
    expression_query_indexes = [
        index
        for index, event in enumerate(notion.events)
        if event == ("data_sources.query", "expression")
    ]
    first_expression_create_index = next(
        index
        for index, event in enumerate(notion.events)
        if event == ("pages.create", "expression:1")
    )
    assert max(expression_query_indexes) < first_expression_create_index
    first_expression_query = next(
        call
        for call in notion.data_sources.query_calls
        if call["data_source_id"] == "expression_db"
    )
    assert first_expression_query == {
        "data_source_id": "expression_db",
        "filter": {
            "and": [
                {
                    "property": "Expression",
                    "title": {"equals": "take ownership"},
                },
                {
                    "property": "Category",
                    "select": {"equals": "Business Phrase"},
                },
                {
                    "property": "Source Podcast",
                    "relation": {"contains": "podcast_page_1"},
                },
            ]
        },
        "page_size": 2,
    }
    assert all(
        call["properties"]["Source Podcast"]
        == {"relation": [{"id": "podcast_page_1"}]}
        for call in expression_creates
    )


def test_complete_publish_recovers_after_mid_expression_create_failure() -> None:
    analysis = analysis_with_items(
        learning_item("expression A"),
        learning_item("expression B"),
        learning_item("expression C"),
    )
    payload = complete_payload(analysis=analysis)
    notion = StatefulCompletePublishNotion()
    notion.fail_expression_create_at = 2

    with pytest.raises(LearningPublisherError, match="expression B"):
        publish_complete_learning_materials(
            payload,
            notion=notion,
            podcast_database_id="podcast_db",
            expression_database_id="expression_db",
        )

    assert notion.expressions == {
        ("expression A", "Business Phrase", "podcast_page_1"): [
            "expression_page_1"
        ]
    }

    notion.fail_expression_create_at = None
    result = publish_complete_learning_materials(
        payload,
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "podcast_page_1"
    assert result.expression_page_ids == [
        "expression_page_1",
        "expression_page_2",
        "expression_page_3",
    ]
    podcast_creates = [
        call
        for call in notion.pages.create_calls
        if call["parent"] == {"data_source_id": "podcast_db"}
    ]
    expression_a_creates = [
        call
        for call in notion.pages.create_calls
        if call["parent"] == {"data_source_id": "expression_db"}
        and call["properties"]["Expression"]["title"][0]["text"]["content"]
        == "expression A"
    ]
    assert len(podcast_creates) == 1
    assert len(expression_a_creates) == 1
    assert all(len(page_ids) == 1 for page_ids in notion.expressions.values())
    assert len(notion.expressions) == 3


def test_complete_publish_stops_before_expression_create_on_duplicate_conflict() -> None:
    source_url = "https://example.com/duplicate"
    notion = StatefulCompletePublishNotion()
    notion.add_podcast("podcast_existing", source_url=source_url)
    notion.add_expression(
        "expression A",
        "Business Phrase",
        "podcast_existing",
        "duplicate_page_1",
    )
    notion.add_expression(
        "expression A",
        "Business Phrase",
        "podcast_existing",
        "duplicate_page_2",
    )
    analysis = analysis_with_items(
        learning_item("expression A"),
        learning_item("expression B"),
    )

    with pytest.raises(LearningPublisherError) as exc_info:
        publish_complete_learning_materials(
            complete_payload(analysis=analysis, source_url=source_url),
            notion=notion,
            podcast_database_id="podcast_db",
            expression_database_id="expression_db",
        )

    error = str(exc_info.value)
    assert error == (
        "Duplicate Expression records found for one expected learning item."
    )
    assert "duplicate_page_1" not in error
    assert "podcast_existing" not in error
    assert len(notion.data_sources.query_calls) == 3
    expression_creates = [
        call
        for call in notion.pages.create_calls
        if call["parent"] == {"data_source_id": "expression_db"}
    ]
    assert expression_creates == []


def test_complete_publish_schema_retrieve_failure_has_no_page_writes_or_sensitive_error() -> None:
    sensitive_values = [
        "secret-token-value",
        "database-sensitive-id",
        "data-source-sensitive-id",
        "page-sensitive-id",
        "https://notion.so/private",
    ]
    notion = StatefulCompletePublishNotion(
        retrieve_error=RuntimeError(" ".join(sensitive_values))
    )

    with pytest.raises(LearningPublisherError) as exc_info:
        publish_complete_learning_materials(
            complete_payload(),
            notion=notion,
            podcast_database_id="podcast_db",
            expression_database_id="expression_db",
        )

    assert str(exc_info.value) == "Failed to inspect Expression Database schema."
    assert all(value not in str(exc_info.value) for value in sensitive_values)
    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []
    assert notion.blocks.children.append_calls == []


def test_complete_publish_repairs_commonness_before_page_create() -> None:
    notion = StatefulCompletePublishNotion(
        properties={
            "Expression": {"type": "title"},
            "Category": {"type": "select"},
            "Source Podcast": {"type": "relation"},
            "Review Status": {"type": "select"},
        }
    )

    publish_complete_learning_materials(
        complete_payload(),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    schema_update_index = notion.events.index(
        ("data_sources.update", "expression")
    )
    first_page_create_index = next(
        index
        for index, event in enumerate(notion.events)
        if event[0] == "pages.create"
    )
    assert schema_update_index < first_page_create_index


def test_complete_publish_treats_same_text_in_different_categories_as_distinct() -> None:
    analysis = analysis_with_items(
        learning_item("challenge assumptions", "Business Phrase"),
        learning_item("challenge assumptions", "Collocation"),
    )
    notion = StatefulCompletePublishNotion()

    result = publish_complete_learning_materials(
        complete_payload(analysis=analysis),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert len(result.expression_page_ids) == 2
    filters = [
        call["filter"]
        for call in notion.data_sources.query_calls
        if call["data_source_id"] == "expression_db"
    ]
    assert [query_filter["and"][1]["select"]["equals"] for query_filter in filters] == [
        "Business Phrase",
        "Collocation",
    ]
    assert len(notion.expressions) == 2


def test_complete_publish_treats_same_expression_for_different_podcasts_as_distinct() -> None:
    analysis = analysis_with_items(learning_item("fundraising"))
    notion = StatefulCompletePublishNotion()

    first = publish_complete_learning_materials(
        complete_payload(
            analysis=analysis,
            source_url="https://example.com/episode-one",
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )
    second = publish_complete_learning_materials(
        complete_payload(
            analysis=analysis,
            source_url="https://example.com/episode-two",
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert first.podcast_page_id != second.podcast_page_id
    assert first.expression_page_ids != second.expression_page_ids
    assert len(notion.expressions) == 2
    assert {
        key[2] for key in notion.expressions
    } == {first.podcast_page_id, second.podcast_page_id}


def test_complete_publish_uses_title_and_source_type_for_local_audio_identity() -> None:
    notion = StatefulCompletePublishNotion()
    notion.add_podcast(
        "local_audio_page",
        title="Better Episode Title",
        source_type="Local Audio",
    )
    analysis = analysis_with_items(learning_item("active listening"))

    result = publish_complete_learning_materials(
        complete_payload(
            analysis=analysis,
            source_url=None,
            source_type="Local Audio",
            title="Recording",
        ),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    assert result.podcast_page_id == "local_audio_page"
    assert notion.data_sources.query_calls[0]["filter"] == {
        "and": [
            {
                "property": "Title",
                "title": {"equals": "Better Episode Title"},
            },
            {
                "property": "Source Type",
                "select": {"equals": "Local Audio"},
            },
        ]
    }


def test_complete_publish_does_not_write_vocabulary_or_weekly_databases() -> None:
    notion = StatefulCompletePublishNotion()

    publish_complete_learning_materials(
        complete_payload(),
        notion=notion,
        podcast_database_id="podcast_db",
        expression_database_id="expression_db",
    )

    parent_ids = {
        call["parent"]["data_source_id"] for call in notion.pages.create_calls
    }
    query_ids = {
        call["data_source_id"] for call in notion.data_sources.query_calls
    }
    assert parent_ids == {"podcast_db", "expression_db"}
    assert query_ids == {"podcast_db", "expression_db"}
    assert "vocabulary_db" not in parent_ids | query_ids
    assert "weekly_db" not in parent_ids | query_ids


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
            super().__init__()
            self.pages = BrokenPages()

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
