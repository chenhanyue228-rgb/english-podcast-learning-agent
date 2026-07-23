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
EXISTING_PATH = _between(
    VISIBLE_CONTRACT,
    "#### Existing Notion Connection",
    "#### No Existing Notion Connection",
)
NO_CONNECTION_PATH = VISIBLE_CONTRACT.split(
    "#### No Existing Notion Connection", 1
)[1]


def _assert_in_order(text: str, phrases: tuple[str, ...]) -> None:
    positions = [text.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)


def test_existing_connection_reply_nodes_are_in_order() -> None:
    _assert_in_order(
        EXISTING_PATH,
        ("已打开 Notion", "页面已创建", "连接已添加", "链接已复制"),
    )


def test_no_connection_reply_nodes_are_in_order() -> None:
    _assert_in_order(
        NO_CONNECTION_PATH,
        (
            "开发者页面已打开",
            "连接已创建",
            "密钥已保存",
            "已打开 Notion",
            "页面已创建",
            "连接已添加",
            "链接已复制",
        ),
    )


def test_each_existing_connection_step_requires_waiting() -> None:
    for reply in ("已打开 Notion", "页面已创建", "连接已添加", "链接已复制"):
        assert f"must wait for `{reply}`" in EXISTING_PATH


def test_each_connection_creation_step_requires_waiting() -> None:
    for reply in ("开发者页面已打开", "连接已创建", "密钥已保存"):
        assert f"must wait for `{reply}`" in NO_CONNECTION_PATH
    assert "Every later reply gate remains mandatory" in NO_CONNECTION_PATH


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


def test_missing_connection_control_has_recovery_copy() -> None:
    assert "如果仍然找不到" in VISIBLE_CONTRACT
    assert "页面右上角现在有哪些按钮" in VISIBLE_CONTRACT
    assert "不包含密钥的截图" in VISIBLE_CONTRACT


def test_owner_acceptance_prompt_cannot_override_user_copy() -> None:
    boundary = SKILL.split("### Owner Acceptance Prompt Boundary", 1)[1]
    assert "must not rewrite or override" in boundary
    assert "user-visible copy" in boundary


def test_user_guide_matches_reply_sequences() -> None:
    _assert_in_order(
        USER_GUIDE,
        ("已打开 Notion", "页面已创建", "连接已添加", "链接已复制"),
    )
    no_connection_section = USER_GUIDE.split(
        "## 4. Notion 第一次设置：没有连接", 1
    )[1]
    _assert_in_order(
        no_connection_section,
        (
            "开发者页面已打开",
            "连接已创建",
            "密钥已保存",
            "已打开 Notion",
            "页面已创建",
            "连接已添加",
            "链接已复制",
        ),
    )


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
