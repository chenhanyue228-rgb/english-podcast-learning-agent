from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from scripts.notion import diagnose_target_binding as cli
from src.notion.config import NotionConfigError
from src.notion.target_binding import (
    TARGET_BINDING_RETRIEVE_FAILED,
    TARGET_DATABASE_AMBIGUOUS,
    TARGET_PARENT_MISMATCH,
    NotionTargetBindingError,
)


def _config():
    return SimpleNamespace(
        token="private-fake-token",
        target_parent_page_id="obviously-fake-target-parent",
    )


@pytest.mark.parametrize(
    ("error", "expected_exit"),
    (
        (NotionTargetBindingError(TARGET_PARENT_MISMATCH), 3),
        (NotionTargetBindingError(TARGET_BINDING_RETRIEVE_FAILED), 4),
        (NotionTargetBindingError(TARGET_DATABASE_AMBIGUOUS), 5),
        (NotionTargetBindingError("target_relation_mode_invalid"), 1),
    ),
)
def test_diagnosis_exit_codes_are_stable_and_redacted(
    monkeypatch,
    error,
    expected_exit,
) -> None:
    monkeypatch.setattr(cli, "load_notion_config", _config)
    monkeypatch.setattr(cli, "create_notion_client", lambda _token: object())

    def fail(*_args):
        raise error

    monkeypatch.setattr(cli, "validate_notion_target_binding", fail)

    report, exit_code = cli.diagnose()

    assert exit_code == expected_exit
    assert report["failure"] == error.code
    assert "private-fake-token" not in json.dumps(report)
    assert report["read_only"] is True


def test_missing_target_parent_exits_two(monkeypatch) -> None:
    def missing():
        raise NotionConfigError(
            "Missing required environment variable "
            "NOTION_TARGET_PARENT_PAGE_ID."
        )

    monkeypatch.setattr(cli, "load_notion_config", missing)

    report, exit_code = cli.diagnose()

    assert exit_code == 2
    assert report["failure"] == "target_parent_not_configured"


def test_valid_diagnosis_only_emits_safe_fingerprints(monkeypatch) -> None:
    result = SimpleNamespace(
        valid=True,
        configured_parent_matches_expected=True,
        all_data_sources_same_group=True,
        internal_relations_verified=True,
        target_parent_fingerprint="a1b2c3d4",
        target_group_fingerprint="0f1e2d3c",
    )
    monkeypatch.setattr(cli, "load_notion_config", _config)
    notion = SimpleNamespace(
        pages=SimpleNamespace(create=lambda **_kwargs: pytest.fail("write")),
        data_sources=SimpleNamespace(update=lambda **_kwargs: pytest.fail("write")),
    )
    monkeypatch.setattr(cli, "create_notion_client", lambda _token: notion)
    monkeypatch.setattr(
        cli,
        "validate_notion_target_binding",
        lambda actual, _config: result if actual is notion else None,
    )

    report, exit_code = cli.diagnose()
    rendered = json.dumps(report)

    assert exit_code == 0
    assert report["status"] == "valid"
    assert re.fullmatch(
        r"[0-9a-f]{8}",
        report["target_parent_fingerprint"],
    )
    assert re.fullmatch(
        r"[0-9a-f]{8}",
        report["target_group_fingerprint"],
    )
    assert "private-fake-token" not in rendered
