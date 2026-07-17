"""Resolve supported podcast page URLs into playable audio URLs.

Podcast page URL support currently means Apple Podcasts URLs only.
Generic podcast platform pages are not supported yet.
"""

from __future__ import annotations

import json
import logging
import re
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from src.config.media import is_supported_audio_extension


LOGGER = logging.getLogger(__name__)


class PodcastResolverError(RuntimeError):
    """Raised when a supported podcast source cannot be resolved to audio."""


class EpisodeNotFoundError(PodcastResolverError):
    """Raised when a requested podcast episode cannot be confidently located."""


APPLE_PODCAST_HOSTS = {"podcasts.apple.com", "itunes.apple.com"}
TITLE_SIMILARITY_THRESHOLD = 0.86
TITLE_SIMILARITY_AMBIGUITY_GAP = 0.03
APPLE_EPISODE_SCORE_THRESHOLD = 80


@dataclass(frozen=True)
class ApplePodcastIds:
    """Identifiers extracted from an Apple Podcasts URL."""

    podcast_id: str
    episode_id: Optional[str]


@dataclass(frozen=True)
class EpisodeMatchHints:
    """Optional metadata used to match an Apple episode inside an RSS feed."""

    episode_id: Optional[str] = None
    title: Optional[str] = None
    publication_date: Optional[str] = None
    author: Optional[str] = None


@dataclass(frozen=True)
class ResolvedPodcastEpisode:
    """Structured result for a resolved podcast episode."""

    episode_title: str
    audio_url: str
    published_date: Optional[str]
    confidence: float
    matching_method: str


def is_apple_podcast_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in APPLE_PODCAST_HOSTS


def is_direct_audio_url(url: str) -> bool:
    return is_supported_audio_extension(Path(urlparse(url).path).suffix)


def is_rss_feed_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    return path.endswith((".xml", ".rss", ".atom")) or "feed" in path or "rss" in path


def extract_apple_podcast_ids(url: str) -> ApplePodcastIds:
    """Extract podcast ID and optional episode ID from an Apple Podcasts URL."""
    if not is_apple_podcast_url(url):
        raise PodcastResolverError(f"Not an Apple Podcasts URL: {url}")

    parsed = urlparse(url)
    podcast_match = re.search(r"/id(\d+)", parsed.path)
    if not podcast_match:
        raise PodcastResolverError(f"Could not extract Apple podcast ID from URL: {url}")

    query = parse_qs(parsed.query)
    episode_ids = query.get("i", [])
    return ApplePodcastIds(
        podcast_id=podcast_match.group(1),
        episode_id=episode_ids[0] if episode_ids else None,
    )


def fetch_json(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "EnglishPodcastLearningAgent/0.1"})
    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise PodcastResolverError(f"Failed to fetch Apple podcast metadata: {exc}") from exc


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        raise PodcastResolverError(f"Failed to fetch Apple podcast page HTML: {exc}") from exc


def lookup_apple_feed_url(podcast_id: str) -> str:
    """Use Apple's public iTunes Lookup API to find a podcast RSS feed URL."""
    lookup_url = f"https://itunes.apple.com/lookup?id={podcast_id}&entity=podcast"
    LOGGER.info("Looking up Apple podcast feed for podcast_id=%s", podcast_id)
    payload = fetch_json(lookup_url)

    for result in payload.get("results", []):
        feed_url = result.get("feedUrl")
        if feed_url:
            return feed_url

    raise PodcastResolverError(f"Apple lookup did not return a feedUrl for {podcast_id}.")


def lookup_apple_episode_hints(episode_id: Optional[str]) -> EpisodeMatchHints:
    """Use Apple Lookup API to collect optional episode title/date hints."""
    if not episode_id:
        return EpisodeMatchHints()

    lookup_url = f"https://itunes.apple.com/lookup?id={episode_id}&entity=podcastEpisode"
    LOGGER.info("Looking up Apple episode metadata for episode_id=%s", episode_id)
    try:
        payload = fetch_json(lookup_url)
    except PodcastResolverError as exc:
        LOGGER.warning("Could not fetch Apple episode metadata: %s", exc)
        return EpisodeMatchHints(episode_id=episode_id)

    for result in payload.get("results", []):
        title = result.get("trackName") or result.get("collectionName")
        publication_date = result.get("releaseDate")
        if title or publication_date:
            return EpisodeMatchHints(
                episode_id=episode_id,
                title=title,
                publication_date=publication_date,
                author=result.get("artistName") or result.get("collectionName"),
            )

    return EpisodeMatchHints(episode_id=episode_id)


