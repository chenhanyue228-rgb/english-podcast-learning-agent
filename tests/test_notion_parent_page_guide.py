from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.notion import parent_page_guide
from src.notion.config import NotionConfig
from src.notion.target_binding import NotionTargetBindingError


PARENT_ID = "target-parent"
USER_GUIDE_PATH = (
    Path(__file__).resolve().parents[1] / "docs" / "USER_GUIDE_ZH.md"
)
CONFIG = NotionConfig(
    token="test-token",
    podcast_database_id="podcast-db",
    expression_database_id="expression-db",
    weekly_database_id="weekly-db",
    vocabulary_database_id="vocabulary-db",
    target_parent_page_id=PARENT_ID,
)


def _canonical_prompt(heading: str) -> str:
    guide = USER_GUIDE_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"^### {re.escape(heading)}\n\n```text\n(.*?)\n```$",
        guide,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None
    return match.group(1)


def _api_block(
    text: str,
    *,
    block_type: str = "paragraph",
    block_id: str = "",
) -> dict:
    return {
        "id": block_id or f"block-{abs(hash((block_type, text)))}",
        "object": "block",
        "type": block_type,
        block_type: {
            "rich_text": [
                {
                    "type": "text",
                    "plain_text": text,
                    "text": {"content": text},
                }
            ]
        },
        "archived": False,
        "in_trash": False,
        "last_edited_time": "2026-07-24T00:00:00.000Z",
    }


def _stored_block(block: dict, index: int) -> dict:
    copied = deepcopy(block)
    copied["id"] = f"guide-{index}"
    copied["archived"] = False
    copied["in_trash"] = False
    copied["last_edited_time"] = "2026-07-24T00:00:00.000Z"
    for item in copied[copied["type"]]["rich_text"]:
        item["plain_text"] = item["text"]["content"]
    return copied


class FakeChildren:
    def __init__(self, blocks: list[dict] | None = None) -> None:
        self.blocks = deepcopy(blocks or [])
        self.list_calls: list[dict] = []
        self.append_calls: list[dict] = []
        self.delete_calls: list[dict] = []
        self.fail_read = False
        self.fail_read_on_call: int | None = None
        self.fail_append = False
        self.mutate_before_second_read = False
        self.omit_appended_blocks = False

    def list(self, **kwargs):
        self.list_calls.append(deepcopy(kwargs))
        if self.fail_read or self.fail_read_on_call == len(self.list_calls):
            raise RuntimeError("private read failure")
        if self.mutate_before_second_read and len(self.list_calls) == 2:
            self.blocks.append(_api_block("Owner added content", block_id="new"))
        return {
            "results": deepcopy(self.blocks),
            "has_more": False,
            "next_cursor": None,
        }

    def append(self, **kwargs):
        self.append_calls.append(deepcopy(kwargs))
        if self.fail_append:
            raise RuntimeError("private write failure")
        if not self.omit_appended_blocks:
            start = len(self.blocks)
            self.blocks.extend(
                _stored_block(block, start + index)
                for index, block in enumerate(kwargs["children"])
            )
        return {"results": []}

    def delete(self, **kwargs):
        self.delete_calls.append(deepcopy(kwargs))
        raise AssertionError("blocks must never be deleted")


class ForbiddenEndpoint:
    def __init__(self) -> None:
        self.create_calls: list[dict] = []
        self.update_calls: list[dict] = []
        self.delete_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(deepcopy(kwargs))
        raise AssertionError("database or record create is forbidden")

    def update(self, **kwargs):
        self.update_calls.append(deepcopy(kwargs))
        raise AssertionError("database or record update is forbidden")

    def delete(self, **kwargs):
        self.delete_calls.append(deepcopy(kwargs))
        raise AssertionError("database or record delete is forbidden")


class FakeNotion:
    def __init__(self, blocks: list[dict] | None = None) -> None:
        self.blocks = SimpleNamespace(children=FakeChildren(blocks))
        self.pages = ForbiddenEndpoint()
        self.databases = ForbiddenEndpoint()
        self.data_sources = ForbiddenEndpoint()


@pytest.fixture(autouse=True)
def _valid_target_binding(monkeypatch):
    calls: list[tuple[object, object]] = []

    def validate(notion, config):
        calls.append((notion, config))
        return SimpleNamespace(
            valid=True,
            target_parent_fingerprint="parent12",
            target_group_fingerprint="group123",
        )

    monkeypatch.setattr(
        parent_page_guide,
        "validate_notion_target_binding",
        validate,
    )
    return calls


