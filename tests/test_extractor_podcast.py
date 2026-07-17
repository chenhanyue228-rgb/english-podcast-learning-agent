from __future__ import annotations

from pathlib import Path
from typing import Union

from src.extractor import podcast


def test_is_direct_audio_url() -> None:
    assert podcast.is_direct_audio_url("https://example.com/audio.mp3")
    assert podcast.is_direct_audio_url("https://example.com/audio.m4a")
    assert not podcast.is_direct_audio_url("https://example.com/feed.xml")


def test_safe_filename_from_url() -> None:
    assert podcast.safe_filename_from_url("https://example.com/My Episode.mp3") == "My_Episode.mp3"


def test_extract_podcast_audio_downloads_direct_audio(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, Union[Path, str]]] = []
    expected_path = tmp_path / "episode.mp3"

    def fake_download(audio_url: str, output_dir: Union[Path, str]) -> Path:
        calls.append((audio_url, output_dir))
        return expected_path

    monkeypatch.setattr(podcast, "download_audio_file", fake_download)

    result = podcast.extract_podcast_audio("https://example.com/episode.mp3", tmp_path)

    assert result == expected_path
    assert calls == [("https://example.com/episode.mp3", tmp_path)]


def test_extract_podcast_audio_resolves_rss_enclosure(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        podcast,
        "resolve_podcast_audio_url",
        lambda source_url: "https://cdn.example.com/episode.mp3",
    )
    monkeypatch.setattr(
        podcast,
        "download_audio_file",
        lambda audio_url, output_dir: tmp_path / "episode.mp3",
    )

    result = podcast.extract_podcast_audio("https://example.com/feed.xml", tmp_path)

    assert result == tmp_path / "episode.mp3"