def lookup_apple_episode_hints_from_collection(
    podcast_id: str,
    episode_id: Optional[str],
) -> EpisodeMatchHints:
    """Find episode metadata from Apple's podcast episode list.

    Some episode IDs do not resolve via ``lookup?id=<episode_id>`` but do appear
    in the parent podcast episode listing. This still uses exact Apple trackId
    matching and never falls back to the first result.
    """
    if not episode_id:
        return EpisodeMatchHints()

    lookup_url = (
        "https://itunes.apple.com/lookup?"
        f"id={podcast_id}&entity=podcastEpisode&limit=200"
    )
    LOGGER.info(
        "Looking up Apple episode metadata from podcast episode list for episode_id=%s",
        episode_id,
    )
    try:
        payload = fetch_json(lookup_url)
    except PodcastResolverError as exc:
        LOGGER.warning("Could not fetch Apple episode list metadata: %s", exc)
        return EpisodeMatchHints(episode_id=episode_id)

    for result in payload.get("results", []):
        if str(result.get("trackId", "")).strip() != episode_id:
            continue
        return EpisodeMatchHints(
            episode_id=episode_id,
            title=result.get("trackName"),
            publication_date=result.get("releaseDate"),
            author=result.get("artistName") or result.get("collectionName"),
        )

    return EpisodeMatchHints(episode_id=episode_id)