def _run(
    notion: FakeNotion,
    *,
    dry_run: bool = True,
    confirmation: str = "",
):
    return parent_page_guide.run_parent_page_guide(
        notion,
        CONFIG,
        dry_run=dry_run,
        confirmation=confirmation,
    )


def test_guide_contains_complete_required_content_and_version() -> None:
    blocks = parent_page_guide.build_parent_page_guide_blocks()
    text = "\n".join(parent_page_guide._block_text(block) for block in blocks)

    assert text.count(parent_page_guide.GUIDE_VERSION) == 1
    for required in (
        "English Audio Learning Agent",
        "从这里开始",
        "Podcast Library",
        "Expression Database",
        "Vocabulary Database",
        "Weekly Review",
        "数据库入口",
        "推荐日常流程",
        "Weekly Reflection 说明",
        "隐私与安全",
        "粉色文字或粉色背景",
        "自动检测、丰富并写入 Vocabulary Database",
        "每周六上午 10:00",
        "明确确认后启用",
        "自定义星期和时间",
        "查询时间、修改时间、暂停或恢复",
        "用 ChatGPT 继续练习",
        "阅读理解、英语口语、表达复用、词汇复习和场景角色扮演",
        "每周复盘和下一周学习计划",
        "ChatGPT 必须已经连接你自己的 Notion",
        "如果无法读取，必须直接说明，不能猜测页面内容",
        "ChatGPT 不得修改对应的 Notion 页面",
        "不要为了让 ChatGPT 读取而把私人页面公开到互联网",
        "不是训练、微调或永久修改 ChatGPT 模型",
        "公司机密、客户信息或个人隐私",
        "Notion Token、数据库 ID 或其他访问密钥",
    ):
        assert required in text
    assert "同步生词" not in text
    assert "Notion AI-assisted workflow" not in text
    assert "Podcast-page Expression synchronization" not in text


def test_chatgpt_practice_guidance_follows_weekly_and_precedes_privacy() -> None:
    blocks = parent_page_guide.build_parent_page_guide_blocks()
    headings = [
        parent_page_guide._block_text(block)
        for block in blocks
        if block.get("type") == "heading_2"
    ]

    assert headings.index("Weekly Reflection 说明") < headings.index(
        "用 ChatGPT 继续练习"
    )
    assert headings.index("用 ChatGPT 继续练习") < headings.index("隐私与安全")


def test_parent_guide_contains_canonical_practice_prompts_as_code_blocks() -> None:
    blocks = parent_page_guide.build_parent_page_guide_blocks()
    block_text = [
        parent_page_guide._block_text(block)
        for block in blocks
    ]
    chatgpt_index = block_text.index("用 ChatGPT 继续练习")
    podcast_index = block_text.index("Podcast 页面练习 Prompt")
    weekly_index = block_text.index("Weekly Review 页面练习 Prompt")
    privacy_index = block_text.index("隐私与安全")

    assert chatgpt_index < podcast_index < weekly_index < privacy_index
    code_blocks = [block for block in blocks if block.get("type") == "code"]
    assert len(code_blocks) == 2

    podcast_block = blocks[podcast_index + 1]
    weekly_block = blocks[weekly_index + 1]
    assert podcast_block["type"] == "code"
    assert weekly_block["type"] == "code"
    assert podcast_block["code"]["language"] == "plain text"
    assert weekly_block["code"]["language"] == "plain text"

    podcast_prompt = parent_page_guide._block_text(podcast_block)
    weekly_prompt = parent_page_guide._block_text(weekly_block)
    assert podcast_prompt == _canonical_prompt("Podcast 页面练习 Prompt")
    assert weekly_prompt == _canonical_prompt("Weekly Review 页面练习 Prompt")

    for required in (
        "<粘贴 Podcast 页面链接>",
        "不要猜测内容，也不要修改 Notion 页面",
        "最值得掌握的 5 个表达",
        "共 5 个；等我回答后再继续",
        "更自然的英文改写",
        "6 轮角色扮演",
        "重点表达和粉色词汇",
        "10 分钟复习任务",
        "动态调整难度",
        "英文提示",
        "中文提示",
    ):
        assert required in podcast_prompt

    for required in (
        "<粘贴 Weekly Review 页面链接>",
        "不要猜测内容，也不要修改 Notion 页面",
        "20 分钟复盘训练",
        "核心观点、重点表达、词汇、思维变化和下周行动",
        "3 个最值得复用的表达",
        "3 个最需要加强的词汇",
        "一次问我一个问题",
        "2 个与我的真实工作、面试或生活场景相关的角色扮演",
        "准确性、自然度和清晰度评分",
        "1 个主题、3 个表达、3 个词汇、2 个口语任务和 1 个真实应用任务",
        "不要一次给出全部答案",
    ):
        assert required in weekly_prompt


