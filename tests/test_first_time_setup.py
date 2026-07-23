from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import first_time_setup
from src.notion.check_workspace import DatabaseValidationResult


FAKE_TOKEN = "secret_test_token"
PARENT_URL = "https://www.notion.so/English-0123456789abcdef0123456789abcdef"
PARENT_ID = "01234567-89ab-cdef-0123-456789abcdef"
SAME_PARENT_URL = (
    "https://www.notion.so/0123456789abcdef0123456789abcdef?source=copy_link"
)
OTHER_PARENT_URL = "https://www.notion.so/Other-fedcba9876543210fedcba9876543210"
DATABASE_IDS = {
    "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast-id",
    "NOTION_EXPRESSION_DATABASE_ID": "expression-id",
    "NOTION_VOCABULARY_DATABASE_ID": "vocabulary-id",
    "NOTION_WEEKLY_REFLECTION_DATABASE_ID": "weekly-id",
}
DATABASE_ORDER = tuple(DATABASE_IDS)


@pytest.fixture(autouse=True)
def mock_schema_reconciler(monkeypatch) -> None:
    monkeypatch.setattr(
        first_time_setup,
        "reconcile_workspace_schema",
        lambda _notion, _ids: None,
    )


def create_missing_database_ids(
    _notion,
    _parent,
    *,
    existing_ids=None,
    on_database_created=None,
):
    database_ids = {
        key: value
        for key, value in (existing_ids or {}).items()
        if value
    }
    for env_key, database_id in DATABASE_IDS.items():
        if env_key in database_ids:
            continue
        database_ids[env_key] = database_id
        if on_database_created is not None:
            on_database_created(env_key, database_id)
    return database_ids


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
        SimpleNamespace(name="Vocabulary Database", is_valid=True),
        SimpleNamespace(name="Weekly Review", is_valid=True),
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
    hidden_values = iter((FAKE_TOKEN, PARENT_URL))

    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **kwargs: first_time_setup.FirstTimeSetupResult(
            DATABASE_IDS, True, valid_results()
        ),
    )

    status_code = first_time_setup.main(
        getpass_fn=lambda prompt: prompts.append(prompt) or next(hidden_values),
    )

    assert status_code == 0
    assert len(prompts) == 2


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

    hidden_values = iter((FAKE_TOKEN, PARENT_URL))
    assert first_time_setup.main(
        getpass_fn=lambda _prompt: next(hidden_values),
    ) == 0
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.out
    assert FAKE_TOKEN not in captured.err
    assert PARENT_URL not in captured.out
    assert PARENT_URL not in captured.err


def test_error_output_redacts_token(monkeypatch, tmp_path: Path, capsys) -> None:
    root = make_project_root(tmp_path)
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)

    def fail(**_kwargs):
        raise first_time_setup.FirstTimeSetupError(
            f"unexpected detail {FAKE_TOKEN}"
        )

    monkeypatch.setattr(first_time_setup, "run_first_time_setup", fail)

    hidden_values = iter((FAKE_TOKEN, PARENT_URL))
    assert (
        first_time_setup.main(
            getpass_fn=lambda _prompt: next(hidden_values),
        )
        == 1
    )
    captured = capsys.readouterr()
    assert FAKE_TOKEN not in captured.err
    assert "[已隐藏]" in captured.err


def test_main_explains_both_hidden_input_steps_and_confirms_receipt(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    root = make_project_root(tmp_path)
    hidden_values = iter((FAKE_TOKEN, PARENT_URL))
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **kwargs: first_time_setup.FirstTimeSetupResult(
            DATABASE_IDS,
            False,
            valid_results(),
        ),
    )

    assert first_time_setup.main(
        getpass_fn=lambda _prompt: next(hidden_values),
    ) == 0

    output = capsys.readouterr().out
    phrases = (
        "第 1/2 步：Notion 访问密钥",
        "访问密钥已接收，内容未显示。",
        "第 2/2 步：Notion 页面链接",
        "为了保护隐私，链接也不会显示。",
        "页面链接已接收，正在检查连接和页面权限。",
    )
    positions = [output.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)
    assert FAKE_TOKEN not in output
    assert PARENT_URL not in output


