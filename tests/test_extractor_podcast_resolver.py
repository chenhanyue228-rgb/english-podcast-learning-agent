from src.extractor import podcast_resolver
import pytest


APPLE_URL = "https://podcasts.apple.com/cn/podcast/world-today/id894467023?i=1000776913465"


def test_is_apple_podcast_url() -> None:
    assert podcast_resolver.is_apple_podcast_url(APPLE_URL)
    assert not podcast_resolver.is_apple_podcast_url("https://example.com/show")


def test_extract_apple_podcast_ids() -> None:
    ids = podcast_resolver.extract_apple_podcast_ids(APPLE_URL)

    assert ids.podcast_id == "894467023"
    assert ids.episode_id == "1000776913465"


def test_extract_apple_podcast_ids_rejects_non_apple_url() -> None:
    with pytest.raises(podcast_resolver.PodcastResolverError, match="Not an Apple"):
        podcast_resolver.extract_apple_podcast_ids("https://example.com/id894467023")


def test_extract_apple_podcast_ids_requires_podcast_id() -> None:
    with pytest.raises(podcast_resolver.PodcastResolverError, match="podcast ID"):
        podcast_resolver.extract_apple_podcast_ids("https://podcasts.apple.com/cn/podcast/world-today")


def test_is_rss_feed_url() -> None:
    assert podcast_resolver.is_rss_feed_url("https://example.com/feed.xml")
    assert podcast_resolver.is_rss_feed_url("https://example.com/rss")
    assert not podcast_resolver.is_rss_feed_url("https://example.com/show")


def test_lookup_apple_feed_url(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "fetch_json",
        lambda url: {"results": [{"feedUrl": "https://example.com/feed.xml"}]},
    )

    assert podcast_resolver.lookup_apple_feed_url("894467023") == "https://example.com/feed.xml"


def test_lookup_apple_feed_url_requires_feed_url(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "fetch_json",
        lambda url: {"results": [{"collectionName": "World Today"}]},
    )

    with pytest.raises(podcast_resolver.PodcastResolverError, match="feedUrl"):
        podcast_resolver.lookup_apple_feed_url("894467023")


def test_get_enclosure_url_from_feed_prefers_matching_episode(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "id": "older",
                "enclosures": [{"href": "https://cdn.example.com/old.mp3", "type": "audio/mpeg"}],
            },
            {
                "id": "1000776913465",
                "enclosures": [{"href": "https://cdn.example.com/new.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            "1000776913465",
        )
        == "https://cdn.example.com/new.mp3"
    )


def test_get_enclosure_url_from_feed_matches_guid(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "id": "older",
                "guid": "older-guid",
                "enclosures": [{"href": "https://cdn.example.com/old.mp3", "type": "audio/mpeg"}],
            },
            {
                "id": "new",
                "guid": "1000776913465",
                "enclosures": [{"href": "https://cdn.example.com/guid.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            "1000776913465",
        )
        == "https://cdn.example.com/guid.mp3"
    )


def test_get_enclosure_url_from_feed_matches_title(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "title": "Older episode",
                "enclosures": [{"href": "https://cdn.example.com/old.mp3", "type": "audio/mpeg"}],
            },
            {
                "title": "World Today: AI leadership",
                "enclosures": [{"href": "https://cdn.example.com/title.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            episode_id="missing",
            title="World Today: AI leadership",
        )
        == "https://cdn.example.com/title.mp3"
    )


def test_get_enclosure_url_from_feed_matches_publication_date(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "published": "2026-07-15T08:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/old.mp3", "type": "audio/mpeg"}],
            },
            {
                "published": "2026-07-16T08:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/date.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            episode_id="missing",
            publication_date="2026-07-16T01:23:45Z",
        )
        == "https://cdn.example.com/date.mp3"
    )


