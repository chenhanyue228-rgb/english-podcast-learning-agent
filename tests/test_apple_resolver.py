from __future__ import annotations

import pytest

from src.extractor import podcast_resolver


APPLE_URL = (
    "https://podcasts.apple.com/cn/podcast/think-fast-talk-smart/"
    "id1494989268?i=1000776282768"
)


def patch_common_lookup(monkeypatch, title=None, publication_date=None):
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_feed_url",
        lambda podcast_id: "https://example.com/feed.xml",
    )
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_episode_hints",
        lambda episode_id: podcast_resolver.EpisodeMatchHints(
            episode_id=episode_id,
            title=title,
            publication_date=publication_date,
        ),
    )
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_episode_hints_from_collection",
        lambda podcast_id, episode_id: podcast_resolver.EpisodeMatchHints(
            episode_id=episode_id
        ),
    )


def test_apple_url_episode_id_exact_match(monkeypatch) -> None:
    patch_common_lookup(monkeypatch)

    class Feed:
        entries = [
            {
                "itunes_episodeid": "1000776282768",
                "title": "Exact Match Episode",
                "published": "2026-07-16T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/exact.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    result = podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    assert result.audio_url == "https://cdn.example.com/exact.mp3"
    assert result.confidence == 100
    assert result.matching_method == "episode_id"


def test_apple_url_title_match_from_html_when_api_metadata_missing(monkeypatch) -> None:
    patch_common_lookup(monkeypatch)
    monkeypatch.setattr(
        podcast_resolver,
        "fetch_html",
        lambda url: """
        <html><head>
          <meta property="og:title" content="How to Design Teams That Actually Work - Apple Podcasts">
        </head></html>
        """,
    )

    class Feed:
        entries = [
            {
                "title": "How to Design Teams That Actually Work",
                "published": "2026-07-16T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/title.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    result = podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    assert result.audio_url == "https://cdn.example.com/title.mp3"
    assert result.confidence == 80
    assert result.matching_method == "title_exact"


def test_apple_url_title_and_date_match_from_html(monkeypatch) -> None:
    patch_common_lookup(monkeypatch)
    monkeypatch.setattr(
        podcast_resolver,
        "fetch_html",
        lambda url: """
        <html><head>
          <meta name="twitter:title" content="Trust the Process: How to Design Teams That Actually Work">
          <script type="application/ld+json">
          {
            "@type": "PodcastEpisode",
            "datePublished": "2026-07-16T12:00:00Z"
          }
          </script>
        </head></html>
        """,
    )

    class Feed:
        entries = [
            {
                "title": "Trust the Process - How to Design Teams That Actually Work",
                "published": "Thu, 16 Jul 2026 06:00:00 -0700",
                "enclosures": [{"href": "https://cdn.example.com/title-date.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    result = podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    assert result.audio_url == "https://cdn.example.com/title-date.mp3"
    assert result.confidence >= 80
    assert result.matching_method == "title_exact+date"


def test_apple_url_no_reliable_match_fails_with_diagnostics(monkeypatch) -> None:
    patch_common_lookup(monkeypatch, title="How to Design Teams That Actually Work")

    class Feed:
        entries = [
            {
                "title": "Completely Different Episode",
                "published": "2026-07-16T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/wrong.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError) as exc_info:
        podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    message = str(exc_info.value)
    assert "Cannot reliably locate Apple Podcast episode" in message
    assert APPLE_URL in message
    assert "How to Design Teams That Actually Work" in message
    assert "https://example.com/feed.xml" in message
    assert "Completely Different Episode" in message
