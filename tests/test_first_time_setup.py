from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import first_time_setup


FAKE_TOKEN = "secret_test_token"
PARENT_URL = "https://www.notion.so/English-0123456789abcdef0123456789abcdef"
DATABASE_IDS = {
    "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast-id",
    "NOTION_EXPRESSION_DATABASE_ID": "expression-id",
    "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly-id",
    "NOTION_VOCABULARY_DATABASE_ID": "vocabulary-id",
}


def make_project_root(tmp_path: Path, *, include_example: bool = True) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("project\n", encoding="utf-8")
    (root / "requirements.txt").write_text("pytest\n", encoding="utf-8")
    for directory in ("skill", "scripts", "src"):
        (root / directory).mkdir()
    if include_example:
        (root / ".env.example").write_text(
            "NOTION_TOKEN=\n"
            "NOTION_PODCAST_LIBRARY_DATABASE_ID=\n"
            "NOTION_EXPRESSION_DATABASE_ID=\n"
            "NOTION_WEEKLY_REFLECTION_DATABASE_ID=\n"
            "NOTION_VOCABULARY_DATABASE_ID=\n"
            "EPLA_ENV=development\n",
            encoding="utf-8",
        )
    return root


def valid_results():
    return [
        SimpleNamespace(name="Podcast Library", is_valid=True),
        SimpleNamespace(name="Expression Database", is_valid=True),
        SimpleNamespace(name="Weekly Review", is_valid=True),
        SimpleNamespace(name="Vocabulary Database", is_valid=True),
    ]


def test_locate_project_root_from_nested_path(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    nested = root / "scripts" / "nested"
    nested.mkdir()

    assert first_time_setup.locate_project_root(nested) == root


def test_secure_update_env_uses_example_when_env_missing(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)

    first_time_setup.secure_update_env(
        root / ".env",
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    content = (root / ".env").read_text(encoding="utf-8")
    assert f"NOTION_TOKEN={FAKE_TOKEN}" in content
    assert "EPLA_ENV=development" in content


def test_secure_update_env_without_example_creates_file(tmp_path: Path) -> None:
    root = make_project_root(tmp_path, include_example=False)

    first_time_setup.secure_update_env(
        root / ".env",
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    assert (root / ".env").read_text(encoding="utf-8") == (
        f"NOTION_TOKEN={FAKE_TOKEN}\n"
    )


def test_main_uses_hidden_token_input(monkeypatch, tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    prompts: list[str] = []

    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **kwargs: first_time_setup.FirstTimeSetupResult(
            DATABASE_IDS, True, valid_results()
        ),
    )

    status_code = first_time_setup.main(
        getpass_fn=lambda prompt: prompts.append(prompt) or FAKE_TOKEN,
        input_fn=lambda _prompt: PARENT_URL,
    )

    assert status_code == 0
    assert prompts
    assert "不会显示" in prompts[0]


def test_empty_token_is_rejected_before_save(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="不能为空"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=" ",
            parent_page=PARENT_URL,
            notion=object(),
            validator=valid_results,
        )

    assert not (root / ".env").exists()


def test_main_does_not_print_token(monkeypatch, tmp_path: Path, capsys) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **kwargs: first_time_setup.FirstTimeSetupResult(
            DATABASE_IDS, False, valid_results()
        ),
    )

    assert (
        first_time_setup.main(
            getpass_fn=lambda _prompt: FAKE_TOKEN,
            input_fn=lambda _prompt: PARENT_URL,
        )
        == 0
    )
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out
    assert FAKE_TOKEN not in captured.err


def test_error_output_redacts_token(monkeypatch, tmp_path: Path, capsys) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)

    def fail(**_kwargs):
        raise first_time_setup.FirstTimeSetupError(
            f"unexpected detail {FAKE_TOKEN}"
        )

    monkeypatch.setattr(first_time_setup, "run_first_time_setup", fail)

    assert (
        first_time_setup.main(
            getpass_fn=lambda _prompt: FAKE_TOKEN,
            input_fn=lambda _prompt: PARENT_URL,
        )
        == 1
    )
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.err
    assert "[已隐藏]" in captured.err


def test_secure_update_preserves_other_configuration(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        "EPLA_ENV=production\nCUSTOM_SETTING=keep-me\n",
        encoding="utf-8",
    )

    first_time_setup.secure_update_env(
        root / ".env",
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    content = (root / ".env").read_text(encoding="utf-8")
    assert "EPLA_ENV=production" in content
    assert "CUSTOM_SETTING=keep-me" in content


def test_secure_update_preserves_database_ids(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    existing = "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
    (root / ".env").write_text(existing + "\n", encoding="utf-8")

    first_time_setup.secure_update_env(
        root / ".env",
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    content = (root / ".env").read_text(encoding="utf-8")
    for key, value in DATABASE_IDS.items():
        assert f"{key}={value}" in content


def test_secure_update_does_not_duplicate_token(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        "NOTION_TOKEN=old\nNOTION_TOKEN=duplicate\n",
        encoding="utf-8",
    )

    first_time_setup.secure_update_env(
        root / ".env",
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    content = (root / ".env").read_text(encoding="utf-8")
    assert content.count("NOTION_TOKEN=") == 1


def test_full_parent_page_url_is_normalized_and_saved(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, parent: DATABASE_IDS
        if parent == "01234567-89ab-cdef-0123-456789abcdef"
        else pytest.fail("unexpected parent id"),
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: None,
    )

    first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
    )

    content = (root / ".env").read_text(encoding="utf-8")
    assert (
        "NOTION_PARENT_PAGE_ID=01234567-89ab-cdef-0123-456789abcdef" in content
    )


def test_complete_database_configuration_only_validates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda *_args: pytest.fail("must not create databases"),
    )

    result = first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        validator=valid_results,
    )

    assert result.created_databases is False


def test_empty_database_configuration_creates_databases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, _parent: calls.append("create") or DATABASE_IDS,
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: calls.append("wire"),
    )

    result = first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
    )

    assert result.created_databases is True
    assert calls == ["create", "wire"]


