from src.config.settings import load_settings


def test_load_settings_uses_default_runtime_paths() -> None:
    settings = load_settings(
        {
            "EPLA_DATA_DIR": "custom-data",
        }
    )

    assert settings.data_dir.name == "custom-data"
    assert settings.audio_output_dir.as_posix() == "custom-data/audio"
    assert settings.transcript_output_dir.as_posix() == "custom-data/transcripts"


def test_load_settings_reads_notion_values() -> None:
    settings = load_settings(
        {
            "NOTION_TOKEN": "secret",
            "NOTION_PARENT_PAGE_ID": "parent",
            "NOTION_PODCAST_LIBRARY_DATABASE_ID": "podcast_db",
        }
    )

    assert settings.notion_token == "secret"
    assert settings.notion_parent_page_id == "parent"
    assert settings.notion_podcast_database_id == "podcast_db"
