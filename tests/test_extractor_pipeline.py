from __future__ import annotations

from pathlib import Path
from typing import Union

import pytest

from src.extractor.pipeline import SourceExtractionError, extract_audio_from_source


def test_pipeline_downloads_youtube_source(tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "youtube.mp3"
    expected_mp3.write_bytes(b"audio")
    calls: list[tuple[str, Union[Path, str]]] = []

    def fake_downloader(source_url: str, output_dir: Union[Path, str]) -> Path:
        calls.append((source_url, output_dir))
        return expected_mp3

    result = extract_audio_from_source(
        "https://www.youtube.com/watch?v=abc",
        output_dir=tmp_path,
        audio_downloader=fake_downloader,
    )

    assert result == expected_mp3
    assert calls == [("https://www.youtube.com/watch?v=abc", tmp_path)]


def test_pipeline_resolves_apple_podcast_then_downloads(tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "apple.mp3"
    expected_mp3.write_bytes(b"audio")
    source = "https://podcasts.apple.com/cn/podcast/world-today/id894467023?i=1000776913465"

    def fake_resolver(source_url: str) -> str:
        assert source_url == source
        return "https://cdn.example.com/apple.mp3"

    def fake_downloader(source_url: str, output_dir: Union[Path, str]) -> Path:
        assert source_url == "https://cdn.example.com/apple.mp3"
        assert output_dir == tmp_path
        return expected_mp3

    assert (
        extract_audio_from_source(
            source,
            output_dir=tmp_path,
            audio_downloader=fake_downloader,
            podcast_resolver=fake_resolver,
        )
        == expected_mp3
    )


def test_pipeline_resolves_rss_then_downloads(tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "rss.mp3"
    expected_mp3.write_bytes(b"audio")

    def fake_resolver(source_url: str) -> str:
        assert source_url == "https://example.com/feed.xml"
        return "https://cdn.example.com/rss.mp3"

    def fake_downloader(source_url: str, output_dir: Union[Path, str]) -> Path:
        assert source_url == "https://cdn.example.com/rss.mp3"
        return expected_mp3

    assert (
        extract_audio_from_source(
            "https://example.com/feed.xml",
            output_dir=tmp_path,
            audio_downloader=fake_downloader,
            podcast_resolver=fake_resolver,
        )
        == expected_mp3
    )


def test_pipeline_downloads_direct_audio(tmp_path: Path) -> None:
    expected_mp3 = tmp_path / "direct.mp3"
    expected_mp3.write_bytes(b"audio")

    def fake_downloader(source_url: str, output_dir: Union[Path, str]) -> Path:
        assert source_url == "https://cdn.example.com/direct.mp3"
        return expected_mp3

    assert (
        extract_audio_from_source(
            "https://cdn.example.com/direct.mp3",
            output_dir=tmp_path,
            audio_downloader=fake_downloader,
        )
        == expected_mp3
    )


def test_pipeline_validates_local_mp3(tmp_path: Path) -> None:
    local_mp3 = tmp_path / "local.mp3"
    local_mp3.write_bytes(b"audio")

    assert extract_audio_from_source(str(local_mp3), output_dir=tmp_path) == local_mp3.resolve()


def test_pipeline_converts_local_non_mp3(tmp_path: Path) -> None:
    local_m4a = tmp_path / "local.m4a"
    local_m4a.write_bytes(b"audio")
    expected_mp3 = tmp_path / "local.mp3"

    def fake_converter(source_path: Path) -> Path:
        assert source_path == local_m4a.resolve()
        expected_mp3.write_bytes(b"mp3")
        return expected_mp3.resolve()

    assert (
        extract_audio_from_source(
            str(local_m4a),
            output_dir=tmp_path,
            mp3_converter=fake_converter,
        )
        == expected_mp3.resolve()
    )


def test_pipeline_wraps_router_errors() -> None:
    with pytest.raises(SourceExtractionError, match="Unsupported"):
        extract_audio_from_source("not-a-supported-source")


def test_pipeline_wraps_downloader_errors(tmp_path: Path) -> None:
    def failing_downloader(source_url: str, output_dir: Union[Path, str]) -> Path:
        raise RuntimeError("download exploded")

    with pytest.raises(SourceExtractionError, match="download exploded"):
        extract_audio_from_source(
            "https://cdn.example.com/direct.mp3",
            output_dir=tmp_path,
            audio_downloader=failing_downloader,
        )