def test_main_does_not_use_visible_input_for_page_link(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    hidden_values = iter((FAKE_TOKEN, PARENT_URL))
    monkeypatch.setattr(first_time_setup, "locate_project_root", lambda: root)
    monkeypatch.setattr(
        first_time_setup,
        "run_first_time_setup",
        lambda **kwargs: first_time_setup.FirstTimeSetupResult(
            DATABASE_IDS,
            False,
            valid_results(),
        ),
    )

    assert first_time_setup.main(
        getpass_fn=lambda _prompt: next(hidden_values),
        input_fn=lambda _prompt: pytest.fail("visible input must not be used"),
    ) == 0


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
        lambda _notion, parent, **kwargs: create_missing_database_ids(
            _notion,
            parent,
            **kwargs,
        )
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


def test_complete_database_configuration_rewires_and_validates(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_COMPLETE}\n"
        + "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
        + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        create_missing_database_ids,
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
        database_access_validator=lambda _notion, ids: calls.append(
            f"access:{len(ids)}"
        ),
    )

    assert result.created_databases is False
    assert calls == ["access:4", "wire"]
    assert (
        first_time_setup.read_env_values(root / ".env")[
            first_time_setup.SETUP_STATE_ENV
        ]
        == first_time_setup.SETUP_STATE_COMPLETE
    )


def test_empty_database_configuration_creates_databases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, _parent, **kwargs: calls.append("create")
        or create_missing_database_ids(_notion, _parent, **kwargs),
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
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
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


def test_partial_in_progress_with_same_parent_resumes_missing_databases(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_IN_PROGRESS}\n"
        "NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast-id\n",
        encoding="utf-8",
    )
    created: list[str] = []

    def creator(_notion, _parent, **kwargs):
        existing_ids = kwargs["existing_ids"]
        created.extend(
            env_key for env_key in DATABASE_ORDER if not existing_ids.get(env_key)
        )
        return create_missing_database_ids(_notion, _parent, **kwargs)

    monkeypatch.setattr(first_time_setup, "create_base_databases", creator)
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
        database_access_validator=lambda _notion, _ids: None,
    )

    assert created == list(DATABASE_ORDER[1:])
    assert result.database_ids == DATABASE_IDS


@pytest.mark.parametrize(
    ("database_lines", "setup_state"),
    [
        ("NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast-id\n", "in_progress"),
        (
            "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
            + "\n",
            "complete",
        ),
    ],
    ids=["partial-in-progress", "complete"],
)
def test_existing_setup_with_different_parent_stops_before_all_operations(
    monkeypatch,
    tmp_path: Path,
    database_lines: str,
    setup_state: str,
) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    original = (
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}={setup_state}\n"
        f"{database_lines}"
    )
    env_path.write_text(original, encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda *_args, **_kwargs: calls.append("create"),
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda *_args, **_kwargs: calls.append("wire"),
    )

    with pytest.raises(
        first_time_setup.FirstTimeSetupError,
        match="父页面与已有设置不一致",
    ) as error:
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=OTHER_PARENT_URL,
            notion=object(),
            validator=lambda: calls.append("validate") or valid_results(),
            database_access_validator=lambda *_args: calls.append("access"),
        )

    assert calls == []
    assert env_path.read_text(encoding="utf-8") == original
    assert FAKE_TOKEN not in str(error.value)


def test_same_parent_id_in_different_url_formats_is_allowed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        "NOTION_PARENT_PAGE_ID=0123456789abcdef0123456789abcdef\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_COMPLETE}\n"
        + "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
        + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        create_missing_database_ids,
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: calls.append("wire"),
    )

    first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=SAME_PARENT_URL,
        notion=object(),
        validator=lambda: calls.append("validate") or valid_results(),
        database_access_validator=lambda _notion, _ids: calls.append("access"),
    )

    assert calls == ["access", "wire", "validate"]


@pytest.mark.parametrize(
    ("database_lines", "setup_state"),
    [
        ("NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast-id\n", "in_progress"),
        (
            "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
            + "\n",
            "complete",
        ),
    ],
    ids=["partial-in-progress", "complete"],
)
def test_existing_database_ids_without_parent_stop_without_operations(
    monkeypatch,
    tmp_path: Path,
    database_lines: str,
    setup_state: str,
) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    original = (
        f"{first_time_setup.SETUP_STATE_ENV}={setup_state}\n"
        f"{database_lines}"
    )
    env_path.write_text(original, encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda *_args, **_kwargs: calls.append("create"),
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda *_args, **_kwargs: calls.append("wire"),
    )

    with pytest.raises(
        first_time_setup.FirstTimeSetupError,
        match="缺少 Notion 父页面编号",
    ):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=lambda: calls.append("validate") or valid_results(),
            database_access_validator=lambda *_args: calls.append("access"),
        )

    assert calls == []
    assert env_path.read_text(encoding="utf-8") == original


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
        create_missing_database_ids,
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