def test_partial_database_configuration_stops_before_create(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        "NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast-id\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda *_args: pytest.fail("must not create databases"),
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="部分数据库"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=valid_results,
        )


def test_tests_never_require_real_notion(monkeypatch, tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(
        first_time_setup,
        "create_notion_client",
        lambda _token: pytest.fail("real client must not be created"),
    )
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, _parent: DATABASE_IDS,
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: None,
    )

    result = first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
    )

    assert result.database_ids == DATABASE_IDS


def test_success_report_is_chinese() -> None:
    report = first_time_setup.format_chinese_validation(valid_results())

    assert "播客资料库" in report
    assert "表达资料库" in report
    assert "每周复盘资料库" in report
    assert "词汇资料库" in report


def test_main_returns_nonzero_on_failure(monkeypatch, tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **_kwargs: (_ for _ in ()).throw(
            first_time_setup.FirstTimeSetupError("安全停止")
        ),
    )

    assert (
        first_time_setup.main(
            getpass_fn=lambda _prompt: FAKE_TOKEN,
            input_fn=lambda _prompt: PARENT_URL,
        )
        == 1
    )


def test_atomic_replace_failure_keeps_original_file(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    original = "NOTION_TOKEN=original\nCUSTOM=keep\n"
    env_path.write_text(original, encoding="utf-8")

    def fail_replace(_source: str, _destination: str) -> None:
        raise OSError("replace failed")

    with pytest.raises(first_time_setup.FirstTimeSetupError):
        first_time_setup.secure_update_env(
            env_path,
            root / ".env.example",
            {"NOTION_TOKEN": FAKE_TOKEN},
            replace_func=fail_replace,
        )

    assert env_path.read_text(encoding="utf-8") == original


def test_env_permissions_are_owner_only(tmp_path: Path) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"

    first_time_setup.secure_update_env(
        env_path,
        root / ".env.example",
        {"NOTION_TOKEN": FAKE_TOKEN},
    )

    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_start_command_uses_its_own_directory_and_project_venv() -> None:
    command_path = first_time_setup.DEFAULT_PROJECT_ROOT / "start_setup.command"
    content = command_path.read_text(encoding="utf-8")

    assert 'dirname -- "$0"' in content
    assert 'cd "$PROJECT_DIR"' in content
    assert '$PROJECT_DIR/.venv/bin/python' in content
    assert "scripts/first_time_setup.py" in content
    assert "sudo" not in content
    assert "NOTION_TOKEN=" not in content


def test_start_command_is_executable() -> None:
    command_path = first_time_setup.DEFAULT_PROJECT_ROOT / "start_setup.command"

    assert os.access(command_path, os.X_OK)
