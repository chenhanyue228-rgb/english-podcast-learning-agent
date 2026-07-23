"""Shared isolation for publisher payload tests.

Existing publisher tests use intentionally small Notion fakes that model page
payloads, not workspace hierarchy. Target-binding behavior is covered by the
dedicated validator and owner-acceptance suites, so these focused tests replace
only the pre-write proof while retaining every underlying write assertion.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def isolate_publisher_payload_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    proof = SimpleNamespace(
        valid=True,
        configured_parent_matches_expected=True,
        all_data_sources_same_group=True,
        internal_relations_verified=True,
        target_parent_fingerprint="00000000",
        target_group_fingerprint="00000000",
    )

    def verified(*_args, **_kwargs):
        return proof

    module_names = (
        "src.notion.create_example_data",
        "src.notion.learning_publisher",
        "src.notion.uploader",
        "src.notion.vocabulary_publisher",
        "src.notion.weekly_reflection_writer",
        "src.notion.weekly_review_publisher",
        "src.workflow.podcast_pipeline",
    )
    for module_name in module_names:
        module = __import__(module_name, fromlist=["_"])
        monkeypatch.setattr(
            module,
            "ensure_notion_target_binding_for_write",
            verified,
        )
