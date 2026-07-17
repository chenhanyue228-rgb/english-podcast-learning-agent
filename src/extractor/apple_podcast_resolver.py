"""Apple Podcasts page resolver.

This module exposes the Apple-specific resolver API while the legacy
``podcast_resolver`` module keeps the public Phase 2 source extraction entrypoint
stable for the rest of the pipeline.
"""

from src.extractor.podcast_resolver import (
    ApplePodcastIds,
    ApplePodcastHTMLMetadataParser,
    EpisodeMatchHints,
    EpisodeNotFoundError,
    PodcastResolverError,
    ResolvedPodcastEpisode,
    build_episode_not_found_message,
    entry_publication_date,
    extract_apple_podcast_ids,
    find_resolved_episode_match,
    lookup_apple_episode_hints,
    lookup_apple_episode_hints_from_collection,
    lookup_apple_episode_hints_from_html,
    lookup_apple_feed_url,
    merge_episode_hints,
    normalize_text,
    parse_apple_episode_hints_from_html,
    resolve_apple_podcast_audio_url,
    resolve_apple_podcast_episode,
    resolve_apple_podcast_title,
    score_entry_match,
    title_similarity,
)

__all__ = [
    "ApplePodcastIds",
    "ApplePodcastHTMLMetadataParser",
    "EpisodeMatchHints",
    "EpisodeNotFoundError",
    "PodcastResolverError",
    "ResolvedPodcastEpisode",
    "build_episode_not_found_message",
    "entry_publication_date",
    "extract_apple_podcast_ids",
    "find_resolved_episode_match",
    "lookup_apple_episode_hints",
    "lookup_apple_episode_hints_from_collection",
    "lookup_apple_episode_hints_from_html",
    "lookup_apple_feed_url",
    "merge_episode_hints",
    "normalize_text",
    "parse_apple_episode_hints_from_html",
    "resolve_apple_podcast_audio_url",
    "resolve_apple_podcast_episode",
    "resolve_apple_podcast_title",
    "score_entry_match",
    "title_similarity",
]
