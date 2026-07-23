from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
SKILL = (PROJECT_ROOT / "skill" / "SKILL.md").read_text(encoding="utf-8")
USER_GUIDE = (PROJECT_ROOT / "docs" / "USER_GUIDE_ZH.md").read_text(
    encoding="utf-8"
)
NOTION_GUIDE = (PROJECT_ROOT / "docs" / "Notion_Onboarding.md").read_text(
    encoding="utf-8"
)
CONTRACT_TEXT = "\n".join((README, SKILL, USER_GUIDE, NOTION_GUIDE))


def test_contract_does_not_require_memorized_phrase() -> None:
    assert "用户只需要记住一句话" not in CONTRACT_TEXT


def test_contract_does_not_require_new_conversation() -> None:
    assert "必须新建一个 Codex 对话" not in CONTRACT_TEXT


def test_current_conversation_is_primary() -> None:
    assert "当前对话优先继续" in CONTRACT_TEXT


def test_new_conversation_is_fallback() -> None:
    assert "新建对话作为第一次备用" in CONTRACT_TEXT


def test_restart_is_second_fallback() -> None:
    assert "重启 Codex 作为第二次备用" in CONTRACT_TEXT


def test_repository_url_is_limited_to_installation_stage() -> None:
    assert "仓库地址只在安装阶段提供一次" in USER_GUIDE


def test_first_time_setup_instruction_has_no_repository_url() -> None:
    instruction = "请使用英语音频学习助手，带我完成第一次设置。"
    assert instruction in CONTRACT_TEXT
    assert "github.com" not in instruction


def test_podcast_instruction_has_no_repository_url() -> None:
    instruction = "请使用英语音频学习助手处理这个播客"
    assert instruction in CONTRACT_TEXT
    assert "github.com" not in instruction


def test_user_is_not_required_to_find_project_folder() -> None:
    assert "不需要寻找项目目录" in CONTRACT_TEXT


def test_user_is_not_required_to_type_cd() -> None:
    assert "不需要输入 `cd`" in CONTRACT_TEXT


def test_codex_owns_project_acquisition_and_location() -> None:
    assert "自动获取或定位完整项目" in CONTRACT_TEXT


def test_notion_official_entry_is_documented() -> None:
    assert "https://www.notion.so/developers" in CONTRACT_TEXT


def test_token_must_not_be_sent_to_chat() -> None:
    assert "不要发送到聊天" in CONTRACT_TEXT


def test_page_url_must_not_be_sent_to_chat() -> None:
    assert "访问密钥和页面链接都不发送到聊天" in USER_GUIDE


def test_safe_setup_tool_is_documented() -> None:
    assert "scripts/first_time_setup.py" in CONTRACT_TEXT
    assert "start_setup.command" in CONTRACT_TEXT


def test_full_parent_page_url_is_supported() -> None:
    assert "完整页面链接" in CONTRACT_TEXT


def test_manual_page_id_extraction_is_not_required() -> None:
    assert "不需要手动提取页面编号" in CONTRACT_TEXT


def test_four_databases_are_documented() -> None:
    for name in (
        "Podcast Library",
        "Expression Database",
        "Weekly Review",
        "Vocabulary Database",
    ):
        assert name in CONTRACT_TEXT


def test_codex_automates_database_creation_and_validation() -> None:
    assert "自动创建和检查" in CONTRACT_TEXT


def test_success_flow_prompts_for_podcast() -> None:
    assert "主动提示用户发送" in CONTRACT_TEXT


def test_terminal_commands_are_fallback_only() -> None:
    assert "手动终端命令只属于最终备用方案" in CONTRACT_TEXT


def test_user_guide_has_all_30_path_stages() -> None:
    for stage_number in range(1, 31):
        assert f"| {stage_number}." in USER_GUIDE
