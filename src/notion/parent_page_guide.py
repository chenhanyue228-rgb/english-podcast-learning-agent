"""Create the idempotent user guide on the configured Notion parent page.

The standalone command is intentionally protected:

    python -m src.notion.parent_page_guide --dry-run
    python -m src.notion.parent_page_guide \
        --confirmation PARENT_PAGE_GUIDE_WRITES_TO_NOTION

First-time workspace setup uses the same deterministic guide builder before it
creates databases. Existing workspaces must use the protected command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

from src.notion.config import (
    NotionConfig,
    NotionConfigError,
    load_dotenv,
    load_notion_config,
)
from src.notion.setup_workspace import create_notion_client
from src.notion.target_binding import (
    NotionTargetBindingError,
    validate_notion_target_binding,
)


GUIDE_VERSION = "EPLA_PARENT_GUIDE_V1"
WRITE_CONFIRMATION = "PARENT_PAGE_GUIDE_WRITES_TO_NOTION"

PODCAST_PRACTICE_PROMPT = """请读取下面的 Notion Podcast 学习页面：
<粘贴 Podcast 页面链接>

如果你无法访问该页面，请直接告诉我，不要猜测内容，也不要修改 Notion 页面。

请把页面作为本次英语训练素材，并按教练式对话带我练习：

1. 先用中文概括主题、难度，以及最值得掌握的 5 个表达。
2. 用英语一次问我一个理解问题，共 5 个；等我回答后再继续。
3. 每次反馈先给更自然的英文改写，再用中文简要说明原因。
4. 基于页面内容设计一个与工作、面试或日常生活相关的 6 轮角色扮演。
5. 主动引导我使用页面中的重点表达和粉色词汇。
6. 最后总结我的主要错误、可复用表达，并给出一个 10 分钟复习任务。

请根据我的回答动态调整难度；我卡住时先给英文提示，仍无法回答再给中文提示。"""

WEEKLY_REVIEW_PRACTICE_PROMPT = """请读取下面的 Notion Weekly Review 页面：
<粘贴 Weekly Review 页面链接>

如果你无法访问该页面，请直接告诉我，不要猜测内容，也不要修改 Notion 页面。

请把它作为我本周的学习档案，带我完成一次 20 分钟复盘训练：

1. 先用中文提炼本周核心观点、重点表达、词汇、思维变化和下周行动。
2. 选出 3 个最值得复用的表达和 3 个最需要加强的词汇。
3. 用英语一次问我一个问题，测试我能否解释核心观点并举例应用。
4. 设计 2 个与我的真实工作、面试或生活场景相关的角色扮演。
5. 对我的回答分别从准确性、自然度和清晰度评分，并给出更自然的英文改写。
6. 最后生成下一周练习计划：1 个主题、3 个表达、3 个词汇、2 个口语任务和 1 个真实应用任务。

