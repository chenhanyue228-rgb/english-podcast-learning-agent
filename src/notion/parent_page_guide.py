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


def build_parent_page_guide_blocks() -> list[dict[str, Any]]:
    """Return the complete deterministic V1 parent-page guide."""
    blocks = [
        _text_block("heading_1", "English Audio Learning Agent"),
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
            "将不熟悉的单词用粉色高亮。",
        ),
        _text_block(
            "numbered_list_item",
            "使用正式的 targeted Vocabulary 流程同步生词。",
        ),
        _text_block(
            "numbered_list_item",
            "学习数据充分后生成 Weekly Reflection。",
        ),
        _text_block("heading_2", "四个数据库"),
        _text_block("heading_3", "Podcast Library"),
        _text_block(
            "paragraph",
            "保存每期音频、摘要、重点内容和学习材料。",
        ),
        _text_block("heading_3", "Expression Database"),
        _text_block(
            "paragraph",
            "保存值得复用的地道表达、商务短语、行业术语、搭配和句型。",
        ),
        _text_block("heading_3", "Vocabulary Database"),
        _text_block(
            "paragraph",
            "保存用户主动用粉色高亮并确认同步的生词。",
        ),
        _text_block("heading_3", "Weekly Review"),
        _text_block("paragraph", "保存 Weekly Reflection，包括："),
        _text_block("bulleted_list_item", "知识总结"),
        _text_block("bulleted_list_item", "表达提升"),
        _text_block("bulleted_list_item", "生词复习"),
        _text_block("bulleted_list_item", "职业思考"),
        _text_block("bulleted_list_item", "下一步学习方向"),
        _text_block("heading_2", "推荐日常流程"),
        _text_block(
            "paragraph",
            "听音频 → 阅读 Podcast 学习页 → 复习 Expression → "
            "粉色高亮生词 → 同步 Vocabulary → 每周生成 Weekly Reflection",
        ),
        _text_block("heading_2", "Weekly Reflection 说明"),
        _text_block(
            "paragraph",
            "Weekly Reflection 只有在本周存在足够学习数据时才生成。",
        ),
        _text_block(
            "paragraph",
            "单次使用后没有 Weekly Reflection，不代表系统故障。",
        ),
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
            "不要分享私人 Notion 页面链接。",
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
    verified_blocks = list_parent_page_blocks(notion, parent_page_id)
    if count_guide_versions(verified_blocks) != 1:
        raise ParentPageGuideError(POST_WRITE_VALIDATION_FAILED)
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
    verified_blocks = list_parent_page_blocks(
        notion,
        config.target_parent_page_id,
    )
    if count_guide_versions(verified_blocks) != 1:
        raise ParentPageGuideError(POST_WRITE_VALIDATION_FAILED)

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