class ApplePodcastHTMLMetadataParser(HTMLParser):
    """Extract useful episode metadata from Apple Podcasts HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.scripts: list[str] = []
        self._script_type: Optional[str] = None
        self._script_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        attributes = {key.lower(): value for key, value in attrs if value is not None}
        if tag.lower() == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
            )
            content = attributes.get("content")
            if key and content:
                self.meta[key.lower()] = unescape(content).strip()

        if tag.lower() == "script":
            self._script_type = attributes.get("type", "")
            self._script_chunks = []

    def handle_data(self, data: str) -> None:
        if self._script_type is not None:
            self._script_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self._script_type is not None:
            script = "".join(self._script_chunks).strip()
            if script:
                self.scripts.append(script)
            self._script_type = None
            self._script_chunks = []


def _clean_apple_title(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    title = unescape(str(value)).strip()
    title = re.sub(r"\s*[-|]\s*Apple Podcasts\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+on Apple Podcasts\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip()
    return title or None


def _extract_date_from_text(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    if match:
        return match.group(0)
    return None


def _walk_json_values(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        values = [payload]
        for child in payload.values():
            values.extend(_walk_json_values(child))
        return values
    if isinstance(payload, list):
        values: list[dict[str, Any]] = []
        for child in payload:
            values.extend(_walk_json_values(child))
        return values
    return []


def _extract_hints_from_json_payload(payload: Any) -> EpisodeMatchHints:
    for item in _walk_json_values(payload):
        title = (
            item.get("name")
            or item.get("headline")
            or item.get("title")
            or item.get("trackName")
        )
        publication_date = (
            item.get("datePublished")
            or item.get("uploadDate")
            or item.get("releaseDate")
            or item.get("publishedDate")
        )
        author_value = item.get("author") or item.get("creator") or item.get("artistName")
        author = None
        if isinstance(author_value, dict):
            author = author_value.get("name")
        elif isinstance(author_value, str):
            author = author_value

        if title or publication_date or author:
            return EpisodeMatchHints(
                title=_clean_apple_title(str(title)) if title else None,
                publication_date=str(publication_date) if publication_date else None,
                author=author,
            )
    return EpisodeMatchHints()


def _extract_hints_from_scripts(scripts: list[str]) -> EpisodeMatchHints:
    for script in scripts:
        stripped = script.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                hints = _extract_hints_from_json_payload(json.loads(stripped))
            except json.JSONDecodeError:
                hints = EpisodeMatchHints()
            if hints.title or hints.publication_date or hints.author:
                return hints

        title_match = re.search(
            r'"(?:name|title|trackName)"\s*:\s*"([^"]+)"',
            script,
        )
        date_match = re.search(
            r'"(?:datePublished|releaseDate|publishedDate)"\s*:\s*"([^"]+)"',
            script,
        )
        if title_match or date_match:
            return EpisodeMatchHints(
                title=_clean_apple_title(title_match.group(1)) if title_match else None,
                publication_date=date_match.group(1) if date_match else None,
            )
    return EpisodeMatchHints()


def parse_apple_episode_hints_from_html(
    html: str,
    episode_id: Optional[str] = None,
) -> EpisodeMatchHints:
    parser = ApplePodcastHTMLMetadataParser()
    parser.feed(html)

    title = (
        parser.meta.get("og:title")
        or parser.meta.get("twitter:title")
        or parser.meta.get("title")
    )
    description = parser.meta.get("og:description") or parser.meta.get("description")
    publication_date = (
        parser.meta.get("article:published_time")
        or parser.meta.get("music:release_date")
        or _extract_date_from_text(description)
    )

    script_hints = _extract_hints_from_scripts(parser.scripts)
    return EpisodeMatchHints(
        episode_id=episode_id,
        title=_clean_apple_title(title) or script_hints.title,
        publication_date=publication_date or script_hints.publication_date,
        author=script_hints.author,
    )


def lookup_apple_episode_hints_from_html(
    apple_url: str,
    episode_id: Optional[str],
) -> EpisodeMatchHints:
    LOGGER.info("Looking up Apple episode metadata from HTML")
    try:
        return parse_apple_episode_hints_from_html(
            fetch_html(apple_url),
            episode_id=episode_id,
        )
    except PodcastResolverError as exc:
        LOGGER.warning("Could not fetch Apple episode HTML metadata: %s", exc)
        return EpisodeMatchHints(episode_id=episode_id)


def merge_episode_hints(
    primary: EpisodeMatchHints,
    fallback: EpisodeMatchHints,
) -> EpisodeMatchHints:
    return EpisodeMatchHints(
        episode_id=primary.episode_id or fallback.episode_id,
        title=primary.title or fallback.title,
        publication_date=primary.publication_date or fallback.publication_date,
        author=primary.author or fallback.author,
    )


def parse_rss_feed(feed_url: str):
    try:
        import feedparser
    except ModuleNotFoundError as exc:
        raise PodcastResolverError(
            "Missing dependency feedparser. Install dependencies with "
            "pip install -r requirements.txt."
        ) from exc

    feed = feedparser.parse(feed_url)
    if getattr(feed, "bozo", False) and not feed.entries:
        raise PodcastResolverError(f"Failed to parse podcast RSS feed: {feed_url}")
    return feed


def enclosure_url_from_entry(entry: dict[str, Any]) -> Optional[str]:
    for enclosure in entry.get("enclosures", []):
        href = enclosure.get("href")
        enclosure_type = enclosure.get("type", "")
        if href and (enclosure_type.startswith("audio/") or is_direct_audio_url(href)):
            return href
    return None


def entry_matches_episode_id(entry: dict[str, Any], episode_id: str) -> bool:
    candidates = [
        entry.get("id"),
        entry.get("itunes_episode"),
        entry.get("itunes_episodeid"),
        entry.get("episode_id"),
    ]
    return any(candidate and str(candidate).strip() == episode_id for candidate in candidates)


def entry_matches_guid(entry: dict[str, Any], episode_id: str) -> bool:
    guid = entry.get("guid")
    return bool(guid and str(guid).strip() == episode_id)


def normalize_text(value: str) -> str:
    value = re.sub(r"\s*[-|]\s*Apple Podcasts\s*$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+on Apple Podcasts\s*$", "", value, flags=re.IGNORECASE)
    normalized = re.sub(r"[\W_]+", " ", value.casefold())
    return " ".join(normalized.split())


def title_similarity(entry: dict[str, Any], title: Optional[str]) -> float:
    if not title:
        return 0.0

    entry_title = entry.get("title")
    if not entry_title:
        return 0.0

    normalized_title = normalize_text(title)
    normalized_entry_title = normalize_text(str(entry_title))
    if not normalized_title or not normalized_entry_title:
        return 0.0
    return SequenceMatcher(None, normalized_title, normalized_entry_title).ratio()


def parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None

    raw_value = str(value).strip()
    if not raw_value:
        return None

    try:
        if raw_value.endswith("Z"):
            raw_value = raw_value[:-1] + "+00:00"
        return datetime.fromisoformat(raw_value).date()
    except ValueError:
        pass

    try:
        parsed = parsedate_to_datetime(str(value))
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def entry_publication_date(entry: dict[str, Any]) -> Optional[date]:
    for candidate in (
        entry.get("published"),
        entry.get("updated"),
        entry.get("created"),
    ):
        parsed = parse_date(str(candidate)) if candidate else None
        if parsed:
            return parsed
    return None


def date_similarity_score(
    entry: dict[str, Any],
    publication_date: Optional[str],
) -> float:
    target_date = parse_date(publication_date)
    candidate_date = entry_publication_date(entry)
    if not target_date or not candidate_date:
        return 0.0

    day_difference = abs((candidate_date - target_date).days)
    if day_difference == 0:
        return 1.0
    if day_difference == 1:
        return 0.8
    return 0.0


def entry_has_apple_episode_id(entry: dict[str, Any], episode_id: str) -> bool:
    return entry_matches_episode_id(entry, episode_id) or entry_matches_guid(entry, episode_id)


def score_entry_match(
    entry: dict[str, Any],
    hints: EpisodeMatchHints,
) -> tuple[int, str]:
    if hints.episode_id and entry_has_apple_episode_id(entry, hints.episode_id):
        return 100, "episode_id"

    score = 0
    method_parts = []
    similarity = title_similarity(entry, hints.title)
    if hints.title and normalize_text(str(entry.get("title", ""))) == normalize_text(hints.title):
        score += 80
        method_parts.append("title_exact")
    elif similarity > 0.85:
        score += 60
        method_parts.append("title_similarity")

    if date_similarity_score(entry, hints.publication_date) > 0:
        score += 20
        method_parts.append("date")

    return score, "+".join(method_parts) or "no_match"


def find_resolved_episode_match(
    entries: list[dict[str, Any]],
    hints: EpisodeMatchHints,
    apple_url: Optional[str] = None,
    feed_url: Optional[str] = None,
) -> ResolvedPodcastEpisode:
    ranked: list[tuple[int, str, dict[str, Any]]] = []
    for entry in entries:
        audio_url = enclosure_url_from_entry(entry)
        if not audio_url:
            continue
        confidence, method = score_entry_match(entry, hints)
        ranked.append((confidence, method, entry))

    candidates = [
        (confidence, method, entry)
        for confidence, method, entry in ranked
        if confidence >= APPLE_EPISODE_SCORE_THRESHOLD
    ]
    candidates.sort(key=lambda item: item[0], reverse=True)

    if len(candidates) > 1:
        raise EpisodeNotFoundError(
            "Multiple possible episodes found. "
            + build_episode_not_found_message(
                hints=hints,
                ranked=ranked,
                apple_url=apple_url,
                feed_url=feed_url,
            )
        )

    if not candidates:
        raise EpisodeNotFoundError(
            build_episode_not_found_message(
                hints=hints,
                ranked=ranked,
                apple_url=apple_url,
                feed_url=feed_url,
            )
        )

    confidence, method, entry = candidates[0]
    audio_url = enclosure_url_from_entry(entry)
    if not audio_url:
        raise PodcastResolverError("Matched RSS episode does not include an audio enclosure.")

    title = entry_title(entry) or hints.title or "Untitled Podcast Episode"
    published_date = entry_publication_date(entry)
    result = ResolvedPodcastEpisode(
        episode_title=title,
        audio_url=audio_url,
        published_date=published_date.isoformat() if published_date else None,
        confidence=float(confidence),
        matching_method=method,
    )
    LOGGER.info(
        "Matched episode: Title: %s Confidence: %.4f Method: %s",
        result.episode_title,
        result.confidence,
        result.matching_method,
    )
    return result


def build_episode_not_found_message(
    hints: EpisodeMatchHints,
    ranked: list[tuple[int, str, dict[str, Any]]],
    apple_url: Optional[str] = None,
    feed_url: Optional[str] = None,
) -> str:
    top_candidates = sorted(ranked, key=lambda item: item[0], reverse=True)[:3]
    candidate_lines = [
        f"- {entry_title(entry) or 'Untitled'} | score={score} | method={method}"
        for score, method, entry in top_candidates
    ]
    return (
        "Cannot reliably locate Apple Podcast episode. "
        f"Apple URL: {apple_url or 'unknown'}; "
        f"extracted metadata: episode_id={hints.episode_id!r}, title={hints.title!r}, "
        f"publication_date={hints.publication_date!r}, author={hints.author!r}; "
        f"RSS feed url: {feed_url or 'unknown'}; "
        f"top candidates: {'; '.join(candidate_lines) if candidate_lines else 'none'}"
    )


def find_title_similarity_match(
    entries: list[dict[str, Any]],
    title: Optional[str],
) -> Optional[dict[str, Any]]:
    if not title:
        return None

    ranked = sorted(
        (
            (title_similarity(entry, title), entry)
            for entry in entries
        ),
        key=lambda item: item[0],
        reverse=True,
    )
    if not ranked or ranked[0][0] < TITLE_SIMILARITY_THRESHOLD:
        return None

    if len(ranked) > 1 and ranked[1][0] >= TITLE_SIMILARITY_THRESHOLD:
        if ranked[0][0] - ranked[1][0] < TITLE_SIMILARITY_AMBIGUITY_GAP:
            raise EpisodeNotFoundError(
                "Cannot locate the requested Apple Podcast episode. "
                "Multiple RSS episodes have similar titles. Please provide RSS "
                "feed URL or direct audio URL."
            )

    LOGGER.info("Matched podcast episode by title similarity")
    return ranked[0][1]


def date_prefix(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"\d{4}-\d{2}-\d{2}", str(value))
    if match:
        return match.group(0)
    return None


def entry_matches_publication_date(
    entry: dict[str, Any],
    publication_date: Optional[str],
) -> bool:
    target_date = date_prefix(publication_date)
    if not target_date:
        return False

    candidates = [
        entry.get("published"),
        entry.get("updated"),
        entry.get("created"),
    ]
    return any(date_prefix(str(candidate)) == target_date for candidate in candidates if candidate)


def find_matching_entry(
    entries: list[dict[str, Any]],
    hints: EpisodeMatchHints,
) -> Optional[dict[str, Any]]:
    """Find a feed entry using the defined priority order."""
    if hints.episode_id:
        for entry in entries:
            if entry_matches_episode_id(entry, hints.episode_id):
                LOGGER.info("Matched podcast episode by episode ID")
                return entry

        for entry in entries:
            if entry_matches_guid(entry, hints.episode_id):
                LOGGER.info("Matched podcast episode by GUID")
                return entry

    title_match = find_title_similarity_match(entries, hints.title)
    if title_match:
        return title_match

    for entry in entries:
        if entry_matches_publication_date(entry, hints.publication_date):
            LOGGER.info("Matched podcast episode by publication date")
            return entry

    return None


def get_enclosure_url_from_feed(
    feed_url: str,
    episode_id: Optional[str] = None,
    title: Optional[str] = None,
    publication_date: Optional[str] = None,
) -> str:
    """Return an audio enclosure from a feed, preferring the target episode."""
    LOGGER.info("Resolving audio enclosure from podcast feed: %s", feed_url)
    feed = parse_rss_feed(feed_url)

    hints = EpisodeMatchHints(
        episode_id=episode_id,
        title=title,
        publication_date=publication_date,
    )
    if episode_id or title or publication_date:
        matching_entry = find_matching_entry(feed.entries, hints)
        if matching_entry:
            audio_url = enclosure_url_from_entry(matching_entry)
            if audio_url:
                return audio_url
        raise EpisodeNotFoundError(
            "Cannot locate the requested Apple Podcast episode. Please provide "
            "RSS feed URL or direct audio URL."
        )

    for entry in feed.entries:
        audio_url = enclosure_url_from_entry(entry)
        if audio_url:
            return audio_url

    raise PodcastResolverError(f"No audio enclosure found in podcast RSS feed: {feed_url}")


def resolve_episode_from_feed(
    feed_url: str,
    hints: EpisodeMatchHints,
    apple_url: Optional[str] = None,
) -> ResolvedPodcastEpisode:
    """Resolve a specific podcast episode from RSS using v2 matching rules."""
    LOGGER.info("Resolving audio enclosure from podcast feed: %s", feed_url)
    feed = parse_rss_feed(feed_url)
    return find_resolved_episode_match(
        feed.entries,
        hints,
        apple_url=apple_url,
        feed_url=feed_url,
    )


def entry_title(entry: dict[str, Any]) -> Optional[str]:
    title = entry.get("title")
    return str(title).strip() if title else None


def resolve_title_from_feed(
    feed_url: str,
    episode_id: Optional[str] = None,
    title: Optional[str] = None,
    publication_date: Optional[str] = None,
) -> Optional[str]:
    """Resolve a podcast episode title from RSS metadata."""
    feed = parse_rss_feed(feed_url)
    hints = EpisodeMatchHints(
        episode_id=episode_id,
        title=title,
        publication_date=publication_date,
    )
    matching_entry = find_matching_entry(feed.entries, hints)
    if matching_entry:
        resolved_title = entry_title(matching_entry)
        if resolved_title:
            return resolved_title

    return None


def resolve_apple_podcast_title(url: str) -> Optional[str]:
    """Resolve a clean episode title from an Apple Podcasts page URL."""
    return resolve_apple_podcast_episode(url).episode_title


def resolve_podcast_title(url: str) -> Optional[str]:
    """Resolve a title for Apple Podcasts or RSS podcast sources."""
    if is_apple_podcast_url(url):
        return resolve_apple_podcast_title(url)
    if is_rss_feed_url(url):
        return resolve_title_from_feed(url)
    return None


def resolve_apple_podcast_audio_url(url: str) -> str:
    """Resolve an Apple Podcasts page URL into a playable audio URL."""
    return resolve_apple_podcast_episode(url).audio_url


def resolve_apple_podcast_episode(url: str) -> ResolvedPodcastEpisode:
    """Resolve an Apple Podcasts page URL into a structured playable episode."""
    LOGGER.info("Resolving Apple Podcasts URL")
    ids = extract_apple_podcast_ids(url)
    feed_url = lookup_apple_feed_url(ids.podcast_id)
    api_hints = lookup_apple_episode_hints(ids.episode_id)
    collection_hints = EpisodeMatchHints(episode_id=ids.episode_id)
    if not api_hints.title or not api_hints.publication_date:
        collection_hints = lookup_apple_episode_hints_from_collection(
            ids.podcast_id,
            ids.episode_id,
        )
    html_hints = EpisodeMatchHints(episode_id=ids.episode_id)
    merged_hints = merge_episode_hints(api_hints, collection_hints)
    if not merged_hints.title or not merged_hints.publication_date:
        html_hints = lookup_apple_episode_hints_from_html(url, ids.episode_id)
    hints = merge_episode_hints(merged_hints, html_hints)
    return resolve_episode_from_feed(feed_url, hints, apple_url=url)


def resolve_podcast_audio_url(url: str) -> str:
    """Resolve direct audio, RSS feed, or Apple Podcasts page URL to audio."""
    if is_direct_audio_url(url):
        return url
    if is_apple_podcast_url(url):
        return resolve_apple_podcast_audio_url(url)
    if is_rss_feed_url(url):
        return get_enclosure_url_from_feed(url)

    raise PodcastResolverError(
        "Unsupported podcast URL. The source resolver supports Apple Podcasts page URLs, "
        "RSS feed URLs, and direct audio URLs. Generic podcast platform pages are "
        "not supported yet."
    )
