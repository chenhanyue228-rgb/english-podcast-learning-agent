"""安全完成 English Audio Learning Agent 的第一次 Notion 设置。

普通用户应由 Codex 自动启动本脚本，或在 macOS 上双击项目根目录中的
``start_setup.command``。访问密钥通过隐藏输入读取，不进入命令参数、日志或
聊天记录。
"""

from __future__ import annotations

import getpass
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Optional, Sequence


SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_PROJECT_ROOT = SCRIPT_PATH.parents[1]
if str(DEFAULT_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULT_PROJECT_ROOT))

from src.notion.config import (  # noqa: E402
    EXPRESSION_DATABASE_ID_ENV,
    LEGACY_WEEKLY_DATABASE_ID_ENV,
    NOTION_PARENT_PAGE_ID_ENV,
    NOTION_TARGET_PARENT_PAGE_ID_ENV,
    NOTION_TOKEN_ENV,
    PODCAST_DATABASE_ID_ENV,
    VOCABULARY_DATABASE_ID_ENV,
    WEEKLY_DATABASE_ID_ENV,
)
from src.notion.setup_workspace import (  # noqa: E402
    WorkspaceSetupError,
    create_base_databases,
    create_notion_client,
    normalize_notion_id,
    reconcile_workspace_schema,
    wire_database_relations,
)
from src.notion.parent_page_guide import (  # noqa: E402
    ParentPageGuideError,
    ensure_parent_page_database_links,
    ensure_parent_page_guide_for_setup,
)


PROJECT_MARKERS = (
    "README.md",
    "skill",
    "scripts",
    "src",
    "requirements.txt",
    ".env.example",
)

DATABASE_ENV_KEYS = (
    PODCAST_DATABASE_ID_ENV,
    EXPRESSION_DATABASE_ID_ENV,
    VOCABULARY_DATABASE_ID_ENV,
    WEEKLY_DATABASE_ID_ENV,
)

SETUP_STATE_ENV = "EPLA_NOTION_SETUP_STATE"
SETUP_STATE_IN_PROGRESS = "in_progress"
SETUP_STATE_COMPLETE = "complete"

DATABASE_ENV_NAMES = {
    PODCAST_DATABASE_ID_ENV: "Podcast Library",
    EXPRESSION_DATABASE_ID_ENV: "Expression Database",
    VOCABULARY_DATABASE_ID_ENV: "Vocabulary Database",
    WEEKLY_DATABASE_ID_ENV: "Weekly Review",
}

DATABASE_NAMES_ZH = {
    "Podcast Library": "播客资料库",
    "Expression Database": "表达资料库",
    "Vocabulary Database": "词汇资料库",
    "Weekly Review": "每周复盘资料库",
}


class FirstTimeSetupError(RuntimeError):
    """首次设置无法安全继续。"""


@dataclass(frozen=True)
class FirstTimeSetupResult:
    """首次设置的确定性结果。"""

    database_ids: dict[str, str]
    created_databases: bool
    validation_results: Sequence[Any]


def locate_project_root(start: Optional[Path] = None) -> Path:
    """从任意项目内路径向上定位完整项目根目录。"""
    candidate = (start or SCRIPT_PATH).expanduser().resolve()
    if candidate.is_file():
        candidate = candidate.parent

    for directory in (candidate, *candidate.parents):
        if all((directory / marker).exists() for marker in PROJECT_MARKERS):
            return directory

    raise FirstTimeSetupError(
        "无法定位完整项目。请让 Codex 重新获取 English Audio Learning Agent 项目。"
    )


