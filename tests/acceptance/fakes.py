"""In-memory Notion fake used only by owner-acceptance tests."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

from scripts.acceptance.podcast_owner_acceptance import AcceptanceConfig
from src.notion.schema import (
    EXPRESSION_DATABASE,
    PODCAST_LIBRARY,
    REQUIRED_DATABASE_PROPERTIES,
    REQUIRED_DATABASE_RELATIONS,
    VOCABULARY_DATABASE,
    WEEKLY_REVIEW,
)


def rich_text_property(value: str) -> dict[str, Any]:
    return {
        "type": "rich_text",
        "rich_text": [{"type": "text", "text": {"content": value}}],
    }


def title_property(value: str) -> dict[str, Any]:
    return {
        "type": "title",
        "title": [{"type": "text", "text": {"content": value}}],
    }


def select_property(value: str) -> dict[str, Any]:
    return {"type": "select", "select": {"name": value}}


def url_property(value: Optional[str]) -> dict[str, Any]:
    return {"type": "url", "url": value}


def date_property(value: str) -> dict[str, Any]:
    return {"type": "date", "date": {"start": value}}


def relation_property(*page_ids: str) -> dict[str, Any]:
    return {
        "type": "relation",
        "relation": [{"id": page_id} for page_id in page_ids],
    }


def acceptance_config() -> AcceptanceConfig:
    return AcceptanceConfig(
        token="secret-owner-token",
        podcast_data_source_id="podcast-data-source",
        expression_data_source_id="expression-data-source",
        vocabulary_data_source_id="vocabulary-data-source",
        weekly_data_source_id="weekly-data-source",
        target_parent_page_id="target-parent-page",
    )


@dataclass
class FakePage:
    page_id: str
    data_source_id: str
    properties: dict[str, Any]
    children: list[dict[str, Any]] = field(default_factory=list)
    archived: bool = False
    in_trash: bool = False

    def to_api(self) -> dict[str, Any]:
        return {
            "id": self.page_id,
            "parent": {
                "type": "data_source_id",
                "data_source_id": self.data_source_id,
            },
            "properties": deepcopy(self.properties),
            "archived": self.archived,
            "in_trash": self.in_trash,
            "url": f"https://notion.so/{self.page_id}",
        }


def _schema_properties(
    name: str,
    data_source_ids: Mapping[str, str],
) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for property_name, property_type in REQUIRED_DATABASE_PROPERTIES[name].items():
        schema: dict[str, Any] = {"type": property_type}
        if property_type == "relation":
            target_name = REQUIRED_DATABASE_RELATIONS[name][property_name]
            schema["relation"] = {
                "data_source_id": data_source_ids[target_name],
                "single_property": {},
            }
        properties[property_name] = schema
    return properties


class FakeDataSources:
    def __init__(self, workspace: "FakeNotion") -> None:
        self.workspace = workspace
        self.retrieve_calls: list[dict[str, Any]] = []
        self.query_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.retrieve_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("data_sources.retrieve")
        data_source_id = kwargs["data_source_id"]
        return {
            "id": data_source_id,
            "name": self.workspace.role_by_data_source_id[data_source_id],
            "parent": {
                "type": "database_id",
                "database_id": self.workspace.database_id_by_data_source_id[
                    data_source_id
                ],
            },
            "properties": deepcopy(self.workspace.schemas[data_source_id]),
        }

    def update(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("data_sources.update")
        data_source_id = kwargs["data_source_id"]
        self.workspace.schemas[data_source_id].update(
            deepcopy(kwargs.get("properties", {}))
        )
        return {"id": data_source_id}

    def query(self, **kwargs: Any) -> dict[str, Any]:
        self.query_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("data_sources.query")
        data_source_id = kwargs["data_source_id"]
        pages = [
            page
            for page in self.workspace.pages_by_id.values()
            if page.data_source_id == data_source_id
        ]
        query_filter = kwargs.get("filter")
        if isinstance(query_filter, Mapping):
            pages = [
                page for page in pages if self._matches(page, query_filter)
            ]
        pages.sort(key=lambda page: page.page_id)
        return {
            "results": [page.to_api() for page in pages],
            "has_more": False,
            "next_cursor": None,
        }

    def _matches(self, page: FakePage, query_filter: Mapping[str, Any]) -> bool:
        if "and" in query_filter:
            clauses = query_filter["and"]
            return isinstance(clauses, list) and all(
                self._matches(page, clause)
                for clause in clauses
                if isinstance(clause, Mapping)
            )
        property_name = str(query_filter.get("property", ""))
        property_value = page.properties.get(property_name, {})
        if "url" in query_filter:
            return property_value.get("url") == query_filter["url"].get("equals")
        if "title" in query_filter:
            return (
                _text_value(property_value.get("title"))
                == query_filter["title"].get("equals")
            )
        if "select" in query_filter:
            selected = property_value.get("select")
            selected_name = selected.get("name") if isinstance(selected, Mapping) else None
            return selected_name == query_filter["select"].get("equals")
        if "relation" in query_filter:
            expected_id = query_filter["relation"].get("contains")
            relations = property_value.get("relation")
            return isinstance(relations, list) and any(
                relation.get("id") == expected_id
                for relation in relations
                if isinstance(relation, Mapping)
            )
        return False


def _text_value(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return "".join(
        str(item.get("text", {}).get("content", ""))
        for item in items
        if isinstance(item, Mapping)
    )


class FakePages:
    def __init__(self, workspace: "FakeNotion") -> None:
        self.workspace = workspace
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.expression_create_attempts = 0
        self.fail_expression_create_at: Optional[int] = None

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("pages.create")
        data_source_id = kwargs["parent"]["data_source_id"]
        if data_source_id == self.workspace.config.podcast_data_source_id:
            page_id = self.workspace.next_id("target-podcast")
        elif data_source_id == self.workspace.config.expression_data_source_id:
            self.expression_create_attempts += 1
            if self.fail_expression_create_at == self.expression_create_attempts:
                raise RuntimeError("fake_expression_create_failure")
            page_id = self.workspace.next_id("target-expression")
        else:
            page_id = self.workspace.next_id("unexpected-page")
        self.workspace.pages_by_id[page_id] = FakePage(
            page_id=page_id,
            data_source_id=data_source_id,
            properties=deepcopy(kwargs.get("properties", {})),
            children=deepcopy(kwargs.get("children", [])),
        )
        return {"id": page_id, "url": f"https://notion.so/{page_id}"}

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.workspace.api_calls.append("pages.retrieve")
        page_id = kwargs["page_id"]
        if page_id == self.workspace.database_parent_page_id:
            return {"id": page_id, "object": "page"}
        page = self.workspace.pages_by_id.get(page_id)
        if page is None:
            raise RuntimeError("fake_page_unavailable")
        return page.to_api()

    def update(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("pages.update")
        page_id = kwargs["page_id"]
        page = self.workspace.pages_by_id[page_id]
        if "properties" in kwargs:
            page.properties.update(deepcopy(kwargs["properties"]))
        if kwargs.get("archived"):
            page.archived = True
        if kwargs.get("in_trash"):
            page.in_trash = True
        if (
            self.workspace.duplicate_body_on_target_update
            and page.data_source_id == self.workspace.config.podcast_data_source_id
            and page.page_id.startswith("target-podcast")
        ):
            page.children.extend(deepcopy(page.children))
        return page.to_api()

    def delete(self, **kwargs: Any) -> dict[str, Any]:
        self.delete_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("pages.delete")
        page = self.workspace.pages_by_id.pop(kwargs["page_id"])
        return page.to_api()


class FakeBlocksChildren:
    def __init__(self, workspace: "FakeNotion") -> None:
        self.workspace = workspace
        self.list_calls: list[dict[str, Any]] = []
        self.append_calls: list[dict[str, Any]] = []

    def list(self, **kwargs: Any) -> dict[str, Any]:
        self.list_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.children.list")
        page = self.workspace.pages_by_id[kwargs["block_id"]]
        return {
            "results": deepcopy(page.children),
            "has_more": False,
            "next_cursor": None,
        }

    def append(self, **kwargs: Any) -> dict[str, Any]:
        self.append_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.children.append")
        self.workspace.pages_by_id[kwargs["block_id"]].children.extend(
            deepcopy(kwargs.get("children", []))
        )
        return {"results": []}


class FakeBlocks:
    def __init__(self, workspace: "FakeNotion") -> None:
        self.children = FakeBlocksChildren(workspace)
        self.delete_calls: list[dict[str, Any]] = []

    def delete(self, **kwargs: Any) -> dict[str, Any]:
        self.delete_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("blocks.delete")
        return {}


class FakeDatabases:
    def __init__(self, workspace: "FakeNotion") -> None:
        self.workspace = workspace
        self.retrieve_calls: list[dict[str, Any]] = []
        self.create_calls: list[dict[str, Any]] = []
        self.update_calls: list[dict[str, Any]] = []

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        self.retrieve_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("databases.retrieve")
        database_id = kwargs["database_id"]
        role = self.workspace.role_by_database_id.get(database_id)
        if role is None:
            raise RuntimeError("fake_database_unavailable")
        data_source_id = self.workspace.data_source_id_by_database_id[database_id]
        return {
            "id": database_id,
            "title": [{"plain_text": role}],
            "parent": {
                "type": "page_id",
                "page_id": self.workspace.database_parent_page_id,
            },
            "data_sources": [{"id": data_source_id, "name": role}],
        }

    def create(self, **kwargs: Any) -> dict[str, Any]:
        self.create_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("databases.create")
        return {"id": "raw-created-database"}

    def update(self, **kwargs: Any) -> dict[str, Any]:
        self.update_calls.append(deepcopy(kwargs))
        self.workspace.api_calls.append("databases.update")
        return {"id": kwargs.get("database_id")}


class FakeNotion:
    """Stateful fake with no network or credential access."""

    def __init__(self, *, seed_unrelated_records: bool = True) -> None:
        self.config = acceptance_config()
        self.api_calls: list[str] = []
        self.database_parent_page_id = self.config.target_parent_page_id
        self.data_source_ids = self.config.data_source_ids
        self.role_by_data_source_id = {
            data_source_id: role
            for role, data_source_id in self.data_source_ids.items()
        }
        self.database_id_by_data_source_id = {
            data_source_id: f"{role.casefold().replace(' ', '-')}-database"
            for role, data_source_id in self.data_source_ids.items()
        }
        self.role_by_database_id = {
            database_id: self.role_by_data_source_id[data_source_id]
            for data_source_id, database_id in (
                self.database_id_by_data_source_id.items()
            )
        }
        self.data_source_id_by_database_id = {
            database_id: data_source_id
            for data_source_id, database_id in (
                self.database_id_by_data_source_id.items()
            )
        }
        self.schemas = {
            data_source_id: _schema_properties(name, self.data_source_ids)
            for name, data_source_id in self.data_source_ids.items()
        }
        self.pages_by_id: dict[str, FakePage] = {}
        self._next_number = 1
        self.duplicate_body_on_target_update = False
        self.data_sources = FakeDataSources(self)
        self.pages = FakePages(self)
        self.blocks = FakeBlocks(self)
        self.databases = FakeDatabases(self)
        if seed_unrelated_records:
            self.seed_unrelated_records()

    def next_id(self, prefix: str) -> str:
        page_id = f"{prefix}-{self._next_number}"
        self._next_number += 1
        return page_id

    def add_page(
        self,
        data_source_id: str,
        properties: dict[str, Any],
        *,
        page_id: Optional[str] = None,
        children: Optional[list[dict[str, Any]]] = None,
    ) -> str:
        resolved_id = page_id or self.next_id("seed-page")
        self.pages_by_id[resolved_id] = FakePage(
            page_id=resolved_id,
            data_source_id=data_source_id,
            properties=deepcopy(properties),
            children=deepcopy(children or []),
        )
        return resolved_id

    def seed_unrelated_records(self) -> None:
        other_podcast_id = self.add_page(
            self.config.podcast_data_source_id,
            {
                "Title": title_property("Existing unrelated podcast"),
                "URL": url_property("https://example.com/unrelated"),
                "Source Type": select_property("Podcast"),
                "Date": date_property("2026-07-01"),
                "Topic": select_property("Leadership"),
                "Difficulty": select_property("Intermediate"),
                "Short Summary": rich_text_property("Existing summary"),
            },
            page_id="existing-podcast",
        )
        self.add_page(
            self.config.expression_data_source_id,
            {
                "Expression": title_property("existing expression"),
                "Category": select_property("Business Phrase"),
                "Commonness": select_property("High"),
                "Source Podcast": relation_property(other_podcast_id),
                "Review Status": select_property("New"),
            },
            page_id="existing-expression",
        )
        self.add_page(
            self.config.vocabulary_data_source_id,
            {
                "Name": title_property("existing vocabulary"),
                "Original Context": rich_text_property("private context"),
                "Meaning": rich_text_property("private meaning"),
                "Professional Category": select_property("Word"),
                "Source": relation_property(other_podcast_id),
                "Source Page ID": rich_text_property("private-source"),
                "First Seen": date_property("2026-07-01"),
                "Review Status": select_property("New"),
                "Last Review": date_property("2026-07-01"),
                "Usage Example": rich_text_property("private example"),
                "Personal Note": rich_text_property("private note"),
            },
            page_id="existing-vocabulary",
        )
        self.add_page(
            self.config.weekly_data_source_id,
            {
                "Week": title_property("Existing week"),
                "Date": date_property("2026-07-01"),
                "Podcasts": relation_property(other_podcast_id),
            },
            page_id="existing-weekly",
        )

    def target_expression_pages(self) -> list[FakePage]:
        return [
            page
            for page in self.pages_by_id.values()
            if page.data_source_id == self.config.expression_data_source_id
            and page.page_id.startswith("target-expression")
        ]

    def target_podcast_pages(self) -> list[FakePage]:
        return [
            page
            for page in self.pages_by_id.values()
            if page.data_source_id == self.config.podcast_data_source_id
            and page.page_id.startswith("target-podcast")
        ]