@pytest.mark.parametrize("completed_count", [1, 2, 3])
def test_interrupted_creation_resumes_only_missing_databases(
    monkeypatch,
    tmp_path: Path,
    completed_count: int,
) -> None:
    root = make_project_root(tmp_path)
    first_run_calls: list[str] = []

    def interrupted_creator(
        _notion,
        _parent,
        *,
        existing_ids=None,
        on_database_created=None,
    ):
        database_ids = {
            key: value
            for key, value in (existing_ids or {}).items()
            if value
        }
        for index, (env_key, database_id) in enumerate(DATABASE_IDS.items()):
            if env_key in database_ids:
                continue
            if index == completed_count:
                raise RuntimeError("simulated creation failure")
            first_run_calls.append(env_key)
            database_ids[env_key] = database_id
            on_database_created(env_key, database_id)
        return database_ids

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        interrupted_creator,
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: None,
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="创建未完成"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=valid_results,
            database_access_validator=lambda _notion, _ids: None,
        )

    saved_after_failure = first_time_setup.read_env_values(root / ".env")
    assert first_run_calls == list(DATABASE_ORDER[:completed_count])
    for env_key in DATABASE_ORDER[:completed_count]:
        assert saved_after_failure[env_key] == DATABASE_IDS[env_key]
    assert (
        saved_after_failure[first_time_setup.SETUP_STATE_ENV]
        == first_time_setup.SETUP_STATE_IN_PROGRESS
    )

    resumed_calls: list[str] = []

    def resumed_creator(_notion, _parent, **kwargs):
        existing_ids = kwargs.get("existing_ids", {})
        resumed_calls.extend(
            env_key for env_key in DATABASE_ORDER if not existing_ids.get(env_key)
        )
        return create_missing_database_ids(_notion, _parent, **kwargs)

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        resumed_creator,
    )
    result = first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
        database_access_validator=lambda _notion, _ids: None,
    )

    assert resumed_calls == list(DATABASE_ORDER[completed_count:])
    assert result.database_ids == DATABASE_IDS
    assert (
        first_time_setup.read_env_values(root / ".env")[
            first_time_setup.SETUP_STATE_ENV
        ]
        == first_time_setup.SETUP_STATE_COMPLETE
    )


def test_relation_failure_is_retried_without_database_recreation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    create_calls: list[str] = []
    relation_calls: list[str] = []

    def creator(_notion, _parent, **kwargs):
        existing_ids = kwargs.get("existing_ids", {})
        create_calls.extend(
            env_key for env_key in DATABASE_ORDER if not existing_ids.get(env_key)
        )
        return create_missing_database_ids(_notion, _parent, **kwargs)

    def fail_first_relation(_notion, _ids):
        relation_calls.append("wire")
        if len(relation_calls) == 1:
            raise RuntimeError("simulated relation failure")

    monkeypatch.setattr(first_time_setup, "create_base_databases", creator)
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        fail_first_relation,
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="关系配置失败"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=valid_results,
            database_access_validator=lambda _notion, _ids: None,
        )

    assert create_calls == list(DATABASE_ORDER)
    assert (
        first_time_setup.read_env_values(root / ".env")[
            first_time_setup.SETUP_STATE_ENV
        ]
        == first_time_setup.SETUP_STATE_IN_PROGRESS
    )

    create_calls.clear()
    first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
        database_access_validator=lambda _notion, _ids: None,
    )

    assert create_calls == []
    assert relation_calls == ["wire", "wire"]


def test_validation_failure_retries_relations_and_keeps_progress(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    relation_calls: list[str] = []
    invalid_results = [
        SimpleNamespace(name="Podcast Library", is_valid=False),
    ]

    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        create_missing_database_ids,
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: relation_calls.append("wire"),
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="验证未通过"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=lambda: invalid_results,
            database_access_validator=lambda _notion, _ids: None,
        )

    assert (
        first_time_setup.read_env_values(root / ".env")[
            first_time_setup.SETUP_STATE_ENV
        ]
        == first_time_setup.SETUP_STATE_IN_PROGRESS
    )

    first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=valid_results,
        database_access_validator=lambda _notion, _ids: None,
    )

    assert relation_calls == ["wire", "wire"]


def test_relation_semantic_validation_failure_preserves_existing_ids(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    env_path.write_text(
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_COMPLETE}\n"
        + "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
        + "\n",
        encoding="utf-8",
    )
    database_create_calls: list[dict] = []

    class RejectDatabaseCreation:
        def create(self, **kwargs):
            database_create_calls.append(kwargs)
            pytest.fail("must not create databases")

    notion = SimpleNamespace(databases=RejectDatabaseCreation())
    invalid_relation_result = DatabaseValidationResult(
        name="Expression Database",
        exists=True,
        relation_mismatches=[
            "Expression Database.Source Podcast: relation mode mismatch"
        ],
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: None,
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="验证未通过"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=notion,
            validator=lambda: [invalid_relation_result],
            database_access_validator=lambda _notion, _ids: None,
        )

    saved = first_time_setup.read_env_values(env_path)
    assert database_create_calls == []
    assert saved[first_time_setup.SETUP_STATE_ENV] == (
        first_time_setup.SETUP_STATE_IN_PROGRESS
    )
    for key, value in DATABASE_IDS.items():
        assert saved[key] == value


