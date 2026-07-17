import pytest

from src.extractor.router import (
    SourceRouterError,
    SourceType,
    detect_source,
    detect_source_type,
)


def test_detect_youtube_url() -> None:
    assert detect_source_type("https://www.youtube.com/watch?v=abc") == SourceType.YOUTUBE
    assert detect_source_type("https://youtu.be/abc") == SourceType.YOUTUBE


def test_detect_apple_podcast_url() -> None:
    source = "https://podcasts.apple.com/cn/podcast/world-today/id894467023?i=1000776913465"

    result = detect_source(source)

    assert result.type == SourceType.APPLE_PODCAST
    assert result.source == source
    assert result.to_dict() == {"type": "apple_podcast"}


def test_detect_podcast_rss_url() -> None:
    assert detect_source_type("https://example.com/feed.xml") == SourceType.PODCAST_RSS
    assert detect_source_type("https://example.com/rss") == SourceType.PODCAST_RSS


def test_detect_direct_audio_url() -> None:
    assert detect_source_type("https://cdn.example.com/episode.mp3") == SourceType.DIRECT_AUDIO
    assert detect_source_type("https://cdn.example.com/episode.m4a") == SourceType.DIRECT_AUDIO
    assert detect_source_type("https://cdn.example.com/episode.webm") == SourceType.DIRECT_AUDIO


def test_detect_local_audio_file() -> None:
    assert detect_source_type("/tmp/audio.mp3") == SourceType.LOCAL_AUDIO
    assert detect_source_type("~/Downloads/audio.wav") == SourceType.LOCAL_AUDIO
    assert detect_source_type("~/Downloads/audio.webm") == SourceType.LOCAL_AUDIO


def test_rejects_unsupported_audio_extension() -> None:
    with pytest.raises(SourceRouterError, match="Unsupported URL"):
        detect_source("https://cdn.example.com/episode.aac")


def test_empty_source_is_rejected() -> None:
    with pytest.raises(SourceRouterError, match="empty"):
        detect_source("  ")


def test_unsupported_url_is_rejected() -> None:
    with pytest.raises(SourceRouterError, match="Generic podcast platform pages"):
        detect_source("https://example.com/article")


def test_unsupported_local_file_is_rejected() -> None:
    with pytest.raises(SourceRouterError, match="Unsupported local file"):
        detect_source("/tmp/notes.txt")