不要一次给出全部答案，请逐步提问并等待我回答。"""

CONFIRMATION_REQUIRED = "parent_guide_confirmation_required"
CONFIRMATION_INVALID = "parent_guide_confirmation_invalid"
PARENT_READ_FAILED = "parent_guide_parent_read_failed"
PARENT_RESPONSE_INVALID = "parent_guide_parent_response_invalid"
DUPLICATE_VERSION = "parent_guide_duplicate_version"
PARENT_STATE_CHANGED = "parent_guide_parent_state_changed"
WRITE_FAILED = "parent_guide_write_failed"
POST_WRITE_VALIDATION_FAILED = "parent_guide_post_write_validation_failed"


class ParentPageGuideError(RuntimeError):
    """A stable, redacted error raised before or during guide publication."""

    def __init__(self, code: str, *, write_attempted: bool = False) -> None:
        self.code = code
        self.write_attempted = write_attempted
        super().__init__(code)


@dataclass(frozen=True)
class ParentPageGuideReport:
    """Safe report that never contains raw Notion identifiers or page text."""

    status: str
    target_binding_pass: bool
    guide_version: str
    guide_already_exists: bool
    planned_guide_blocks: int
    planned_parent_page_writes: int
    planned_database_writes: int
    planned_record_writes: int
    planned_deletes: int
    planned_archives: int
    historical_database_group_writes: int
    real_notion_writes: int
    target_parent_fingerprint: str
    target_group_fingerprint: str
    manual_move_to_top: bool


def _rich_text(content: str, *, code: bool = False) -> list[dict[str, Any]]:
    annotations = {"code": True} if code else {}
    return [
        {
            "type": "text",
            "text": {"content": content},
            "annotations": annotations,
        }
    ]


def _text_block(
    block_type: str,
    content: str,
    *,
    code: bool = False,
) -> dict[str, Any]:
    return {
        "object": "block",
        "type": block_type,
        block_type: {"rich_text": _rich_text(content, code=code)},
    }


def _code_block(
    content: str,
    language: str = "plain text",
) -> dict[str, Any]:
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": _rich_text(content),
            "language": language,
        },
    }


def _database_entry(
    name: str,
    description: str,
    *,
    emoji: str,
) -> dict[str, Any]:
    """Return a visual database entry without changing the database name."""
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(f"{name}\n{description}"),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": "default_background",
        },
    }


def build_parent_page_guide_blocks() -> list[dict[str, Any]]:
    """Return the complete deterministic V1 parent-page guide."""
    blocks = [
        _text_block("heading_1", "English Audio Learning Agent"),
        _text_block("heading_2", "数据库入口"),
        _database_entry(
            "Podcast Library",
            "保存每期音频、摘要、重点内容和学习材料。",
            emoji="🎧",
        ),
        _database_entry(
            "Expression Database",
            "保存值得复用的地道表达、商务短语、行业术语、搭配和句型。",
            emoji="💬",
        ),
        _database_entry(
            "Vocabulary Database",
            "保存用户用粉色文字或粉色背景主动选择、并由系统自动处理的生词。",
            emoji="📚",
        ),
        _database_entry(
            "Weekly Review",
            "保存自动生成的 Weekly Reflection 学习复盘。",
            emoji="📝",
        ),
        _text_block(
            "paragraph",
            "把英语 Podcast、RSS 或本地音频整理成可持续复习的 Notion 学习系统。",
        ),
        _text_block("heading_2", "从这里开始"),
        _text_block(
            "numbered_list_item",
            "选择一个不包含隐私内容的英语音频。",
        ),
        _text_block(
            "numbered_list_item",
            "让 Agent 处理音频并生成 Podcast 学习页。",
        ),
        _text_block(
            "numbered_list_item",
            "在 Podcast 页面查看摘要、重点内容和表达。",
        ),
        _text_block(
            "numbered_list_item",
            "将不熟悉的单词设置为粉色文字或粉色背景。",
        ),
        _text_block(
            "numbered_list_item",
            "系统自动检测、丰富并写入 Vocabulary Database。",
        ),
        _text_block(
            "numbered_list_item",
            "学习数据充分后生成 Weekly Reflection。",
        ),
        _text_block("heading_2", "推荐日常流程"),
        _text_block(
            "paragraph",
            "听音频 → 阅读 Podcast 学习页 → 复习 Expression → "
            "粉色高亮生词 → 自动写入 Vocabulary → 每周生成 Weekly Reflection",
        ),
        _text_block("heading_2", "Weekly Reflection 说明"),
        _text_block(
            "paragraph",
            "Weekly Reflection 只有在本周存在足够学习数据时才生成。",
        ),
        _text_block(
            "paragraph",
            "本地自动计划在用户明确确认后启用；默认时间为每周六上午 10:00，"
            "也可以通过 Agent 修改、暂停或恢复。",
        ),
        _text_block(
            "paragraph",
            "第一次设置时可以使用默认时间、自定义星期和时间，或暂不开启。"
            "之后可以直接用自然语言查询时间、修改时间、暂停或恢复，无需打开"
            "终端、编辑配置文件或管理 LaunchAgent。",
        ),
        _text_block(
            "paragraph",
            "单次使用后没有 Weekly Reflection，不代表系统故障。",
        ),
        _text_block("heading_2", "用 ChatGPT 继续练习"),
        _text_block(
            "paragraph",
            "可以把 Podcast 学习页面链接发送给 ChatGPT，继续做阅读理解、"
            "英语口语、表达复用、词汇复习和场景角色扮演。",
        ),
        _text_block(
            "paragraph",
            "可以把 Weekly Review 页面链接发送给 ChatGPT，完成每周复盘和"
            "下一周学习计划。",
        ),
        _text_block(
            "paragraph",
            "ChatGPT 必须已经连接你自己的 Notion，并有权限读取对应页面。"
            "如果无法读取，必须直接说明，不能猜测页面内容；你可以改为粘贴"
            "页面内容或上传不含敏感信息的 Notion 导出文件。",
        ),
        _text_block(
            "paragraph",
            "ChatGPT 不得修改对应的 Notion 页面，也不要为了让 ChatGPT 读取而"
            "把私人页面公开到互联网。",
        ),
        _text_block(
            "paragraph",
            "这是当前对话中的个性化练习，不是训练、微调或永久修改 ChatGPT"
            " 模型。",
        ),
        _text_block("heading_3", "Podcast 页面练习 Prompt"),
        _code_block(PODCAST_PRACTICE_PROMPT),
        _text_block("heading_3", "Weekly Review 页面练习 Prompt"),
        _code_block(WEEKLY_REVIEW_PRACTICE_PROMPT),
        _text_block("heading_2", "隐私与安全"),
        _text_block(
            "bulleted_list_item",
            "不要使用包含隐私或机密内容的音频。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要在聊天中粘贴 Notion Token。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要粘贴完整数据库 ID。",
        ),
        _text_block(
            "bulleted_list_item",
            "只在 ChatGPT 已连接你自己的 Notion 且有页面读取权限时，在当前"
            "对话中提供页面链接；不要把私人页面公开到互联网。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要使用包含公司机密、客户信息或个人隐私的页面。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要在练习内容中提供 Notion Token、数据库 ID 或其他访问密钥。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要删除、重建或重命名四个核心数据库。",
        ),
        _text_block(
            "bulleted_list_item",
            "不要删除、重建或重命名现有 Select options。",
        ),
        _text_block(
            "bulleted_list_item",
            "遇到错误时，先保留当前页面和数据，再向 Agent 描述看到的错误。",
        ),
        _text_block("paragraph", GUIDE_VERSION, code=True),
    ]
    return blocks


def _plain_text(rich_text: object) -> str:
    if not isinstance(rich_text, list):
        return ""
    parts: list[str] = []
    for item in rich_text:
        if not isinstance(item, Mapping):
            continue
        plain_text = item.get("plain_text")
        text_payload = item.get("text")
        content = (
            text_payload.get("content")
            if isinstance(text_payload, Mapping)
            else ""
        )
        parts.append(str(plain_text or content or ""))
    return "".join(parts)


def _block_text(block: Mapping[str, Any]) -> str:
    block_type = str(block.get("type") or "")
    payload = block.get(block_type)
    if not isinstance(payload, Mapping):
        return ""
    return _plain_text(payload.get("rich_text"))


def list_parent_page_blocks(
    notion: Any,
    parent_page_id: str,
) -> list[dict[str, Any]]:
    """Read every direct child block without mutating the parent page."""
    blocks: list[dict[str, Any]] = []
    cursor: Optional[str] = None

    while True:
        kwargs: dict[str, Any] = {
            "block_id": parent_page_id,
            "page_size": 100,
        }
        if cursor:
            kwargs["start_cursor"] = cursor
        try:
            response = notion.blocks.children.list(**kwargs)
        except Exception:
            raise ParentPageGuideError(PARENT_READ_FAILED) from None
        if not isinstance(response, Mapping):
            raise ParentPageGuideError(PARENT_RESPONSE_INVALID)

        results = response.get("results")
        if not isinstance(results, list):
            raise ParentPageGuideError(PARENT_RESPONSE_INVALID)
        for block in results:
            if not isinstance(block, Mapping):
                raise ParentPageGuideError(PARENT_RESPONSE_INVALID)
            blocks.append(dict(block))

        if not response.get("has_more"):
            return blocks
        cursor_value = response.get("next_cursor")
        if not isinstance(cursor_value, str) or not cursor_value:
            raise ParentPageGuideError(PARENT_RESPONSE_INVALID)
        cursor = cursor_value


def count_guide_versions(blocks: Sequence[Mapping[str, Any]]) -> int:
    return sum(GUIDE_VERSION in _block_text(block) for block in blocks)


def _parent_snapshot_fingerprint(
    blocks: Sequence[Mapping[str, Any]],
) -> str:
    safe_material = [
        {
            "id": str(block.get("id") or ""),
            "type": str(block.get("type") or ""),
            "archived": bool(block.get("archived", False)),
            "in_trash": bool(block.get("in_trash", False)),
            "last_edited_time": str(block.get("last_edited_time") or ""),
            "text": _block_text(block),
        }
        for block in blocks
    ]
    encoded = json.dumps(
        safe_material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _append_guide(
    notion: Any,
    parent_page_id: str,
    blocks: Sequence[Mapping[str, Any]],
) -> None:
    try:
        notion.blocks.children.append(
            block_id=parent_page_id,
            children=[dict(block) for block in blocks],
        )
    except Exception:
        raise ParentPageGuideError(
            WRITE_FAILED,
            write_attempted=True,
        ) from None


def _verify_after_append(
    notion: Any,
    parent_page_id: str,
) -> None:
    try:
        verified_blocks = list_parent_page_blocks(notion, parent_page_id)
    except ParentPageGuideError as exc:
        raise ParentPageGuideError(
            exc.code,
            write_attempted=True,
        ) from None
    if count_guide_versions(verified_blocks) != 1:
        raise ParentPageGuideError(
            POST_WRITE_VALIDATION_FAILED,
            write_attempted=True,
        )


def ensure_parent_page_guide_for_setup(
    notion: Any,
    parent_page_id: str,
) -> bool:
    """Create the guide during initial setup; return whether it was appended.

    This setup-only entrypoint deliberately does not validate a complete target
    binding because the four databases do not exist yet. It performs no action
    other than reading and appending direct child blocks.
    """
    existing_blocks = list_parent_page_blocks(notion, parent_page_id)
    version_count = count_guide_versions(existing_blocks)
    if version_count > 1:
        raise ParentPageGuideError(DUPLICATE_VERSION)
    if version_count == 1:
        return False

    guide_blocks = build_parent_page_guide_blocks()
    before_fingerprint = _parent_snapshot_fingerprint(existing_blocks)
    current_blocks = list_parent_page_blocks(notion, parent_page_id)
    if _parent_snapshot_fingerprint(current_blocks) != before_fingerprint:
        raise ParentPageGuideError(PARENT_STATE_CHANGED)

    _append_guide(notion, parent_page_id, guide_blocks)
    _verify_after_append(notion, parent_page_id)
    return True


def run_parent_page_guide(
    notion: Any,
    config: NotionConfig,
    *,
    dry_run: bool,
    confirmation: str = "",
) -> ParentPageGuideReport:
    """Plan or publish the guide after proving the configured target group."""
    if not dry_run:
        if not confirmation:
            raise ParentPageGuideError(CONFIRMATION_REQUIRED)
        if confirmation != WRITE_CONFIRMATION:
            raise ParentPageGuideError(CONFIRMATION_INVALID)

    binding = validate_notion_target_binding(notion, config)
    existing_blocks = list_parent_page_blocks(
        notion,
        config.target_parent_page_id,
    )
    version_count = count_guide_versions(existing_blocks)
    if version_count > 1:
        raise ParentPageGuideError(DUPLICATE_VERSION)

    guide_exists = version_count == 1
    guide_blocks = build_parent_page_guide_blocks()
    planned_writes = 0 if guide_exists else 1
    report_kwargs = {
        "target_binding_pass": binding.valid,
        "guide_version": GUIDE_VERSION,
        "guide_already_exists": guide_exists,
        "planned_guide_blocks": 0 if guide_exists else len(guide_blocks),
        "planned_parent_page_writes": planned_writes,
        "planned_database_writes": 0,
        "planned_record_writes": 0,
        "planned_deletes": 0,
        "planned_archives": 0,
        "historical_database_group_writes": 0,
        "target_parent_fingerprint": binding.target_parent_fingerprint,
        "target_group_fingerprint": binding.target_group_fingerprint,
        "manual_move_to_top": bool(existing_blocks) and not guide_exists,
    }

    if guide_exists:
        return ParentPageGuideReport(
            status="already_exists",
            real_notion_writes=0,
            **report_kwargs,
        )
    if dry_run:
        return ParentPageGuideReport(
            status="dry_run_ready",
            real_notion_writes=0,
            **report_kwargs,
        )

    before_fingerprint = _parent_snapshot_fingerprint(existing_blocks)
    current_blocks = list_parent_page_blocks(
        notion,
        config.target_parent_page_id,
    )
    if _parent_snapshot_fingerprint(current_blocks) != before_fingerprint:
        raise ParentPageGuideError(PARENT_STATE_CHANGED)

    _append_guide(
        notion,
        config.target_parent_page_id,
        guide_blocks,
    )
    _verify_after_append(
        notion,
        config.target_parent_page_id,
    )

    return ParentPageGuideReport(
        status="published",
        real_notion_writes=1,
        **report_kwargs,
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Safely add the English Audio Learning Agent parent-page guide."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and plan without writing to Notion.",
    )
    parser.add_argument(
        "--confirmation",
        default="",
        help="Exact one-time write confirmation for live mode.",
    )
    return parser.parse_args(argv)


def _print_report(report: ParentPageGuideReport) -> None:
    print(json.dumps(asdict(report), ensure_ascii=False, indent=2, sort_keys=True))
    if report.manual_move_to_top:
        print(
            "Guide position: appended safely. The Owner may move the complete "
            "guide to the top in the Notion UI."
        )


def main(argv: Optional[Sequence[str]] = None) -> int:
    load_dotenv()
    args = parse_args(argv)

    try:
        config = load_notion_config()
        notion = create_notion_client(config.token)
        report = run_parent_page_guide(
            notion,
            config,
            dry_run=args.dry_run,
            confirmation=args.confirmation,
        )
    except (
        NotionConfigError,
        NotionTargetBindingError,
        ParentPageGuideError,
    ) as exc:
        error_code = getattr(exc, "code", "parent_guide_configuration_invalid")
        write_attempted = bool(getattr(exc, "write_attempted", False))
        print(
            json.dumps(
                {
                    "status": "SAFE_STOP",
                    "error_code": error_code,
                    "write_attempted": write_attempted,
                    "real_notion_writes": (
                        "unknown" if write_attempted else 0
                    ),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1

    _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