def test_inaccessible_existing_database_stops_without_overwrite(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    original = (
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_IN_PROGRESS}\n"
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        "NOTION_PODCAST_LIBRARY_DATABASE_ID=podcast-id\n"
    )
    env_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda *_args, **_kwargs: pytest.fail("must not create databases"),
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="无法访问"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=valid_results,
            database_access_validator=lambda _notion, _ids: (_ for _ in ()).throw(
                RuntimeError("not found")
            ),
        )

    saved = first_time_setup.read_env_values(env_path)
    assert saved["NOTION_PODCAST_LIBRARY_DATABASE_ID"] == "podcast-id"
    assert (
        saved[first_time_setup.SETUP_STATE_ENV]
        == first_time_setup.SETUP_STATE_IN_PROGRESS
    )


def test_schema_reconcile_runs_before_relations_and_validation(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    (root / ".env").write_text(
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_IN_PROGRESS}\n"
        + "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
        + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, _parent, **kwargs: calls.append("create")
        or dict(kwargs["existing_ids"]),
    )
    monkeypatch.setattr(
        first_time_setup,
        "reconcile_workspace_schema",
        lambda _notion, _ids: calls.append("reconcile"),
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: calls.append("wire"),
    )

    first_time_setup.run_first_time_setup(
        project_root=root,
        token=FAKE_TOKEN,
        parent_page=PARENT_URL,
        notion=object(),
        validator=lambda: calls.append("validate") or valid_results(),
        database_access_validator=lambda _notion, _ids: calls.append("access"),
    )

    assert calls == ["access", "create", "reconcile", "wire", "validate"]


def test_schema_reconcile_failure_keeps_ids_and_in_progress_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    root = make_project_root(tmp_path)
    env_path = root / ".env"
    env_path.write_text(
        f"NOTION_PARENT_PAGE_ID={PARENT_ID}\n"
        f"{first_time_setup.SETUP_STATE_ENV}="
        f"{first_time_setup.SETUP_STATE_COMPLETE}\n"
        + "\n".join(f"{key}={value}" for key, value in DATABASE_IDS.items())
        + "\n",
        encoding="utf-8",
    )
    calls: list[str] = []
    monkeypatch.setattr(
        first_time_setup,
        "create_base_databases",
        lambda _notion, _parent, **kwargs: calls.append("create")
        or dict(kwargs["existing_ids"]),
    )
    monkeypatch.setattr(
        first_time_setup,
        "reconcile_workspace_schema",
        lambda _notion, _ids: (_ for _ in ()).throw(
            RuntimeError("simulated schema conflict")
        ),
    )
    monkeypatch.setattr(
        first_time_setup,
        "wire_database_relations",
        lambda _notion, _ids: calls.append("wire"),
    )

    with pytest.raises(first_time_setup.FirstTimeSetupError, match="字段修复"):
        first_time_setup.run_first_time_setup(
            project_root=root,
            token=FAKE_TOKEN,
            parent_page=PARENT_URL,
            notion=object(),
            validator=lambda: calls.append("validate") or valid_results(),
            database_access_validator=lambda _notion, _ids: calls.append("access"),
        )

    saved = first_time_setup.read_env_values(env_path)
    assert calls == ["access", "create"]
    assert saved[first_time_setup.SETUP_STATE_ENV] == (
        first_time_setup.SETUP_STATE_IN_PROGRESS
    )
    for key, value in DATABASE_IDS.items():
        assert saved[key] == value


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

    hidden_values = iter((FAKE_TOKEN, PARENT_URL))
    assert (
        first_time_setup.main(
            getpass_fn=lambda _prompt: next(hidden_values),
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
    assert "scripts/bootstrap_environment.py" in content
    assert "--skip-tests" in content
    assert "import notion_client" not in content
    assert "scripts/first_time_setup.py" in content
    assert 'LANG="en_US.UTF-8"' in content
    assert 'LC_CTYPE="en_US.UTF-8"' in content
    assert "重新双击 start_setup.command" in content
    assert "sudo" not in content
    assert "NOTION_TOKEN=" not in content


def test_start_command_is_executable() -> None:
    command_path = first_time_setup.DEFAULT_PROJECT_ROOT / "start_setup.command"

    assert os.access(command_path, os.X_OK)
