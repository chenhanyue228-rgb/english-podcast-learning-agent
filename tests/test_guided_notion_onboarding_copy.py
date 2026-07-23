from __future__ import annotations

import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL = (PROJECT_ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
USER_GUIDE = (PROJECT_ROOT / "docs" / "USER_GUIDE_ZH.md").read_text(
    encoding="utf-8"
)
NOTION_GUIDE = (PROJECT_ROOT / "docs" / "Notion_Onboarding.md").read_text(
    encoding="utf-8"
)


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


VISIBLE_CONTRACT = _between(
    SKILL,
    "### User-Visible Notion Conversation Contract",
    "### First-Time Setup Responsibilities",
)
DEVELOPER_CONNECTION_STEPS = _between(
    VISIBLE_CONTRACT,
    "#### Step 1: Open the Developer Dashboard",
    "#### Step 6: Open Notion and Create the Learning Page",
)
PAGE_INTEGRATION_STEP = _between(
    VISIBLE_CONTRACT,
    "#### Step 7: Add the Integration to the Page",
    "#### Step 8: Copy the Page Link",
)

REPLY_SEQUENCE = (
    "开发者页面已打开",
    "连接列表已打开",
    "连接页面已打开",
    "权限已确认",
    "密钥已保存",
    "已打开 Notion",
    "页面已创建",
    "集成已添加",
    "链接已复制",
)


def _assert_in_order(text: str, phrases: tuple[str, ...]) -> None:
    positions = [text.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)


def test_unified_notion_reply_nodes_are_in_order() -> None:
    _assert_in_order(VISIBLE_CONTRACT, REPLY_SEQUENCE)


def test_each_unified_step_requires_waiting() -> None:
    for reply in REPLY_SEQUENCE:
        assert f"must wait for `{reply}`" in VISIBLE_CONTRACT


def test_contract_does_not_preclassify_existing_connection() -> None:
    assert "你是否已有可以使用的 Notion 内部连接" not in VISIBLE_CONTRACT
    assert "When the user says `已有`" not in VISIBLE_CONTRACT
    assert "When the user says `没有`" not in VISIBLE_CONTRACT


def test_developer_dashboard_uses_connection_term() -> None:
    assert "开发者后台左侧栏的“连接”" in DEVELOPER_CONNECTION_STEPS
    assert "连接列表已打开" in DEVELOPER_CONNECTION_STEPS
    assert "连接页面已打开" in DEVELOPER_CONNECTION_STEPS


def test_notion_page_uses_integration_term_only() -> None:
    assert "找到“集成”" in PAGE_INTEGRATION_STEP
    assert "点击“集成”" in PAGE_INTEGRATION_STEP
    assert "集成已添加" in PAGE_INTEGRATION_STEP
    assert "Connections" not in PAGE_INTEGRATION_STEP
    assert "添加连接" not in PAGE_INTEGRATION_STEP


def test_permissions_and_token_are_from_connection_configuration() -> None:
    assert "当前连接的“配置”页面" in DEVELOPER_CONNECTION_STEPS
    assert "同一个连接配置页面找到“访问令牌”" in DEVELOPER_CONNECTION_STEPS
    for permission in ("读取内容", "更新内容", "插入内容"):
        assert permission in DEVELOPER_CONNECTION_STEPS


def test_local_setup_is_not_part_of_visible_steps() -> None:
    assert "scripts/first_time_setup.py" not in VISIBLE_CONTRACT
    assert "start_setup.command" not in VISIBLE_CONTRACT
    responsibilities = SKILL.split("### First-Time Setup Responsibilities", 1)[1]
    assert "After the user replies `链接已复制`" in responsibilities
    assert "scripts/first_time_setup.py" in responsibilities


def test_formal_user_copy_avoids_internal_acceptance_terms() -> None:
    for forbidden in (
        "一次性测试父页面",
        "测试父页面",
        "测试连接密钥",
        "Notion 授权已经完成",
        "parent page ID",
        "database ID",
        "workspace initialization",
        "disposable environment",
    ):
        assert forbidden not in VISIBLE_CONTRACT


def test_secrets_and_page_link_stay_out_of_chat() -> None:
    assert "不要发送到聊天" in VISIBLE_CONTRACT
    assert "请先保留这个链接，不要发送到聊天" in VISIBLE_CONTRACT
    assert "本地安全窗口" in VISIBLE_CONTRACT
    assert "访问密钥和页面链接都不发送到聊天" in USER_GUIDE


def test_user_does_not_decide_technical_validation() -> None:
    assert "用户不需要判断技术授权或" in NOTION_GUIDE
    assert "数据库验证是否成功" in NOTION_GUIDE


def test_missing_integration_control_has_recovery_copy() -> None:
    assert "如果仍然找不到" in PAGE_INTEGRATION_STEP
    assert "页面右上角现在有哪些按钮" in PAGE_INTEGRATION_STEP
    assert "不包含密钥的截图" in PAGE_INTEGRATION_STEP


def test_owner_acceptance_prompt_cannot_override_user_copy() -> None:
    boundary = SKILL.split("### Owner Acceptance Prompt Boundary", 1)[1]
    assert "must not rewrite or override" in boundary
    assert "user-visible copy" in boundary


def test_guides_match_unified_reply_sequence() -> None:
    _assert_in_order(USER_GUIDE, REPLY_SEQUENCE)
    _assert_in_order(NOTION_GUIDE, REPLY_SEQUENCE)


def test_guides_distinguish_connection_and_integration() -> None:
    assert "开发者后台中的入口名称是“连接”" in USER_GUIDE
    assert "普通 Notion 页面中的授权入口名称是“集成”" in USER_GUIDE
    assert "开发者后台左侧入口使用“连接”" in NOTION_GUIDE
    assert "普通 Notion 页面右上角授权入口使用“集成”" in NOTION_GUIDE


def test_database_display_order_is_fixed() -> None:
    expected = (
        "Podcast Library",
        "Expression Database",
        "Vocabulary Database",
        "Weekly Review",
    )
    for document in (USER_GUIDE, NOTION_GUIDE):
        _assert_in_order(document, expected)


def test_guides_do_not_use_failed_owner_acceptance_instruction() -> None:
    failed_copy = "Notion 授权已经完成"
    assert failed_copy not in USER_GUIDE
    assert failed_copy not in NOTION_GUIDE


def test_user_guide_second_level_section_numbers_are_continuous() -> None:
    section_numbers = [
        int(number)
        for number in re.findall(r"^## (\d+)\.", USER_GUIDE, flags=re.MULTILINE)
    ]
    assert section_numbers == list(range(1, len(section_numbers) + 1))


def test_user_journey_table_stage_numbers_are_continuous() -> None:
    stage_numbers = [
        int(number)
        for number in re.findall(r"^\| (\d+)\.", USER_GUIDE, flags=re.MULTILINE)
    ]
    assert stage_numbers == list(range(1, len(stage_numbers) + 1))