def test_get_enclosure_url_from_feed_rejects_episode_mismatch(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "id": "older",
                "enclosures": [{"href": "https://cdn.example.com/old.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Cannot locate"):
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            "1000776913465",
        )


def test_get_enclosure_url_from_feed_rejects_multiple_similar_titles(monkeypatch) -> None:
    class Feed:
        entries = [
            {
                "title": "How to Communicate With Confidence",
                "enclosures": [{"href": "https://cdn.example.com/a.mp3", "type": "audio/mpeg"}],
            },
            {
                "title": "How to Communicate With Confidence!",
                "enclosures": [{"href": "https://cdn.example.com/b.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Multiple"):
        podcast_resolver.get_enclosure_url_from_feed(
            "https://example.com/feed.xml",
            title="How to Communicate With Confidence",
        )


def test_get_enclosure_url_from_feed_requires_audio_enclosure(monkeypatch) -> None:
    class Feed:
        entries = [{"id": "episode", "enclosures": []}]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.PodcastResolverError, match="No audio enclosure"):
        podcast_resolver.get_enclosure_url_from_feed("https://example.com/feed.xml")


def test_resolve_title_from_feed_prefers_matching_entry(monkeypatch) -> None:
    class Feed:
        entries = [
            {"id": "older", "title": "Older episode"},
            {"id": "1000776913465", "title": "Real episode title"},
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.resolve_title_from_feed(
            "https://example.com/feed.xml",
            episode_id="1000776913465",
        )
        == "Real episode title"
    )


def test_resolve_title_from_feed_does_not_fall_back_to_first_entry(monkeypatch) -> None:
    class Feed:
        entries = [
            {"id": "older", "title": "First episode title"},
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.resolve_title_from_feed(
            "https://example.com/feed.xml",
            episode_id="missing",
        )
        is None
    )


def test_resolve_apple_podcast_audio_url(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_feed_url",
        lambda podcast_id: "https://example.com/feed.xml",
    )
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_episode_hints",
        lambda episode_id: podcast_resolver.EpisodeMatchHints(episode_id=episode_id),
    )

    class Feed:
        entries = [
            {
                "id": "1000776913465",
                "title": "World Today",
                "published": "2026-07-16T08:00:00Z",
                "enclosures": [
                    {
                        "href": "https://cdn.example.com/1000776913465.mp3",
                        "type": "audio/mpeg",
                    }
                ],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    assert (
        podcast_resolver.resolve_apple_podcast_audio_url(APPLE_URL)
        == "https://cdn.example.com/1000776913465.mp3"
    )


def test_resolve_apple_podcast_episode_matches_apple_id_in_rss(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_feed_url",
        lambda podcast_id: "https://example.com/feed.xml",
    )
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_episode_hints",
        lambda episode_id: podcast_resolver.EpisodeMatchHints(episode_id=episode_id),
    )

    class Feed:
        entries = [
            {
                "id": "1000776913465",
                "title": "Exact ID episode",
                "published": "2026-07-16T08:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/exact.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    result = podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    assert result.episode_title == "Exact ID episode"
    assert result.audio_url == "https://cdn.example.com/exact.mp3"
    assert result.published_date == "2026-07-16"
    assert result.confidence == 100.0
    assert result.matching_method == "episode_id"


def test_resolve_apple_podcast_title_uses_v3_episode_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "resolve_apple_podcast_episode",
        lambda url: podcast_resolver.ResolvedPodcastEpisode(
            episode_title="302. Master This: How to Learn Like the Experts Do",
            audio_url="https://cdn.example.com/audio.mp3",
            published_date="2026-07-02",
            confidence=100,
            matching_method="title_exact+date",
        ),
    )

    assert (
        podcast_resolver.resolve_apple_podcast_title(APPLE_URL)
        == "302. Master This: How to Learn Like the Experts Do"
    )


def test_resolve_apple_podcast_episode_matches_title_when_id_missing(monkeypatch) -> None:
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
            title="Think Fast Talk Smart: Better Communication at Work",
            publication_date="2026-07-16T12:00:00Z",
            author="Stanford GSB",
        ),
    )

    class Feed:
        entries = [
            {
                "id": "rss-id",
                "title": "Think Fast, Talk Smart - Better Communication at Work",
                "published": "Thu, 16 Jul 2026 09:00:00 GMT",
                "enclosures": [{"href": "https://cdn.example.com/title.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    result = podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)

    assert result.audio_url == "https://cdn.example.com/title.mp3"
    assert result.confidence >= 80
    assert result.matching_method == "title_exact+date"


def test_resolve_apple_podcast_episode_rejects_date_mismatch(monkeypatch) -> None:
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
            title="Moderately Similar Episode Title",
            publication_date="2026-07-16T12:00:00Z",
        ),
    )

    class Feed:
        entries = [
            {
                "id": "rss-id",
                "title": "Moderately Similar Episode",
                "published": "2026-07-20T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/wrong-date.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Cannot reliably locate"):
        podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)


def test_resolve_apple_podcast_episode_rejects_wrong_episode(monkeypatch) -> None:
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
            title="How to Communicate With Confidence",
            publication_date="2026-07-16T12:00:00Z",
        ),
    )

    class Feed:
        entries = [
            {
                "id": "wrong",
                "title": "Managing Finance Teams",
                "published": "2026-07-16T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/wrong.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Cannot reliably locate"):
        podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)


def test_resolve_apple_podcast_episode_rejects_multiple_candidates(monkeypatch) -> None:
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
            title="How to Communicate With Confidence",
            publication_date="2026-07-16T12:00:00Z",
        ),
    )

    class Feed:
        entries = [
            {
                "id": "a",
                "title": "How to Communicate With Confidence",
                "published": "2026-07-16T09:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/a.mp3", "type": "audio/mpeg"}],
            },
            {
                "id": "b",
                "title": "How to Communicate With Confidence!",
                "published": "2026-07-16T10:00:00Z",
                "enclosures": [{"href": "https://cdn.example.com/b.mp3", "type": "audio/mpeg"}],
            },
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Multiple possible"):
        podcast_resolver.resolve_apple_podcast_episode(APPLE_URL)