def read_env_values(path: Path) -> dict[str, str]:
    """读取非敏感配置状态，不输出任何值。"""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _validate_private_value(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise FirstTimeSetupError(f"{label}不能为空。")
    if "\n" in cleaned or "\r" in cleaned:
        raise FirstTimeSetupError(f"{label}格式无效。")
    return cleaned


def _render_env_content(base_content: str, updates: Mapping[str, str]) -> str:
    """保留原有配置和注释，并确保被更新的键只出现一次。"""
    rendered: list[str] = []
    updated_keys: set[str] = set()

    for raw_line in base_content.splitlines():
        stripped = raw_line.strip()
        if "=" not in raw_line or stripped.startswith("#"):
            rendered.append(raw_line)
            continue

        key, _value = raw_line.split("=", 1)
        normalized_key = key.strip()
        if normalized_key not in updates:
            rendered.append(raw_line)
            continue

        if normalized_key in updated_keys:
            continue

        rendered.append(f"{normalized_key}={updates[normalized_key]}")
        updated_keys.add(normalized_key)

    for key, value in updates.items():
        if key not in updated_keys:
            rendered.append(f"{key}={value}")

    return "\n".join(rendered).rstrip("\n") + "\n"


def secure_update_env(
    env_path: Path,
    example_path: Path,
    updates: Mapping[str, str],
    *,
    replace_func: Callable[[str, str], None] = os.replace,
) -> None:
    """通过同目录临时文件和原子替换安全更新 .env。"""
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if env_path.exists():
        base_content = env_path.read_text(encoding="utf-8")
    elif example_path.exists():
        base_content = example_path.read_text(encoding="utf-8")
    else:
        base_content = ""

    content = _render_env_content(base_content, updates)
    temp_path: Optional[Path] = None

    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{env_path.name}.",
            dir=str(env_path.parent),
            text=True,
        )
        temp_path = Path(temp_name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        replace_func(str(temp_path), str(env_path))
        os.chmod(env_path, 0o600)
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise FirstTimeSetupError(
            "无法安全更新本地私密配置文件；原配置未被覆盖。"
        ) from exc


def configured_database_ids(values: Mapping[str, str]) -> dict[str, str]:
    """返回四个规范数据库编号，并兼容旧 Weekly Review 变量名。"""
    weekly_id = (
        values.get(WEEKLY_DATABASE_ID_ENV, "").strip()
        or values.get(LEGACY_WEEKLY_DATABASE_ID_ENV, "").strip()
    )
    return {
        PODCAST_DATABASE_ID_ENV: values.get(PODCAST_DATABASE_ID_ENV, "").strip(),
        EXPRESSION_DATABASE_ID_ENV: values.get(
            EXPRESSION_DATABASE_ID_ENV, ""
        ).strip(),
        VOCABULARY_DATABASE_ID_ENV: values.get(
            VOCABULARY_DATABASE_ID_ENV, ""
        ).strip(),
        WEEKLY_DATABASE_ID_ENV: weekly_id,
    }


def database_configuration_state(database_ids: Mapping[str, str]) -> str:
    configured_count = sum(bool(value) for value in database_ids.values())
    if configured_count == 0:
        return "empty"
    if configured_count == len(DATABASE_ENV_KEYS):
        return "complete"
    return "partial"


@contextmanager
def temporary_environment(values: Mapping[str, str]) -> Iterator[None]:
    """临时向既有验证器提供配置，结束后恢复调用方环境。"""
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _default_validator() -> Sequence[Any]:
    from src.notion.check_workspace import validate_workspace

    return validate_workspace()


def _default_database_access_validator(
    notion: Any,
    database_ids: Mapping[str, str],
) -> None:
    """Confirm configured database IDs are accessible before reusing them."""
    from src.notion.check_workspace import fetch_database

    for env_key, database_id in database_ids.items():
        if database_id:
            fetch_database(notion, database_id, DATABASE_ENV_NAMES[env_key])


def _ensure_validation_passed(results: Sequence[Any]) -> None:
    invalid_names = [
        DATABASE_NAMES_ZH.get(getattr(result, "name", ""), getattr(result, "name", ""))
        for result in results
        if not bool(getattr(result, "is_valid", False))
    ]
    if invalid_names:
        joined = "、".join(name for name in invalid_names if name)
        raise FirstTimeSetupError(f"工作区验证未通过：{joined or '未知数据库'}。")


def run_first_time_setup(
    *,
    project_root: Path,
    token: str,
    parent_page: str,
    notion: Optional[Any] = None,
    validator: Callable[[], Sequence[Any]] = _default_validator,
    database_access_validator: Callable[
        [Any, Mapping[str, str]], None
    ] = _default_database_access_validator,
) -> FirstTimeSetupResult:
    """安全保存配置，按状态创建或验证四个 Notion 数据库。"""
    project_root = project_root.resolve()
    env_path = project_root / ".env"
    example_path = project_root / ".env.example"

    safe_token = _validate_private_value(token, "Notion 访问密钥")
    safe_parent_page = _validate_private_value(parent_page, "Notion 父页面完整链接")
    try:
        normalized_parent_id = normalize_notion_id(safe_parent_page)
    except WorkspaceSetupError as exc:
        raise FirstTimeSetupError("无法识别 Notion 父页面完整链接。") from exc

    existing_values = read_env_values(env_path)
    database_ids = configured_database_ids(existing_values)
    state = database_configuration_state(database_ids)
    setup_state = existing_values.get(SETUP_STATE_ENV, "").strip()
    existing_parent_page = existing_values.get(
        NOTION_PARENT_PAGE_ID_ENV, ""
    ).strip()
    parent_must_match = any(database_ids.values()) or setup_state in {
        SETUP_STATE_IN_PROGRESS,
        SETUP_STATE_COMPLETE,
    }

    if parent_must_match:
        if not existing_parent_page:
            raise FirstTimeSetupError(
                "检测到已有设置缺少 Notion 父页面编号。为避免把数据库拆分到"
                "不同页面，首次设置已安全停止；请让 Codex 检查现有配置。"
            )
        try:
            existing_parent_id = normalize_notion_id(existing_parent_page)
        except WorkspaceSetupError as exc:
            raise FirstTimeSetupError(
                "无法识别已有 Notion 父页面配置。为避免修改现有数据库，"
                "首次设置已安全停止；请让 Codex 检查现有配置。"
            ) from exc

        if existing_parent_id != normalized_parent_id:
            raise FirstTimeSetupError(
                "检测到父页面与已有设置不一致。已有数据库属于之前配置的"
                "父页面。为避免把数据库拆分到不同页面，首次设置已安全停止。"
                "请使用原来的 Notion 父页面链接，或让 Codex 检查并清理"
                "测试配置。"
            )

    if state == "partial" and setup_state != SETUP_STATE_IN_PROGRESS:
        raise FirstTimeSetupError(
            "检测到部分数据库编号。为避免重复创建，首次设置已停止；"
            "请让 Codex 检查现有 Notion 配置。"
        )

    base_updates = {
        NOTION_TOKEN_ENV: safe_token,
        NOTION_PARENT_PAGE_ID_ENV: normalized_parent_id,
        NOTION_TARGET_PARENT_PAGE_ID_ENV: normalized_parent_id,
        SETUP_STATE_ENV: SETUP_STATE_IN_PROGRESS,
    }
    if database_ids[WEEKLY_DATABASE_ID_ENV]:
        base_updates[WEEKLY_DATABASE_ID_ENV] = database_ids[WEEKLY_DATABASE_ID_ENV]

    secure_update_env(env_path, example_path, base_updates)
    notion_client = notion or create_notion_client(safe_token)

    try:
        database_access_validator(notion_client, database_ids)
    except Exception as exc:
        raise FirstTimeSetupError(
            "已有 Notion 数据库无法访问。为避免覆盖或重复创建，首次设置已停止；"
            "请检查数据库编号、页面共享权限和网络后重试。"
        ) from exc

    created_keys: list[str] = []

    def persist_database_id(env_key: str, database_id: str) -> None:
        existing_id = database_ids.get(env_key, "")
        if existing_id and existing_id != database_id:
            raise FirstTimeSetupError(
                f"{DATABASE_ENV_NAMES[env_key]} 已存在不同数据库编号，已安全停止。"
            )
        database_ids[env_key] = database_id
        created_keys.append(env_key)
        secure_update_env(
            env_path,
            example_path,
            {
                env_key: database_id,
                SETUP_STATE_ENV: SETUP_STATE_IN_PROGRESS,
            },
        )

    if state != "complete":
        try:
            ensure_parent_page_guide_for_setup(
                notion_client,
                normalized_parent_id,
            )
        except ParentPageGuideError as exc:
            raise FirstTimeSetupError(
                "Notion 父页面使用指南创建未完成。数据库尚未继续创建；"
                "请检查页面权限和网络后重新运行，系统不会重复创建指南。"
            ) from exc

    try:
        database_ids = create_base_databases(
            notion_client,
            normalized_parent_id,
            existing_ids=database_ids,
            on_database_created=persist_database_id,
        )
    except Exception as exc:
        raise FirstTimeSetupError(
            "Notion 数据库创建未完成。已保存成功进度；"
            "请检查页面权限和网络后重新运行，系统只会继续创建缺失数据库。"
        ) from exc

    try:
        reconcile_workspace_schema(notion_client, database_ids)
    except Exception as exc:
        raise FirstTimeSetupError(
            "Notion 数据库字段修复未完成。已有数据库编号和内容均已保留；"
            "请检查权限和网络后重新运行，系统会继续原地补齐字段。"
        ) from exc

    try:
        wire_database_relations(notion_client, database_ids)
    except Exception as exc:
        raise FirstTimeSetupError(
            "Notion 数据库关系配置失败。数据库编号已保存；"
            "请检查权限和网络后重新运行，系统会重试关系配置而不会重复建库。"
        ) from exc

    runtime_values = {
        NOTION_TOKEN_ENV: safe_token,
        NOTION_PARENT_PAGE_ID_ENV: normalized_parent_id,
        NOTION_TARGET_PARENT_PAGE_ID_ENV: normalized_parent_id,
        **database_ids,
    }
    with temporary_environment(runtime_values):
        try:
            validation_results = validator()
        except Exception as exc:
            raise FirstTimeSetupError(
                "Notion 工作区验证失败。请检查连接权限和网络后重试。"
            ) from exc

    _ensure_validation_passed(validation_results)
    if state != SETUP_STATE_COMPLETE:
        try:
            ensure_parent_page_database_links(
                notion_client,
                normalized_parent_id,
                database_ids,
            )
        except ParentPageGuideError as exc:
            raise FirstTimeSetupError(
                "Notion 父页面数据库入口链接未完成。数据库和已有内容均已保留；"
                "请检查页面权限和网络后重新运行，系统只会补齐缺失链接。"
            ) from exc
    secure_update_env(
        env_path,
        example_path,
        {SETUP_STATE_ENV: SETUP_STATE_COMPLETE},
    )
    return FirstTimeSetupResult(
        database_ids=dict(database_ids),
        created_databases=bool(created_keys),
        validation_results=validation_results,
    )


def format_chinese_validation(results: Sequence[Any]) -> str:
    lines: list[str] = []
    for result in results:
        english_name = getattr(result, "name", "")
        chinese_name = DATABASE_NAMES_ZH.get(english_name, english_name)
        marker = "✓" if bool(getattr(result, "is_valid", False)) else "✗"
        lines.append(f"{marker} {chinese_name}")
    return "\n".join(lines)


def _safe_error_message(error: Exception, secrets: Sequence[str]) -> str:
    message = str(error)
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[已隐藏]")
    message = re.sub(r"https?://\S+", "[已隐藏链接]", message)
    message = re.sub(
        r"\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b",
        "[已隐藏编号]",
        message,
    )
    message = re.sub(r"\b[0-9a-fA-F]{32}\b", "[已隐藏编号]", message)
    return message


def main(
    *,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    input_fn: Optional[Callable[[str], str]] = None,
) -> int:
    # ``input_fn`` remains for call-site compatibility; private values are
    # deliberately collected only through ``getpass_fn``.
    del input_fn
    token = ""
    parent_page = ""

    try:
        project_root = locate_project_root()
        print("英语音频学习助手第一次设置", flush=True)
        print("", flush=True)
        print("接下来需要输入两项内容。", flush=True)
        print("", flush=True)
        print("第 1/2 步：Notion 访问密钥", flush=True)
        print("", flush=True)
        print("粘贴时屏幕不会显示字符，这是正常的。", flush=True)
        print("粘贴完成后请按回车。", flush=True)
        token = getpass_fn("")
        print("", flush=True)
        print("访问密钥已接收，内容未显示。", flush=True)
        print("", flush=True)
        print("第 2/2 步：Notion 页面链接", flush=True)
        print("", flush=True)
        print(
            "请粘贴刚才复制的“英语音频学习助手”页面完整链接。",
            flush=True,
        )
        print("为了保护隐私，链接也不会显示。", flush=True)
        print("粘贴完成后请按回车。", flush=True)
        parent_page = getpass_fn("")
        print("", flush=True)
        print("页面链接已接收，正在检查连接和页面权限。", flush=True)
        result = run_first_time_setup(
            project_root=project_root,
            token=token,
            parent_page=parent_page,
        )
    except FirstTimeSetupError as exc:
        safe_message = _safe_error_message(exc, (token, parent_page))
        print(
            f"第一次设置失败：{safe_message}",
            file=sys.stderr,
            flush=True,
        )
        print(
            "请修正后重新双击 start_setup.command。",
            file=sys.stderr,
            flush=True,
        )
        return 1
    except Exception:
        print(
            "第一次设置失败：未能完成本地设置。",
            file=sys.stderr,
            flush=True,
        )
        print(
            "请重新双击 start_setup.command；如果仍然失败，请只提供"
            "非敏感错误摘要。",
            file=sys.stderr,
            flush=True,
        )
        return 1

    action = "已创建并验证" if result.created_databases else "已验证现有"
    print("", flush=True)
    print(f"第一次设置已经完成，{action} Notion 工作区：", flush=True)
    print(format_chinese_validation(result.validation_results), flush=True)
    print("", flush=True)
    print(
        "请返回 Codex 继续设置 Weekly Review 自动生成时间。",
        flush=True,
    )
    print(
        "默认时间是每周六上午 10:00；只有在你确认后才会安装本地自动计划。",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