def test_database_entries_precede_instructions_with_icons_and_names_unchanged() -> None:
    blocks = parent_page_guide.build_parent_page_guide_blocks()
    entry_names = (
        "Podcast Library",
        "Expression Database",
        "Vocabulary Database",
        "Weekly Review",
    )
    entry_icons = ("🎧", "💬", "📚", "📝")

    assert parent_page_guide._block_text(blocks[1]) == "数据库入口"
    start_index = next(
        index
        for index, block in enumerate(blocks)
        if parent_page_guide._block_text(block) == "从这里开始"
    )
    entries = [
        block
        for block in blocks[:start_index]
        if block.get("type") == "callout"
    ]

    assert len(entries) == 4
    assert tuple(
        parent_page_guide._block_text(block).splitlines()[0]
        for block in entries
    ) == entry_names
    assert tuple(block["callout"]["icon"]["emoji"] for block in entries) == (
        entry_icons
    )


def test_dry_run_plans_parent_write_and_performs_zero_writes() -> None:
    notion = FakeNotion([_api_block("Existing owner text")])

    report = _run(notion)

    assert report.status == "dry_run_ready"
    assert report.target_binding_pass is True
    assert report.guide_already_exists is False
    assert report.planned_guide_blocks > 0
    assert report.planned_parent_page_writes == 1
    assert report.planned_database_writes == 0
    assert report.planned_record_writes == 0
    assert report.planned_deletes == 0
    assert report.planned_archives == 0
    assert report.historical_database_group_writes == 0
    assert report.real_notion_writes == 0
    assert notion.blocks.children.append_calls == []


def test_live_publish_requires_exact_confirmation_before_reads() -> None:
    notion = FakeNotion()

    with pytest.raises(parent_page_guide.ParentPageGuideError) as missing:
        _run(notion, dry_run=False)
    with pytest.raises(parent_page_guide.ParentPageGuideError) as invalid:
        _run(notion, dry_run=False, confirmation="WRONG")

    assert missing.value.code == parent_page_guide.CONFIRMATION_REQUIRED
    assert invalid.value.code == parent_page_guide.CONFIRMATION_INVALID
    assert notion.blocks.children.list_calls == []
    assert notion.blocks.children.append_calls == []


def test_first_publish_appends_once_without_database_or_record_writes() -> None:
    manual = _api_block("Owner manual text", block_id="manual")
    database = {
        "id": "database-block",
        "type": "child_database",
        "child_database": {"title": "Podcast Library"},
        "archived": False,
        "in_trash": False,
        "last_edited_time": "2026-07-24T00:00:00.000Z",
    }
    notion = FakeNotion([manual, database])

    report = _run(
        notion,
        dry_run=False,
        confirmation=parent_page_guide.WRITE_CONFIRMATION,
    )

    assert report.status == "published"
    assert report.real_notion_writes == 1
    assert report.manual_move_to_top is True
    assert len(notion.blocks.children.append_calls) == 1
    assert notion.blocks.children.blocks[0] == manual
    assert notion.blocks.children.blocks[1] == database
    assert notion.pages.create_calls == []
    assert notion.pages.update_calls == []
    assert notion.databases.create_calls == []
    assert notion.databases.update_calls == []
    assert notion.data_sources.create_calls == []
    assert notion.data_sources.update_calls == []
    assert notion.blocks.children.delete_calls == []