def test_resolve_apple_podcast_audio_url_raises_episode_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_feed_url",
        lambda podcast_id: "https://example.com/feed.xml",
    )
    monkeypatch.setattr(
        podcast_resolver,
        "lookup_apple_episode_hints",
        lambda episode_id: podcast_resolver.EpisodeMatchHints(episode_id=episode_id),
    )

    class Feed:
        entries = [
            {
                "id": "different",
                "enclosures": [{"href": "https://cdn.example.com/wrong.mp3", "type": "audio/mpeg"}],
            }
        ]

    monkeypatch.setattr(podcast_resolver, "parse_rss_feed", lambda feed_url: Feed())

    with pytest.raises(podcast_resolver.EpisodeNotFoundError, match="Cannot reliably locate"):
        podcast_resolver.resolve_apple_podcast_audio_url(APPLE_URL)


def test_resolve_podcast_audio_url_returns_direct_audio_url() -> None:
    assert (
        podcast_resolver.resolve_podcast_audio_url("https://cdn.example.com/episode.mp3")
        == "https://cdn.example.com/episode.mp3"
    )


def test_resolve_podcast_audio_url_resolves_rss(monkeypatch) -> None:
    monkeypatch.setattr(
        podcast_resolver,
        "get_enclosure_url_from_feed",
        lambda feed_url, episode_id=None: "https://cdn.example.com/rss.mp3",
    )

    assert (
        podcast_resolver.resolve_podcast_audio_url("https://example.com/feed.xml")
        == "https://cdn.example.com/rss.mp3"
    )


def test_resolve_podcast_audio_url_rejects_unsupported_url() -> None:
    with pytest.raises(
        podcast_resolver.PodcastResolverError,
        match="Generic podcast platform pages",
    ):
        podcast_resolver.resolve_podcast_audio_url("https://example.com/article")