def test_exact_retry_adds_zero_blocks_and_preserves_existing_content() -> None:
    notion = FakeNotion([_api_block("Owner manual text", block_id="manual")])

    first = _run(
        notion,
        dry_run=False,
        confirmation=parent_page_guide.WRITE_CONFIRMATION,
    )
    block_count_after_first = len(notion.blocks.children.blocks)
    second = _run(
        notion,
        dry_run=False,
        confirmation=parent_page_guide.WRITE_CONFIRMATION,
    )

    assert first.status == "published"
    assert second.status == "already_exists"
    assert second.planned_guide_blocks == 0
    assert second.planned_parent_page_writes == 0
    assert second.real_notion_writes == 0
    assert len(notion.blocks.children.append_calls) == 1
    assert len(notion.blocks.children.blocks) == block_count_after_first
    assert parent_page_guide.count_guide_versions(
        notion.blocks.children.blocks
    ) == 1
    assert notion.blocks.children.blocks[0]["id"] == "manual"


def test_existing_version_is_idempotent_with_other_blocks() -> None:
    notion = FakeNotion(
        [
            _api_block("Manual callout", block_type="callout"),
            _api_block(parent_page_guide.GUIDE_VERSION),
            _api_block("Image placeholder"),
        ]
    )

    report = _run(
        notion,
        dry_run=False,
        confirmation=parent_page_guide.WRITE_CONFIRMATION,
    )

    assert report.status == "already_exists"
    assert report.guide_already_exists is True
    assert report.real_notion_writes == 0
    assert notion.blocks.children.append_calls == []


def test_duplicate_version_fails_closed_without_write() -> None:
    notion = FakeNotion(
        [
            _api_block(parent_page_guide.GUIDE_VERSION, block_id="one"),
            _api_block(parent_page_guide.GUIDE_VERSION, block_id="two"),
        ]
    )

    with pytest.raises(parent_page_guide.ParentPageGuideError) as error:
        _run(notion)

    assert error.value.code == parent_page_guide.DUPLICATE_VERSION
    assert notion.blocks.children.append_calls == []


def test_parent_read_failure_stops_without_write() -> None:
    notion = FakeNotion()
    notion.blocks.children.fail_read = True

    with pytest.raises(parent_page_guide.ParentPageGuideError) as error:
        _run(notion)

    assert error.value.code == parent_page_guide.PARENT_READ_FAILED
    assert notion.blocks.children.append_calls == []


def test_target_binding_failure_stops_before_parent_read(monkeypatch) -> None:
    notion = FakeNotion()
    monkeypatch.setattr(
        parent_page_guide,
        "validate_notion_target_binding",
        lambda *_args: (_ for _ in ()).throw(
            NotionTargetBindingError("target_parent_mismatch")
        ),
    )

    with pytest.raises(NotionTargetBindingError):
        _run(notion)

    assert notion.blocks.children.list_calls == []
    assert notion.blocks.children.append_calls == []


def test_parent_state_change_stops_before_append() -> None:
    notion = FakeNotion()
    notion.blocks.children.mutate_before_second_read = True

    with pytest.raises(parent_page_guide.ParentPageGuideError) as error:
        _run(
            notion,
            dry_run=False,
            confirmation=parent_page_guide.WRITE_CONFIRMATION,
        )

    assert error.value.code == parent_page_guide.PARENT_STATE_CHANGED
    assert notion.blocks.children.append_calls == []


def test_write_failure_is_redacted_and_marks_attempt() -> None:
    notion = FakeNotion()
    notion.blocks.children.fail_append = True

    with pytest.raises(parent_page_guide.ParentPageGuideError) as error:
        _run(
            notion,
            dry_run=False,
            confirmation=parent_page_guide.WRITE_CONFIRMATION,
        )

    assert error.value.code == parent_page_guide.WRITE_FAILED
    assert error.value.write_attempted is True
    assert "private write failure" not in str(error.value)
    assert len(notion.blocks.children.append_calls) == 1


def test_post_write_validation_failure_stops() -> None:
    notion = FakeNotion()
    notion.blocks.children.omit_appended_blocks = True

    with pytest.raises(parent_page_guide.ParentPageGuideError) as error:
        _run(
            notion,
            dry_run=False,
            confirmation=parent_page_guide.WRITE_CONFIRMATION,
        )

    assert error.value.code == parent_page_guide.POST_WRITE_VALIDATION_FAILED
    assert error.value.write_attempted is True


def test_post_write_read_failure_reports_unknown_write_outcome(
    monkeypatch,
    capsys,
) -> None:
    notion = FakeNotion()
    notion.blocks.children.fail_read_on_call = 3
    monkeypatch.setattr(parent_page_guide, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        parent_page_guide,
        "load_notion_config",
        lambda: CONFIG,
    )
    monkeypatch.setattr(
        parent_page_guide,
        "create_notion_client",
        lambda _token: notion,
    )

    assert parent_page_guide.main(
        ["--confirmation", parent_page_guide.WRITE_CONFIRMATION]
    ) == 1

    captured = capsys.readouterr()
    assert parent_page_guide.PARENT_READ_FAILED in captured.err
    assert '"write_attempted": true' in captured.err
    assert '"real_notion_writes": "unknown"' in captured.err
    assert len(notion.blocks.children.append_calls) == 1


def test_setup_entrypoint_creates_once_and_retries_idempotently() -> None:
    notion = FakeNotion()

    assert parent_page_guide.ensure_parent_page_guide_for_setup(
        notion,
        PARENT_ID,
    )
    assert not parent_page_guide.ensure_parent_page_guide_for_setup(
        notion,
        PARENT_ID,
    )

    assert len(notion.blocks.children.append_calls) == 1
    assert parent_page_guide.count_guide_versions(
        notion.blocks.children.blocks
    ) == 1


def test_paginated_parent_read_uses_cursor() -> None:
    class PaginatedChildren(FakeChildren):
        def list(self, **kwargs):
            self.list_calls.append(deepcopy(kwargs))
            if "start_cursor" not in kwargs:
                return {
                    "results": [_api_block("first", block_id="first")],
                    "has_more": True,
                    "next_cursor": "cursor-2",
                }
            return {
                "results": [_api_block("second", block_id="second")],
                "has_more": False,
                "next_cursor": None,
            }

    notion = FakeNotion()
    notion.blocks.children = PaginatedChildren()

    blocks = parent_page_guide.list_parent_page_blocks(notion, PARENT_ID)

    assert [block["id"] for block in blocks] == ["first", "second"]
    assert notion.blocks.children.list_calls == [
        {"block_id": PARENT_ID, "page_size": 100},
        {
            "block_id": PARENT_ID,
            "page_size": 100,
            "start_cursor": "cursor-2",
        },
    ]


def test_report_contains_only_safe_fingerprints_not_raw_ids() -> None:
    notion = FakeNotion()

    report = _run(notion)
    rendered = str(report)

    assert PARENT_ID not in rendered
    for raw_id in (
        CONFIG.podcast_database_id,
        CONFIG.expression_database_id,
        CONFIG.vocabulary_database_id,
        CONFIG.weekly_database_id,
    ):
        assert raw_id not in rendered
    assert report.target_parent_fingerprint == "parent12"
    assert report.target_group_fingerprint == "group123"


def test_cli_dry_run_prints_safe_report(monkeypatch, capsys) -> None:
    notion = FakeNotion([_api_block("Existing database area")])
    monkeypatch.setattr(parent_page_guide, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        parent_page_guide,
        "load_notion_config",
        lambda: CONFIG,
    )
    monkeypatch.setattr(
        parent_page_guide,
        "create_notion_client",
        lambda _token: notion,
    )

    assert parent_page_guide.main(["--dry-run"]) == 0

    output = capsys.readouterr().out
    assert '"status": "dry_run_ready"' in output
    assert '"real_notion_writes": 0' in output
    assert parent_page_guide.GUIDE_VERSION in output
    assert "move the complete guide to the top" in output
    assert PARENT_ID not in output
    assert notion.blocks.children.append_calls == []


def test_cli_rejects_missing_confirmation_with_safe_error(
    monkeypatch,
    capsys,
) -> None:
    notion = FakeNotion()
    monkeypatch.setattr(parent_page_guide, "load_dotenv", lambda: None)
    monkeypatch.setattr(
        parent_page_guide,
        "load_notion_config",
        lambda: CONFIG,
    )
    monkeypatch.setattr(
        parent_page_guide,
        "create_notion_client",
        lambda _token: notion,
    )

    assert parent_page_guide.main([]) == 1

    captured = capsys.readouterr()
    assert parent_page_guide.CONFIRMATION_REQUIRED in captured.err
    assert '"real_notion_writes": 0' in captured.err
    assert CONFIG.token not in captured.err
    assert notion.blocks.children.list_calls == []
    assert notion.blocks.children.append_calls == []
